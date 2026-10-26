#!/usr/bin/env python
# coding: utf-8
"""Смена конечного URL (final_urls) у объявлений Search-кампании по группам. ЗАПИСЬ только с --execute.

Зачем (Landver, 2026-10-26): новая посадочная страница подключается к существующим группам без новых групп и копий ключей:
адрес задан только в объявлениях (у ключей своих адресов нет), поэтому смена адреса = правка final_urls у объявлений групп.
Меняются только объявления (включённые и на паузе, не удалённые), у которых final_urls сейчас ровно --from-url; остальные не трогаются.
Шаблон отслеживания кампании ({lpurl}?utm_…) подставляет метки к любому адресу, поэтому метки сохраняются.

По умолчанию validate_only (Google проверяет, ничего не меняет). Снимок «до» — CSV в Статистика/ клиента; после записи читает обратно.
Откат: те же аргументы с --from-url и --to-url наоборот (команда печатается в конце).

    python gads_ad_final_url.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" \
        --groups "Car Accident" "Auto Accident" "Car Accident - Exact" "Car Accident - LA/BH Exact" \
        --from-url https://landverpersonalinjury.tilda.ws/california-car-truck-accident \
        --to-url https://landverpersonalinjury.tilda.ws/california-car-accident-lawyer [--execute]
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
    q = ("SELECT ad_group.name, ad_group.status, ad_group_ad.status, ad_group_ad.ad.id, ad_group_ad.ad.resource_name, "
         "ad_group_ad.ad.final_urls, ad_group_ad.policy_summary.approval_status FROM ad_group_ad "
         f"WHERE campaign.name = '{campaign}' AND ad_group_ad.status != 'REMOVED' AND ad_group.status != 'REMOVED'")
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        a = r.ad_group_ad
        rows.append({"group": r.ad_group.name, "ad_id": a.ad.id, "resource": a.ad.resource_name,
                     "status": E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(a.status),
                     "approval": E.PolicyApprovalStatusEnum.PolicyApprovalStatus.Name(a.policy_summary.approval_status),
                     "final_urls": list(a.ad.final_urls)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--groups", nargs="+", required=True, help="полные имена групп")
    ap.add_argument("--from-url", required=True)
    ap.add_argument("--to-url", required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    rows = read_ads(ga, E, cid, a.campaign)
    missing = [g for g in a.groups if g not in {r["group"] for r in rows}]
    if missing:
        raise SystemExit(f"групп нет в кампании: {missing}")
    todo = [r for r in rows if r["group"] in a.groups and r["final_urls"] == [a.from_url]]
    skip = [r for r in rows if r["group"] in a.groups and r["final_urls"] != [a.from_url]]
    print(f"Объявления к смене ({len(todo)}):")
    for r in todo:
        print(f"  {r['group']} | объявление {r['ad_id']} | {r['status']} | {r['approval']} | {a.from_url} -> {a.to_url}")
    for r in skip:
        print(f"  ПРОПУСК {r['group']} | объявление {r['ad_id']} | адрес сейчас {r['final_urls']}")
    others = [r for r in rows if r["group"] not in a.groups]
    print(f"Не трогаем: объявлений в других группах {len(others)} ({sorted({r['group'] for r in others})})")
    if not todo:
        raise SystemExit("нечего менять")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_final_url_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "ad_id", "status", "final_url"])
        for r in rows:
            w.writerow([r["group"], r["ad_id"], r["status"], "|".join(r["final_urls"])])
    print("Снимок «до»:", snap)
    svc = client.get_service("AdService")
    ops = []
    for r in todo:
        op = client.get_type("AdOperation")
        op.update.resource_name = r["resource"]
        op.update.final_urls.append(a.to_url)
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["final_urls"]))
        ops.append(op)
    try:
        req = client.get_type("MutateAdsRequest")
        req.customer_id = cid
        req.operations.extend(ops)
        req.validate_only = not a.execute
        svc.mutate_ads(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors:
            print("  ОШИБКА:", e.message)
        raise SystemExit(1)
    if not a.execute:
        print("\nПроверка Google пройдена (validate_only). НИЧЕГО не изменено. Для записи: --execute")
        return
    after = {r["ad_id"]: r for r in read_ads(ga, E, cid, a.campaign)}
    print("\nЧтение обратно:")
    ok = True
    for r in todo:
        n = after.get(r["ad_id"])
        good = bool(n) and n["final_urls"] == [a.to_url]
        ok &= good
        print(f"  {r['group']} | {r['ad_id']} | {n['status'] if n else '?'} | {n['approval'] if n else '?'} | {n['final_urls'] if n else 'объявление не найдено'} | {'OK' if good else 'НЕ СОВПАЛО'}")
    print("\nОткат: те же аргументы с --from-url и --to-url наоборот и --execute")
    if not ok:
        raise SystemExit("часть объявлений не совпала с планом")


if __name__ == "__main__":
    main()
