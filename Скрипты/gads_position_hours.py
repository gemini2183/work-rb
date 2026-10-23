#!/usr/bin/env python
# coding: utf-8
"""Показы кампании по позиции на странице (верх / низ) и по часам — ТОЛЬКО ЧТЕНИЕ.

Зачем: доля показов и «потеряно по рейтингу» не говорят, где именно на странице мы стоим. Разбивка по `segments.slot`
(SEARCH_TOP — над обычными результатами, SEARCH_OTHER — ниже) показывает, куда ушёл рост показов после повышения ставок, и
CTR/цену клика в каждой позиции (Landver 2026-10-23: верх ~100–115 показов в день и до, и после повышения ставок, прирост — внизу,
CTR вверху 1–5%, внизу ~0,1–0,2%). Разбивка по часам (час в часовом поясе аккаунта) — для решений по расписанию показа.
Ограничение API: `segments.slot` нельзя запрашивать вместе с `segments.hour` — это два отдельных запроса.

Использование (из папки Скрипты):
    python gads_position_hours.py --customer-id 213-621-6123 --campaign "search / car+truck injuries / s / lp - tilda" \
        --date-from 2026-10-12 --date-to 2026-10-22 [--hours]
По умолчанию — таблица «день: верх/низ». С --hours добавляется таблица «час: показы, клики, расход».
"""
import argparse
import collections
import io
import sys

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign", required=True, help="точное имя кампании")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--hours", action="store_true", help="добавить разбивку по часам")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc, E = client.get_service("GoogleAdsService"), client.enums
    q = lambda x: list(svc.search(customer_id=cid, query=x))
    camp = a.campaign.replace("'", "\\'")
    rng = f"segments.date BETWEEN '{a.date_from}' AND '{a.date_to}'"

    days = collections.defaultdict(lambda: {"SEARCH_TOP": [0, 0, 0.0], "SEARCH_OTHER": [0, 0, 0.0]})
    for r in q(f"SELECT segments.date, segments.slot, metrics.impressions, metrics.clicks, metrics.cost_micros "
               f"FROM campaign WHERE campaign.name = '{camp}' AND {rng}"):
        name = E.SlotEnum.Slot.Name(r.segments.slot)
        if name not in ("SEARCH_TOP", "SEARCH_OTHER"):
            continue
        x = days[str(r.segments.date)][name]
        x[0] += r.metrics.impressions
        x[1] += r.metrics.clicks
        x[2] += r.metrics.cost_micros / 1e6
    print(f"== позиция на странице: {a.campaign} | {a.date_from} → {a.date_to}")
    print("день        | верх: показы клики расход CTR   | низ: показы клики расход CTR")
    tot = {"SEARCH_TOP": [0, 0, 0.0], "SEARCH_OTHER": [0, 0, 0.0]}
    for d in sorted(days):
        row = []
        for k in ("SEARCH_TOP", "SEARCH_OTHER"):
            i, c, s = days[d][k]
            tot[k][0] += i
            tot[k][1] += c
            tot[k][2] += s
            row.append(f"{i:5} {c:3} ${s:6.0f} {(c / i * 100 if i else 0):4.1f}%")
        print(f"{d} | {row[0]} | {row[1]}")
    row = []
    for k in ("SEARCH_TOP", "SEARCH_OTHER"):
        i, c, s = tot[k]
        row.append(f"{i:5} {c:3} ${s:6.0f} {(c / i * 100 if i else 0):4.1f}%")
    print(f"ИТОГО      | {row[0]} | {row[1]}")
    n = max(len(days), 1)
    print(f"в среднем в день: верх {tot['SEARCH_TOP'][0] / n:.0f} показов, низ {tot['SEARCH_OTHER'][0] / n:.0f}")

    if a.hours:
        h = collections.defaultdict(lambda: [0, 0, 0.0])
        for r in q(f"SELECT segments.hour, metrics.impressions, metrics.clicks, metrics.cost_micros "
                   f"FROM campaign WHERE campaign.name = '{camp}' AND {rng}"):
            x = h[r.segments.hour]
            x[0] += r.metrics.impressions
            x[1] += r.metrics.clicks
            x[2] += r.metrics.cost_micros / 1e6
        print("\n== по часам (час в поясе аккаунта): показы клики расход")
        for k in sorted(h):
            print(f"{k:02d}:00  {h[k][0]:5} {h[k][1]:3} ${h[k][2]:6.0f}")


if __name__ == "__main__":
    main()
