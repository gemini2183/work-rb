#!/usr/bin/env python
# coding: utf-8
"""РАЗОВЫЙ: Merchant_Performance Max-1, метрики по asset_group x дата,
9 июля - 8 сентября - проверить, не сосредоточен ли обвал 3 сентября в одной
конкретной группе (Ретаргет / Поисковые запросы / Интересы)."""
import pandas as pd
from _config import get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from google.ads.googleads.client import GoogleAdsClient

CLIENT_MERCHANT = "Корогва - Merchant Center"
DATE_FROM = "2026-07-09"
DATE_TO = "2026-09-08"

row = get_client_row(CLIENT_MERCHANT, tab="Google_Ads_API", agency="adwhite")
customer_id = str(row.get("client_id", "")).replace("-", "").strip()
login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
ga_service = get_ads_service(login_customer_id)

query = f"""
    SELECT
        asset_group.name,
        segments.date,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions
    FROM asset_group
    WHERE campaign.name = 'Merchant_Performance Max-1'
        AND segments.date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
"""

rows = []
for batch in ga_service.search_stream(customer_id=customer_id, query=query):
    for r in batch.results:
        rows.append({
            "asset_group": r.asset_group.name,
            "date": r.segments.date,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "cost": r.metrics.cost_micros / 1_000_000,
            "conversions": r.metrics.conversions,
        })

df = pd.DataFrame(rows)
out_path = "../Клиенты/Корогва/Статистика/_tmp_pmax1_assetgroups_daily_2026-07-09_to_2026-09-08.csv"
df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"Строк: {len(df)}, сохранено в {out_path}")
