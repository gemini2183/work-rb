#!/usr/bin/env python
# coding: utf-8
"""Сверка: сколько звонков из журнала Ringostat доходит до GA4 (событие Ringostat_calls).

Только сбор и подсчёт, без выводов. Результат — по каждому звонку "найдено ли событие в GA4"
(CSV в Клиенты/ProfiMet/Статистика/, без номеров звонящих) и сводка в консоли: по источнику,
по кампании (id из utm_campaign), по статусу звонка, отдельно уникальные (`unique_call`=1).

Как сопоставляется звонок с событием. Прямой связи (id звонка в событии GA4) нет, поэтому
сопоставление по времени: событие Ringostat_calls приходит в GA4 в минуту окончания звонка
(время начала + duration из журнала Ringostat; эмпирическое наблюдение на ProfiMet 2026-10-06,
не документация Ringostat). Звонок и событие считаются парой, если минута события отличается от
времени окончания не больше чем на --tolerance минут (по умолчанию 2), пара жадная, один к одному.
Сопоставление приблизительное: оно говорит "событие вокруг этого времени есть", а не "это то
самое событие". Для последних дней периода данные GA4 могут дозревать — берите --date-to минимум
на 2 дня раньше сегодняшнего.

Что именно считается "динамикой Google Ads": категория Ringostat "Google Ads" (см.
ringostat_stats_profimet.categorize_source), входящие звонки, пул НЕ "Google CPC calls from ads"
(статический пул: кампания не определяется, в GA4 идёт отдельным событием Ringostat_calls_static).

Что известно по результатам первого использования (ProfiMet, 2026-10-06): ~1/3 уникальных
динамических звонков не доходит в GA4, потому что у посетителя нет GA client id (нет согласия на
cookie / блокировщик) — подтверждено поддержкой Ringostat. См.
База_знаний/Инструменты/Ringostat-передача-звонков-в-GA4-события-и-типы.md, разделы 8–13.

Доступ к GA4: Data API, ключ сервисного аккаунта ga4-analytics. По умолчанию берётся из прод-репозитория
(путь ниже), можно задать переменной окружения GA4_KEY_PATH. Ключ в вики не копируется.
Admin API выключен — настройки key events этим скриптом не прочитать.

Использование:
    python ringostat_ga4_delivery_profimet.py --date-from 2026-09-22 --date-to 2026-10-05
"""
import argparse
import os
import re
from datetime import date, timedelta

import pandas as pd
import requests
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression,
                                                FilterExpressionList, Metric, RunReportRequest)
from google.oauth2 import service_account

from _config import client_stats_dir
from ringostat_stats_profimet import AUTH_KEY, STATIC_POOL_NAME, categorize_source

GA4_PROPERTY = "properties/349001266"  # mocnaszklarnia.pl - GA4
GA4_KEY_PATH = os.environ.get(
    "GA4_KEY_PATH",
    r"E:\PythonProjects\RedBird\google-cloud-jobs\adwhite\func\ga4_profimet\redbird-196813-ga4.json",
)
TIMEZONE = "Europe/Warsaw"
FIELDS = "calldate,caller,disposition,billsec,duration,call_type,uniqueid,utm_source,utm_medium,utm_campaign,pool_name,unique_call"


def fetch_ringostat(date_from, date_to):
    r = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": f"{date_from} 00:00:00", "to": f"{date_to} 23:59:59", "fields": FIELDS},
        headers={"Content-Type": "application/json; charset=utf-8", "Auth-key": AUTH_KEY},
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return df
    for c in ["utm_source", "utm_medium", "utm_campaign", "pool_name", "disposition", "call_type"]:
        df[c] = df[c].fillna("")
    df["calldate"] = pd.to_datetime(df["calldate"], utc=True)
    df["start"] = df["calldate"].dt.tz_convert(TIMEZONE).dt.tz_localize(None)
    df["end"] = df["start"] + pd.to_timedelta(df["duration"], unit="s")
    df["category"] = df.apply(categorize_source, axis=1)
    df["unique_call"] = df["unique_call"].astype(int)
    df["campaign_id"] = df["utm_campaign"].str.extract(r"(\d{8,})", expand=False)
    return df


def ga4_client():
    creds = service_account.Credentials.from_service_account_file(
        GA4_KEY_PATH, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    return BetaAnalyticsDataClient(credentials=creds)


def ga4_events(client, event_name, date_from, date_to, dims):
    ev = FilterExpression(filter=Filter(field_name="eventName",
                                        string_filter=Filter.StringFilter(value=event_name)))
    rows, offset = [], 0
    while True:
        rep = client.run_report(RunReportRequest(
            property=GA4_PROPERTY,
            date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name="eventCount"), Metric(name="conversions")],
            dimension_filter=ev, limit=100000, offset=offset))
        rows += [[v.value for v in r.dimension_values] + [float(v.value) for v in r.metric_values] for r in rep.rows]
        offset += 100000
        if offset >= rep.row_count:
            break
    return pd.DataFrame(rows, columns=dims + ["eventCount", "conversions"])


def match_calls_to_events(calls, events, tolerance_min):
    """Жадное сопоставление по времени окончания звонка. Возвращает calls с колонками found,
    ga4_campaign, ga4_conversions. events — по строке на минуту, eventCount разворачивается."""
    ev = events.copy()
    ev["t"] = pd.to_datetime(ev["dateHourMinute"], format="%Y%m%d%H%M")
    ev = ev.loc[ev.index.repeat(ev["eventCount"].astype(int))].reset_index(drop=True)
    ev["used"] = False
    calls = calls.sort_values("end").copy()
    found, camp, conv = [], [], []
    tol = pd.Timedelta(minutes=tolerance_min)
    for _, c in calls.iterrows():
        cand = ev[(~ev["used"]) & ((ev["t"] - c["end"]).abs() <= tol)]
        if len(cand):
            i = (cand["t"] - c["end"]).abs().idxmin()
            ev.loc[i, "used"] = True
            found.append(True)
            camp.append(ev.loc[i, "sessionCampaignName"])
            conv.append(ev.loc[i, "conversions"])
        else:
            found.append(False)
            camp.append(None)
            conv.append(None)
    calls["found"], calls["ga4_campaign"], calls["ga4_conversions"] = found, camp, conv
    return calls, int((~ev["used"]).sum())


def share(df):
    n = len(df)
    return f"{int(df['found'].sum())} из {n} ({df['found'].mean():.0%})" if n else "нет звонков"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию позавчера (последние дни в GA4 дозревают)")
    ap.add_argument("--tolerance", type=float, default=2.0, help="допуск по времени окончания звонка, минут")
    args = ap.parse_args()
    date_to = args.date_to or str(date.today() - timedelta(2))

    print(f"Период {args.date_from} — {date_to} (Europe/Warsaw), допуск {args.tolerance} мин")
    calls = fetch_ringostat(args.date_from, date_to)
    calls = calls[(calls["call_type"] == "in") & (calls["category"] != "Other")]
    print(f"Входящих звонков Ringostat (Google Ads / SEO / Facebook / No Source): {len(calls)}")

    client = ga4_client()
    events = ga4_events(client, "Ringostat_calls", args.date_from, date_to, ["dateHourMinute", "sessionCampaignName"])
    print(f"Событий Ringostat_calls в GA4: {int(events['eventCount'].sum())}")
    matched, unmatched_events = match_calls_to_events(calls, events, args.tolerance)
    print(f"Событий GA4, не сопоставленных ни с одним звонком: {unmatched_events}")

    out = matched.copy()
    out["time"] = out["start"].dt.strftime("%Y-%m-%d %H:%M")
    cols = ["time", "uniqueid", "category", "pool_name", "campaign_id", "disposition", "duration",
            "unique_call", "found", "ga4_campaign", "ga4_conversions"]
    path = client_stats_dir("ProfiMet") / f"ringostat_ga4_delivery_{args.date_from}_to_{date_to}.csv"
    out[cols].to_csv(path, index=False, encoding="utf-8")
    print(f"Сохранено: {path} (по звонку, без номеров звонящих)")

    dyn = matched[(matched["category"] == "Google Ads") & (matched["pool_name"] != STATIC_POOL_NAME)]
    stat = matched[(matched["category"] == "Google Ads") & (matched["pool_name"] == STATIC_POOL_NAME)]
    print("\n=== Дошло до GA4 (событие найдено рядом со временем окончания звонка) ===")
    print(f"Google Ads, динамика, все звонки: {share(dyn)}")
    print(f"Google Ads, динамика, уникальные (unique_call=1): {share(dyn[dyn['unique_call'] == 1])}")
    print(f"Google Ads, статический пул (звонок по номеру в объявлении): {share(stat)} — в GA4 идёт другим событием")
    print(f"Facebook: {share(matched[matched['category'] == 'Facebook'])}")
    print(f"Google SEO: {share(matched[matched['category'] == 'Google SEO'])}")

    print("\n--- Google Ads динамика, по кампании (id из utm_campaign): уникальные / всего, найдено ---")
    for cid, g in dyn.groupby(dyn["campaign_id"].fillna("(нет id)")):
        u = g[g["unique_call"] == 1]
        print(f"  {cid}: уникальных {len(u)}, найдено {int(u['found'].sum())}; всего {len(g)}, найдено {int(g['found'].sum())}")
    print("\n--- Google Ads динамика, по статусу звонка: найдено / всего ---")
    print(dyn.groupby("disposition")["found"].agg(["sum", "count"]).to_string())

    # независимая сверка: событие Unique_Calls (аудитория-триггер с условием call_unique=1)
    uc = ga4_events(client, "Unique_Calls", args.date_from, date_to, ["sessionSourceMedium"])
    n_uc = int(uc[uc["sessionSourceMedium"] == "google / cpc"]["eventCount"].sum()) if len(uc) else 0
    print(f"\nКонтроль: событий Unique_Calls в GA4 (google / cpc): {n_uc}; "
          f"уникальных динамических звонков Google Ads в Ringostat: {int((dyn['unique_call'] == 1).sum())}")


if __name__ == "__main__":
    main()
