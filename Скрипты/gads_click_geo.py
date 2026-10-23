#!/usr/bin/env python
# coding: utf-8
"""Откуда кликают: клики и расход кампании (или одной группы) по метро и округам за период. ТОЛЬКО ЧТЕНИЕ.

Зачем: понять, какая доля трафика идёт из-за пределов офисного региона (Landver, 2026-10-23: офис в
Беверли-Хиллз, адвокат работает по всей Калифорнии). Выводов не делает. Уровень группы объявлений API для этого отчёта не отдаёт (только кампания).

    python gads_click_geo.py --customer-id 213-621-6123 --campaign 24331208797 \
        --date-from 2026-10-06 --date-to 2026-10-22
"""
import argparse
from collections import defaultdict
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign", required=True, help="id кампании")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", default=str(date.today() - timedelta(1)))
    a = ap.parse_args()

    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    def q(query):
        return [r for b in ga.search_stream(customer_id=cid, query=query) for r in b.results]

    period = f"segments.date BETWEEN '{a.date_from}' AND '{a.date_to}'"
    res = "user_location_view"  # где пользователь физически был (не «интересовался»)
    where = f"campaign.id = {a.campaign}"

    adg_sel = ""
    names = {}

    def name_of(rn):
        if not rn:
            return "(не определено)"
        if rn not in names:
            rows = q(f"SELECT geo_target_constant.name, geo_target_constant.canonical_name "
                     f"FROM geo_target_constant WHERE geo_target_constant.resource_name = '{rn}'")
            names[rn] = rows[0].geo_target_constant.canonical_name if rows else rn
        return names[rn]

    title = f"кампания {a.campaign}"
    print(f"=== Клики по географии | {title} | {a.date_from} → {a.date_to} | только чтение ===")
    for seg, label in (("geo_target_metro", "по метро"), ("geo_target_county", "по округам")):
        agg = defaultdict(lambda: [0, 0, 0.0])
        try:
            rows = q(f"SELECT campaign.id, {adg_sel}segments.{seg}, metrics.impressions, metrics.clicks, metrics.cost_micros "
                     f"FROM {res} WHERE {where} AND {period}")
        except Exception as e:  # noqa: BLE001
            print(f"\n[{label}] запрос не поддерживается: {str(e)[:160]}")
            continue
        for r in rows:
            k = getattr(r.segments, seg)
            m = r.metrics
            agg[k][0] += m.impressions
            agg[k][1] += m.clicks
            agg[k][2] += m.cost_micros / 1e6
        tot_c = sum(v[1] for v in agg.values()) or 1
        tot_i = sum(v[0] for v in agg.values())
        print(f"\n[{label}] показы {tot_i}, клики {sum(v[1] for v in agg.values())}")
        for k, v in sorted(agg.items(), key=lambda x: -x[1][1])[:15]:
            if v[0] == 0:
                continue
            print(f"  {name_of(k):55} показы {v[0]:5} клики {v[1]:3} ({100 * v[1] / tot_c:4.0f}%) ${v[2]:8.2f}")


if __name__ == "__main__":
    main()
