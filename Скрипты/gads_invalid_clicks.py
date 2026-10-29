#!/usr/bin/env python
# coding: utf-8
"""Недействительные клики Google Ads — ТОЛЬКО ЧТЕНИЕ.

Зачем: у Landver 28.10 в `click_view` 923 строки при 5 оплаченных кликах (Хроника 29.10). Нужен повторяемый срез:
сколько кликов Google отфильтровал как недействительные и как это выглядит у других клиентов.

Два режима:
  --customer-id <ID> [--campaign-id <ID>] --days N   по дням: показы | оплаченные | недействительные | из них general
  --compare-mcc --from ГГГГ-ММ-ДД --to ГГГГ-ММ-ДД     по всем клиентским аккаунтам MCC из конфига Ads: доля
                                                      недействительных = invalid / (clicks + invalid)

Что это за поля — документация Google Ads API: `metrics.invalid_clicks` — клики, которые Google считает недействительными
и не списывает; `metrics.general_invalid_clicks` — их подмножество, найденное обычной фильтрацией (дата-центры, боты,
пауки); `click_view` включает и действительные, и недействительные клики. На уровне группы объявлений
`invalid_clicks` недоступен (только кампания и аккаунт).

Примеры:
  python gads_invalid_clicks.py --customer-id 2136216123 --campaign-id 24331208797 --days 10
  python gads_invalid_clicks.py --compare-mcc --from 2026-10-15 --to 2026-10-28
"""
import argparse
import datetime as dt

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML


def daily(svc, customer_id, campaign_id, days):
    d2 = dt.date.today() - dt.timedelta(days=1)
    d1 = d2 - dt.timedelta(days=days - 1)
    where = f"segments.date BETWEEN '{d1}' AND '{d2}'"
    if campaign_id:
        where += f" AND campaign.id = {campaign_id}"
    agg = {}
    for r in svc.search(customer_id=customer_id, query=(
            "SELECT segments.date, metrics.impressions, metrics.clicks, metrics.invalid_clicks, "
            f"metrics.general_invalid_clicks FROM campaign WHERE {where}")):
        m = r.metrics
        a = agg.setdefault(r.segments.date, [0, 0, 0, 0])
        a[0] += m.impressions
        a[1] += m.clicks
        a[2] += m.invalid_clicks
        a[3] += m.general_invalid_clicks
    print(f"аккаунт {customer_id}" + (f", кампания {campaign_id}" if campaign_id else ", все кампании"))
    print("дата        показы  оплач.  недейств.  из них general  недейств/показы  доля недейств.")
    for d in sorted(agg):
        i, c, inv, gen = agg[d]
        print(f"{d}  {i:6}  {c:6}  {inv:9.0f}  {gen:14.0f}  {inv / i if i else 0:14.1f}  {inv / (c + inv) * 100 if c + inv else 0:13.1f}%")


def compare(client, svc, d1, d2):
    mcc = str(client.login_customer_id)
    clients = [(str(r.customer_client.id), r.customer_client.descriptive_name) for r in svc.search(
        customer_id=mcc, query=("SELECT customer_client.id, customer_client.descriptive_name FROM customer_client "
                                "WHERE customer_client.manager = FALSE AND customer_client.status = 'ENABLED'"))]
    rows = []
    for cid, name in clients:
        try:
            imp = cl = inv = 0
            cost = 0.0
            for r in svc.search(customer_id=cid, query=(
                    "SELECT metrics.impressions, metrics.clicks, metrics.invalid_clicks, metrics.cost_micros "
                    f"FROM campaign WHERE segments.date BETWEEN '{d1}' AND '{d2}'")):
                m = r.metrics
                imp += m.impressions
                cl += m.clicks
                inv += m.invalid_clicks
                cost += m.cost_micros / 1e6
            rows.append((name, cid, imp, cl, inv, cost))
        except Exception as e:  # доступа может не быть
            print(f"{name} ({cid}): ошибка {str(e)[:80]!r}")
    print(f"MCC {mcc}, период {d1} — {d2}; расход в валюте аккаунта")
    print("клиент | id | показы | оплач. | недейств. | недейств/(оплач+недейств) | расход")
    for name, cid, imp, cl, inv, cost in sorted(rows, key=lambda x: -(x[4] / (x[3] + x[4]) if x[3] + x[4] else 0)):
        share = inv / (cl + inv) * 100 if cl + inv else 0
        print(f"{name[:34]:34} | {cid} | {imp:7} | {cl:6} | {inv:6} | {share:5.1f}% | {cost:9.0f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id")
    ap.add_argument("--campaign-id")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--compare-mcc", action="store_true")
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    a = ap.parse_args()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc = client.get_service("GoogleAdsService")
    if a.compare_mcc:
        if not (a.d_from and a.d_to):
            ap.error("--compare-mcc требует --from и --to")
        compare(client, svc, a.d_from, a.d_to)
    elif a.customer_id:
        daily(svc, a.customer_id.replace("-", ""), a.campaign_id, a.days)
    else:
        ap.error("нужен --customer-id или --compare-mcc")


if __name__ == "__main__":
    main()
