#!/usr/bin/env python
# coding: utf-8
"""Разбивка расхода, кликов и конверсий кампании (в первую очередь Performance Max) по сети показа:
SEARCH / DISCOVER / YOUTUBE / CONTENT (Display) / SEARCH_PARTNERS. Только чтение.

Нужна, чтобы мерить долю расхода и цену конверсии на YouTube и Discover до и после исключений площадок.

Использование:
    python gads_pmax_channel_split.py --customer-id 7552781705 --campaign-id 23775369828 --date-from 2026-09-01 --date-to 2026-10-08
Можно сравнить два периода: добавить --compare-from и --compare-to.
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML


def split(client, ga, cid, campaign_id, d_from, d_to):
    q = ("SELECT campaign.id, segments.ad_network_type, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
         f"FROM campaign WHERE campaign.id = {campaign_id} AND segments.date BETWEEN '{d_from}' AND '{d_to}'")
    agg = {}
    for r in ga.search(customer_id=cid, query=q):
        k = client.enums.AdNetworkTypeEnum.AdNetworkType.Name(r.segments.ad_network_type)
        m = r.metrics
        a = agg.setdefault(k, [0, 0, 0.0, 0.0])
        a[0] += m.impressions
        a[1] += m.clicks
        a[2] += m.cost_micros / 1e6
        a[3] += m.conversions
    return agg


def show(title, agg):
    tc = sum(v[2] for v in agg.values()) or 1
    tv = sum(v[3] for v in agg.values()) or 1
    print(f"--- {title}")
    print("сеть | показы | клики | расход | доля расхода | конв | доля конв | CPA | CPC")
    for k, v in sorted(agg.items(), key=lambda x: -x[1][2]):
        cpa = f"{v[2] / v[3]:.1f}" if v[3] else "-"
        cpc = f"{v[2] / v[1]:.3f}" if v[1] else "-"
        print(f"{k} | {v[0]} | {v[1]} | {v[2]:.0f} | {v[2] / tc:.0%} | {v[3]:.1f} | {v[3] / tv:.0%} | {cpa} | {cpc}")
    print(f"ИТОГО расход {tc:.0f}, конверсий {tv:.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--compare-from")
    ap.add_argument("--compare-to")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    show(f"{args.date_from}..{args.date_to}", split(client, ga, cid, args.campaign_id, args.date_from, args.date_to))
    if args.compare_from and args.compare_to:
        show(f"{args.compare_from}..{args.compare_to}", split(client, ga, cid, args.campaign_id, args.compare_from, args.compare_to))


if __name__ == "__main__":
    main()
