#!/usr/bin/env python
# coding: utf-8
"""Пауза / включение отдельных объявлений Search-кампании по id. ЗАПИСЬ только с --execute.

Зачем (ProfiMet, 2026-11-09): в группе, которую подключаем к карточке товара, одно объявление говорило про другой товар
(заголовки про тоннели) — его снимаем, остальные работают. Печатает заголовки каждого объявления, чтобы видеть, что именно
меняется. По умолчанию validate_only. Снимок «до» — CSV в Статистика/ клиента; после записи читает обратно.
Откат: тот же вызов с противоположным --status.

    python gads_ad_status.py --customer-id 7552781705 --client-folder ProfiMet --campaign "Search | Poliweglan | Pl" \
        --ad-ids 639567482853 --status PAUSED [--execute]
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def read_ads(ga, E, cid, campaign):
    q = ("SELECT ad_group.name, ad_group_ad.resource_name, ad_group_ad.status, ad_group_ad.ad.id, "
         "ad_group_ad.ad.responsive_search_ad.headlines FROM ad_group_ad "
         f"WHERE campaign.name = '{campaign}' AND ad_group_ad.status != 'REMOVED'")
    out = {}
    for r in ga.search(customer_id=cid, query=q):
        a = r.ad_group_ad
        out[a.ad.id] = {"group": r.ad_group.name, "resource": a.resource_name,
                        "status": E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(a.status),
                        "headlines": [h.text for h in a.ad.responsive_search_ad.headlines]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--ad-ids", nargs="+", required=True, type=int)
    ap.add_argument("--status", required=True, choices=["PAUSED", "ENABLED"])
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    ads = read_ads(ga, E, cid, a.campaign)
    missing = [i for i in a.ad_ids if i not in ads]
    if missing:
        raise SystemExit(f"объявлений нет в кампании: {missing}")
    print(f"Объявления к смене статуса на {a.status}:")
    for i in a.ad_ids:
        r = ads[i]
        print(f"  {r['group']} | {i} | сейчас {r['status']} | заголовки: {' / '.join(r['headlines'][:6])}")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_ad_status_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "ad_id", "status"])
        for i, r in ads.items():
            w.writerow([r["group"], i, r["status"]])
    print("Снимок «до»:", snap)
    svc = client.get_service("AdGroupAdService")
    ops = []
    for i in a.ad_ids:
        op = client.get_type("AdGroupAdOperation")
        op.update.resource_name = ads[i]["resource"]
        op.update.status = getattr(E.AdGroupAdStatusEnum.AdGroupAdStatus, a.status)
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
        ops.append(op)
    try:
        req = client.get_type("MutateAdGroupAdsRequest")
        req.customer_id = cid
        req.operations.extend(ops)
        req.validate_only = not a.execute
        svc.mutate_ad_group_ads(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors:
            print("  ОШИБКА:", e.message)
        raise SystemExit(1)
    if not a.execute:
        print("\nПроверка Google пройдена (validate_only). НИЧЕГО не изменено. Для записи: --execute")
        return
    after = read_ads(ga, E, cid, a.campaign)
    print("\nЧтение обратно:")
    ok = True
    for i in a.ad_ids:
        good = i in after and after[i]["status"] == a.status
        ok &= good
        print(f"  {after[i]['group'] if i in after else '?'} | {i} | {after[i]['status'] if i in after else '?'} | {'OK' if good else 'НЕ СОВПАЛО'}")
    other = "ENABLED" if a.status == "PAUSED" else "PAUSED"
    print(f"\nОткат: тот же вызов с --status {other} и --execute")
    if not ok:
        raise SystemExit("статус не совпал с планом")


if __name__ == "__main__":
    main()
