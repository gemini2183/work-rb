#!/usr/bin/env python
# coding: utf-8
"""Performance Max: список Asset Group внутри кампании + метрики по дням на каждую.

У Performance Max нет ad_group/keyword в смысле обычного Search — структура
кампании состоит из Asset Group (набор креативов + сигналы аудитории), а не
из групп объявлений с ключами. gads_campaign_inventory.py под это не подходит
(написан под ad_group_criterion/ad_group_ad, которых у PMax просто нет).

Отвечает на вопрос "какие Asset Group есть в PMax-кампании и как каждая из них
показывает себя по дням" — например, чтобы проверить, не сосредоточен ли обвал
конверсии в одной конкретной группе (пример: клиент Корогва, Merchant_Performance
Max-1, группы "Ретаргет"/"Поисковые запросы"/"Интересы..." — см.
Клиенты/Корогва/Решения.md, 2026-09-09).

Использование:
    python gads_pmax_asset_groups.py --customer-id 845-234-6433 \
        --client-folder "Корогва" --campaigns "Merchant_Performance Max-1" \
        --date-from 2026-07-09 --date-to 2026-09-08
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


def fetch_asset_groups_list(ga_service, customer_id, campaign_name):
    query = f"""
        SELECT
            asset_group.id,
            asset_group.name,
            asset_group.status
        FROM asset_group
        WHERE campaign.name = '{campaign_name}'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            rows.append({
                "Asset_group_id": r.asset_group.id,
                "Asset_group": r.asset_group.name,
                "Status": _enum_name("AssetGroupStatusEnum", "AssetGroupStatus", r.asset_group.status),
            })
    return pd.DataFrame(rows)


def fetch_asset_groups_by_day(ga_service, customer_id, campaign_name, date_from, date_to):
    query = f"""
        SELECT
            asset_group.name,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM asset_group
        WHERE campaign.name = '{campaign_name}'
            AND segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            rows.append({
                "Asset_group": r.asset_group.name,
                "Date": r.segments.date,
                "Impressions": r.metrics.impressions,
                "Clicks": r.metrics.clicks,
                "Cost": round(r.metrics.cost_micros / 1_000_000, 2),
                "Conversions": round(r.metrics.conversions, 3),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Asset_group", "Date"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Корогва"')
    ap.add_argument("--campaigns", required=True, help="Список названий PMax-кампаний через запятую")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
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

    pd.set_option("display.width", 200)

    for campaign_name in campaign_names:
        safe_name = campaign_name.replace("/", "-").replace("\\", "-").strip()
        print(f"\n=== {campaign_name} ===")

        df_list = fetch_asset_groups_list(ga_service, customer_id, campaign_name)
        list_path = out_dir / f"gads_pmax_asset_groups_list_{safe_name}.csv"
        df_list.to_csv(list_path, index=False, encoding="utf-8")
        print(f"Asset Group ({len(df_list)}): сохранено в {list_path}")
        print(df_list.to_string(index=False))

        df_daily = fetch_asset_groups_by_day(ga_service, customer_id, campaign_name, args.date_from, args.date_to)
        if df_daily.empty:
            print("Нет данных по дням за период")
            continue
        daily_path = out_dir / f"gads_pmax_asset_groups_daily_{safe_name}_{args.date_from}_to_{args.date_to}.csv"
        df_daily.to_csv(daily_path, index=False, encoding="utf-8")
        print(f"\nМетрики по дням: сохранено в {daily_path} ({len(df_daily)} строк)")

        summary = df_daily.groupby("Asset_group", as_index=False).agg(
            Clicks=("Clicks", "sum"), Cost=("Cost", "sum"), Conversions=("Conversions", "sum")
        )
        summary["CPA"] = summary["Cost"] / summary["Conversions"].replace(0, pd.NA)
        summary["CVR_%"] = 100 * summary["Conversions"] / summary["Clicks"]
        print("\nИтого за период по группе:")
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
