#!/usr/bin/env python
# coding: utf-8
"""РАЗОВЫЙ скрипт (не часть постоянного набора): товарный разрез Merchant_Shopping,
сеть SEARCH, 2026-09-01..2026-09-07. Явный фильтр campaign.name = 'Merchant_Shopping'
и segments.ad_network_type = SEARCH, чтобы не смешать с Merchant_Performance Max-1
и с другими сетями (см. База_знаний/Паттерны/Google-Ads-аудит-кампании..., Правило №1).
"""
import pandas as pd
from _config import get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from gads_campaigns_breakdown import _enum_name
from google.ads.googleads.client import GoogleAdsClient

CLIENT_MERCHANT = "Корогва - Merchant Center"
DATE_FROM = "2026-09-01"
DATE_TO = "2026-09-07"

row = get_client_row(CLIENT_MERCHANT, tab="Google_Ads_API", agency="adwhite")
customer_id = str(row.get("client_id", "")).replace("-", "").strip()

login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
ga_service = get_ads_service(login_customer_id)

query = f"""
    SELECT
        campaign.name,
        segments.ad_network_type,
        segments.product_item_id,
        segments.product_title,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value
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
            "campaign": r.campaign.name,
            "network": net_name,
            "product_id": r.segments.product_item_id,
            "product_title": r.segments.product_title,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "cost": r.metrics.cost_micros / 1_000_000,
            "conversions": r.metrics.conversions,
            "conv_value": r.metrics.conversions_value,
        })

df = pd.DataFrame(rows)
if df.empty:
    print("Нет данных (пустой результат)")
else:
    agg = df.groupby(["product_id", "product_title"], as_index=False).agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        cost=("cost", "sum"),
        conversions=("conversions", "sum"),
        conv_value=("conv_value", "sum"),
    )
    agg["CPA"] = agg["cost"] / agg["conversions"].replace(0, pd.NA)
    agg["CVR_%"] = 100 * agg["conversions"] / agg["clicks"].replace(0, pd.NA)
    agg = agg.sort_values("cost", ascending=False)
    out_path = "../Клиенты/Корогва/Статистика/_tmp_merchant_shopping_search_products_2026-09-01_to_2026-09-07.csv"
    agg.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Строк: {len(agg)}, сохранено в {out_path}")
    print(agg.to_string(index=False))
