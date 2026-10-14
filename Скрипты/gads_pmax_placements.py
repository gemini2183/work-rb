#!/usr/bin/env python
# coding: utf-8
"""Диагностика PMax-кампании: сеть по дням, площадки, конверсии по действиям, темп месяца — ТОЛЬКО ЧТЕНИЕ.

Зачем: при всплеске расхода / жалобе на спам-заявки одним прогоном ответить на вопросы
  [1] куда ушёл расход (сеть × день: расход, клики, конверсии);
  [2] какие площадки показывались (performance_max_placement_view: только показы, без расхода и кликов;
      за сегодня пусто — задержка, см. База_знаний/Инструменты/Performance-Max-площадки-инвентарь-и-исключения);
  [3] какими действиями пришли конверсии (форма / звонок / другое) по дням;
  [4] темп месяца по кампаниям аккаунта: расход и конверсии с 1-го числа.
Ничего не пишет в кабинет. Исключения площадок — отдельным шагом по протоколу «таблица → да».

Использование:
    python gads_pmax_placements.py --customer-id 8826134558 --campaign-id 23593683252 \
        --since 2026-10-10 --until 2026-10-14 [--top 40] [--csv-dir ..\\Клиенты\\EkspertAgro\\Статистика]
"""
import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML


def enum_name(enum_type, field, value):
    """В этой версии клиента enum приходит числом: переводим номер в имя через descriptor."""
    if hasattr(value, "name"):
        return value.name
    return getattr(_CLIENT.enums, enum_type).DESCRIPTOR.enum_types_by_name[field].values_by_number[int(value)].name


def run(ga, cid, query):
    for batch in ga.search_stream(customer_id=cid, query=query):
        for r in batch.results:
            yield r


def save(csv_dir, name, header, rows):
    if not csv_dir:
        return
    p = Path(csv_dir) / name
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  (сохранено: {p})")


def network_by_day(ga, cid, camp, since, until, csv_dir):
    q = f"""
        SELECT segments.date, segments.ad_network_type, metrics.impressions, metrics.clicks,
               metrics.cost_micros, metrics.conversions
        FROM campaign
        WHERE campaign.id = {camp} AND segments.date BETWEEN '{since}' AND '{until}'
    """
    agg = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for r in run(ga, cid, q):
        k = (r.segments.date, enum_name("AdNetworkTypeEnum", "AdNetworkType", r.segments.ad_network_type))
        m = r.metrics
        a = agg[k]
        a[0] += m.impressions
        a[1] += m.clicks
        a[2] += m.cost_micros / 1e6
        a[3] += m.conversions
    rows = [(d, n, *v) for (d, n), v in sorted(agg.items())]
    print(f"{'дата':10} {'сеть':14} {'показы':>8} {'клики':>6} {'расход':>8} {'конв.':>6} {'zł/конв.':>9}")
    for d, n, imp, clk, cost, conv in rows:
        cpa = f"{cost / conv:.0f}" if conv else "—"
        print(f"{d:10} {n:14} {imp:8d} {clk:6d} {cost:8.2f} {conv:6.1f} {cpa:>9}")
    save(csv_dir, f"pmax_{camp}_network_by_day_{since}_{until}.csv",
         ["date", "network", "impressions", "clicks", "cost", "conversions"], rows)


def placements(ga, cid, camp, since, until, top, csv_dir):
    q = f"""
        SELECT campaign.id, performance_max_placement_view.display_name, performance_max_placement_view.placement_type,
               performance_max_placement_view.placement, segments.date, metrics.impressions
        FROM performance_max_placement_view
        WHERE campaign.id = {camp} AND segments.date BETWEEN '{since}' AND '{until}'
    """
    by_place = defaultdict(lambda: {"type": "", "name": "", "days": defaultdict(int)})
    total = defaultdict(int)
    for r in run(ga, cid, q):
        v = r.performance_max_placement_view
        p = by_place[v.placement]
        p["type"], p["name"] = enum_name("PlacementTypeEnum", "PlacementType", v.placement_type), v.display_name
        p["days"][r.segments.date] += r.metrics.impressions
        total[r.segments.date] += r.metrics.impressions
    days = sorted(total)
    if not days:
        print("  строк нет (за сегодня и свежие даты отчёт пуст — задержка)")
        return
    print(f"  показов всего по дням: " + ", ".join(f"{d}: {total[d]}" for d in days))
    ranked = sorted(by_place.items(), key=lambda kv: -sum(kv[1]["days"].values()))
    all_imp = sum(total.values())
    print(f"{'#':>3} {'тип':14} {'показы':>7} {'доля':>6}  площадка (по дням: " + ", ".join(days) + ")")
    out = []
    for i, (pl, v) in enumerate(ranked[:top], 1):
        s = sum(v["days"].values())
        per_day = [v["days"].get(d, 0) for d in days]
        label = pl if not v["name"] or v["name"] == pl else f"{pl} ({v['name']})"
        print(f"{i:3d} {v['type']:14} {s:7d} {s / all_imp:6.1%}  {label}  {per_day}")
    for pl, v in ranked:
        out.append((pl, v["name"], v["type"], *[v["days"].get(d, 0) for d in days]))
    save(csv_dir, f"pmax_{camp}_placements_{since}_{until}.csv", ["placement", "name", "type", *days], out)
    print(f"  всего площадок: {len(ranked)}; показано топ-{min(top, len(ranked))} из {all_imp} показов")


def conv_by_action(ga, cid, camp, since, until, csv_dir):
    q = f"""
        SELECT segments.date, segments.conversion_action_name, metrics.conversions
        FROM campaign
        WHERE campaign.id = {camp} AND segments.date BETWEEN '{since}' AND '{until}'
          AND metrics.conversions > 0
    """
    agg = defaultdict(float)
    for r in run(ga, cid, q):
        agg[(r.segments.date, r.segments.conversion_action_name)] += r.metrics.conversions
    if not agg:
        print("  конверсий нет")
        return
    for (d, n), v in sorted(agg.items()):
        print(f"  {d}  {n:40} {v:6.1f}")
    save(csv_dir, f"pmax_{camp}_conv_by_action_{since}_{until}.csv",
         ["date", "action", "conversions"], [(d, n, v) for (d, n), v in sorted(agg.items())])


def month_pace(ga, cid, today):
    first = today.replace(day=1)
    q = f"""
        SELECT campaign.name, campaign.status, metrics.cost_micros, metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{first}' AND '{today}' AND metrics.cost_micros > 0
    """
    agg = defaultdict(lambda: [0.0, 0.0, ""])
    for r in run(ga, cid, q):
        a = agg[r.campaign.name]
        a[0] += r.metrics.cost_micros / 1e6
        a[1] += r.metrics.conversions
        a[2] = enum_name("CampaignStatusEnum", "CampaignStatus", r.campaign.status)
    print(f"  период {first} — {today} (конверсии Ads, цели аккаунта; план считается по заявкам Ringostat + Supabase + «Calls from ads»)")
    tc = tv = 0.0
    for n, (cost, conv, st) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
        cpa = f"{cost / conv:.0f}" if conv else "—"
        print(f"  {st:8} {n:40} расход {cost:8.2f}  конв. {conv:6.1f}  zł/конв. {cpa}")
        tc += cost
        tv += conv
    print(f"  ИТОГО расход {tc:.2f}, конв. {tv:.1f}")


_CLIENT = None


def main():
    global _CLIENT
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--csv-dir", default=None)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    _CLIENT = client
    ga = client.get_service("GoogleAdsService")
    print(f"=== PMax {a.campaign_id}: {a.since} — {a.until} ===")
    print("\n[1] Сеть × день:")
    network_by_day(ga, cid, a.campaign_id, a.since, a.until, a.csv_dir)
    print("\n[2] Площадки (показы):")
    placements(ga, cid, a.campaign_id, a.since, a.until, a.top, a.csv_dir)
    print("\n[3] Конверсии по действиям:")
    conv_by_action(ga, cid, a.campaign_id, a.since, a.until, a.csv_dir)
    print("\n[4] Темп месяца по кампаниям аккаунта:")
    month_pace(ga, cid, date.today())


if __name__ == "__main__":
    main()
