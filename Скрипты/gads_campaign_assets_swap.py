#!/usr/bin/env python
# coding: utf-8
"""Замена быстрых ссылок и уточнений на уровне КАМПАНИИ по JSON-плану. ЗАПИСЬ только с --execute (по умолчанию validate_only).

Зачем (ProfiMet `search / montaz`, 2026-11-12): после согласования в таблице заменить набор быстрых ссылок и два уточнения.
Отвязывает от кампании перечисленные ассеты (сами ассеты не удаляются, у других кампаний остаются), создаёт новые
быстрые ссылки и уточнения и привязывает их к кампании. Одна атомарная транзакция. Снимок «до» — в Статистика/ клиента.
Откат: привязать старые ассеты обратно (id в снимке) и отвязать новые.

План (JSON):
  {"customer_id": "7552781705", "client_folder": "ProfiMet", "campaign": "search / montaz",
   "unlink_assets": [438636795103, ...],                      # id ассетов, привязанных к кампании (SITELINK / CALLOUT)
   "sitelinks": [{"text": "..", "desc1": "..", "desc2": "..", "url": "https://.."}],   # text <=25, desc <=35
   "callouts": ["..."]}                                       # <=25

    python gads_campaign_assets_swap.py --plan "Клиенты/ProfiMet/Работы/2026-11-12_монтаж_тест/файлы/assets_swap_plan.json"
    python gads_campaign_assets_swap.py --plan ... --execute
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir, VAULT_ROOT
from gads_quota_ledger import record_mutate
from gads_stats import GOOGLE_ADS_YAML

SCRIPT = "gads_campaign_assets_swap"


def read_links(ga, cid, camp_id, E):
    rows = []
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_asset.resource_name, campaign_asset.field_type, campaign_asset.status, "
            "asset.id, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, "
            "asset.final_urls, asset.callout_asset.callout_text FROM campaign_asset "
            f"WHERE campaign.id = {camp_id} AND campaign_asset.field_type IN (SITELINK, CALLOUT) "
            "AND campaign_asset.status != 'REMOVED'")):
        ft = E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type)
        rows.append({"rn": r.campaign_asset.resource_name, "type": ft, "asset_id": r.asset.id,
                     "text": r.asset.sitelink_asset.link_text or r.asset.callout_asset.callout_text,
                     "d1": r.asset.sitelink_asset.description1, "d2": r.asset.sitelink_asset.description2,
                     "url": ";".join(r.asset.final_urls)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    p = Path(args.plan)
    plan = json.loads((p if p.is_absolute() else VAULT_ROOT / p).read_text(encoding="utf-8"))
    cid = plan["customer_id"]
    for s in plan.get("sitelinks", []):
        assert len(s["text"]) <= 25 and len(s["desc1"]) <= 35 and len(s["desc2"]) <= 35, s
    for c in plan.get("callouts", []):
        assert len(c) <= 25, c

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    E = client.enums
    ga = client.get_service("GoogleAdsService")
    camp = list(ga.search(customer_id=cid, query=(
        f"SELECT campaign.id FROM campaign WHERE campaign.name = '{plan['campaign']}' AND campaign.status != 'REMOVED'")))
    assert len(camp) == 1, f"кампаний с именем {plan['campaign']}: {len(camp)}"
    camp_id = camp[0].campaign.id
    camp_rn = f"customers/{cid}/campaigns/{camp_id}"
    before = read_links(ga, cid, camp_id, E)
    by_asset = {r["asset_id"]: r for r in before}
    missing = [a for a in plan["unlink_assets"] if a not in by_asset]
    assert not missing, f"не привязаны к кампании: {missing}"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = client_stats_dir(plan["client_folder"]) / f"snapshot_before_assets_swap_{ts}.csv"
    with open(snap, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rn", "type", "asset_id", "text", "d1", "d2", "url"])
        w.writeheader()
        w.writerows(before)
    print("Снимок «до»:", snap)
    print("Отвязываем:")
    for a in plan["unlink_assets"]:
        r = by_asset[a]
        print(f"  {r['type']} {a} «{r['text']}»")

    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    for a in plan["unlink_assets"]:
        new_op().campaign_asset_operation.remove = by_asset[a]["rn"]
    n = [0]

    def new_asset():
        n[0] += 1
        return f"customers/{cid}/assets/-{n[0]}"

    for s in plan.get("sitelinks", []):
        rn = new_asset()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.final_urls.append(s["url"])
        a.sitelink_asset.link_text = s["text"]
        a.sitelink_asset.description1 = s["desc1"]
        a.sitelink_asset.description2 = s["desc2"]
        ca = new_op().campaign_asset_operation.create
        ca.campaign = camp_rn
        ca.asset = rn
        ca.field_type = E.AssetFieldTypeEnum.SITELINK
    for text in plan.get("callouts", []):
        rn = new_asset()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.callout_asset.callout_text = text
        ca = new_op().campaign_asset_operation.create
        ca.campaign = camp_rn
        ca.asset = rn
        ca.field_type = E.AssetFieldTypeEnum.CALLOUT
    print(f"Операций: {len(ops)}")
    try:
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.mutate_operations.extend(ops)
        req.validate_only = not args.execute
        record_mutate(SCRIPT, len(ops), validate_only=not args.execute)
        client.get_service("GoogleAdsService").mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)
    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не записано (validate_only).")
        return
    print("Записано. Чтение обратно:")
    for r in read_links(ga, cid, camp_id, E):
        print(f"  {r['type']} «{r['text']}» | {r['d1']} | {r['d2']} | {r['url']}")


if __name__ == "__main__":
    main()
