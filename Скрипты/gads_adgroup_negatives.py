#!/usr/bin/env python
# coding: utf-8
"""Минус-слова на уровне ГРУПП объявлений Search-кампании. ЗАПИСЬ только с --execute (по умолчанию validate_only).

Зачем (Landver, 2026-10-26): «near me» отрезаем во всех группах, кроме «Car Accident - LA/BH Exact» (там ключи с городом).
Кампанийный минус отрезал бы и её, поэтому нужны минусы групп. Add пропускает уже существующие; снимок «до» — CSV в Статистика/ клиента;
после записи читает обратно. Откат — --remove (снимает именно эти фразы в этих группах).

    python gads_adgroup_negatives.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" \
        --groups "Car Accident" "Car Accident - Exact" --texts "near me" "nearby" --match PHRASE [--execute] [--remove]
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def read_negs(ga, E, cid, campaign):
    q = ("SELECT ad_group.name, ad_group.resource_name, ad_group_criterion.resource_name, ad_group_criterion.keyword.text, "
         "ad_group_criterion.keyword.match_type FROM ad_group_criterion "
         f"WHERE campaign.name = '{campaign}' AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.negative = TRUE "
         "AND ad_group_criterion.status != 'REMOVED' AND ad_group.status != 'REMOVED'")
    return [(r.ad_group.name, r.ad_group.resource_name, r.ad_group_criterion.resource_name, r.ad_group_criterion.keyword.text.lower(),
             E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.ad_group_criterion.keyword.match_type)) for r in ga.search(customer_id=cid, query=q)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--groups", nargs="+", required=True, help="полные имена групп")
    ap.add_argument("--texts", nargs="+", required=True)
    ap.add_argument("--match", choices=["EXACT", "PHRASE", "BROAD"], default="PHRASE")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    groups = {r.ad_group.name: r.ad_group.resource_name for r in ga.search(
        customer_id=cid, query=f"SELECT ad_group.name, ad_group.resource_name FROM ad_group WHERE campaign.name = '{a.campaign}' AND ad_group.status != 'REMOVED'")}
    miss = [g for g in a.groups if g not in groups]
    if miss:
        raise SystemExit(f"групп нет в кампании: {miss}")
    before = read_negs(ga, E, cid, a.campaign)
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_adgroup_negatives_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["group", "group_resource", "criterion_resource", "text", "match"]); w.writerows(before)
    print(f"Снимок «до»: {snap} (групповых минусов в кампании: {len(before)})")
    texts = [t.lower() for t in a.texts]
    have = {(x[0], x[3], x[4]) for x in before}
    svc = client.get_service("AdGroupCriterionService")
    ops, plan = [], []
    if a.remove:
        for x in before:
            if x[0] in a.groups and x[3] in texts and x[4] == a.match:
                op = client.get_type("AdGroupCriterionOperation"); op.remove = x[2]; ops.append(op); plan.append((x[0], x[3]))
    else:
        for g in a.groups:
            for t in texts:
                if (g, t, a.match) in have:
                    print(f"  уже есть: {g} | {t} | {a.match}")
                    continue
                op = client.get_type("AdGroupCriterionOperation")
                c = op.create
                c.ad_group = groups[g]
                c.negative = True
                c.keyword.text = t
                c.keyword.match_type = getattr(E.KeywordMatchTypeEnum, a.match)
                ops.append(op); plan.append((g, t))
    print(f"\n{'К снятию' if a.remove else 'К добавлению'}: {len(ops)}")
    for g, t in plan:
        print(f"  {g} | {t} | {a.match}")
    if not ops:
        return
    try:
        req = client.get_type("MutateAdGroupCriteriaRequest")
        req.customer_id = cid
        req.operations.extend(ops)
        req.validate_only = not a.execute
        svc.mutate_ad_group_criteria(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors:
            print("  ОШИБКА:", e.message)
        raise SystemExit(1)
    if not a.execute:
        print("\nПроверка Google пройдена (validate_only). НИЧЕГО не изменено. Для записи: --execute")
        return
    after = {(x[0], x[3], x[4]) for x in read_negs(ga, E, cid, a.campaign)}
    print("\nЧтение обратно:")
    ok = True
    for g, t in plan:
        present = (g, t, a.match) in after
        good = (not present) if a.remove else present
        ok &= good
        print(f"  {g} | {t} | {'нет' if a.remove and not present else ('есть' if present else 'нет')} | {'OK' if good else 'НЕ СОВПАЛО'}")
    print("\nОткат: те же аргументы с --remove --execute" if not a.remove else "\nСнято.")
    if not ok:
        raise SystemExit("часть не совпала с планом")


if __name__ == "__main__":
    main()
