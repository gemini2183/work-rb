#!/usr/bin/env python
# coding: utf-8
"""Landver LA+BH (2026-11-11): ассеты под страницу Car. ЗАПИСЬ только с --execute (по умолчанию validate_only).

1. Своя структурированная подпись «Types» на кампанию LA+BH (перекрывает аккаунтную только для этой кампании); значения — из блока
   страницы Car «Common car accident situations». Аккаунтная подпись и подпись основной кампании НЕ трогаются.
2. Снять с группы «Car Accident - LA/BH Exact» две картинки пустого перекрёстка (ассеты остаются в библиотеке).
Снимок «до» — Статистика/snapshot_before_labh_assets_<время>.json. Откат: --rollback --execute (вернуть картинки, снять подпись с кампании).

    python gads_labh_assets_fix.py --customer-id 213-621-6123 [--execute] [--rollback]
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.api_core.exceptions import ResourceExhausted

from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import wrap_ga, record_mutate

CAMPAIGN_ID = 24447075486
GROUP_NAME = "Car Accident - LA/BH Exact"
REMOVE_IMAGES = [434394643301, 434580645711]       # ai_car_2_intersection_sq / _wide_landscape
SNIPPET_HEADER = "Types"
SNIPPET_VALUES = ["Rear-End Car Crashes", "Intersection Crashes", "T-Bone Crashes",
                  "Multi-Vehicle Collisions", "Wrong-Way Crashes", "Rideshare Crashes"]
SNAP_DIR = Path(__file__).resolve().parent.parent / "Клиенты" / "Andverpersonalinjury" / "Статистика"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    E = client.enums
    ga = wrap_ga(client.get_service("GoogleAdsService"), "gads_labh_assets_fix")
    for v in SNIPPET_VALUES:
        assert len(v) <= 25, v

    def q(s):
        return list(ga.search(customer_id=cid, query=s))

    grp = q(f"SELECT campaign.id, ad_group.id, ad_group.name FROM ad_group WHERE campaign.id = {CAMPAIGN_ID} AND ad_group.name = '{GROUP_NAME}' AND ad_group.status != REMOVED")
    assert grp, "группа не найдена"
    gid = grp[0].ad_group.id
    links = {r.asset.id: (r.ad_group_asset.resource_name, r.asset.name, r.ad_group_asset.status) for r in q(
        f"SELECT campaign.id, ad_group_asset.resource_name, ad_group_asset.status, asset.id, asset.name FROM ad_group_asset "
        f"WHERE campaign.id = {CAMPAIGN_ID} AND ad_group_asset.field_type = AD_IMAGE AND ad_group_asset.status != REMOVED")}
    snip = q(f"SELECT campaign.id, campaign_asset.resource_name, asset.id, asset.structured_snippet_asset.header, asset.structured_snippet_asset.values "
             f"FROM campaign_asset WHERE campaign.id = {CAMPAIGN_ID} AND campaign_asset.field_type = STRUCTURED_SNIPPET AND campaign_asset.status != REMOVED")
    print(f"картинок группы сейчас: {len(links)}; подпись на кампании: {[(r.asset.structured_snippet_asset.header, list(r.asset.structured_snippet_asset.values)) for r in snip] or 'нет'}")

    ops = []
    if not a.rollback:
        for aid in REMOVE_IMAGES:
            if aid in links:
                op = client.get_type("MutateOperation")
                op.ad_group_asset_operation.remove = links[aid][0]
                ops.append(op)
            else:
                print(f"картинка {aid} уже не привязана")
        if not snip:
            o1 = client.get_type("MutateOperation")
            asset = o1.asset_operation.create
            asset.resource_name = f"customers/{cid}/assets/-1"
            asset.structured_snippet_asset.header = SNIPPET_HEADER
            asset.structured_snippet_asset.values.extend(SNIPPET_VALUES)
            o2 = client.get_type("MutateOperation")
            ca = o2.campaign_asset_operation.create
            ca.campaign = f"customers/{cid}/campaigns/{CAMPAIGN_ID}"
            ca.asset = f"customers/{cid}/assets/-1"
            ca.field_type = E.AssetFieldTypeEnum.STRUCTURED_SNIPPET
            ops += [o1, o2]
        else:
            print("подпись на кампании уже есть — не создаю")
    else:
        for aid in REMOVE_IMAGES:
            if aid not in links:
                op = client.get_type("MutateOperation")
                x = op.ad_group_asset_operation.create
                x.ad_group = f"customers/{cid}/adGroups/{gid}"
                x.asset = f"customers/{cid}/assets/{aid}"
                x.field_type = E.AssetFieldTypeEnum.AD_IMAGE
                ops.append(op)
        for r in snip:
            if list(r.asset.structured_snippet_asset.values) == SNIPPET_VALUES:
                op = client.get_type("MutateOperation")
                op.campaign_asset_operation.remove = r.campaign_asset.resource_name
                ops.append(op)
    print(f"операций: {len(ops)} ({'rollback' if a.rollback else 'fix'}), {'ЗАПИСЬ' if a.execute else 'validate_only'}")
    if not ops:
        return

    if a.execute and not a.rollback:
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        f = SNAP_DIR / f"snapshot_before_labh_assets_{datetime.now():%Y%m%d_%H%M}.json"
        f.write_text(json.dumps({"ad_group_id": gid, "images": {str(k): [v[1], int(v[2])] for k, v in links.items()},
                                 "snippet_before": [[r.asset.structured_snippet_asset.header, list(r.asset.structured_snippet_asset.values)] for r in snip]},
                                ensure_ascii=False, indent=1), encoding="utf-8")
        print("снимок «до»:", f)

    svc = client.get_service("GoogleAdsService")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not a.execute
    record_mutate("gads_labh_assets_fix", len(ops), validate_only=not a.execute)
    try:
        resp = svc.mutate(request=req)
    except ResourceExhausted as ex:
        raise SystemExit(f"ЛИМИТ ОПЕРАЦИЙ Google Ads: {str(ex)[:300]}")
    except GoogleAdsException as ex:
        for err in ex.failure.errors:
            d = err.details.policy_violation_details
            print("ОШИБКА:", err.message, "| политика:", d.key.policy_name, d.key.violating_text, "исключаемо:", d.is_exemptible)
        raise SystemExit(1)
    if not a.execute:
        print("validate_only пройден, ничего не записано")
        return
    print("записано, ответов:", len(resp.mutate_operation_responses))

    print("\n=== Чтение обратно ===")
    n = 0
    for r in q(f"SELECT campaign.id, ad_group_asset.status, ad_group_asset.primary_status, asset.id, asset.name FROM ad_group_asset "
               f"WHERE campaign.id = {CAMPAIGN_ID} AND ad_group_asset.field_type = AD_IMAGE AND ad_group_asset.status != REMOVED"):
        n += 1
        print("  картинка", r.asset.id, r.asset.name, E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.ad_group_asset.status),
              E.AssetLinkPrimaryStatusEnum.AssetLinkPrimaryStatus.Name(r.ad_group_asset.primary_status))
    print("картинок в группе:", n)
    for r in q(f"SELECT campaign.id, campaign_asset.status, campaign_asset.primary_status, campaign_asset.primary_status_reasons, asset.id, asset.structured_snippet_asset.header, "
               f"asset.structured_snippet_asset.values FROM campaign_asset WHERE campaign.id = {CAMPAIGN_ID} AND campaign_asset.field_type = STRUCTURED_SNIPPET AND campaign_asset.status != REMOVED"):
        ca = r.campaign_asset
        print("  подпись кампании:", r.asset.structured_snippet_asset.header, list(r.asset.structured_snippet_asset.values),
              E.AssetLinkStatusEnum.AssetLinkStatus.Name(ca.status), E.AssetLinkPrimaryStatusEnum.AssetLinkPrimaryStatus.Name(ca.primary_status), list(ca.primary_status_reasons))


if __name__ == "__main__":
    main()
