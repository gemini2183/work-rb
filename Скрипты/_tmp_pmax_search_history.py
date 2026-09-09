#!/usr/bin/env python
# coding: utf-8
"""РАЗОВЫЙ: Merchant_Performance Max-1, сеть SEARCH конкретно, весь период 9 июля - 2 сентября,
для точного расчёта исторической CVR именно этой сети (не всей кампании)."""
import pandas as pd
from _config import get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from gads_campaigns_breakdown import _enum_name
from google.ads.googleads.client import GoogleAdsClient

CLIENT_MERCHANT = "Корогва - Merchant Center"
DATE_FROM = "2026-07-09"
DATE_TO = "2026-09-02"

row = get_client_row(CLIENT_MERCHANT, tab="Google_Ads_API", agency="adwhite")
customer_id = str(row.get("client_id", "")).replace("-", "").strip()
login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
ga_service = get_ads_service(login_customer_id)

query = f"""
    SELECT
        segments.ad_network_type,
        metrics.clicks,
        metrics.cost_micros,
        metrics.conversions
    FROM campaign
    WHERE segments.date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
        AND campaign.name = 'Merchant_Performance Max-1'
"""

totals = {}
for batch in ga_service.search_stream(customer_id=customer_id, query=query):
    for r in batch.results:
        net = _enum_name("AdNetworkTypeEnum", "AdNetworkType", r.segments.ad_network_type)
        t = totals.setdefault(net, {"clicks":0, "cost":0.0, "conv":0.0})
        t["clicks"] += r.metrics.clicks
        t["cost"] += r.metrics.cost_micros/1e6
        t["conv"] += r.metrics.conversions

for net, t in totals.items():
    cvr = t["conv"]/t["clicks"]*100 if t["clicks"] else 0
    print(f"{net}: clicks={t['clicks']}, cost={t['cost']:.2f}, conv={t['conv']:.2f}, CVR={cvr:.2f}%")
