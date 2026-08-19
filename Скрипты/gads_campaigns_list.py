#!/usr/bin/env python
# coding: utf-8
"""Список кампаний аккаунта Google Ads на текущий момент — статус, тип, бюджет.

Отдельная задача от gads_campaigns_breakdown.py (тот — исторический трафик за
период, метрики) и от gads_search_partners_audit.py (тот — площадки Search
Partners). Этот скрипт отвечает на другой вопрос: "что вообще сейчас включено
и на каком бюджете", без разбивки по датам — снимок настроек кампаний, не
статистики показов.

Использование (customer_id напрямую — для клиентов не заведённых строкой в
общей таблице, см. Клиенты/Andverpersonalinjury/_project.md):
    python gads_campaigns_list.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury"

Использование (по строке в таблице Google_Ads_API):
    python gads_campaigns_list.py --client "Клиент - Google Ads" --client-folder "Клиент"

--all показывает и PAUSED/REMOVED кампании (по умолчанию только ENABLED).
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def fetch_campaigns(ga_service, customer_id, include_all=False):
    """Кампании аккаунта -> DataFrame (Name, Status, Channel_type, Bidding_strategy,
    Daily_budget). Бюджет берётся из campaign_budget (join по campaign.campaign_budget)
    — сумма в микро-единицах, делится на 1_000_000 для человекочитаемого $/день.
    """
    query = """
        SELECT
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros,
            campaign_budget.delivery_method
        FROM campaign
        ORDER BY campaign.name
    """

    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            status = _enum_name("CampaignStatusEnum", "CampaignStatus", row.campaign.status)
            if not include_all and status != "ENABLED":
                continue
            channel = _enum_name(
                "AdvertisingChannelTypeEnum", "AdvertisingChannelType",
                row.campaign.advertising_channel_type,
            )
            bidding = _enum_name(
                "BiddingStrategyTypeEnum", "BiddingStrategyType",
                row.campaign.bidding_strategy_type,
            )
            rows.append({
                "Campaign": row.campaign.name,
                "Status": status,
                "Channel_type": channel,
                "Bidding_strategy": bidding,
                "Daily_budget": round(row.campaign_budget.amount_micros / 1_000_000, 2),
            })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values(["Status", "Channel_type", "Campaign"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без) — если клиент не заведён в таблице")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Andverpersonalinjury"')
    ap.add_argument("--all", action="store_true", help="Показать все статусы (по умолчанию только ENABLED)")
    args = ap.parse_args()

    if args.customer_id:
        customer_id = args.customer_id.replace("-", "").strip()
    elif args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
        if not customer_id:
            print(f"У клиента '{args.client}' на вкладке 'Google_Ads_API' пустой client_id")
            return
    else:
        print("Нужен либо --client (строка в таблице Google_Ads_API), либо --customer-id напрямую")
        return

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder}")
    df = fetch_campaigns(ga_service, customer_id, include_all=args.all)

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / "gads_campaigns_list.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} кампаний)")
    if not df.empty:
        print()
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
