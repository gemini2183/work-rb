#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: цена рекламной продажи по кампаниям и по группам Search — ТОЛЬКО ЧТЕНИЕ (09.11.2026, задача «Цена продажи по кампаниям»).

Продажа = проданный заказ без отмены (таблица CRM клиента «Данные по продажам», лист mocnaszklarnia.pl), дата продажи в окне --from..--to.
Кампания и группа — из метки ПЕРВОГО обращения номера за 60 дней до заказа (как в profimet_sales_trend.py): `utm_campaign` (id кампании
внутри метки) и `gid_<id группы>` в `utm_content`. Звонки по номеру из объявлений и обращения без метки кампании в строку кампании не попадают
(у них кампании нет). Расход — Google Ads API за те же даты, ВСЕ дни (включая паузы).
Это не «цена заявки»: продажа появляется в таблице через день-два после заказа (медиана лага 1 день), последние дни окна могут быть неполными.
P(цена ≤ цели) — грубая оценка по Пуассону (flat prior), без поправки на потерянные метки (продажи в «Нет метки» кампании не получают → цена завышена).

Запуск (из папки Скрипты): PYTHONUTF8=1 python profimet_price_per_sale_by_campaign.py --from 2026-10-16 --to 2026-11-07 [--target 30]
"""
import argparse
import math
import re
from datetime import date

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet

CUSTOMER_ID = "7552781705"
SITE = "mocnaszklarnia.pl"
WINDOW_DAYS = 60


def p_price_below(cost, n, target):
    """P(истинная цена продажи ≤ target) ≈ P(Пуассон(cost/target) ≤ n−1); при n=0 — 0."""
    if n <= 0:
        return 0.0
    lam = cost / target
    return sum(math.exp(-lam) * lam ** k / math.factorial(k) for k in range(n))


def first_touch_sales(sheet, d0, d1):
    s = sheet[sheet["site"] == SITE]
    by_phone = {p: g for p, g in s.groupby("p9") if p}
    rows = []
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd or any(grp["cancel_date"] != ""):
            continue
        sale = pd.Timestamp(min(sd)).date()
        if not (d0 <= sale <= d1):
            continue
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        parts = [by_phone[p] for p in set(grp["p9"]) if p in by_phone]
        t = pd.concat(parts) if parts else grp
        t = t[(t["ts"] >= t0 - pd.Timedelta(days=WINDOW_DAYS)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        first = t.iloc[0] if not t.empty else grp.iloc[0]
        m = re.search(r"gid_(\d+)", first["utm_content"] or "")
        rows.append({"order": order, "sale": sale, "src": first["src"] or "Нет метки", "camp": first["utm_campaign"] or "",
                     "gid": int(m.group(1)) if m else None})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--target", type=float, default=30.0, help="красная линия клиента, € за продажу")
    ap.add_argument("--min-cost", type=float, default=20.0, help="не печатать группы с расходом меньше, €")
    a = ap.parse_args()
    d0, d1 = date.fromisoformat(a.frm), date.fromisoformat(a.to)

    ga = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).get_service("GoogleAdsService")
    camp_cost, camp_name, grp_cost, grp_name = {}, {}, {}, {}
    for r in ga.search(customer_id=CUSTOMER_ID, query=(
            "SELECT campaign.id, campaign.name, segments.date, metrics.cost_micros FROM campaign "
            f"WHERE segments.date BETWEEN '{d0}' AND '{d1}'")):
        camp_cost[r.campaign.id] = camp_cost.get(r.campaign.id, 0) + r.metrics.cost_micros / 1e6
        camp_name[r.campaign.id] = r.campaign.name
    for r in ga.search(customer_id=CUSTOMER_ID, query=(
            "SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status, segments.date, metrics.cost_micros FROM ad_group "
            f"WHERE campaign.advertising_channel_type = 'SEARCH' AND segments.date BETWEEN '{d0}' AND '{d1}'")):
        k = r.ad_group.id
        grp_cost[k] = grp_cost.get(k, 0) + r.metrics.cost_micros / 1e6
        grp_name[k] = (r.campaign.id, r.ad_group.name, "вкл" if int(r.ad_group.status) == 2 else "пауза")

    sales = first_touch_sales(load_sheet(SHEET_ID), d0, d1)
    g = sales[sales["src"] == "Google Ads"]
    print(f"=== Цена рекламной продажи Google Ads, продажи {d0} … {d1}, цель {a.target:g} € (только чтение) ===")
    print(f"Продаж всего в окне (все источники, без отмен): {len(sales)}; с первым обращением Google Ads: {len(g)}; "
          f"без метки кампании у Google: {int((g['camp'] == '').sum() + g['camp'].isin(['calls_from_ads']).sum())}")
    print("\nПо кампаниям (кампания из utm_campaign; расход — все дни окна):")
    print(f"{'кампания':32} {'расход':>8} {'продаж':>7} {'цена':>7} {'P(≤цель)':>9}")
    total_c = total_n = 0
    for cid, cost in sorted(camp_cost.items(), key=lambda kv: -kv[1]):
        if cost < a.min_cost:
            continue
        n = int(g["camp"].str.contains(str(cid)).sum())
        total_c += cost
        total_n += n
        price = f"{cost / n:7.1f}" if n else "      —"
        print(f"{camp_name[cid][:32]:32} {cost:8.1f} {n:7d} {price} {p_price_below(cost, n, a.target):9.0%}")
    print(f"{'ИТОГО (показанные кампании)':32} {total_c:8.1f} {total_n:7d} {total_c / total_n if total_n else float('nan'):7.1f}")
    print("\nПо группам Search (gid из utm_content):")
    print(f"{'кампания / группа':58} {'статус':6} {'расход':>8} {'продаж':>7} {'цена':>7} {'P(≤цель)':>9}")
    for k, cost in sorted(grp_cost.items(), key=lambda kv: (grp_name[kv[0]][0], -kv[1])):
        if cost < a.min_cost:
            continue
        n = int((g["gid"] == k).sum())
        cid, gname, st = grp_name[k]
        label = f"{camp_name.get(cid, cid)[:24]} / {gname[:30]}"
        price = f"{cost / n:7.1f}" if n else "      —"
        print(f"{label:58} {st:6} {cost:8.1f} {n:7d} {price} {p_price_below(cost, n, a.target):9.0%}")
    print("\nОговорки: продажи в «Нет метки» и звонки из объявлений кампании не получают, цена завышена; выборки в группах малы (единицы продаж);")
    print("последние дни окна могут быть неполными (продажа попадает в таблицу через 1–2 дня).")


if __name__ == "__main__":
    main()
