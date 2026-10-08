#!/usr/bin/env python
# coding: utf-8
"""Меняет статус группы ассетов Performance Max (ENABLED / PAUSED) через Google Ads API.

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
Снимок «до» (статус, оценка, адреса, расход за 30 дней) — в Статистика/ клиента; после записи статус читается обратно.

Использование:
    python gads_set_asset_group_status.py --customer-id 7552781705 --client-folder ProfiMet \
        --asset-group-id 6753581516 --status PAUSED
    ... --execute
"""
import argparse
import json
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--asset-group-id", required=True)
    ap.add_argument("--status", required=True, choices=["ENABLED", "PAUSED"])
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    st = client.enums.AssetGroupStatusEnum.AssetGroupStatus

    def read():
        q = ("SELECT campaign.name, asset_group.name, asset_group.status, asset_group.ad_strength, asset_group.final_urls "
             f"FROM asset_group WHERE asset_group.id = {args.asset_group_id}")
        for r in ga.search(customer_id=cid, query=q):
            return {
                "campaign": r.campaign.name,
                "name": r.asset_group.name,
                "status": st.Name(r.asset_group.status),
                "ad_strength": client.enums.AdStrengthEnum.AdStrength.Name(r.asset_group.ad_strength),
                "final_urls": list(r.asset_group.final_urls),
            }
        raise SystemExit("группа ассетов не найдена")

    before = read()
    print(f"{before['campaign']} / {before['name']}: статус до = {before['status']}, оценка {before['ad_strength']}")
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_asset_group_status_{args.asset_group_id}_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Снимок «до»: {snap}")

    op = client.get_type("AssetGroupOperation")
    op.update.resource_name = client.get_service("AssetGroupService").asset_group_path(cid, args.asset_group_id)
    op.update.status = getattr(st, args.status)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    req = client.get_type("MutateAssetGroupsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not args.execute
    try:
        client.get_service("AssetGroupService").mutate_asset_groups(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            print("  -", err.message)
        raise SystemExit(1)

    if not args.execute:
        print(f"Проверка пройдена. НИЧЕГО не изменено (validate_only). Было бы: {before['status']} -> {args.status}")
        return
    after = read()
    print(f"Прочитано обратно: статус = {after['status']}")


if __name__ == "__main__":
    main()
