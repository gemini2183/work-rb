#!/usr/bin/env python
# coding: utf-8
"""Сверка продаж EkspertAgro, шаг 9: цена продажи по месяцам — ТОЛЬКО ЧТЕНИЕ (Google Ads API + таблица клиента).

Расход — весь аккаунт Google Ads (все кампании, Facebook не входит) по месяцам. Продажи — заказы таблицы клиента
по колонке «Дата продажи» (статус в строке — на момент обращения, ему верить нельзя). Три способа отнести заказ к рекламе:
  A. первая строка заказа — Google Ads;
  B. первая строка заказа — не Facebook (Google Ads + «Нет метки» + «Телефон»), верхняя граница для Google;
  C. в заказе есть хоть одна строка Google Ads.
Продажи считаются двумя разрезами: по месяцу создания заказа (когорта) и по месяцу продажи. Последний месяц не созрел.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_cost_per_sale.py [--from 2026-03-01] [--customer-id 8826134558] [--rate 4.3691]
"""
import argparse
from collections import defaultdict

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from ea_sales_orders_check import load as load_sheet
from gads_stats import GOOGLE_ADS_YAML

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"


def spend_by_month(customer_id, date_from):
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    q = f"""SELECT campaign.name, segments.month, metrics.cost_micros FROM campaign
            WHERE segments.date >= '{date_from}' AND segments.date <= '{pd.Timestamp.now():%Y-%m-%d}'"""
    tot, by_c = defaultdict(float), defaultdict(float)
    for batch in ga.search_stream(customer_id=customer_id, query=q):
        for r in batch.results:
            m = r.segments.month[:7]
            c = r.metrics.cost_micros / 1e6
            tot[m] += c
            by_c[(m, r.campaign.name)] += c
    return tot, by_c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", default="2026-03-01")
    ap.add_argument("--customer-id", default="8826134558")
    ap.add_argument("--rate", type=float, default=4.3691, help="zł за 1 EUR (граница 30 € = 131 zł)")
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    args = ap.parse_args()

    spend, by_c = spend_by_month(args.customer_id, args.date_from)
    df = load_sheet(SHEET_ID, args.worksheet)
    o = df[df["order"] != ""].sort_values("ts")
    g = o.groupby("order")
    orders = pd.DataFrame({
        "created": g["ts"].min(),
        "first_src": g["src"].first(),
        "any_google": g["src"].apply(lambda s: (s == "Google Ads").any()),
        "sale": g["sale_date_dt"].max(),
        "cancel": g["cancel_date_dt"].max(),
    })
    sold = orders[orders["sale"].notna()].copy()
    sold["cmonth"] = sold["created"].dt.strftime("%Y-%m")
    sold["smonth"] = sold["sale"].dt.strftime("%Y-%m")

    limit = 30 * args.rate
    print(f"Граница 30 € = {limit:.0f} zł за продажу (курс {args.rate}); подтверждена клиентом? НЕТ (перенос от ProfiMet)\n")
    rows = []
    for m in sorted(spend):
        for basis, col in (("по месяцу создания заказа", "cmonth"), ("по месяцу продажи", "smonth")):
            s = sold[sold[col] == m]
            a = int((s["first_src"] == "Google Ads").sum())
            b = int((s["first_src"] != "Facebook").sum())
            c = int(s["any_google"].sum())
            rows.append({"месяц": m, "разрез": basis, "расход zł": round(spend[m]), "A Google первая": a,
                         "zł/прод A": round(spend[m] / a) if a else None, "B не-Facebook": b,
                         "zł/прод B": round(spend[m] / b) if b else None, "C Google в заказе": c,
                         "zł/прод C": round(spend[m] / c) if c else None, "всего проданных": len(s)})
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    for basis in out["разрез"].unique():
        print(f"== Продажи {basis} ==")
        print(out[out["разрез"] == basis].drop(columns="разрез").to_string(index=False))
        print()

    last = sorted(spend)[-3:]
    print("Расход по кампаниям (zł), последние месяцы:")
    for m in last:
        parts = sorted(((v, c) for (mm, c), v in by_c.items() if mm == m and v > 0.5), reverse=True)
        print(" ", m, "; ".join(f"{c} {v:.0f}" for v, c in parts))

    # отмены среди созданных: доля отменённых от закрытых (проданные + отменённые без продажи)
    print("\nДоля отмен среди закрытых заказов по месяцу создания (закрыт = продан или отменён):")
    orders["cmonth"] = orders["created"].dt.strftime("%Y-%m")
    for m, x in orders.groupby("cmonth"):
        sold_n = int(x["sale"].notna().sum())
        canc = int((x["cancel"].notna() & x["sale"].isna()).sum())
        if sold_n + canc:
            print(f"  {m}: продано {sold_n}, отменено {canc}, не закрыто {len(x) - sold_n - canc}, доля продаж среди закрытых {sold_n / (sold_n + canc):.0%}")


if __name__ == "__main__":
    main()
