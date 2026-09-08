#!/usr/bin/env python
# coding: utf-8
"""РАЗОВЫЙ скрипт: Merchant_Shopping/SEARCH по product_type_l1, по дням,
2026-07-13..2026-09-07 - проверка историчности категорий (обвалились сейчас
или всегда были слабыми)."""
import pandas as pd
from _config import get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from gads_campaigns_breakdown import _enum_name
from google.ads.googleads.client import GoogleAdsClient

CLIENT_MERCHANT = "Корогва - Merchant Center"
DATE_FROM = "2026-07-13"
DATE_TO = "2026-09-07"

row = get_client_row(CLIENT_MERCHANT, tab="Google_Ads_API", agency="adwhite")
customer_id = str(row.get("client_id", "")).replace("-", "").strip()

login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
ga_service = get_ads_service(login_customer_id)

query = f"""
    SELECT
        campaign.name,
        segments.date,
        segments.ad_network_type,
        segments.product_type_l1,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions
    FROM shopping_performance_view
    WHERE segments.date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
        AND campaign.name = 'Merchant_Shopping'
"""

rows = []
for batch in ga_service.search_stream(customer_id=customer_id, query=query):
    for r in batch.results:
        net_name = _enum_name("AdNetworkTypeEnum", "AdNetworkType", r.segments.ad_network_type)
        if net_name != "SEARCH":
            continue
        rows.append({
            "date": r.segments.date,
            "l1": r.segments.product_type_l1 or "(пусто)",
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "cost": r.metrics.cost_micros / 1_000_000,
            "conversions": r.metrics.conversions,
        })

df = pd.DataFrame(rows)
out_path = "../Клиенты/Корогва/Статистика/_tmp_merchant_shopping_search_by_category_daily_2026-07-13_to_2026-09-07.csv"
df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"Строк: {len(df)}, сохранено в {out_path}")
