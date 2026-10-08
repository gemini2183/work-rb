#!/usr/bin/env python
# coding: utf-8
"""Убирает из групп ассетов кампании (отвязывает) тексты, содержащие заданную подстроку.

Нужен, чтобы быстро снять из рекламы неподтверждённые формулировки (например, «100 000+ zamówień rocznie»).
Ассеты в аккаунте остаются, удаляется только привязка к группам; можно привязать обратно по снимку «до».

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
Снимок «до» (группа, тип поля, текст, resource_name привязки) — CSV в Статистика/ клиента; после записи читает привязки обратно.

Использование:
    python gads_remove_asset_group_texts.py --customer-id 7552781705 --client-folder ProfiMet --campaign-id 23775369828 --contains "100 000"
    ... --execute
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def find(client, ga, cid, campaign_id, needles):
    E = client.enums
    q = ("SELECT campaign.id, asset_group.name, asset_group.status, asset_group_asset.resource_name, asset_group_asset.field_type, asset.text_asset.text "
         f"FROM asset_group_asset WHERE campaign.id = {campaign_id} AND asset_group_asset.status != 'REMOVED'")
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        t = r.asset.text_asset.text
        if t and any(n in t for n in needles):
            rows.append({"group": r.asset_group.name,
                         "group_status": E.AssetGroupStatusEnum.AssetGroupStatus.Name(r.asset_group.status),
                         "field": E.AssetFieldTypeEnum.AssetFieldType.Name(r.asset_group_asset.field_type),
                         "text": t, "link": r.asset_group_asset.resource_name})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--contains", required=True, nargs="+", help="подстроки (достаточно одной в тексте)")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    rows = find(client, ga, cid, args.campaign_id, args.contains)
    print(f"найдено привязок: {len(rows)}")
    for r in rows:
        print(" ", r["group"][:24], "|", r["group_status"], "|", r["field"], "|", r["text"][:70])
    if not rows:
        return
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_remove_texts_{args.campaign_id}_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("Снимок «до»:", snap)

    ops = []
    for r in rows:
        op = client.get_type("AssetGroupAssetOperation")
        op.remove = r["link"]
        ops.append(op)
    req = client.get_type("MutateAssetGroupAssetsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not args.execute
    try:
        client.get_service("AssetGroupAssetService").mutate_asset_group_assets(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:5]:
            print("  -", err.message)
        raise SystemExit(1)
    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не изменено (validate_only).")
        return
    left = find(client, ga, cid, args.campaign_id, args.contains)
    print(f"Прочитано обратно: привязок с этими текстами осталось {len(left)}")


if __name__ == "__main__":
    main()
