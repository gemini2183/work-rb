#!/usr/bin/env python
# coding: utf-8
"""Убирает параметры Roistat (`roistat=…`, `roistat_referrer=…`, `roistat_pos=…`) из конечных URL: объявления, группы
ассетов PMax, сайтлинки. Решение пользователя 2026-10-09: Roistat не используется, убрать везде.

Остальные параметры URL (utm, {ValueTrack}) и якорь #… сохраняются как были. Меняются только final_urls.
Объявления в архивных кампаниях на паузе тоже правятся (показов нет, поведение не меняется).

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
Снимок «до» (тип, id, старые URL) — CSV в Статистика/ клиента. После записи считает, сколько объектов с `roistat` осталось.

Использование:
    python gads_strip_roistat.py --customer-id 7552781705 --client-folder ProfiMet
    ... --execute
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


SKIPPED = {}


def strip_url(url):
    base, hsh_sep, hsh = url.partition("#")
    path, q_sep, query = base.partition("?")
    if not q_sep:
        return url
    kept = [p for p in query.split("&") if not p.lower().startswith("roistat")]
    new = path + ("?" + "&".join(kept) if kept else "")
    return new + (hsh_sep + hsh if hsh_sep else "")


def find_all(client, ga, cid):
    rows = []
    q = ("SELECT campaign.name, ad_group_ad.ad.resource_name, ad_group_ad.ad.id, ad_group_ad.ad.final_urls, ad_group_ad.ad.type "
         "FROM ad_group_ad WHERE ad_group_ad.status != 'REMOVED'")
    for r in ga.search(customer_id=cid, query=q):
        urls = list(r.ad_group_ad.ad.final_urls)
        if client.enums.AdTypeEnum.AdType.Name(r.ad_group_ad.ad.type_) == "EXPANDED_TEXT_AD":
            if any("roistat" in u.lower() for u in urls):
                SKIPPED["expanded_text_ad"] = SKIPPED.get("expanded_text_ad", 0) + 1  # Google не даёт править такие объявления
            continue
        if any("roistat" in u.lower() for u in urls):
            rows.append({"kind": "ad", "name": r.campaign.name, "id": r.ad_group_ad.ad.id,
                         "resource": r.ad_group_ad.ad.resource_name, "urls": urls})
    q = "SELECT asset_group.resource_name, asset_group.id, asset_group.name, asset_group.final_urls FROM asset_group WHERE asset_group.status != 'REMOVED'"
    for r in ga.search(customer_id=cid, query=q):
        urls = list(r.asset_group.final_urls)
        if any("roistat" in u.lower() for u in urls):
            rows.append({"kind": "asset_group", "name": r.asset_group.name, "id": r.asset_group.id,
                         "resource": r.asset_group.resource_name, "urls": urls})
    q = "SELECT asset.resource_name, asset.id, asset.final_urls, asset.sitelink_asset.link_text FROM asset WHERE asset.type = 'SITELINK'"
    for r in ga.search(customer_id=cid, query=q):
        urls = list(r.asset.final_urls)
        if any("roistat" in u.lower() for u in urls):
            rows.append({"kind": "sitelink", "name": r.asset.sitelink_asset.link_text, "id": r.asset.id,
                         "resource": r.asset.resource_name, "urls": urls})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    rows = find_all(client, ga, cid)
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("Найдено с Roistat:", kinds, "| пропущено (Google не даёт править):", SKIPPED)
    if not rows:
        return
    ex = rows[0]
    print("Пример до :", ex["urls"][0][:200])
    print("Пример после:", strip_url(ex["urls"][0])[:200])

    snap = client_stats_dir(args.client_folder) / f"snapshot_before_strip_roistat_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["kind", "name", "id", "resource", "urls_before"])
        for r in rows:
            w.writerow([r["kind"], r["name"], r["id"], r["resource"], " | ".join(r["urls"])])
    print("Снимок «до»:", snap)

    failed = 0
    for kind, svc_name, req_name, method, op_name, getter in (
            ("ad", "AdService", "MutateAdsRequest", "mutate_ads", "AdOperation", None),
            ("asset_group", "AssetGroupService", "MutateAssetGroupsRequest", "mutate_asset_groups", "AssetGroupOperation", None),
            ("sitelink", "AssetService", "MutateAssetsRequest", "mutate_assets", "AssetOperation", None)):
        items = [r for r in rows if r["kind"] == kind]
        if not items:
            continue
        ops = []
        for r in items:
            op = client.get_type(op_name)
            obj = op.update
            obj.resource_name = r["resource"]
            obj.final_urls.extend([strip_url(u) for u in r["urls"]])
            op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["final_urls"]))
            ops.append(op)
        req = client.get_type(req_name)
        req.customer_id = cid
        req.operations.extend(ops)
        req.validate_only = not args.execute
        try:
            getattr(client.get_service(svc_name), method)(request=req)
            print(f"  {kind}: {'записано' if args.execute else 'проверка пройдена'} ({len(ops)})")
        except GoogleAdsException as ex_:
            failed += 1
            print(f"  {kind}: ОШИБКА от Google Ads:")
            for err in ex_.failure.errors[:4]:
                print("    -", err.message)
    if not args.execute:
        print("НИЧЕГО не изменено (validate_only)." + (f" Ошибок проверки: {failed}." if failed else ""))
        return
    left = {}
    SKIPPED.clear()
    for r in find_all(client, ga, cid):
        left[r["kind"]] = left.get(r["kind"], 0) + 1
    print("Прочитано обратно: осталось с Roistat (правимых):", left or "0", "| не правимых старых объявлений:", SKIPPED)


if __name__ == "__main__":
    main()
