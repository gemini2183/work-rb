#!/usr/bin/env python
# coding: utf-8
"""Цена продажи и допустимая цена заявки по когортам заявок — ТОЛЬКО ЧТЕНИЕ (в кабинеты, CRM и вики ничего не пишет).

Зачем: главный показатель ProfiMet и EkspertAgro — цена продажи (цель 43 €, решение пользователя 2026-11-16). В таблице «Цели2 Адвайта»
есть только цель по заявкам (бюджет, число заявок, цена заявки), цели по объёму продаж нет. Скрипт по неделям заявок считает, какая
доля заявок становится продажей, и из неё — допустимую цену заявки = целевая цена продажи × доля.

Что берёт (ничего не дублирует):
  план месяца, расход, заявки месяца, прогноз закрытия — pace_vs_plan.run() (Цели2 Адвайта; Google Ads API; leads_standard: звонки
      Ringostat Google Ads + формы Supabase Google);
  заявки по дням для когорт — pace_vs_plan.daily_leads() (тот же стандарт заявки);
  продажи — как в НАШЕМ дашборде клиента (режим «наш», режим «как у клиента» не используется):
      ProfiMet: profimet_sources_dashboard.sales_with_source + apply_sales_form_check — проданные заказы выгрузки CRM,
          источник = первое обращение номера за 60 дней до первой строки заказа, в расчёт идут только рекламные Google Ads
          (YouTube yt_* - отдельный проект, расход и заявки без него; Facebook не входит). День когорты = дата первого касания, день продажи = «Дата продажи».
      EkspertAgro: логика ea_sources_dashboard — заказ с «Датой продажи», без отмены (отмена раньше продажи — заказ действует), источник = первая строка
          заказа; форма «Нет метки» уточняется по GA4 (form_submit ±3 мин, только последние ~55 дней), в расчёт идёт только Google Ads. День когорты = дата первой
          строки заказа.
  Продажи — это ЗАКАЗЫ, не штуки (количества товара в выгрузке нет).

Что считает:
  1) когорты по неделям (пн-вс) заявок: заявок, продаж на сегодня, доля; задержка заявка -> продажа (дни: среднее, медиана, 80-й процентиль);
  2) зрелая доля — только по неделям, от конца которых прошло не меньше 80-го процентиля задержки (свежие недели недооценены и не усредняются).
     Если зрелых недель < 4 или продаж < 10 — предупреждение «данных мало»; всегда показан интервал Уилсона (95%), не одна цифра;
  3) допустимая цена заявки = целевая цена продажи × зрелая доля (по центру и по границам интервала); сравнение с фактической ценой заявки месяца и планом таблицы;
  4) факт цены продажи на сегодня (расход ÷ продажи когорт месяца, недосчитан по незрелым заявкам); ожидаемые продажи = заявки месяца × зрелая доля;
     прогноз цены продажи по месяцу = прогноз расхода ÷ (прогноз заявок × доля);
  5) сколько заявок нужно на остаток месяца, чтобы выйти на цель, при плановом бюджете месяца и при прогнозном расходе; допустимая цена заявки на остаток.
Задержка: P80 берётся как большее из двух — по всем случившимся продажам когорт (занижена: свежие когорты ещё не дождались продаж) и по продажам с касанием
старше 60 дней (не обрезана свежестью), если их >= 10.
Режим один: чтение. --execute нет. Запись в Google Таблицу — только с --update-sheet и только для ProfiMet (лист «Темп к плану», блок с A41, и лист
«Продажи_когорты»); без флага печатает план блока.

Результат: таблица в stdout и CSV `Клиенты/<Имя>/Статистика/sales_pace_<ГГГГ-ММ>.csv` (перезаписывается). Побочный эффект: pace_vs_plan.run() тоже
перезаписывает свой `pace_vs_plan_<ГГГГ-ММ>.csv`.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python sales_pace.py --customer-id 7552781705 --client-folder ProfiMet [--month 2026-11] [--today 2026-11-16]
                         [--target-sale-cost 43] [--weeks 12] [--rate 4.3691] [--cache путь.pkl] [--update-sheet [ID]]
--target-sale-cost всегда в евро; для EkspertAgro (аккаунт в злотых) переводится по --rate (zł за 1 €, по умолчанию 4.3691 как в ea_cost_per_sale.py).
Создан 2026-11-16.
"""
import argparse
import contextlib
import csv
import io
import math
import pickle
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

import pace_vs_plan as P  # noqa: E402
from _config import client_stats_dir  # noqa: E402

CLIENTS = {
    "ProfiMet": dict(customer_id="7552781705", cur="€", rate=1.0, sheet=True, loader="profimet",
                     mode="наш: источник продажи = первое обращение номера за 60 дней, рекламные Google Ads (без YouTube); когорта = дата первого касания"),
    "EkspertAgro": dict(customer_id="8826134558", cur="zł", rate=4.3691, sheet=False, loader="ea",
                        mode="наш: источник продажи = первая строка заказа (форма «Нет метки» по GA4), только Google Ads; когорта = дата первой строки заказа"),
}
ALIASES = {"expertagro": "EkspertAgro", "ekspertagro": "EkspertAgro", "profimet": "ProfiMet"}
Z = 1.96            # интервал Уилсона 95%
MIN_WEEKS, MIN_SALES = 4, 10
WARSAW = "Europe/Warsaw"
S_MAIN, S_COH, BLOCK_ROW = "Темп к плану", "Продажи_когорты", 41
COH_HEAD = ["Неделя с (пн)", "Неделя по (вс)", "Заявок", "Продаж на сегодня", "Доля", "Возраст конца недели, дн.", "Зрелая (в расчёте)"]


# ---------- продажи ----------
def sales_profimet(cache):
    from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
    import profimet_sources_dashboard as D
    if cache and Path(cache).exists():
        sheet, _ringo = pickle.load(open(cache, "rb"))
    else:
        sheet = load_sheet(SHEET_ID)
    empty_ringo = pd.DataFrame({"category": pd.Series(dtype=str), "utm_campaign": pd.Series(dtype=str)})  # звонки для разметки YouTube не нужны: считаем Google Ads + YouTube вместе
    _r, sheet, _n1, _n2 = D.tag_youtube(empty_ringo, sheet)
    sales = D.apply_sales_form_check(D.sales_with_source(sheet))
    sel = sales[sales["counted"] & (sales["src2"] == "Google Ads")]   # YouTube (yt_) - отдельный проект, не входит (решение 2026-11-16)
    info = [f"ProfiMet: проданных заказов в выгрузке {len(sales)}, рекламных Google Ads {len(sel)}, YouTube {int((sales['src2'] == 'YouTube').sum())} (не входит: отдельный проект), "
            f"Facebook {int((sales['src2'] == 'Facebook').sum())} (не входит: расход Google Ads), "
            f"нерекламных/не найдено {int((~sales['counted']).sum())}; последняя строка выгрузки CRM {sheet['ts'].max().tz_convert(WARSAW):%Y-%m-%d %H:%M}"]
    return pd.DataFrame({"touch_date": sel["touch_date"], "sale_date": sel["sale_date"], "src2": sel["src2"]}).reset_index(drop=True), info


def sales_ea(today):
    import ea_sources_dashboard as E
    from ea_sales_orders_check import SHEET_ID, load
    df = load(SHEET_ID, "Ekspertagro.pl")
    o = df[df["order"] != ""].sort_values("ts")
    g = o.groupby("order")
    orders = pd.DataFrame({"created": g["ts"].min(), "first_type": g["type"].first(), "first_src": g["src"].first(),
                           "sale": g["sale_date_dt"].max(), "cancel": g["cancel_date_dt"].max()})
    sold = orders[orders["sale"].notna() & (orders["cancel"].isna() | (orders["sale"] > orders["cancel"]))].copy()
    info, gm = [], None
    need = sold[(sold["first_type"] == "форма") & (sold["first_src"] == "Нет метки")]
    ga4_ok = False
    if len(need):
        d0 = max(need["created"].min().tz_convert(WARSAW).date(), today - timedelta(days=55))
        try:
            gm = E.ga4_minutes(E.ga4_session(), d0.isoformat(), today.isoformat())
            ga4_ok = True
        except Exception as ex:   # noqa: BLE001
            info.append(f"GA4 по минуте не прочитан ({type(ex).__name__}): формы «Нет метки» остаются без источника")

    def attribute(row):
        src = row["first_src"]
        if row["first_type"] == "форма" and src == "Нет метки" and gm is not None and len(gm):
            near = gm[(gm["ts"] - row["created"]).abs() <= pd.Timedelta(minutes=3)]
            if len(near):
                return near.iloc[(near["ts"] - row["created"]).abs().argsort().iloc[0]]["src"]
        return src if src in E.SRC else "Нет метки"

    sold["src2"] = sold.apply(attribute, axis=1)
    sel = sold[sold["src2"] == "Google Ads"]
    unres = int(len(need) - ((need.index.isin(sel.index)).sum()))
    info.append(f"EkspertAgro: проданных заказов {len(sold)}, Google Ads {len(sel)}, Facebook {int((sold['src2'] == 'Facebook').sum())} (не входит), «Нет метки» {int((sold['src2'] == 'Нет метки').sum())}; "
                f"форм «Нет метки» среди проданных {len(need)}, из них опознано как Google GA4 {len(need) - unres if ga4_ok else 0} (GA4 по минуте доступен ~55 дней: у старых когорт доля занижена); "
                f"последняя строка выгрузки CRM {df['ts'].max().tz_convert(WARSAW):%Y-%m-%d %H:%M}")
    out = pd.DataFrame({"touch_date": sel["created"].dt.tz_convert(WARSAW).dt.date,
                        "sale_date": sel["sale"].dt.tz_convert("UTC").dt.date, "src2": sel["src2"]}).reset_index(drop=True)
    un = sold[sold["src2"] == "Нет метки"]
    out.attrs["unres_dates"] = list(un["created"].dt.tz_convert(WARSAW).dt.date)   # проданные заказы без источника: возможно, часть из них Google
    return out, info


# ---------- статистика ----------
def wilson(k, n, z=Z):
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(c - h, 0.0), min(c + h, 1.0)


def lag_stats(lags):
    if not len(lags):
        return None
    a = np.array(lags, dtype=float)
    return dict(n=len(a), mean=float(a.mean()), median=float(np.median(a)), p80=float(np.percentile(a, 80)), p95=float(np.percentile(a, 95)))


def week_start(d):
    return d - timedelta(days=d.weekday())


def f0(v, nd=0):
    return "н/д" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{nd}f}"


def pc(v):
    return "н/д" if v is None else f"{v * 100:.1f}%"


def compute(a, cfg, pace, sales, today):
    """-> dict с когортами, задержкой, долей, допустимой ценой и прогнозом."""
    first, done_end = pace["first"], pace["done_end"]
    unres_dates = sales.attrs.get("unres_dates")
    last_end = week_start(today) - timedelta(days=1)                     # воскресенье последней полной недели
    w0 = week_start(last_end) - timedelta(days=7 * (a.weeks - 1))        # понедельник первой недели глубины
    leads = P.daily_leads(a.client_folder, w0, today - timedelta(days=1))
    sales = sales[(sales["sale_date"] <= today)].copy()
    sales["lag"] = [max((s - t).days, 0) for s, t in zip(sales["sale_date"], sales["touch_date"])]
    in_win = sales[sales["touch_date"] >= w0]
    old = sales[sales["touch_date"] <= today - timedelta(days=60)]
    ls_all, ls_old = lag_stats(in_win["lag"]), lag_stats(old["lag"])
    p80_all = ls_all["p80"] if ls_all else 0.0
    p80_old = ls_old["p80"] if ls_old and ls_old["n"] >= 10 else None
    p80 = max(p80_all, p80_old or 0.0)
    cut = int(math.ceil(p80))
    weeks = []
    d = w0
    while d <= last_end:
        e = d + timedelta(days=6)
        n_l = sum(leads.get(d + timedelta(days=i), 0) for i in range(7))
        n_s = int(((sales["touch_date"] >= d) & (sales["touch_date"] <= e)).sum())
        age = (today - e).days
        weeks.append(dict(start=d, end=e, leads=n_l, sales=n_s, share=(n_s / n_l if n_l else None), age=age, mature=(age >= cut and n_l > 0)))
        d += timedelta(days=7)
    mat = [w for w in weeks if w["mature"]]
    nl, ks = sum(w["leads"] for w in mat), sum(w["sales"] for w in mat)
    share = ks / nl if nl else None
    lo, hi = wilson(ks, nl)
    warns = []
    if len(mat) < MIN_WEEKS or ks < MIN_SALES:
        warns.append(f"ДАННЫХ МАЛО: зрелых недель {len(mat)} (нужно >= {MIN_WEEKS}), продаж в них {ks} (нужно >= {MIN_SALES}); доля ненадёжна, смотреть диапазон {pc(lo)}..{pc(hi)}, а не центр")
    if not mat:
        warns.append("зрелых недель нет: доля не посчитана")
    if any(w["leads"] == 0 for w in weeks):
        warns.append("недели с нулём заявок в стандарте: " + ", ".join(f"{w['start']:%d.%m}" for w in weeks if w["leads"] == 0) + " (возможно, нет данных источника)")
    if unres_dates is not None and mat:
        n_un = sum(1 for u in unres_dates if any(w["start"] <= u <= w["end"] for w in mat))
        up = wilson(ks + n_un, nl)
        warns.append(f"ИСТОЧНИК ПРОДАЖ НЕПОЛНЫЙ: в зрелых неделях {n_un} проданных заказов с источником «Нет метки» (форма без метки, GA4 по минуте их не опознал) в Google не засчитаны, "
                     f"а заявки по стандарту включают формы Supabase с gclid/utm Google. Доля {pc(share)} - НИЖНЯЯ оценка; если бы все {n_un} были Google: {pc((ks + n_un) / nl if nl else None)} "
                     f"[{pc(up[0])}..{pc(up[1])}]. Проверка: сопоставить телефоны этих заказов с Supabase expertagro_leads (не сделано)")
    warns.append(f"доля занижена на хвост: продажи позже {cut} дн. после заявки не видны (по определению P80 это около 20% продаж); справочно с поправкой ÷0,80: "
                 f"{pc(share / 0.8 if share is not None else None)}, в расчёте НЕ используется (осторожный вариант: можем недобрать заявки, но не сольём бюджет)")
    warns.append("доля = продажи когорты (касание в неделе) ÷ заявки недели по стандарту leads_standard; источники разные (CRM и Ringostat/Supabase), точного совпадения номеров нет")

    T_eur = a.target_sale_cost
    T = T_eur * cfg["rate"]       # в валюте аккаунта
    allowed = {k: (T * v if v is not None else None) for k, v in (("mid", share), ("lo", lo), ("hi", hi))}
    spent, got, plan_b = pace["spent"], pace["got"], pace["plan_b"]
    sales_m = int(((sales["touch_date"] >= first) & (sales["touch_date"] <= done_end)).sum())
    fact_price = spent / sales_m if sales_m else None
    exp = {k: (got * v if v is not None else None) for k, v in (("mid", share), ("lo", lo), ("hi", hi))}
    price_exp = {k: (spent / exp[k] if exp[k] else None) for k in exp}
    fc_s, fc_l = pace["fc_s"], pace["fc_l"]
    fc_price = {k: (fc_s / (fc_l * v) if v and fc_l else None) for k, v in (("mid", share), ("lo", hi), ("hi", lo))}  # низкая доля -> высокая цена
    fc_price_lohi = {"mid": fc_price["mid"], "best": (fc_s / (fc_l * hi) if hi and fc_l else None), "worst": (fc_s / (fc_l * lo) if lo and fc_l else None)}
    need = {}
    for name, S in (("по плановому бюджету месяца", plan_b), ("по прогнозному расходу месяца", fc_s)):
        row = {}
        for k, v in (("mid", share), ("worst", lo), ("best", hi)):
            if not v:
                row[k] = None
                continue
            tot = S / (T * v)                       # заявок за месяц, чтобы цена продажи = цель
            rest = tot - got
            row[k] = dict(total=tot, rest=rest, cpl_rest=((S - spent) / rest if rest > 0 and S > spent else None))
        need[name] = (S, row)
    return dict(weeks=weeks, mat=mat, ks=ks, nl=nl, share=share, lo=lo, hi=hi, ls_all=ls_all, ls_old=ls_old, p80=p80, cut=cut, p80_all=p80_all,
                p80_old=p80_old, warns=warns, T_eur=T_eur, T=T, allowed=allowed, sales_m=sales_m, fact_price=fact_price, exp=exp, price_exp=price_exp,
                fc_price=fc_price_lohi, need=need, w0=w0, last_end=last_end, n_sales_all=len(sales), n_sales_win=len(in_win))


def build_rows(a, cfg, pace, R, today, info):
    """Строки таблицы: (показатель, значение, нижняя граница, верхняя граница, источник и срез)."""
    cur, rows = cfg["cur"], []
    first, done_end = pace["first"], pace["done_end"]
    per_w = f"недели {R['w0']:%d.%m}..{R['last_end']:%d.%m.%Y}"
    per_m = f"{first}..{done_end}"
    src_sales = "выгрузка CRM клиента (лист продаж), режим «наш»"
    src_pace = "pace_vs_plan.run (Цели2 Адвайта, Google Ads API, leads_standard)"
    ls, lo_ = R["ls_all"], R["ls_old"]

    def add(name, v, lo=None, hi=None, src=""):
        rows.append((name, v, lo if lo is not None else "", hi if hi is not None else "", src))

    add("Режим", cfg["mode"], src="решение пользователя: «наш» режим, не смешивать с «как у клиента»")
    add("Цель цены продажи, €", f"{R['T_eur']:.0f}", src="параметр --target-sale-cost (решение пользователя 2026-11-16)")
    if cfg["rate"] != 1.0:
        add(f"Цель цены продажи, {cur}", f"{R['T']:.0f}", src=f"{R['T_eur']:.0f} € × курс {cfg['rate']} zł/€ (параметр --rate)")
    if ls:
        add("Задержка заявка -> продажа: среднее, дн.", f0(ls["mean"], 1), src=f"{src_sales}; {ls['n']} продаж с касанием в {per_w}; обрезана свежестью когорт")
        add("Задержка: медиана, дн.", f0(ls["median"], 1), src="тот же срез")
        add("Задержка: 80-й процентиль, дн.", f0(ls["p80"], 1), src="тот же срез")
        add("Задержка: 95-й процентиль, дн. (справочно, хвост)", f0(ls["p95"], 1), src="тот же срез; в расчёте не используется")
    if lo_:
        add("Задержка (касание старше 60 дн.): среднее / медиана / P80 / P95, дн.", f"{lo_['mean']:.1f} / {lo_['median']:.1f} / {lo_['p80']:.1f} / {lo_['p95']:.1f}",
            src=f"{lo_['n']} продаж с касанием не позже {today - timedelta(days=60)} (не обрезана свежестью)" + ("" if lo_["n"] >= 10 else "; продаж < 10, в отсечку зрелости не берётся"))
    add("Порог зрелости, дн.", f"{R['cut']}", src="большее из двух P80, округлено вверх; неделя зрелая, если от её воскресенья прошло не меньше")
    add("Зрелых недель / заявок / продаж", f"{len(R['mat'])} / {R['nl']} / {R['ks']}", src=f"{per_w}; {src_sales}; заявки: leads_standard")
    add("Зрелая доля заявок -> продажа", pc(R["share"]), R["lo"], R["hi"], src="продажи ÷ заявки по зрелым неделям; границы - интервал Уилсона 95%")
    add("Допустимая цена заявки (цель × доля), " + cur, f0(R["allowed"]["mid"]), R["allowed"]["lo"], R["allowed"]["hi"], src=f"цель {R['T']:.0f} {cur} × доля; границы по границам доли")
    add("Фактическая цена заявки месяца, " + cur, f0(pace["cpa_fact"]), src=f"{src_pace}: расход ÷ заявки, {per_m}")
    add("План таблицы: цена заявки, " + cur, f0(pace["plan_cpa"]), src=f"{pace['plan_src']}" + ("; строка только «Теплицы Польша», расход - аккаунт целиком" if a.client_folder == "EkspertAgro" else ""))
    am = R["allowed"]["mid"]
    if am and pace["cpa_fact"]:
        add("Факт цены заявки против допустимой (центр)", f"{(pace['cpa_fact'] / am - 1) * 100:+.0f}%", src="факт ÷ допустимая - 1; минус = дешевле допустимой")
    add("Факт месяца: расход, " + cur, f0(pace["spent"]), src=f"{src_pace}, {per_m}")
    add("Факт месяца: заявки", f"{pace['got']}", src=f"{src_pace}, {per_m}")
    add("Факт месяца: продажи на сегодня (по касанию в месяце)", f"{R['sales_m']}", src=f"{src_sales}; касание {per_m}; недосчитаны по незрелым заявкам")
    add("Факт цены продажи на сегодня, " + cur, f0(R["fact_price"]), src="расход ÷ продажи на сегодня; ЗАВЫШЕНА: свежие заявки ещё не стали продажами")
    ex = R["exp"]
    add("Ожидаемые продажи по заявкам месяца", f0(ex["mid"], 1), ex["lo"], ex["hi"], src=f"заявки {pace['got']} × зрелая доля; границы по границам доли")
    pe = R["price_exp"]
    add("Цена продажи при ожидаемых продажах, " + cur, f0(pe["mid"]), pe["hi"], pe["lo"], src="расход на сегодня ÷ ожидаемые продажи; границы - обратные границам доли")
    fp = R["fc_price"]
    add("Прогноз цены продажи по месяцу, " + cur, f0(fp["mid"]), fp["best"], fp["worst"],
        src=f"прогноз расхода {pace['fc_s']:.0f} ÷ (прогноз заявок {pace['fc_l']:.0f} × доля); {src_pace}; границы - лучшая/худшая доля")
    for name, (S, row) in R["need"].items():
        m, w, b = row["mid"], row["worst"], row["best"]
        add(f"Заявок за месяц, чтобы выйти на цель ({name}: {S:.0f} {cur})", f0(m["total"]) if m else "н/д", b["total"] if b else None, w["total"] if w else None,
            src=f"расход ÷ (цель × доля); диапазон по границам доли; уже получено {pace['got']}")
        add(f"Нужно ещё заявок на остаток месяца ({name})", f0(m["rest"]) if m else "н/д", b["rest"] if b else None, w["rest"] if w else None,
            src="заявок за месяц - получено; отрицательное = уже хватает")
        add(f"Допустимая цена заявки на остаток ({name}), " + cur, f0(m["cpl_rest"]) if m and m["cpl_rest"] else "н/д", w["cpl_rest"] if w and w["cpl_rest"] else None,
            b["cpl_rest"] if b and b["cpl_rest"] else None, src=f"(расход месяца {S:.0f} - факт {pace['spent']:.0f}) ÷ нужные заявки на остаток; пусто, если заявок хватает или бюджет исчерпан")
    return rows


def print_all(a, cfg, pace, R, rows, info):
    print(f"=== Цена продажи и допустимая цена заявки: {a.client_folder}, {pace['first']:%Y-%m}, на {pace['today']} (чтение, режим «наш») ===")
    for x in info:
        print("Данные:", x)
    print(f"Режим: {cfg['mode']}")
    print(f"Валюта аккаунта: {cfg['cur']}" + (f" (1 € = {cfg['rate']} zł)" if cfg["rate"] != 1.0 else ""))
    print()
    print("Когорты по неделям заявок (источник: leads_standard + выгрузка CRM, режим «наш»):")
    print(f"  {'неделя':<14}{'заявок':>8}{'продаж':>8}{'доля':>8}{'возраст, дн.':>14}  зрелая")
    for w in R["weeks"]:
        print(f"  {w['start']:%d.%m}-{w['end']:%d.%m}   {w['leads']:>8}{w['sales']:>8}{pc(w['share']):>8}{w['age']:>14}  {'да' if w['mature'] else 'нет'}")
    print()
    wdt = max(len(r[0]) for r in rows)
    for n, v, lo, hi, s in rows:
        rng = f"  [{f0(lo) if not isinstance(lo, str) and lo != '' else ''}..{f0(hi) if not isinstance(hi, str) and hi != '' else ''}]" if (lo != "" or hi != "") else ""
        if "доля" in n.lower() and "Зрелая" in n:
            rng = f"  [{pc(lo)}..{pc(hi)}]"
        elif "Ожидаемые продажи" in n:
            rng = f"  [{f0(lo, 1)}..{f0(hi, 1)}]"
        print(f"{n:{wdt}} | {str(v):>14}{rng} | {s}")
    print()
    for x in R["warns"]:
        print("ПРЕДУПРЕЖДЕНИЕ: " + x)
    for x in pace["warns"]:
        print("ПРЕДУПРЕЖДЕНИЕ (pace_vs_plan): " + x)


def write_csv(a, pace, R, rows, info):
    out = client_stats_dir(a.client_folder) / f"sales_pace_{pace['first']:%Y-%m}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["показатель", "значение", "нижняя граница", "верхняя граница", "источник и срез"])
        for n, v, lo, hi, s in rows:
            fmt = lambda x: "" if x == "" or x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))  # noqa: E731
            wr.writerow([n, v, fmt(lo), fmt(hi), s])
        wr.writerow([])
        wr.writerow(["неделя с", "неделя по", "заявок", "продаж на сегодня", "доля", "возраст конца недели, дн.", "зрелая"])
        for w in R["weeks"]:
            wr.writerow([w["start"], w["end"], w["leads"], w["sales"], "" if w["share"] is None else f"{w['share']:.4f}", w["age"], "да" if w["mature"] else "нет"])
        wr.writerow([])
        for x in info:
            wr.writerow(["данные", x])
        for x in R["warns"] + pace["warns"]:
            wr.writerow(["предупреждение", x])
        wr.writerow(["дата расчёта", str(pace["today"])])
    print(f"CSV: {out}")


# ---------- Google Таблица (только ProfiMet, только --update-sheet) ----------
def sheet_block(rows):
    """Блок «Продажи» для листа «Темп к плану»: (показатель, значение, источник); границы вписаны в значение."""
    out = []
    for n, v, lo, hi, s in rows:
        val = str(v)
        if lo != "" or hi != "":
            if "доля" in n.lower() and "Зрелая" in n:
                val += f" [{pc(lo)}..{pc(hi)}]"
            else:
                val += f" [{f0(lo, 1) if not isinstance(lo, str) else ''}..{f0(hi, 1) if not isinstance(hi, str) else ''}]"
        out.append([n, val, s])
    return out


def sheet_plan_text(sheet_id, blk, R):
    last = BLOCK_ROW + 2 + len(blk) - 1
    t = [f"Таблица: https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
         f"Лист «{S_MAIN}»: блок «Продажи» A{BLOCK_ROW}:C{last} (A{BLOCK_ROW} заголовок, A{BLOCK_ROW + 1}:C{BLOCK_ROW + 1} шапка, {len(blk)} строк с A{BLOCK_ROW + 2}); строки 1-36, графики (колонка E) и другие листы не трогаются. "
         f"Перед записью очищается только A{BLOCK_ROW}:C{BLOCK_ROW + 80}.",
         f"Лист «{S_COH}» (создать, если нет; перезаписать только его): шапка + {len(R['weeks'])} недель + строка итога.",
         "ВАЖНО: pace_vs_plan_sheet.py очищает «Темп к плану» A1:C39 (не ниже), блок с A41 он не стирает."]
    return "\n".join(t)


def write_sheet(sheet_id, blk, R, pace):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials
    from _config import SERVICE_ACCOUNT_FILE
    from zoneinfo import ZoneInfo
    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    sheets = s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in sheets}
    if S_MAIN not in ids:
        raise SystemExit(f"На листе нет «{S_MAIN}»: сначала pace_vs_plan_sheet.py --update-sheet")
    if S_COH not in ids:
        s.post(base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": S_COH}}}]}, timeout=60).raise_for_status()
        sheets = s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]
        ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in sheets}

    def read(rng):
        return s.get(base + f"/values/{rng}?valueRenderOption=UNFORMATTED_VALUE", timeout=60).json().get("values", [])
    r0, r1 = BLOCK_ROW, BLOCK_ROW + 2 + len(blk) - 1
    before = {x[0]: (x[1] if len(x) > 1 else "") for x in read(f"{S_MAIN}!A{r0}:B{r1}") if x}
    now = datetime.now(ZoneInfo(WARSAW)).strftime("%d.%m.%Y %H:%M")
    s.post(base + f"/values/{S_MAIN}!A{BLOCK_ROW}:C{BLOCK_ROW + 80}:clear", json={}, timeout=60).raise_for_status()
    s.post(base + f"/values/{S_COH}!A1:J200:clear", json={}, timeout=60).raise_for_status()
    coh = [COH_HEAD] + [[w["start"].isoformat(), w["end"].isoformat(), w["leads"], w["sales"], w["share"] if w["share"] is not None else "", w["age"],
                         "да" if w["mature"] else "нет"] for w in R["weeks"]]
    coh.append(["Зрелые недели", "", R["nl"], R["ks"], R["share"] if R["share"] is not None else "", "", ""])
    data = [
        {"range": f"{S_MAIN}!A{BLOCK_ROW}", "values": [[f"Продажи: цена продажи и допустимая цена заявки (скрипт sales_pace.py, обновлено {now}, на {pace['today']})"]]},
        {"range": f"{S_MAIN}!A{BLOCK_ROW + 1}", "values": [["Показатель", "Значение [нижняя..верхняя граница]", "Источник и срез"]]},
        {"range": f"{S_MAIN}!A{BLOCK_ROW + 2}", "values": blk},
        {"range": f"{S_COH}!A1", "values": coh},
    ]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()
    sid_m, sid_c = ids[S_MAIN], ids[S_COH]
    bold = {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.867, "green": 0.922, "blue": 0.969}}}
    rg = lambda sid, a0, a1, c0, c1: {"sheetId": sid, "startRowIndex": a0, "endRowIndex": a1, "startColumnIndex": c0, "endColumnIndex": c1}  # noqa: E731
    reqs = [{"repeatCell": {"range": rg(sid_m, BLOCK_ROW - 1, BLOCK_ROW + 1, 0, 3), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
            {"repeatCell": {"range": rg(sid_c, 0, 1, 0, len(COH_HEAD)), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
            {"repeatCell": {"range": rg(sid_c, 1, len(coh), 4, 5), "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
                            "fields": "userEnteredFormat.numberFormat"}},
            {"updateSheetProperties": {"properties": {"sheetId": sid_c, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}}]
    s.post(base + ":batchUpdate", json={"requests": reqs}, timeout=60).raise_for_status()
    after = {x[0]: (x[1] if len(x) > 1 else "") for x in read(f"{S_MAIN}!A{r0}:B{r1}") if x}
    print("Прочитано обратно (было -> стало), ключевые ячейки блока:")
    for k, v, *_ in blk:
        if k.startswith(("Зрелая доля", "Допустимая цена заявки (цель", "Прогноз цены продажи")):
            print(f"  {k}: {before.get(k, '(пусто)')} -> {after.get(k, '(пусто)')}")
    print(f"Строк блока записано: {len([k for k in after if k in {b[0] for b in blk}])} из {len(blk)}; недель на листе «{S_COH}»: {len(R['weeks'])}")


def build_parser():
    ap = argparse.ArgumentParser(description="Цена продажи и допустимая цена заявки по когортам заявок (только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True, help="ProfiMet или EkspertAgro (ExpertAgro принимается как синоним)")
    ap.add_argument("--month", help="ГГГГ-ММ, по умолчанию месяц --today")
    ap.add_argument("--today", help="ГГГГ-ММ-ДД, по умолчанию сегодня (Варшава)")
    ap.add_argument("--target-sale-cost", type=float, default=43.0, help="целевая цена продажи, € (по умолчанию 43)")
    ap.add_argument("--weeks", type=int, default=12, help="глубина когорт, полных недель (по умолчанию 12)")
    ap.add_argument("--rate", type=float, help="zł за 1 € (только EkspertAgro; по умолчанию 4.3691)")
    ap.add_argument("--cache", help="pickle (sheet, ringo) как у profimet_sources_dashboard.py --cache; только ProfiMet")
    ap.add_argument("--update-sheet", nargs="?", const="DEFAULT", default=None, metavar="ID",
                    help="ProfiMet: записать блок «Продажи» на лист «Темп к плану» и лист «Продажи_когорты» (по умолчанию — таблица дашборда ProfiMet); без флага — только печать плана")
    return ap


def main():
    a = build_parser().parse_args()
    a.client_folder = ALIASES.get(a.client_folder.lower(), a.client_folder)
    if a.client_folder not in CLIENTS:
        raise SystemExit(f"Пробел: клиент {a.client_folder} не заведён в CLIENTS (есть: {', '.join(CLIENTS)})")
    cfg = dict(CLIENTS[a.client_folder])
    if a.rate:
        cfg["rate"] = a.rate
    a.customer_id = a.customer_id.replace("-", "")
    if a.customer_id != cfg["customer_id"]:
        raise SystemExit(f"customer-id {a.customer_id} не совпадает с CLIENTS[{a.client_folder}] = {cfg['customer_id']}")
    if a.update_sheet and not cfg["sheet"]:
        raise SystemExit("--update-sheet для этого клиента не поддержан (только консоль и CSV)")

    pa = argparse.Namespace(customer_id=a.customer_id, client_folder=a.client_folder, month=a.month, today=a.today, weeks=6, weekend_weight=None)
    with contextlib.redirect_stdout(io.StringIO()):
        pace = P.run(pa)
    today = pace["today"]
    sales, info = sales_profimet(a.cache) if cfg["loader"] == "profimet" else sales_ea(today)
    R = compute(a, cfg, pace, sales, today)
    rows = build_rows(a, cfg, pace, R, today, info)
    print_all(a, cfg, pace, R, rows, info)
    write_csv(a, pace, R, rows, info)
    if cfg["sheet"]:
        from pace_vs_plan_sheet import DASHBOARD_SHEET_ID
        sid = DASHBOARD_SHEET_ID if a.update_sheet in (None, "DEFAULT") else a.update_sheet
        blk = sheet_block(rows)
        print("\n=== Google Таблица: " + ("ЗАПИСЬ" if a.update_sheet else "план (в таблицу НЕ пишу, нужен --update-sheet)") + " ===")
        print(sheet_plan_text(sid, blk, R))
        if a.update_sheet:
            write_sheet(sid, blk, R, pace)
    else:
        print("\nGoogle Таблица: для этого клиента не пишется (только консоль и CSV). Блок мог бы лежать в таблице «Цели2 Адвайта», лист «Ноябрь 26» (ниже строки клиента) или в отдельной таблице-дашборде EkspertAgro — решение пользователя.")


if __name__ == "__main__":
    main()
