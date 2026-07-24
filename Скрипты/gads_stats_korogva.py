#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики Google Ads для Корогвы — со спец-фильтрацией под клиента.

Один аккаунт Google Ads (client_id 845-234-6433), разбитый на два подпроекта
по названию кампании (1:1 логика прод-job'ов
E:/PythonProjects/RedBird/google-cloud-jobs/adwhite/func/gads_korogva_gads/main.py
и .../gads_korogva_merchant/main.py):
  - "Корогва - Google Ads"      — обычные кампании (Search и пр.)
  - "Корогва - Merchant Center" — товарные кампании (название содержит
    "Sales" или "Merchant_")

Тянет и трафик, и конверсии одним проходом (используя fetch_traffic/
fetch_conversions из gads_stats.py) с фильтром campaign_filter, отдельно для
каждого подпроекта — оба сохраняются в Статистика/ с суффиксом gads/merchant.

Использование:
    python gads_stats_korogva.py --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service, fetch_traffic, fetch_conversions

CLIENT_FOLDER = "Корогва"
CLIENT_GADS = "Корогва - Google Ads"
CLIENT_MERCHANT = "Корогва - Merchant Center"

MERCHANT_MARKERS = ("Sales", "Merchant_")


def is_merchant(name: str) -> bool:
    return any(m in name for m in MERCHANT_MARKERS)


def is_not_merchant(name: str) -> bool:
    return not is_merchant(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(CLIENT_GADS, tab="Google_Ads_API", agency="adwhite")
    customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    if not customer_id:
        print(f"У клиента '{CLIENT_GADS}' на вкладке 'Google_Ads_API' пустой client_id")
        return

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {CLIENT_FOLDER} | период {date_from} → {date_to}")
    out_dir = client_stats_dir(CLIENT_FOLDER)

    for suffix, campaign_filter in (("gads", is_not_merchant), ("merchant", is_merchant)):
        df_traffic = fetch_traffic(ga_service, customer_id, date_from, date_to, campaign_filter)
        df_goals = fetch_conversions(ga_service, customer_id, date_from, date_to, campaign_filter)

        traffic_path = out_dir / f"gads_korogva-{suffix}_{date_from}_to_{date_to}.csv"
        goals_path = out_dir / f"gads_korogva-{suffix}-goals_{date_from}_to_{date_to}.csv"

        df_traffic.to_csv(traffic_path, index=False, encoding="utf-8")
        df_goals.to_csv(goals_path, index=False, encoding="utf-8")
        print(f"Сохранено: {traffic_path} ({len(df_traffic)} дней)")
        print(f"Сохранено: {goals_path} ({len(df_goals)} строк)")


if __name__ == "__main__":
    main()
