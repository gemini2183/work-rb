#!/usr/bin/env python
# coding: utf-8
"""Цена продажи EkspertAgro по кампаниям Google Ads — ТОЛЬКО ЧТЕНИЕ (Google Ads API + выгрузка CRM клиента).

Заказ относится к кампании по `utm_campaign` строки заказа с источником «Google Ads» (ID по regex `_(\\d+)_`, иначе совпадение
названия). Продажа — есть «Дата продажи»; «чистая» — и нет «Даты отмены» (у заказа бывает и то и другое). Заказы берутся по
дате создания (первая строка заказа) в периоде. Расход — Google Ads по кампании за тот же период.
Два базиса: A — первая строка заказа Google Ads (основной), C — в заказе есть хоть одна строка Google Ads.
Ограничения: продажи без рекламной метки («Нет метки», «Телефон») не попадают ни в одну кампанию — цена завышена; заказы
последних дней не созрели; на кампанию обычно 3–7 продаж, различия в десятки процентов — внутри шума.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python ea_sales_by_campaign.py [--from 2026-09-27] [--to 2026-10-27] [--customer-id 8826134558] [--limit 131]
"""
import argparse
import re
from collections import defaultdict

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from ea_sales_orders_check import load as load_sheet
from gads_stats import GOOGLE_ADS_YAML

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"


def campaigns_and_spend(customer_id, date_from, date_to):
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    names, spend = {}, defaultdict(float)
    for b in ga.search_stream(customer_id=customer_id, query="SELECT campaign.id, campaign.name FROM campaign"):
        for r in b.results:
            names[str(r.campaign.id)] = r.campaign.name
    q = (f"SELECT campaign.name, metrics.cost_micros FROM campaign "
         f"WHERE segments.date >= '{date_from}' AND segments.date <= '{date_to}'")
    for b in ga.search_stream(customer_id=customer_id, query=q):
        for r in b.results:
            spend[r.campaign.name] += r.metrics.cost_micros / 1e6
    return names, spend


def resolve(utm, names, by_name):
    u = str(utm or "")
    m = re.search(r"_(\d+)_", u)
    if m and m.group(1) in names:
        return names[m.group(1)]
    k = u.strip().lower().rstrip("_")
    if k in by_name:
        return by_name[k]
    return f"[не сопоставлено] {u}" if u else "[пусто]"


def build_orders(df, names):
    by_name = {n.strip().lower().rstrip("_"): n for n in names.values()}
    rows = []
    for oid, g in df[df["order"] != ""].sort_values("ts").groupby("order"):
        gg = g[g["src"] == "Google Ads"]
        first = g.iloc[0]
        rows.append({
            "order": oid, "created": g["ts"].min(), "first_type": first["type"], "first_src": first["src"],
            "any_google": len(gg) > 0,
            "first_camp": resolve(first["utm_campaign"], names, by_name) if first["src"] == "Google Ads" else "",
            "g_camp": resolve(gg.iloc[0]["utm_campaign"], names, by_name) if len(gg) else "",
            "sold": pd.notna(g["sale_date_dt"].max()), "cancelled": pd.notna(g["cancel_date_dt"].max()),
        })
    o = pd.DataFrame(rows)
    o["net"] = o["sold"] & ~o["cancelled"]
    return o


def table(o, camp_col, spend, limit_zl):
    out = []
    for camp, g in o.groupby(camp_col):
        s = spend.get(camp, 0.0)
        out.append({"кампания": camp, "заказов": len(g), "с датой продажи": int(g["sold"].sum()),
                    "из них отменён": int((g["sold"] & g["cancelled"]).sum()), "чистых продаж": int(g["net"].sum()),
                    "отменено без продажи": int((g["cancelled"] & ~g["sold"]).sum()), "расход": round(s),
                    "расход / чистая продажа": round(s / g["net"].sum()) if g["net"].sum() and s else None,
                    f"выше границы {limit_zl:.0f}": (s / g["net"].sum() > limit_zl) if g["net"].sum() and s else None})
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", default=str((pd.Timestamp.now() - pd.Timedelta(days=30)).date()))
    ap.add_argument("--to", dest="date_to", default=str(pd.Timestamp.now().date()))
    ap.add_argument("--customer-id", default="8826134558")
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    ap.add_argument("--limit", type=float, default=131, help="граница цены продажи, zł (30 € × 4.3691)")
    a = ap.parse_args()

    names, spend = campaigns_and_spend(a.customer_id, a.date_from, a.date_to)
    df = load_sheet(SHEET_ID, a.worksheet)
    print(f"Выгрузка CRM: строк {len(df)}, последняя строка {df['ts'].max():%Y-%m-%d %H:%M}, "
          f"последняя продажа {df['sale_date_dt'].max():%Y-%m-%d}")
    o = build_orders(df, names)
    lo, hi = pd.Timestamp(a.date_from, tz="UTC"), pd.Timestamp(a.date_to, tz="UTC") + pd.Timedelta(days=1)
    o = o[(o["created"] >= lo) & (o["created"] < hi)]
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print(f"\nПериод {a.date_from} – {a.date_to}; расход аккаунта {sum(spend.values()):.0f}; заказов {len(o)}")
    print("\n=== Базис A: первая строка заказа — Google Ads ===")
    ta = table(o[o["first_src"] == "Google Ads"], "first_camp", spend, a.limit)
    print(ta.to_string())
    net = int(o[(o["first_src"] == "Google Ads")]["net"].sum())
    print(f"Итого Google (A): расход {sum(spend.values()):.0f}, чистых продаж {net}, "
          f"{'расход / продажа ' + str(round(sum(spend.values()) / net)) if net else 'продаж нет'}")
    print("\n=== Базис C: в заказе есть строка Google Ads (кампания по первой такой строке) ===")
    print(table(o[o["any_google"]], "g_camp", spend, a.limit).to_string())
    print("\nПо типу создания заказа (звонок / форма), базис A:")
    print(pd.crosstab([o[o["first_src"] == "Google Ads"]["first_camp"], o[o["first_src"] == "Google Ads"]["first_type"]],
                      o[o["first_src"] == "Google Ads"]["net"].map({True: "чистая продажа", False: "нет"})).to_string())


if __name__ == "__main__":
    main()
