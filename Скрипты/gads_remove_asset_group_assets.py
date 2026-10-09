#!/usr/bin/env python
# coding: utf-8
"""Отвязывает от групп ассетов PMax-кампании ассеты по id (например, видео, созданные Google автоматически).

Ассеты в аккаунте остаются, удаляется только привязка к группам; вернуть можно по снимку «до».
Google может создать автовидео снова, если автоопция включена: проверить `campaign.asset_automation_settings`.

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись — только с --execute. Снимок «до» — CSV в Статистика/ клиента;
после записи читает привязки обратно.

Использование:
    python gads_remove_asset_group_assets.py --customer-id 7552781705 --client-folder ProfiMet \
        --campaign-id 24332178236 --asset-ids 428471587886 428471588453 428475080309 428475080483
    ... --execute
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def find(client, ga, cid, campaign_id, asset_ids):
    E = client.enums
    ids = ", ".join(str(i) for i in asset_ids)
    q = ("SELECT asset_group.name, asset_group_asset.resource_name, asset_group_asset.field_type, asset_group_asset.status, asset.id, asset.name "
         f"FROM asset_group_asset WHERE campaign.id = {campaign_id} AND asset.id IN ({ids}) AND asset_group_asset.status != 'REMOVED'")
    return [{"group": r.asset_group.name, "field": E.AssetFieldTypeEnum.AssetFieldType.Name(r.asset_group_asset.field_type),
             "asset_id": r.asset.id, "link": r.asset_group_asset.resource_name} for r in ga.search(customer_id=cid, query=q)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--asset-ids", required=True, nargs="+", type=int)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    rows = find(client, ga, cid, args.campaign_id, args.asset_ids)
    print(f"найдено привязок: {len(rows)}")
    for r in rows:
        print(" ", r["group"], "|", r["field"], "|", r["asset_id"])
    if not rows:
        return
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_remove_assets_{args.campaign_id}_{datetime.now():%Y%m%d_%H%M}.csv"
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
    left = find(client, ga, cid, args.campaign_id, args.asset_ids)
    print(f"Прочитано обратно: привязок этих ассетов осталось {len(left)}")


if __name__ == "__main__":
    main()
