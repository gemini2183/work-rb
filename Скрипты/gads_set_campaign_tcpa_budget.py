#!/usr/bin/env python
# coding: utf-8
"""Меняет целевую цену конверсии (tCPA, Maximize conversions) и/или дневной бюджет кампании Google Ads.

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
Снимок «до» сохраняется в Статистика/ клиента, после записи значения читаются обратно из аккаунта.

Использование:
    python gads_set_campaign_tcpa_budget.py --customer-id 7552781705 --client-folder ProfiMet \
        --campaign-id 23775369828 --tcpa 32 --budget 120
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
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--tcpa", type=float, help="новая цель по CPA в валюте аккаунта (стратегия Maximize conversions)")
    ap.add_argument("--budget", type=float, help="новый дневной бюджет в валюте аккаунта")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()
    if args.tcpa is None and args.budget is None:
        raise SystemExit("нужен хотя бы один из --tcpa / --budget")

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    def read():
        q = ("SELECT campaign.name, campaign.status, campaign.bidding_strategy_type, "
             "campaign.maximize_conversions.target_cpa_micros, campaign.campaign_budget, "
             "campaign_budget.amount_micros FROM campaign "
             f"WHERE campaign.id = {args.campaign_id}")
        for r in ga.search(customer_id=cid, query=q):
            return {
                "name": r.campaign.name,
                "status": client.enums.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status),
                "strategy": client.enums.BiddingStrategyTypeEnum.BiddingStrategyType.Name(r.campaign.bidding_strategy_type),
                "tcpa": r.campaign.maximize_conversions.target_cpa_micros / 1_000_000,
                "budget": r.campaign_budget.amount_micros / 1_000_000,
                "budget_resource": r.campaign.campaign_budget,
            }
        raise SystemExit("кампания не найдена")

    before = read()
    print(f"{before['name']} [{before['status']}, {before['strategy']}]: tCPA до = {before['tcpa']}, бюджет до = {before['budget']}")
    if args.tcpa is not None and before["strategy"] != "MAXIMIZE_CONVERSIONS":
        raise SystemExit(f"tCPA меняется только при MAXIMIZE_CONVERSIONS, сейчас {before['strategy']}")

    out_dir = client_stats_dir(args.client_folder)
    snap = out_dir / f"snapshot_before_tcpa_budget_{args.campaign_id}_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Снимок «до»: {snap}")

    ops = []  # (service, request)
    if args.tcpa is not None:
        op = client.get_type("CampaignOperation")
        op.update.resource_name = client.get_service("CampaignService").campaign_path(cid, args.campaign_id)
        op.update.maximize_conversions.target_cpa_micros = int(round(args.tcpa * 1_000_000))
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["maximize_conversions.target_cpa_micros"]))
        req = client.get_type("MutateCampaignsRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not args.execute
        ops.append((client.get_service("CampaignService").mutate_campaigns, req))
    if args.budget is not None:
        op = client.get_type("CampaignBudgetOperation")
        op.update.resource_name = before["budget_resource"]
        op.update.amount_micros = int(round(args.budget * 1_000_000))
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))
        req = client.get_type("MutateCampaignBudgetsRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not args.execute
        ops.append((client.get_service("CampaignBudgetService").mutate_campaign_budgets, req))

    try:
        for fn, req in ops:
            fn(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            print("  -", err.message)
        raise SystemExit(1)

    if not args.execute:
        print(f"Проверка пройдена. НИЧЕГО не изменено (validate_only). Было бы: tCPA {before['tcpa']} -> "
              f"{args.tcpa if args.tcpa is not None else before['tcpa']}, бюджет {before['budget']} -> "
              f"{args.budget if args.budget is not None else before['budget']}")
        return
    after = read()
    print(f"Прочитано обратно: tCPA = {after['tcpa']}, бюджет = {after['budget']}")


if __name__ == "__main__":
    main()
