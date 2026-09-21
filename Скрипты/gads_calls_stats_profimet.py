#!/usr/bin/env python
# coding: utf-8
"""Диагностический снапшот конверсий-звонков Google Ads ProfiMet по кампаниям —
для сверки со звонками Ringostat (см. ringostat_stats_profimet.py и
Клиенты/ProfiMet/Решения.md, запись про сверку Ringostat vs Google Ads calls).

НЕ прод-скрипт: не трогает adwhite/func/gads_profimet_db в
E:/PythonProjects/RedBird/google-cloud-jobs (тот тянет только сумму по
аккаунту без кампаний/типа конверсии — недостаточно для этой задачи).

customer_id захардкожен по образцу прод-скрипта gads_profimet_db/main.py —
ProfiMet не заведён строкой в общей таблице Google_Ads_API.

Оставляет только conversion actions, которые физически являются звонком
(проверено 2026-09-21 через прямой запрос conversion_action — см. докстринг
ниже), а не любую конверсию аккаунта:
  - "mocnaszklarnia.pl - GA4 (web) Ringostat_calls" — GA4-событие от Ringostat
    (то, что клиент называет "цель Ringostat calls", импортируется в Ads из GA4)
  - "mocnaszklarnia.pl - GA4 (web) Ringostat_calls_static" — тот же механизм,
    видимо под статический канал; на практике за 2026-08-01+ конверсий не даёт
  - "Звонки по объявлениям" — встроенный тип Google Ads AD_CALL (звонок по
    номеру в самом объявлении), независимый от Ringostat механизм замера
  - "call_static_server" — UPLOAD_CLICKS/CONTACT, вероятно офлайн-импорт по
    клику; на практике за 2026-08-01+ конверсий тоже не даёт

Использование:
    python gads_calls_stats_profimet.py --date-from 2026-08-01
    python gads_calls_stats_profimet.py --date-from 2026-08-01 --date-to 2026-09-20 --by-week
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

CUSTOMER_ID = "7552781705"  # ProfiMet, см. adwhite/func/gads_profimet_db/main.py

CALL_CONVERSION_ACTIONS = {
    "mocnaszklarnia.pl - GA4 (web) Ringostat_calls",
    "mocnaszklarnia.pl - GA4 (web) Ringostat_calls_static",
    "Звонки по объявлениям",
    "call_static_server",
}

_ENUM_CLIENT = None


def _enum_name(enum_type_name, field_name, value):
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def fetch_call_conversions_by_campaign(ga_service, date_from, date_to):
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.advertising_channel_type,
            segments.date,
            segments.conversion_action_name,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
            AND metrics.conversions > 0
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=CUSTOMER_ID, query=query):
        for row in batch.results:
            action = row.segments.conversion_action_name
            if action not in CALL_CONVERSION_ACTIONS:
                continue
            channel = _enum_name(
                "AdvertisingChannelTypeEnum", "AdvertisingChannelType",
                row.campaign.advertising_channel_type,
            )
            rows.append({
                "Date": row.segments.date,
                "Campaign_id": row.campaign.id,
                "Campaign": row.campaign.name,
                "Channel_type": channel,
                "Conversion_action": action,
                "Conversions": row.metrics.conversions,
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--by-week", action="store_true", help="Дополнительно показать разбивку по неделям x кампания")
    args = ap.parse_args()

    date_to = args.date_to or str(date.today() - timedelta(1))

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"ProfiMet (customer_id {CUSTOMER_ID}) | период {args.date_from} -> {date_to}")
    df = fetch_call_conversions_by_campaign(ga_service, args.date_from, date_to)

    out_dir = client_stats_dir("ProfiMet")
    out_path = out_dir / f"gads_calls_by_campaign_{args.date_from}_to_{date_to}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} строк)")

    if df.empty:
        print("Нет конверсий-звонков за период")
        return

    print("\n=== Итого по кампании x тип конверсии ===")
    pivot = df.groupby(["Campaign", "Channel_type", "Conversion_action"])["Conversions"].sum().unstack(fill_value=0)
    print(pivot.to_string())

    print("\n=== Итого по кампании (все типы звонков суммой) ===")
    totals = df.groupby(["Campaign", "Channel_type"])["Conversions"].sum().sort_values(ascending=False)
    print(totals.to_string())

    if args.by_week:
        df["Date"] = pd.to_datetime(df["Date"])
        df["Week"] = df["Date"].dt.to_period("W-MON")
        print("\n=== По неделям x кампания ===")
        weekly = df.groupby(["Week", "Campaign"])["Conversions"].sum().unstack(fill_value=0)
        print(weekly.to_string())
        weekly_path = out_dir / f"gads_calls_by_week_{args.date_from}_to_{date_to}.csv"
        weekly.to_csv(weekly_path, encoding="utf-8")
        print(f"Сохранено: {weekly_path}")


if __name__ == "__main__":
    main()
