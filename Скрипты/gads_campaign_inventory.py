#!/usr/bin/env python
# coding: utf-8
"""Полная инвентаризация кампании: группы объявлений, ключевые слова, тексты объявлений.

Отвечает на вопрос "как устроена кампания и в чём замысел" — в отличие от
gads_campaign_settings.py (сетевые/гео/расписание настройки на уровне
кампании), здесь — содержимое групп объявлений внутри неё. Нужен, когда
кампания заведена вручную в кабинете и в вики о её структуре ничего не
известно (см. Клиенты/Andverpersonalinjury/Решения.md).

Как и gads_ads_dump.py, идёт через ad_group_criterion (не keyword_view —
keyword_view молча пропускает ключи без статистики за период, проверено на
Andverpersonalinjury) и ad_group_ad. Только ENABLED-объекты.

Использование:
    python gads_campaign_inventory.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" \
        --campaigns "search / all injuries / geo - la specific,search / all injuries / kw -  la specific"
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


def _pin_label(pinned_field: int) -> str:
    if not pinned_field:
        return ""
    name = _enum_name("ServedAssetFieldTypeEnum", "ServedAssetFieldType", pinned_field)
    return name.replace("HEADLINE_", "H").replace("DESCRIPTION_", "D")


def fetch_keywords(ga_service, customer_id, campaign_name):
    """Ключевые слова кампании (все статусы) -> DataFrame."""
    query = f"""
        SELECT
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status
        FROM ad_group_criterion
        WHERE campaign.name = '{campaign_name}'
            AND ad_group_criterion.type = 'KEYWORD'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            rows.append({
                "Ad_group": row.ad_group.name,
                "Keyword": row.ad_group_criterion.keyword.text,
                "Match_type": _enum_name(
                    "KeywordMatchTypeEnum", "KeywordMatchType", row.ad_group_criterion.keyword.match_type
                ),
                "Status": _enum_name("AdGroupCriterionStatusEnum", "AdGroupCriterionStatus", row.ad_group_criterion.status),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Ad_group", "Keyword"]).reset_index(drop=True)


def fetch_ads(ga_service, customer_id, campaign_name):
    """RSA-объявления кампании (все статусы) -> DataFrame."""
    query = f"""
        SELECT
            ad_group.name,
            ad_group_ad.ad.id,
            ad_group_ad.status,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions
        FROM ad_group_ad
        WHERE campaign.name = '{campaign_name}'
            AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            ad = row.ad_group_ad.ad.responsive_search_ad
            headlines = " | ".join(a.text for a in ad.headlines)
            descriptions = " | ".join(a.text for a in ad.descriptions)
            rows.append({
                "Ad_group": row.ad_group.name,
                "AdId": row.ad_group_ad.ad.id,
                "Status": _enum_name("AdGroupAdStatusEnum", "AdGroupAdStatus", row.ad_group_ad.status),
                "Final_url": row.ad_group_ad.ad.final_urls[0] if row.ad_group_ad.ad.final_urls else "",
                "Headlines": headlines,
                "Descriptions": descriptions,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Ad_group", "AdId"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Andverpersonalinjury"')
    ap.add_argument("--campaigns", required=True, help="Список названий кампаний через запятую")
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
        print("Нужен либо --client, либо --customer-id")
        return

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    out_dir = client_stats_dir(args.client_folder)
    campaign_names = [c.strip() for c in args.campaigns.split(",")]

    for campaign_name in campaign_names:
        safe_name = campaign_name.replace("/", "-").strip()
        print(f"\n=== {campaign_name} ===")

        df_kw = fetch_keywords(ga_service, customer_id, campaign_name)
        kw_path = out_dir / f"gads_inventory_keywords_{safe_name}.csv"
        df_kw.to_csv(kw_path, index=False, encoding="utf-8")
        print(f"Ключевые слова: {kw_path} ({len(df_kw)} строк)")
        if not df_kw.empty:
            print(f"  По группам: {df_kw.groupby('Ad_group').size().to_dict()}")
            print(f"  По статусам: {df_kw.groupby('Status').size().to_dict()}")

        df_ads = fetch_ads(ga_service, customer_id, campaign_name)
        ads_path = out_dir / f"gads_inventory_ads_{safe_name}.csv"
        df_ads.to_csv(ads_path, index=False, encoding="utf-8")
        print(f"Объявления: {ads_path} ({len(df_ads)} строк)")
        if not df_ads.empty:
            print(f"  По группам: {df_ads.groupby('Ad_group').size().to_dict()}")


if __name__ == "__main__":
    main()
