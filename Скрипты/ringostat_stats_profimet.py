#!/usr/bin/env python
# coding: utf-8
"""Диагностический снапшот звонков Ringostat ProfiMet — для сверки со звонками,
доходящими до конверсий Google Ads (см. gads_calls_stats_profimet.py и
Клиенты/ProfiMet/Решения.md, запись про сверку Ringostat vs Google Ads calls).

НЕ прод-скрипт: не трогает и не заменяет adwhite/func/ringostat_profimet2 в
E:/PythonProjects/RedBird/google-cloud-jobs — это read-only копия для разовой
диагностики в этой вики, по образцу остальных local-скриптов сбора статистики
(см. Скрипты/README.md, раздел "Два агентства").

Отличие от прод-версии ringostat_profimet2 (которая агрегирует до уровня
"день x источник", теряя кампанию): здесь campaign/pool сохраняются в каждой
строке результата — без этого нельзя сопоставить конкретно Performance Max со
звонками, попадающими в Google Ads. Методология уникальности звонков (единое
множество caller по ВСЕМ источникам сразу, история считается с HISTORY_FROM,
но в отчёт попадают только звонки от --date-from) скопирована 1:1 из
ringostat_profimet2/main.py, чтобы числа совпадали с продовой таблицей
adwhite.ringostat_calls_profimet2.

Категоризация источника (Google Ads / Google SEO / Facebook / No Source) —
тоже 1:1 из прод-скрипта. У Performance Max/Demand Gen Ringostat не передаёт
корректный utm_medium=cpc (вместо него там имя пула номеров) — категория
'Google Ads' ловится по utm_source (google/dspl/kms/performance_max),
без проверки канала, см. комментарий в самой функции.

ВАЖНО (проверено эмпирически 2026-09-21, см. Клиенты/ProfiMet/Решения.md):
кампания в utm_campaign доступна только для звонков ДИНАМИЧЕСКОГО пула
(Google CPC_dyn — переход на сайт с UTM). У звонков статического пула
(Google CPC calls from ads — звонок прямо по номеру в объявлении) в Ringostat
жёстко зашита метка-заглушка utm_campaign=calls_from_ads, а не реальный
campaign_id — Ringostat физически не знает, из какой кампании был звонок по
номеру в объявлении. Эти звонки в разбивке по кампаниям помечаются отдельной
меткой, не путать с "кампания не указана" по other причинам.

Использование:
    python ringostat_stats_profimet.py --date-from 2026-08-01
    python ringostat_stats_profimet.py --date-from 2026-08-01 --date-to 2026-09-20
"""
import argparse
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from _config import client_stats_dir

AUTH_KEY = "w9q9HIT873Vvvg0VB1eQjkTliKnFPHhp"  # тот же аккаунт, что в проде (ringostat_profimet2/main.py)
HISTORY_FROM = "2025-08-01 00:00:00"  # начало прошлого сезона — нужно для правильной уникальности, см. докстринг
STATIC_POOL_NAME = "Google CPC calls from ads"
STATIC_CAMPAIGN_LABEL = "(статический канал — кампания не определяется)"


def fetch_ringostat_calls(date_to_str):
    url = "https://api.ringostat.net/calls/list"
    params = {
        "export_type": "json",
        "from": HISTORY_FROM,
        "to": date_to_str,
        "fields": "calldate,caller,utm_source,utm_medium,utm_campaign,pool_name",
    }
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Auth-key": AUTH_KEY,
    }
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["calldate"] = pd.to_datetime(df["calldate"], utc=True)
    for col in ("utm_source", "utm_medium", "utm_campaign", "pool_name"):
        df[col] = df[col].fillna("")
    return df


def categorize_source(row):
    """1:1 логика ringostat_profimet2/main.py — порядок условий важен."""
    s = str(row["utm_source"]).lower()
    m = str(row["utm_medium"]).lower()

    if "карты" in s:
        return "No Source"
    if "google" in s and "organic" in m:
        return "No Source"
    if "seomocna" in s:
        return "Google SEO"
    if "facebook" in s and "cpc" in m:
        return "Facebook"
    # PMax/Demand Gen не передают utm_medium=cpc корректно — ловим по source
    if any(k in s for k in ["google", "dspl", "kms", "performance_max"]):
        return "Google Ads"
    return "Other"


def compute_unique_calls_by_campaign(df, date_from):
    """Единое множество caller по всем источникам сразу (методология
    ringostat_profimet2) + сохранение campaign/pool на каждой уникальной строке."""
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["category"] = df.apply(categorize_source, axis=1)
    df = df[df["category"].isin(["Google Ads", "Google SEO", "Facebook", "No Source"])]
    df["date_only"] = df["calldate"].dt.date
    df_sorted = df.sort_values(["date_only", "calldate"])

    date_from_d = pd.Timestamp(date_from).date()
    all_unique_callers = set()
    rows = []

    for date_, day_data in df_sorted.groupby("date_only", sort=True):
        for _, r in day_data.sort_values("calldate").iterrows():
            caller = r["caller"]
            if caller in all_unique_callers:
                continue
            all_unique_callers.add(caller)
            if date_ < date_from_d:
                continue
            campaign_label = STATIC_CAMPAIGN_LABEL if r["pool_name"] == STATIC_POOL_NAME else r["utm_campaign"]
            rows.append({
                "Date": date_.strftime("%Y-%m-%d"),
                "Category": r["category"],
                "Pool_name": r["pool_name"],
                "Campaign_raw": r["utm_campaign"],
                "Campaign": campaign_label or "(пусто)",
                "Caller": caller,
            })

    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD — с какой даты показывать строки в отчёте (не влияет на подсчёт уникальности, для этого всегда берётся вся история с HISTORY_FROM)")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_to_str = datetime.strptime(date_to, "%Y-%m-%d").strftime("%Y-%m-%d 23:59:59")

    print(f"Запрос звонков Ringostat: {HISTORY_FROM} -> {date_to_str} (история нужна для корректной уникальности)")
    raw = fetch_ringostat_calls(date_to_str)
    print(f"Получено сырых записей: {len(raw)}")

    result = compute_unique_calls_by_campaign(raw, args.date_from)
    print(f"Уникальных звонков в отчётном периоде ({args.date_from} -> {date_to}): {len(result)}")

    out_dir = client_stats_dir("ProfiMet")
    out_path = out_dir / f"ringostat_calls_by_campaign_{args.date_from}_to_{date_to}.csv"
    result.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path}")

    if not result.empty:
        gads = result[result["Category"] == "Google Ads"]
        print("\n=== Google Ads — уникальные звонки по кампаниям ===")
        print(gads["Campaign"].value_counts().to_string())
        print(f"\nИтого Google Ads звонков: {len(gads)} (из них по статическому каналу без кампании: {(gads['Pool_name'] == STATIC_POOL_NAME).sum()})")


if __name__ == "__main__":
    main()
