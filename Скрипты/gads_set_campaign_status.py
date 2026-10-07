#!/usr/bin/env python
# coding: utf-8
"""Меняет статус кампании (ENABLED / PAUSED) через Google Ads API.

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
После записи читает статус обратно из аккаунта.

Использование:
    python gads_set_campaign_status.py --customer-id 7552781705 --campaign-id 24335049091 --status ENABLED
    ... --execute
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--status", required=True, choices=["ENABLED", "PAUSED"])
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    st = client.enums.CampaignStatusEnum.CampaignStatus

    def read():
        q = ("SELECT campaign.name, campaign.status, campaign.primary_status FROM campaign "
             f"WHERE campaign.id = {args.campaign_id}")
        for r in ga.search(customer_id=cid, query=q):
            return r.campaign.name, st.Name(r.campaign.status), \
                client.enums.CampaignPrimaryStatusEnum.CampaignPrimaryStatus.Name(r.campaign.primary_status)
        raise SystemExit("кампания не найдена")

    name, before, primary_before = read()
    print(f"{name}: статус до = {before} (primary {primary_before})")

    op = client.get_type("CampaignOperation")
    op.update.resource_name = client.get_service("CampaignService").campaign_path(cid, args.campaign_id)
    op.update.status = getattr(st, args.status)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    req = client.get_type("MutateCampaignsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not args.execute
    try:
        client.get_service("CampaignService").mutate_campaigns(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            print("  -", err.message)
        raise SystemExit(1)

    if not args.execute:
        print(f"Проверка пройдена. НИЧЕГО не изменено (validate_only). Было бы: {before} → {args.status}")
        return
    name, after, primary_after = read()
    print(f"Прочитано обратно: статус = {after} (primary {primary_after})")


if __name__ == "__main__":
    main()
