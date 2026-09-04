#!/usr/bin/env python
# coding: utf-8
"""Callout и Structured Snippet extensions (assets) кампании/аккаунта.

Современный Google Ads API (v20+) хранит расширения объявлений как Asset
(единый ресурс для sitelink/callout/structured snippet/...), привязанный к
campaign_asset / customer_asset / ad_group_asset — не через устаревший
extension_setting. Этот скрипт читает CALLOUT и STRUCTURED_SNIPPET assets на
уровне кампании и аккаунта (campaign_asset + customer_asset), чтобы увидеть,
что уже реально настроено, прежде чем менять/добавлять новые при запуске
кампании (см. Клиенты/Andverpersonalinjury/Кампании/Search/
Эталонное-объявление-и-sitelinks.yaml про такой же паттерн для sitelinks).

Использование:
    python gads_ad_extensions.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" \
        --campaigns "search / all injuries / kw - la specific"
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


def fetch_callouts(ga_service, customer_id, campaign_name=None):
    """CALLOUT assets -> DataFrame. campaign_name=None -> уровень аккаунта (customer_asset)."""
    if campaign_name:
        query = f"""
            SELECT
                campaign.name,
                asset.callout_asset.callout_text,
                campaign_asset.status
            FROM campaign_asset
            WHERE campaign.name = '{campaign_name}'
                AND asset.type = 'CALLOUT'
        """
    else:
        query = """
            SELECT
                asset.callout_asset.callout_text,
                customer_asset.status
            FROM customer_asset
            WHERE asset.type = 'CALLOUT'
        """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_name:
                rows.append({
                    "Level": "Campaign",
                    "Campaign": row.campaign.name,
                    "Callout_text": row.asset.callout_asset.callout_text,
                    "Status": _enum_name("AssetLinkStatusEnum", "AssetLinkStatus", row.campaign_asset.status),
                })
            else:
                rows.append({
                    "Level": "Account",
                    "Campaign": "",
                    "Callout_text": row.asset.callout_asset.callout_text,
                    "Status": _enum_name("AssetLinkStatusEnum", "AssetLinkStatus", row.customer_asset.status),
                })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_structured_snippets(ga_service, customer_id, campaign_name=None):
    """STRUCTURED_SNIPPET assets -> DataFrame. campaign_name=None -> уровень аккаунта."""
    if campaign_name:
        query = f"""
            SELECT
                campaign.name,
                asset.structured_snippet_asset.header,
                asset.structured_snippet_asset.values,
                campaign_asset.status
            FROM campaign_asset
            WHERE campaign.name = '{campaign_name}'
                AND asset.type = 'STRUCTURED_SNIPPET'
        """
    else:
        query = """
            SELECT
                asset.structured_snippet_asset.header,
                asset.structured_snippet_asset.values,
                customer_asset.status
            FROM customer_asset
            WHERE asset.type = 'STRUCTURED_SNIPPET'
        """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            snippet = row.asset.structured_snippet_asset
            if campaign_name:
                rows.append({
                    "Level": "Campaign",
                    "Campaign": row.campaign.name,
                    "Header": snippet.header,
                    "Values": ", ".join(snippet.values),
                    "Status": _enum_name("AssetLinkStatusEnum", "AssetLinkStatus", row.campaign_asset.status),
                })
            else:
                rows.append({
                    "Level": "Account",
                    "Campaign": "",
                    "Header": snippet.header,
                    "Values": ", ".join(snippet.values),
                    "Status": _enum_name("AssetLinkStatusEnum", "AssetLinkStatus", row.customer_asset.status),
                })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Andverpersonalinjury"')
    ap.add_argument("--campaigns", help="Список названий кампаний через запятую (опционально — без него читается только уровень аккаунта)")
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
    campaign_names = [c.strip() for c in args.campaigns.split(",")] if args.campaigns else [None]

    callout_frames = []
    snippet_frames = []

    for campaign_name in campaign_names:
        label = campaign_name if campaign_name else "(уровень аккаунта)"
        print(f"\n=== {label} ===")

        df_callouts = fetch_callouts(ga_service, customer_id, campaign_name)
        if not df_callouts.empty:
            callout_frames.append(df_callouts)
            print(f"Callouts: {len(df_callouts)}")
            for _, r in df_callouts.iterrows():
                print(f"  [{r['Status']}] {r['Callout_text']}")
        else:
            print("Callouts: нет")

        df_snippets = fetch_structured_snippets(ga_service, customer_id, campaign_name)
        if not df_snippets.empty:
            snippet_frames.append(df_snippets)
            print(f"Structured snippets: {len(df_snippets)}")
            for _, r in df_snippets.iterrows():
                print(f"  [{r['Status']}] {r['Header']}: {r['Values']}")
        else:
            print("Structured snippets: нет")

    if callout_frames:
        df = pd.concat(callout_frames, ignore_index=True)
        path = out_dir / "gads_ad_extensions_callouts.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"\nСохранено: {path}")

    if snippet_frames:
        df = pd.concat(snippet_frames, ignore_index=True)
        path = out_dir / "gads_ad_extensions_snippets.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"Сохранено: {path}")


if __name__ == "__main__":
    main()
