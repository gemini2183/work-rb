#!/usr/bin/env python
# coding: utf-8
"""РАЗОВЫЙ скрипт: search_term_view для Merchant_Shopping, 2026-09-01..2026-09-07.
Известное ограничение (см. База_знаний/Инструменты/Search-Term-View-ограничения-
Shopping-Performance-Max): этот отчёт для Shopping не даёт привязки термин->товар/
категория, только термин + агрегированные метрики по кампании. Тянем всё, что есть,
затем размечаем по словарю (человечий одяг / прапори / прочее) вручную по тексту."""
import pandas as pd
from _config import get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
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
        search_term_view.search_term,
        campaign.name,
        metrics.impressions,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions
    FROM search_term_view
    WHERE segments.date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
        AND campaign.name = 'Merchant_Shopping'
"""

rows = []
try:
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            rows.append({
                "term": r.search_term_view.search_term,
                "campaign": r.campaign.name,
                "impressions": r.metrics.impressions,
                "clicks": r.metrics.clicks,
                "cost": r.metrics.cost_micros / 1_000_000,
                "conversions": r.metrics.conversions,
            })
except Exception as e:
    print("ERROR:", e)

df = pd.DataFrame(rows)
if df.empty:
    print("ПУСТО — search_term_view не отдал ни одной строки для Merchant_Shopping за этот период (ожидаемо, см. известное ограничение)")
else:
    out_path = "../Клиенты/Корогва/Статистика/_tmp_searchterms_merchant_shopping_2026-09-01_to_2026-09-07.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Строк: {len(df)}, сохранено в {out_path}")
    print(df.sort_values('cost', ascending=False).head(20).to_string(index=False))
