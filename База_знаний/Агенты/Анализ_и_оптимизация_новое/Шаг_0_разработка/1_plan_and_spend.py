#!/usr/bin/env python
# coding: utf-8
"""Шаг 0, скрипт 1 «план и факт» — ТОЛЬКО ЧТЕНИЕ (в кабинет, таблицу и вики ничего не пишет).

Что делает: читает план месяца из «Цели2» (бюджет, заявки, плановая цена заявки) и расход Google Ads по дням
в разрезе кампаний. Факт — только завершённые дни: до вчера включительно. Кампании yt_* исключены.
Ничего не считает, кроме суммы расхода за месяц для сводки. Прогноз, веса, отставание — скрипт 4.

Окно расхода: с более раннего из двух — начала месяца и (вчера - 6 недель + 1 день).

Выход (в --out-dir, ничего не пишет в Статистика/):
  plan.csv        — одна строка: клиент, месяц, бюджет, заявки, плановая цена заявки, источник, пометки.
  spend_daily.csv — день, кампания, расход (в валюте кабинета).
Пробелы (нет плана, нет столбца) — остановка с сообщением, без подстановок.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python ../База_знаний/Агенты/Анализ_и_оптимизация_новое/Шаг_0_разработка/1_plan_and_spend.py --customer-id 7552781705 --client-folder ProfiMet --today 2026-11-20 \
        --out-dir "../Клиенты/ProfiMet/Работы/2026-11-20_шаг0_прогон"
"""
import argparse
import calendar
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "Скрипты"))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd  # noqa: E402
import pace_vs_plan as P  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Шаг 0, скрипт 1: план и расход по дням (только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--today", help="ГГГГ-ММ-ДД, по умолчанию сегодня (Варшава)")
    ap.add_argument("--weeks", type=int, default=6, help="глубина истории расхода, недель (по умолчанию 6)")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    from zoneinfo import ZoneInfo
    today = date.fromisoformat(a.today) if a.today else datetime.now(ZoneInfo("Europe/Warsaw")).date()
    first = date(today.year, today.month, 1)
    done_end = today - timedelta(days=1)
    if done_end < first:
        raise SystemExit("В месяце нет завершённых дней, считать нечего")
    d0 = min(first, done_end - timedelta(days=7 * a.weeks - 1))
    cid = a.customer_id.replace("-", "")
    notes = []

    cfg = P.load_cfg(a.client_folder)
    if cfg["plan"].get("projects"):
        notes.append("в plan.projects несколько проектов: взят один план (plan.client_name)")
    from campaign_analyzer.sources import read_plan
    plan = read_plan(cfg, pd.Timestamp(first))
    for k in ("budget", "leads", "cpa"):
        if plan.get(k) in (None, 0) or pd.isna(plan.get(k)):
            raise SystemExit(f"Пробел: в плане нет значения «{k}» ({plan})")

    from google.ads.googleads.client import GoogleAdsClient
    from gads_stats import GOOGLE_ADS_YAML
    ga = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).get_service("GoogleAdsService")
    q = ("SELECT segments.date, campaign.name, metrics.cost_micros, customer.currency_code FROM campaign "
         f"WHERE segments.date BETWEEN '{d0}' AND '{done_end}'")
    rows, cur = {}, set()
    for r in ga.search(customer_id=cid, query=q):
        if P.is_excluded(r.campaign.name):
            continue
        cur.add(r.customer.currency_code)
        key = (r.segments.date, r.campaign.name)
        rows[key] = rows.get(key, 0.0) + r.metrics.cost_micros / 1e6
    currency = ",".join(sorted(cur)) or "н/д"

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "spend_daily.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["day", "campaign", "cost", "currency"])
        for (d, c), v in sorted(rows.items()):
            w.writerow([d, c, round(v, 2), currency])
    src = f"Цели2 Адвайта, лист «{plan['tab']}», строка «{cfg['plan']['client_name']}»"
    with open(out / "plan.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["client", "month", "plan_budget", "plan_leads", "plan_cpa", "currency", "source", "notes"])
        w.writerow([a.client_folder, first.strftime("%Y-%m"), plan["budget"], plan["leads"], plan["cpa"],
                    currency, src, "; ".join(notes)])

    spent = sum(v for (d, _), v in rows.items() if d >= first.isoformat())
    days = (done_end - first).days + 1
    dim = calendar.monthrange(first.year, first.month)[1]
    print(f"Клиент {a.client_folder}, {first:%Y-%m}, сегодня {today}, факт по {done_end} включительно ({days} из {dim} дн.)")
    print(f"План: бюджет {plan['budget']}, заявок {plan['leads']}, цена заявки {plan['cpa']} ({currency}); {src}")
    print(f"Расход с {first} по {done_end}: {spent:.2f} {currency}; окно в файле: {d0}..{done_end}, строк {len(rows)}")
    for n in notes:
        print("ПРИМЕЧАНИЕ:", n)
    print(f"Файлы: {out / 'plan.csv'}, {out / 'spend_daily.csv'}")


if __name__ == "__main__":
    main()


