#!/usr/bin/env python
# coding: utf-8
"""A/B текстов RSA: новое объявление против старого в той же группе — ТОЛЬКО ЧТЕНИЕ.

Берёт файл соответствий «старое → новое» (его оставляет скрипт замены объявлений, например
`Клиенты/ProfiMet/Статистика/rsa_replace_map_20261013_1401.csv`) и сравнивает показы, клики, CTR и долю показов вверху
страницы (слот TOP) по парам. Сравнение внутри одной группы в одни и те же дни — позиция и расписание у пары общие.
Дни выбираются явно (--dates): ПЕРЕД выбором прогнать `window_check.py` и взять только чистые дни; сокращённые (суббота)
и переходные считать отдельно или не брать. Итог — по сумме показов и кликов, а не по среднему CTR пар.
Порог из реестра эксперимента (ProfiMet Э-14): ≥ 100 показов на объявление; различие CTR ≥ 1.0 п.п.

    python rsa_ab_compare.py --customer-id 7552781705 --map ../Клиенты/ProfiMet/Статистика/rsa_replace_map_20261013_1401.csv \
        --dates 2026-10-14 2026-10-15 2026-10-16 [--min-impr 100]
"""
import argparse
import csv
import io
import sys
from collections import defaultdict

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--min-impr", type=int, default=100)
    a = ap.parse_args()
    pairs = []
    with open(a.map, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            pairs.append((str(r["old_ad_id"]), str(r["new_ad_id"]), r["campaign"], r["ad_group"]))
    ids = {i for p in pairs for i in p[:2]}
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc, E = client.get_service("GoogleAdsService"), client.enums
    want = set(a.dates)
    q = (f"SELECT ad_group_ad.ad.id, segments.date, segments.slot, metrics.impressions, metrics.clicks "
         f"FROM ad_group_ad WHERE segments.date BETWEEN '{min(want)}' AND '{max(want)}' AND ad_group_ad.ad.id IN ({','.join(sorted(ids))})")
    m = defaultdict(lambda: {"i": 0, "c": 0, "top": 0})
    by_day = defaultdict(lambda: {"old": [0, 0], "new": [0, 0]})
    kind = {}
    for old, new, *_ in pairs:
        kind[old], kind[new] = "old", "new"
    for r in svc.search(customer_id=a.customer_id, query=q):
        if r.segments.date not in want:
            continue
        ad = str(r.ad_group_ad.ad.id)
        x = m[ad]
        x["i"] += r.metrics.impressions
        x["c"] += r.metrics.clicks
        if E.SlotEnum.Slot.Name(r.segments.slot) == "SEARCH_TOP":
            x["top"] += r.metrics.impressions
        d = by_day[r.segments.date][kind[ad]]
        d[0] += r.metrics.impressions
        d[1] += r.metrics.clicks

    def ctr(c, i):
        return f"{100 * c / i:5.1f}%" if i else "   —  "

    print(f"дни: {', '.join(a.dates)}; порог показов на объявление: {a.min_impr}")
    print("кампания / группа                          | СТАРОЕ: показы клики CTR  вверху | НОВОЕ: показы клики CTR  вверху | Δ CTR, п.п.")
    tot = {"old": [0, 0, 0], "new": [0, 0, 0]}
    enough = {"old": [0, 0], "new": [0, 0]}
    for old, new, camp, grp in pairs:
        o, n = m[old], m[new]
        for k, x in (("old", o), ("new", n)):
            tot[k][0] += x["i"]; tot[k][1] += x["c"]; tot[k][2] += x["top"]
        ok = o["i"] >= a.min_impr and n["i"] >= a.min_impr
        if ok:
            for k, x in (("old", o), ("new", n)):
                enough[k][0] += x["i"]; enough[k][1] += x["c"]
        delta = (100 * n["c"] / n["i"] - 100 * o["c"] / o["i"]) if o["i"] and n["i"] else None
        top = lambda x: f"{100 * x['top'] / x['i']:3.0f}%" if x["i"] else "  — "
        print(f"{(camp.split('|')[1].strip() if '|' in camp else camp)[:12]:12} {grp[:28]:28} | "
              f"{o['i']:6} {o['c']:5} {ctr(o['c'], o['i'])} {top(o)} | {n['i']:6} {n['c']:5} {ctr(n['c'], n['i'])} {top(n)} | "
              f"{'' if delta is None else f'{delta:+5.1f}'}{'' if ok else '  (< порога)'}")
    print("\nИТОГО по всем парам (все показы):")
    for k, name in (("old", "старые"), ("new", "новые")):
        i, c, t = tot[k]
        print(f"  {name}: показы {i}, клики {c}, CTR {ctr(c, i)}, вверху {100 * t / i if i else 0:.0f}%")
    print("ИТОГО по парам, где у обоих ≥ порога показов:")
    for k, name in (("old", "старые"), ("new", "новые")):
        i, c = enough[k]
        print(f"  {name}: показы {i}, клики {c}, CTR {ctr(c, i)}")
    print("\nПо дням (все пары вместе):")
    for d in sorted(by_day):
        o, n = by_day[d]["old"], by_day[d]["new"]
        print(f"  {d}: старые {o[0]} показов / {o[1]} кликов ({ctr(o[1], o[0])}); новые {n[0]} / {n[1]} ({ctr(n[1], n[0])})")


if __name__ == "__main__":
    main()
