#!/usr/bin/env python
# coding: utf-8
"""РАЗОВЫЙ скрипт: товарный разрез Merchant_Performance Max-1, все сети, по дням,
9 июля - 8 сентября - для поиска конкретных товаров/категорий, ответственных за
обвал конверсии с 3 сентября."""
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
        campaign.name,
        segments.date,
        segments.product_item_id,
        segments.product_title,
        segments.product_type_l1,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions
    FROM shopping_performance_view
    WHERE segments.date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
        AND campaign.name = 'Merchant_Performance Max-1'
"""

rows = []
for batch in ga_service.search_stream(customer_id=customer_id, query=query):
    for r in batch.results:
        rows.append({
            "date": r.segments.date,
            "product_id": r.segments.product_item_id,
            "product_title": r.segments.product_title,
            "l1": r.segments.product_type_l1 or "(пусто)",
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "cost": r.metrics.cost_micros / 1_000_000,
            "conversions": r.metrics.conversions,
        })

df = pd.DataFrame(rows)
out_path = "../Клиенты/Корогва/Статистика/_tmp_pmax1_products_daily_2026-07-09_to_2026-09-08.csv"
df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"Строк: {len(df)}, сохранено в {out_path}")
