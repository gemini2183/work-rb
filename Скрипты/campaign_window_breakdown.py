#!/usr/bin/env python
# coding: utf-8
"""Разложение кампании за окно: показы -> клики -> заявки -> цена заявки с интервалами.

Зачем: шаг 3 «Алгоритм_анализа_кампании.md» (База_знаний/Агенты/): цепочка по одной кампании за
окно с интервалами 80 % и 95 %, источники заявок, две половины окна, потеря показов, положение
допустимой цены относительно интервала. Раньше считалось разовым кодом, теперь - этот скрипт.

Только ЧТЕНИЕ: Google Ads (GAQL), Ringostat и Supabase через leads_standard.month_leads.
Ничего не пишет во внешние системы (флага --execute нет и не нужно); пишет только markdown
в --out-dir. Кампании с префиксом yt_ (YouTube - отдельный проект) отклоняются.

Что считает (два варианта: все дни / без --exclude-days; плюс две половины окна):
  показы, клики, CTR (Вильсон и Клоппер-Пирсон, 80 и 95 %), цена клика, расход,
  заявки в дни с расходом по источникам (сайт Ringostat / формы Supabase с меткой кампании / звонки из объявлений
  call_view) и доли, конверсия заявки/клики (Клоппер-Пирсон), заявки (Гарвуд, точный Пуассон),
  цена заявки = расход / интервал заявок (расход фиксирован), формы без метки (отдельно, в счёт
  не входят), заявки в дни без расхода (число отдельно, в счёт не входят; цена с ними справочно), потеря показов по бюджету и
  рейтингу (gads_impression_share.fetch_impression_share, агрегат за окно), число заявок для
  полуширины +-35 %, положение допустимой цены --target-cpa-low/high относительно интервала.

Performance Max: у него нет ключей и поисковой доли показов - потеря показов пишется «нет в данных»
(метрики Search IS недоступны); заявки привязываются по кампании в month_leads (utm_campaign / id).

Запуск (из папки Скрипты):
  PYTHONUTF8=1 python campaign_window_breakdown.py --customer-id 7552781705 --campaign-id 19158580966 \\
      --from 2026-10-19 --to 2026-11-12 --exclude-days 2026-10-28,2026-10-29,2026-11-05 \\
      --client-folder ProfiMet --out-dir "../Клиенты/ProfiMet/Работы/2026-11-16_campaign_analysis"
  (вместо --campaign-id можно --campaign "Search | Poliweglan | Pl")

Дата создания: 2026-11-16.
"""
import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LEVELS = (0.80, 0.95)


# ---------- интервалы ----------
def clopper_pearson(k, n, cl):
    if n <= 0:
        return (float("nan"), float("nan"))
    a = (1 - cl) / 2
    lo = 0.0 if k == 0 else stats.beta.ppf(a, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(1 - a, k + 1, n - k)
    return lo, hi


def wilson(k, n, cl):
    if n <= 0:
        return (float("nan"), float("nan"))
    z = stats.norm.ppf(1 - (1 - cl) / 2)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def garwood(k, cl):
    a = (1 - cl) / 2
    lo = 0.0 if k == 0 else stats.gamma.ppf(a, k)
    hi = stats.gamma.ppf(1 - a, k + 1)
    return lo, hi


def n_for_halfwidth(cl, rel=0.35, kmax=2000):
    for k in range(1, kmax):
        lo, hi = garwood(k, cl)
        if (hi - lo) / 2 / k <= rel:
            return k
    return None


# ---------- данные ----------
def _en(enum_type, field, value):
    from gads_campaigns_breakdown import _enum_name
    return _enum_name(enum_type, field, int(value))


def resolve_campaign(ga, cid, campaign_id, campaign_name):
    where = f"campaign.id = {int(campaign_id)}" if campaign_id else "campaign.name = '%s'" % campaign_name.replace("'", "\\'")
    q = f"SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type FROM campaign WHERE {where}"
    rows = [r for b in ga.search_stream(customer_id=cid, query=q) for r in b.results]
    if not rows:
        raise SystemExit("Кампания не найдена в аккаунте %s" % cid)
    r = rows[0]
    return {"id": str(r.campaign.id), "name": r.campaign.name, "status": _en("CampaignStatusEnum", "CampaignStatus", r.campaign.status),
            "channel": _en("AdvertisingChannelTypeEnum", "AdvertisingChannelType", r.campaign.advertising_channel_type)}


def fetch_days(ga, cid, camp_id, d0, d1):
    q = f"""SELECT segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros
            FROM campaign
            WHERE campaign.id = {int(camp_id)} AND segments.date BETWEEN '{d0}' AND '{d1}'"""
    rows = []
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            rows.append({"Date": pd.Timestamp(r.segments.date), "Impressions": int(r.metrics.impressions),
                         "Clicks": int(r.metrics.clicks), "Cost": r.metrics.cost_micros / 1e6})
    df = pd.DataFrame(rows, columns=["Date", "Impressions", "Clicks", "Cost"])
    df = df.groupby("Date", as_index=False).sum()
    return df[df["Cost"] > 0].sort_values("Date").reset_index(drop=True)   # день с расходом


def fetch_leads(folder, d0, d1, camp_name):
    import leads_standard as L
    r = L.month_leads(folder, d0, d1, calls_from_ads="call_view")
    c, f = r["calls"], r["forms"]
    cc = c[c.camp == camp_name].copy()
    cc["day"] = pd.to_datetime(cc["day"])
    cc["k"] = np.where(cc.via_call_view, "ads", "site")
    ff = f[f.camp == camp_name].copy()
    ff["day"] = pd.to_datetime(ff["day"])
    fn = f[f.camp == ""].copy()
    fn["day"] = pd.to_datetime(fn["day"])
    out = {
        "site": cc[cc.k == "site"].groupby("day").size(),
        "ads": cc[cc.k == "ads"].groupby("day").size(),
        "forms": ff.groupby("day").size(),
        "nolabel": fn,
        "guard_cid": str(r["guard_cfg"]["customer_id"]),
    }
    return out


def lost_is(ga, cid, d0, d1, name):
    try:
        import gads_impression_share as G
        df = G.fetch_impression_share(ga, cid, d0, d1, {name})
    except Exception as e:  # noqa: BLE001 - любой отказ API = «нет в данных», не падаем
        return None, "ошибка запроса: %s" % str(e)[:120]
    if df is None or df.empty:
        return None, "нет в данных (метрики Search IS недоступны для этого типа кампании)"
    return df.iloc[0].to_dict(), None


# ---------- расчёт ----------
def calc(days, leads, nolabel_count, day_filter=None):
    """days - дневной ряд с расходом; leads - dict рядов по дням; day_filter - даты в расчёте (по умолчанию все)."""
    d = days
    if day_filter is not None:
        d = d[d.Date.isin(day_filter)]
    s = {"days": len(d), "imp": int(d.Impressions.sum()), "clk": int(d.Clicks.sum()), "cost": float(d.Cost.sum())}
    lo, hi = (days.Date.min(), days.Date.max()) if len(days) else (None, None)

    def cnt(series, in_spend):
        if series.empty:
            return 0
        x = series
        if day_filter is not None:
            x = x[x.index.isin(day_filter)]
        if in_spend is not None:
            spend_days = set(d.Date)
            x = x[x.index.isin(spend_days)] if in_spend else x[~x.index.isin(spend_days)]
        return int(x.sum())

    s["site"], s["ads"], s["forms"] = (cnt(leads[k], True) for k in ("site", "ads", "forms"))
    s["n"] = s["site"] + s["ads"] + s["forms"]
    s["n_nospend"] = sum(cnt(leads[k], False) for k in ("site", "ads", "forms"))
    s["nolabel"] = nolabel_count
    return s


def fmt_ci(lo, hi, mult=1.0, nd=2):
    return f"{lo*mult:.{nd}f}-{hi*mult:.{nd}f}"


def rows_for(s, cpa_lo, cpa_hi):
    """Строки таблицы (звено, значение) для одного набора s."""
    imp, clk, cost, n = s["imp"], s["clk"], s["cost"], s["n"]
    R = []
    R.append(("Дней с расходом", str(s["days"])))
    R.append(("Показы", f"{imp:,}".replace(",", " ")))
    R.append(("Клики", f"{clk:,}".replace(",", " ")))
    if imp:
        ctr = clk / imp * 100
        parts = [f"{ctr:.2f} %"]
        for cl in LEVELS:
            w = wilson(clk, imp, cl)
            parts.append(f"{int(cl*100)} % Вильсон {fmt_ci(*w, 100)}")
        cp = clopper_pearson(clk, imp, 0.95)
        parts.append(f"95 % КП {fmt_ci(*cp, 100)}")
        R.append(("CTR", "; ".join(parts)))
    R.append(("Цена клика, €", f"{cost/clk:.3f}" if clk else "нет данных"))
    R.append(("Расход, €", f"{cost:.2f}"))
    pct = lambda x: f"{x/n*100:.0f} %" if n else "-"
    R.append(("Заявки: сайт Ringostat", f"{s['site']} / {pct(s['site'])}"))
    R.append(("Заявки: звонки из объявлений (call_view)", f"{s['ads']} / {pct(s['ads'])}"))
    R.append(("Заявки: формы Supabase с меткой кампании", f"{s['forms']} / {pct(s['forms'])}"))
    parts = [str(n)]
    for cl in LEVELS:
        parts.append(f"{int(cl*100)} % Гарвуд {fmt_ci(*garwood(n, cl), 1, 1)}")
    R.append(("Заявки всего", "; ".join(parts)))
    if clk:
        parts = [f"{n/clk*100:.2f} %"]
        for cl in LEVELS:
            parts.append(f"{int(cl*100)} % КП {fmt_ci(*clopper_pearson(n, clk, cl), 100)}")
        R.append(("Конверсия (заявки/клики)", "; ".join(parts)))
    if n:
        parts = [f"{cost/n:.1f} €"]
        for cl in LEVELS:
            lo, hi = garwood(n, cl)
            parts.append(f"{int(cl*100)} % {cost/hi:.1f}-{(cost/lo if lo else float('inf')):.1f}")
        R.append(("Цена заявки (расход фикс.)", "; ".join(parts)))
        pos = []
        for cl in LEVELS:
            lo, hi = garwood(n, cl)
            p_lo, p_hi = cost / hi, (cost / lo if lo else float("inf"))
            if cpa_hi < p_lo:
                t = "вся зона ниже нижней границы интервала (цена выше допустимой)"
            elif cpa_lo > p_hi:
                t = "вся зона выше верхней границы (цена ниже допустимой)"
            else:
                t = "зона пересекает интервал: данных для вывода нет"
            pos.append(f"{int(cl*100)} %: {t}")
        R.append((f"Допустимая цена {cpa_lo:g}-{cpa_hi:g} € относительно интервала", "; ".join(pos)))
    else:
        R.append(("Цена заявки", "заявок 0: цены нет"))
    nosp = s["n_nospend"]
    R.append(("Заявок в дни без расхода (в счёт НЕ входят)", str(nosp)))
    if nosp and n + nosp > 0:
        R.append(("Цена заявки, если их добавить, €", f"{cost/(n+nosp):.1f}"))
    R.append(("Формы без метки campaign (в счёт не входят)", str(s["nolabel"])))
    return R


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def two_cols(sa, sb, cpa_lo, cpa_hi, ha, hb):
    ra, rb = rows_for(sa, cpa_lo, cpa_hi), rows_for(sb, cpa_lo, cpa_hi)
    kb = dict(rb)
    return md_table(["Звено", ha, hb], [(k, v, kb.get(k, "-")) for k, v in ra])


def main():
    ap = argparse.ArgumentParser(description="Разложение кампании за окно (чтение). См. docstring файла.")
    ap.add_argument("--customer-id", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--campaign-id")
    g.add_argument("--campaign", help="точное имя кампании")
    ap.add_argument("--from", dest="d0", required=True)
    ap.add_argument("--to", dest="d1", required=True)
    ap.add_argument("--exclude-days", default="", help="даты через запятую YYYY-MM-DD")
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--halves", default="yes", choices=["yes", "no"], help="две половины окна (по умолчанию yes)")
    ap.add_argument("--target-cpa-low", type=float, default=22.0)
    ap.add_argument("--target-cpa-high", type=float, default=24.0)
    ap.add_argument("--out-dir", help="папка для markdown-файла; без неё только консоль")
    a = ap.parse_args()

    cid = a.customer_id.replace("-", "").strip()
    from gads_stats import GOOGLE_ADS_YAML, get_ads_service
    from google.ads.googleads.client import GoogleAdsClient
    ga = get_ads_service(GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id)

    camp = resolve_campaign(ga, cid, a.campaign_id, a.campaign)
    if camp["name"].lower().startswith("yt_"):
        raise SystemExit("Кампания yt_* (YouTube) - отдельный проект, не анализируется этим скриптом.")
    days = fetch_days(ga, cid, camp["id"], a.d0, a.d1)
    L = fetch_leads(a.client_folder, a.d0, a.d1, camp["name"])
    warn = []
    if L["guard_cid"] != cid:
        warn.append(f"customer-id {cid} не совпадает с guard_config клиента {L['guard_cid']}: заявки могли быть взяты из другого аккаунта")

    excl = [pd.Timestamp(x.strip()) for x in a.exclude_days.split(",") if x.strip()]
    nl = L["nolabel"]
    nlc = lambda lo, hi, skip=(): int(((nl.day >= lo) & (nl.day <= hi) & ~nl.day.isin(skip)).sum()) if len(nl) else 0
    t0, t1 = pd.Timestamp(a.d0), pd.Timestamp(a.d1)
    # заявки в исключённые дни из счёта вариантов «без» убираются через day_filter
    all_days = set(pd.date_range(t0, t1))
    keep = all_days - set(excl)
    s_all = calc(days, L, nlc(t0, t1))
    s_red = calc(days, L, nlc(t0, t1, excl), day_filter=keep) if excl else None
    # day_filter для days: дни с расходом, не исключённые
    out = [f"# Разложение кампании {camp['name']} ({camp['id']}), окно {a.d0}..{a.d1}", "",
           f"Тип: {camp['channel']}, статус сейчас: {camp['status']}. Клиент: {a.client_folder}. Сформировано: {datetime.now():%Y-%m-%d %H:%M}. Только чтение, без yt_.",
           f"Источники: показы/клики/расход - GAQL campaign x день; заявки - leads_standard.month_leads (call_view); потеря показов - gads_impression_share.",
           f"Интервалы: CTR - Вильсон и Клоппер-Пирсон; конверсия - Клоппер-Пирсон; заявки - Гарвуд; цена заявки = расход / интервал заявок (расход фиксирован); уровни 80 и 95 %.",
           f"Исключённые дни: {', '.join(x.strftime('%Y-%m-%d') for x in excl) or 'нет'}.", ""]
    for w in warn:
        out.append("ВНИМАНИЕ: " + w)
    out += ["## 1. Цепочка за окно", ""]
    if s_red:
        out += two_cols(s_all, s_red, a.target_cpa_low, a.target_cpa_high, "Все дни", f"Без исключённых ({len(excl)})")
        ex = days[days.Date.isin(excl)]
        out += ["", f"Исключённые дни с расходом в ряду: {len(ex)}; их расход {ex.Cost.sum():.2f} €, показы {int(ex.Impressions.sum())}, клики {int(ex.Clicks.sum())}."]
    else:
        out += md_table(["Звено", "Все дни"], rows_for(s_all, a.target_cpa_low, a.target_cpa_high))
    out += ["", "Цена клика: интервала нет (расход/клики по сумме). Формы без метки - нижняя оценка, кампания неизвестна."]

    # половины
    if a.halves == "yes" and len(days):
        total = (t1 - t0).days + 1
        mid = t0 + timedelta(days=(total + 1) // 2 - 1)
        h1 = set(pd.date_range(t0, mid))
        h2 = set(pd.date_range(mid + timedelta(days=1), t1))
        out += ["", f"## 2. Две половины окна ({a.d0}..{mid:%Y-%m-%d} и {(mid + timedelta(days=1)):%Y-%m-%d}..{a.d1})", ""]
        for label, flt in (("Все дни", None), ("Без исключённых", keep)):
            if flt is None:
                f1, f2 = h1, h2
            elif not excl:
                continue
            else:
                f1, f2 = h1 & keep, h2 & keep
            sa = calc(days, L, nlc(min(f1), max(f1)), day_filter=f1)
            sb = calc(days, L, nlc(min(f2), max(f2)), day_filter=f2)
            out += [f"**{label}**", ""] + two_cols(sa, sb, a.target_cpa_low, a.target_cpa_high,
                                                   f"{min(f1):%d.%m}-{max(f1):%d.%m}", f"{min(f2):%d.%m}-{max(f2):%d.%m}") + [""]
            if sa["imp"] and sb["imp"]:
                out.append(f"В день: показы {sa['imp']/sa['days']:.0f} -> {sb['imp']/sb['days']:.0f}, расход {sa['cost']/sa['days']:.1f} -> {sb['cost']/sb['days']:.1f} € (на день с расходом).")
                out.append("")

    # потеря показов
    out += ["## 3. Потеря показов (агрегат за окно, по дням в данных этого нет)", ""]
    if camp["channel"] != "SEARCH":
        out.append(f"Нет в данных: метрики Search IS недоступны для типа {camp['channel']} (нет поисковой доли показов).")
    else:
        row, err = lost_is(ga, cid, a.d0, a.d1, camp["name"])
        if row is None:
            out.append("Нет в данных: " + str(err))
        else:
            pc = lambda v: "нет в данных" if v is None or pd.isna(v) else f"{v*100:.1f} %"
            out.append(f"Доля показов {pc(row.get('Impression_share'))}; потеря по бюджету {pc(row.get('Lost_IS_budget'))}; потеря по рейтингу {pc(row.get('Lost_IS_rank'))}; вверху страницы {pc(row.get('Top_IS'))}; абсолютный верх {pc(row.get('Absolute_top_IS'))}. Показы/клики в выгрузке: {row.get('Impressions')}/{row.get('Clicks')}.")

    # сколько заявок нужно
    out += ["", "## 4. Сколько заявок нужно для полуширины +-35 %", ""]
    out.append(f"На 80 %: {n_for_halfwidth(.80)}; на 95 %: {n_for_halfwidth(.95)} (Гарвуд, (верх - низ)/2/k <= 0,35). Сейчас заявок: {s_all['n']}" + (f" / {s_red['n']} без исключённых." if s_red else "."))
    out += ["", "Не учтено: связь между днями (перегруженность Пуассона), полнота форм в Supabase (мусорные пачки), потеря форм до записи в базу."]
    text = "\n".join(out)
    print(text)
    if a.out_dir:
        p = Path(a.out_dir)
        p.mkdir(parents=True, exist_ok=True)
        fn = p / f"campaign_window_{camp['id']}_{a.d0}_to_{a.d1}.md"
        fn.write_text(text + "\n", encoding="utf-8")
        print("\nСохранено:", fn)


if __name__ == "__main__":
    main()
