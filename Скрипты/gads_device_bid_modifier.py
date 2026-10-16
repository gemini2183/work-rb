#!/usr/bin/env python
# coding: utf-8
"""Корректировка ставки по устройству на уровне кампании Google Ads (MOBILE / DESKTOP / TABLET). ЗАПИСЬ, по умолчанию validate_only.

Работает только на ручной цене клика (и Максимум кликов); на Smart Bidding (tCPA и др.) такие корректировки не действуют
(см. База_знаний/Инструменты/Google-Ads-Smart-Bidding-и-корректировки-ставок.md).

Использование:
    python gads_device_bid_modifier.py --customer-id 7552781705 --client-folder ProfiMet --campaign-id 19158580966 \
        --device MOBILE --modifier 0.65            # план/validate_only
    ... --execute                                   # записать, прочитать обратно
Множитель 0.65 = −35%; 1.0 = без корректировки.
"""
import argparse
import json
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def read_device(ga, cid, campaign_id):
    out = {}
    q = ("SELECT campaign_criterion.resource_name, campaign_criterion.device.type, campaign_criterion.bid_modifier "
         f"FROM campaign_criterion WHERE campaign.id = {campaign_id} AND campaign_criterion.type = DEVICE")
    for r in ga.search(customer_id=cid, query=q):
        out[int(r.campaign_criterion.device.type_)] = (r.campaign_criterion.resource_name, r.campaign_criterion.bid_modifier)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--device", required=True, choices=["MOBILE", "DESKTOP", "TABLET"])
    ap.add_argument("--modifier", required=True, type=float, help="множитель ставки, 0.65 = −35%%")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    dev = getattr(client.enums.DeviceEnum.Device, a.device)
    before = read_device(ga, cid, a.campaign_id)
    cur = before.get(int(dev))
    print(f"Кампания {a.campaign_id}, устройство {a.device}: сейчас {cur[1] if cur else 'нет корректировки (1.0)'} → {a.modifier}")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_device_modifier_{a.campaign_id}_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps({str(k): list(v) for k, v in before.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Снимок «до»:", snap)

    svc = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    if cur:
        op.update.resource_name = cur[0]
        op.update.bid_modifier = a.modifier
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["bid_modifier"]))
    else:
        c = op.create
        c.campaign = client.get_service("CampaignService").campaign_path(cid, a.campaign_id)
        c.device.type_ = dev
        c.bid_modifier = a.modifier
    req = client.get_type("MutateCampaignCriteriaRequest")
    req.customer_id = cid
    req.operations.append(op)
    try:
        req.validate_only = True
        svc.mutate_campaign_criteria(request=req)
        print("validate_only OK")
        if not a.execute:
            print("ПЛАН. Ничего не записано (добавьте --execute).")
            return
        req.validate_only = False
        svc.mutate_campaign_criteria(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors[:8]:
            print("ОШИБКА:", e.message)
        raise SystemExit(1)
    after = read_device(ga, cid, a.campaign_id)
    print("Прочитано обратно:", {k: v[1] for k, v in after.items()})


if __name__ == "__main__":
    main()
