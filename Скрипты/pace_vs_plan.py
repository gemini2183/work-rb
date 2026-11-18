#!/usr/bin/env python
# coding: utf-8
"""Темп к плану месяца с поправкой на выходные — ТОЛЬКО ЧТЕНИЕ (в кабинеты, сайты и вики ничего не пишет).

Зачем: линейный темп «план / дней в месяце» (раздел [4] state_digest.py) врёт, если клиент по расписанию почти не тратит
в выходные или заявки приходят в будни: «отстаём» на понедельник, хотя прошли выходные. Здесь будний день = 1.0, а выходной
(сб и вс вместе) считается за один вес: среднее по выходному дню / среднее по будничному дню за последние --weeks недель.
Вес считается отдельно по расходу и по заявкам, по одному числу на выходные. Сб и вс по отдельности печатаются справочно,
в расчёте не используются.

Что берёт (ничего не дублирует, всё переиспользовано):
  план месяца — campaign_analyzer.sources.read_plan (таблица «Цели2 Адвайта», строка из analysis_config.yaml -> plan);
  расход по дням — Google Ads API (segments.date), как в state_digest.py;
  заявки по дням — единый стандарт leads_standard.month_leads (звонки Ringostat Google Ads + формы Supabase Google).
Дни с правками кампаний НЕ исключаются: правки бывают каждый день, исключение выбросило бы половину данных.

Окно веса: --weeks N полных недель = последние 7*N дней, заканчивая ВЧЕРА (сегодняшний неполный день не берётся):
N суббот, N воскресений, 5*N будней. Мало данных (<4 недель, нет расхода) — предупреждение в выводе.

Что считает: план месяца; факт на дату (расход, заявки, цена заявки) по завершённым дням; сколько «взвешенных будней»
прошло и осталось; план на дату с поправкой на вес; отставание/опережение по расходу и заявкам (абс. и %), и для сравнения
по календарным дням (как state_digest); прогноз закрытия месяца по текущему темпу; нужный расход и допустимая цена заявки
в будний день на остаток. Режим один: чтение. --execute нет.

Результат: таблица в stdout и CSV `Клиенты/<Имя>/Статистика/pace_vs_plan_<ГГГГ-ММ>.csv` (перезаписывается).

Использование (из папки Скрипты, с PYTHONUTF8=1):
    python pace_vs_plan.py --customer-id 7552781705 --client-folder ProfiMet [--month 2026-11] [--today 2026-11-16]
                           [--weeks 6] [--weekend-weight 0.1]
--weekend-weight вручную задаёт один вес выходных (и для расхода, и для заявок) вместо посчитанного из истории.
Выгрузка в Google Таблицу дашборда — отдельный скрипт pace_vs_plan_sheet.py (берёт расчёт из run() здесь).
Создан 2026-11-16, переделан 2026-11-16 (один вес выходных, без исключения грязных дней).
"""
import argparse
import calendar
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd
import yaml

sys.stdout.reconfigure(encoding="utf-8")

from _config import client_stats_dir  # noqa: E402

def load_cfg(folder):
    path = client_stats_dir(folder).parent / "analysis_config.yaml"
    if not path.exists():
        raise SystemExit(f"Пробел: нет {path} (секция plan: sheet_id, client_name, budget_column)")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not cfg.get("plan", {}).get("client_name"):
        raise SystemExit(f"В {path} нет plan.client_name")
    return cfg


EXCLUDE_PREFIX = "yt_"   # YouTube - отдельный проект (решение пользователя 2026-11-16): не входит в расход и заявки


def is_excluded(name):
    return str(name or "").lower().startswith(EXCLUDE_PREFIX)


def daily_cost(ga, cid, d0, d1):
    """Расход по дням без кампаний yt_* (YouTube - отдельный проект)."""
    out = defaultdict(float)
    for r in ga.search(customer_id=cid, query=("SELECT segments.date, campaign.name, metrics.cost_micros FROM campaign "
                                               f"WHERE segments.date BETWEEN '{d0}' AND '{d1}'")):
        if is_excluded(r.campaign.name):
            continue
        out[date.fromisoformat(r.segments.date)] += r.metrics.cost_micros / 1e6
    return out


def daily_leads(folder, d0, d1):
    """Заявки Google Ads по дням по единому стандарту: звонки Ringostat + формы Supabase (src=google), без кампаний yt_*."""
    import leads_standard as LS
    res = LS.month_leads(folder, d0.isoformat(), d1.isoformat())
    out = defaultdict(int)
    calls = res["calls"]
    for d in calls.loc[~calls["camp"].map(is_excluded), "day"]:
        out[d] += 1
    g = res["forms"]
    for d in g.loc[(g["src"] == "google") & ~g["camp"].map(is_excluded), "day"]:
        out[d] += 1
    return out


def weekend_weight(series, days):
    """→ (вес выходных, среднее по будню, среднее по выходному, вес сб, вес вс); None, если среднее будней = 0."""
    wd = [series.get(d, 0.0) for d in days if d.weekday() < 5]
    we = [series.get(d, 0.0) for d in days if d.weekday() >= 5]
    sa = [series.get(d, 0.0) for d in days if d.weekday() == 5]
    su = [series.get(d, 0.0) for d in days if d.weekday() == 6]
    base = sum(wd) / len(wd) if wd else 0.0
    if base <= 0 or not we:
        return None, base, 0.0, 0.0, 0.0
    mean_we = sum(we) / len(we)
    return (mean_we / base, base, mean_we,
            (sum(sa) / len(sa) / base) if sa else 0.0, (sum(su) / len(su) / base) if su else 0.0)


def day_w(w, d):
    return w if d.weekday() >= 5 else 1.0


def wsum(w, d0, d1):
    s, d = 0.0, d0
    while d <= d1:
        s += day_w(w, d)
        d += timedelta(days=1)
    return s


def pct(a, b):
    return f"{(a / b - 1) * 100:+.0f}%" if b else "н/д"


def build_parser():
    ap = argparse.ArgumentParser(description="Темп к плану месяца с поправкой на день недели (только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--month", help="ГГГГ-ММ, по умолчанию месяц --today")
    ap.add_argument("--today", help="ГГГГ-ММ-ДД, по умолчанию сегодня (Варшава)")
    ap.add_argument("--weeks", type=int, default=6, help="окно весов, полных недель (по умолчанию 6)")
    ap.add_argument("--weekend-weight", type=float, help="ручной вес выходных (сб и вс), для расхода и заявок; по умолчанию из истории")
    return ap


def main():
    run(build_parser().parse_args())


def run(a):
    """Считает, печатает таблицу, пишет CSV; возвращает dict с числами (его же берёт pace_vs_plan_sheet.py)."""
    from zoneinfo import ZoneInfo
    today = date.fromisoformat(a.today) if a.today else datetime.now(ZoneInfo("Europe/Warsaw")).date()
    if a.month:
        y, m = map(int, a.month.split("-"))
    else:
        y, m = today.year, today.month
    first = date(y, m, 1)
    dim = calendar.monthrange(y, m)[1]
    last = date(y, m, dim)
    if today < first:
        raise SystemExit("Месяц ещё не начался")
    if today > last:
        today = last + timedelta(days=1)   # месяц закончен: все дни завершены
    done_end = today - timedelta(days=1)    # последний завершённый день
    folder, cid = a.client_folder, a.customer_id.replace("-", "")
    warns = []

    cfg = load_cfg(folder)
    if cfg["plan"].get("projects"):
        warns.append("в analysis_config.yaml plan.projects несколько проектов: скрипт считает один план (plan.client_name) "
                     "против расхода всего аккаунта")

    from google.ads.googleads.client import GoogleAdsClient
    from gads_stats import GOOGLE_ADS_YAML
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    from campaign_analyzer.sources import read_plan
    plan = read_plan(cfg, pd.Timestamp(first))
    plan_b, plan_l, plan_cpa = plan["budget"], plan["leads"], plan["cpa"]
    plan_src = f"Цели2 Адвайта, лист «{plan['tab']}», строка «{cfg['plan']['client_name']}»"

    w_end = min(done_end, today - timedelta(days=1))
    w_start = w_end - timedelta(days=7 * a.weeks - 1)
    win = [w_start + timedelta(days=i) for i in range(7 * a.weeks)]
    d0 = min(first, w_start)
    spend = daily_cost(ga, cid, d0, w_end)
    leads = daily_leads(folder, d0, w_end)

    if a.weeks < 4:
        warns.append(f"окно веса {a.weeks} нед. < 4: вес ненадёжен")
    if not any(spend.get(d, 0) > 0 for d in win):
        warns.append("в окне веса нет расхода: вес не посчитать")

    ws, base_s, we_s, sa_s, su_s = weekend_weight(spend, win)
    wl, base_l, we_l, sa_l, su_l = weekend_weight(leads, win)
    if ws is None or wl is None:
        print("\n".join("ПРЕДУПРЕЖДЕНИЕ: " + x for x in warns))
        raise SystemExit("Вес выходных не посчитан (среднее будней = 0), таблицу не строю")
    if a.weekend_weight is not None:
        ws = wl = a.weekend_weight
    n_wd = len([d for d in win if d.weekday() < 5])
    if sum(leads.get(d, 0) for d in win) < 100:
        warns.append(f"заявок в окне веса {sum(leads.get(d, 0) for d in win)} (< 100): вес выходных по заявкам шумный (малая выборка)")

    # факт месяца: завершённые дни
    spent = sum(spend.get(first + timedelta(days=i), 0.0) for i in range((done_end - first).days + 1)) if done_end >= first else 0.0
    got = sum(leads.get(first + timedelta(days=i), 0) for i in range((done_end - first).days + 1)) if done_end >= first else 0
    elapsed = max((done_end - first).days + 1, 0)
    if elapsed == 0:
        raise SystemExit("В месяце нет завершённых дней, считать нечего")
    cpa_fact = spent / got if got else 0.0

    # взвешенные дни
    Ws_done, Ws_left = wsum(ws, first, done_end), (wsum(ws, today, last) if today <= last else 0.0)
    Wl_done, Wl_left = wsum(wl, first, done_end), (wsum(wl, today, last) if today <= last else 0.0)
    Ws_tot, Wl_tot = Ws_done + Ws_left, Wl_done + Wl_left
    remaining = (last - today).days + 1 if today <= last else 0

    exp_s = plan_b * Ws_done / Ws_tot
    exp_l = plan_l * Wl_done / Wl_tot
    cal_s = plan_b * elapsed / dim
    cal_l = plan_l * elapsed / dim
    fc_s = spent / Ws_done * Ws_tot if Ws_done else 0.0
    fc_l = got / Wl_done * Wl_tot if Wl_done else 0.0
    fc_cpa = fc_s / fc_l if fc_l else 0.0
    need_b = plan_b - spent
    need_l = plan_l - got

    per = f"{first}..{done_end}"
    src_cost = "Google Ads API, segments.date, расход аккаунта без кампаний yt_* (YouTube - отдельный проект)"
    src_leads = "leads_standard: звонки Ringostat (Google Ads) + формы Supabase (Google), без кампаний yt_*"
    wl_note = f"вес выходных: окно {w_start}..{w_end} ({a.weeks} нед., {n_wd} будней, {len(win) - n_wd} выходных)"
    rows = []

    def add(name, val, src):
        rows.append((name, val, src))

    add("План месяца: бюджет", f"{plan_b:.0f}", plan_src)
    add("План месяца: заявки", f"{plan_l:.0f}", plan_src)
    add("План месяца: цена заявки", f"{plan_cpa:.0f}", plan_src)
    add("Факт на дату: расход", f"{spent:.0f}", f"{src_cost}; завершённые дни {per} ({elapsed} дн.), сегодня не входит")
    add("Факт на дату: заявки", f"{got}", f"{src_leads}; {per}")
    add("Факт на дату: цена заявки", f"{cpa_fact:.0f}" if got else "н/д", f"расход / заявки, {per}")
    add("Взвешенные будни по расходу: прошло / осталось / всего", f"{Ws_done:.2f} / {Ws_left:.2f} / {Ws_tot:.2f}",
        f"сумма весов расхода дней месяца (будни 1, выходные = вес выходных); прошло {per}, осталось {today}..{last} ({remaining} дн., сегодня как полный); {wl_note}")
    add("Взвешенные будни по заявкам: прошло / осталось / всего", f"{Wl_done:.2f} / {Wl_left:.2f} / {Wl_tot:.2f}",
        f"сумма весов заявок; тот же срез; {wl_note}")
    add("План на дату по расходу (с весами)", f"{exp_s:.0f}", f"план бюджета × {Ws_done:.2f} / {Ws_tot:.2f}")
    add("Расход: отставание(-)/опережение(+) с весами", f"{spent - exp_s:+.0f} ({pct(spent, exp_s)})",
        f"факт {spent:.0f} против {exp_s:.0f}; знаменатель — план на дату с весами")
    add("План на дату по заявкам (с весами)", f"{exp_l:.1f}", f"план заявок × {Wl_done:.2f} / {Wl_tot:.2f}")
    add("Заявки: отставание(-)/опережение(+) с весами", f"{got - exp_l:+.1f} ({pct(got, exp_l)})",
        f"факт {got} против {exp_l:.1f}; знаменатель — план на дату с весами")
    add("Для сравнения, по календарным дням: план расхода на дату", f"{cal_s:.0f}", f"план бюджета × {elapsed}/{dim}, как state_digest")
    add("Для сравнения: расход отставание/опережение", f"{spent - cal_s:+.0f} ({pct(spent, cal_s)})", f"факт {spent:.0f} против {cal_s:.0f}")
    add("Для сравнения: план заявок на дату", f"{cal_l:.1f}", f"план заявок × {elapsed}/{dim}")
    add("Для сравнения: заявки отставание/опережение", f"{got - cal_l:+.1f} ({pct(got, cal_l)})", f"факт {got} против {cal_l:.1f}")
    add("Прогноз закрытия: расход", f"{fc_s:.0f}", f"факт {spent:.0f} / {Ws_done:.2f} × {Ws_tot:.2f} (текущий темп на взвешенный будень); план {plan_b:.0f}")
    add("Прогноз закрытия: заявки", f"{fc_l:.0f}", f"факт {got} / {Wl_done:.2f} × {Wl_tot:.2f}; план {plan_l:.0f}")
    add("Прогноз закрытия: цена заявки", f"{fc_cpa:.0f}" if fc_l else "н/д", f"прогноз расхода / прогноз заявок; план {plan_cpa:.0f}")
    need_day_b = need_day_l = allowed = None
    if remaining and Ws_left:
        need_day_b = need_b / Ws_left
    if remaining and Wl_left and need_l > 0 and need_b > 0 and Ws_left:
        need_day_l = need_l / Wl_left
        allowed = need_day_b / need_day_l
    if remaining and Ws_left:
        add("Нужен расход в будний день до конца месяца", f"{need_b / Ws_left:.0f}",
            f"(план бюджета {plan_b:.0f} - факт {spent:.0f}) / {Ws_left:.2f} взвеш. будней; тот же знаменатель {today}..{last}")
    if remaining and Wl_left:
        if need_l > 0 and need_b > 0:
            add("Нужно заявок в будний день", f"{need_l / Wl_left:.2f}", f"({plan_l:.0f} - {got}) / {Wl_left:.2f} взвеш. будней по заявкам")
            add("Допустимая цена заявки в будний день на остаток",
                f"{(need_b / Ws_left) / (need_l / Wl_left):.0f}",
                f"(нужный расход в будний день {need_b / Ws_left:.0f}) / (нужных заявок в будний день {need_l / Wl_left:.2f}); "
                f"без весов (state_digest): {need_b / need_l:.0f}")
        elif need_l <= 0:
            add("Допустимая цена заявки в будний день на остаток", "план по заявкам выполнен", f"заявок {got} из {plan_l:.0f}")
    elif not remaining:
        add("Остаток месяца", "месяц завершён", "")

    # вывод
    print(f"=== Темп к плану с поправкой на день недели: {folder}, {first:%Y-%m}, на {today} (чтение) ===")
    ovr = " (ручное --weekend-weight)" if a.weekend_weight is not None else ""
    print(f"Вес выходных по расходу: {ws:.2f}{ovr} (среднее выходного дня {we_s:.0f} / будничного {base_s:.0f}; "
          f"справочно сб {sa_s:.2f}, вс {su_s:.2f}; окно {w_start}..{w_end}); будни = 1.0")
    print(f"Вес выходных по заявкам: {wl:.2f}{ovr} (среднее выходного дня {we_l:.2f} / будничного {base_l:.2f}; "
          f"справочно сб {sa_l:.2f}, вс {su_l:.2f}; то же окно)")
    print()
    wdt = max(len(r[0]) for r in rows)
    for n, v, s in rows:
        print(f"{n:{wdt}} | {v:>22} | {s}")
    print()
    for x in warns:
        print("ПРЕДУПРЕЖДЕНИЕ: " + x)
    if not warns:
        print("Предупреждений нет.")

    out = client_stats_dir(folder) / f"pace_vs_plan_{first:%Y-%m}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["показатель", "значение", "источник и срез"])
        wr.writerows(rows)
        wr.writerow([])
        wr.writerow(["вес выходных, расход", f"{ws:.3f}", f"справочно сб {sa_s:.3f}, вс {su_s:.3f}"])
        wr.writerow(["вес выходных, заявки", f"{wl:.3f}", f"справочно сб {sa_l:.3f}, вс {su_l:.3f}"])
        wr.writerow(["дата расчёта", str(today)])
        for x in warns:
            wr.writerow(["предупреждение", x])
    print(f"CSV: {out}")
    return dict(folder=folder, first=first, last=last, dim=dim, today=today, done_end=done_end, elapsed=elapsed,
                plan_b=plan_b, plan_l=plan_l, plan_cpa=plan_cpa, plan_src=plan_src, spent=spent, got=got, cpa_fact=cpa_fact,
                exp_s=exp_s, exp_l=exp_l, cal_s=cal_s, cal_l=cal_l, fc_s=fc_s, fc_l=fc_l, fc_cpa=fc_cpa,
                need_day_b=need_day_b, need_day_l=need_day_l, allowed=allowed, ws=ws, wl=wl,
                sa_s=sa_s, su_s=su_s, sa_l=sa_l, su_l=su_l, Ws_tot=Ws_tot, Wl_tot=Wl_tot,
                spend=spend, leads=leads, warns=warns, w_start=w_start, w_end=w_end, weeks=a.weeks,
                src_cost=src_cost, src_leads=src_leads, per=per, rows=rows, wl_note=wl_note)


if __name__ == "__main__":
    main()
