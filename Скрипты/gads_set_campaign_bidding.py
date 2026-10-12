#!/usr/bin/env python
# coding: utf-8
"""Переключает стратегию ставок кампании Google Ads: «Максимум кликов» (с потолком цены клика) ↔ «Максимум конверсий».

Зачем: опыт 2026-10-12 на `dg_lookalike_test` (Demand Gen без показов 3 дня при «Максимум конверсий» без истории конверсий):
проверить, начнёт ли кампания показываться на стратегии «Максимум кликов» (гипотеза, не проверена).

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
Снимок «до» сохраняется в Статистика/ клиента, после записи стратегия читается обратно из аккаунта.

Использование:
    python gads_set_campaign_bidding.py --customer-id 7552781705 --client-folder ProfiMet --campaign-id 24332648825 \
        --strategy MAXIMIZE_CLICKS --cpc-ceiling 0.50 [--execute]
    # откат:
    python gads_set_campaign_bidding.py ... --strategy MAXIMIZE_CONVERSIONS [--execute]
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
    ap.add_argument("--strategy", required=True, choices=["MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS"])
    ap.add_argument("--cpc-ceiling", type=float, help="потолок цены клика (для MAXIMIZE_CLICKS), в валюте аккаунта")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()
    if args.strategy == "MAXIMIZE_CLICKS" and not args.cpc_ceiling:
        raise SystemExit("для MAXIMIZE_CLICKS нужен --cpc-ceiling (потолок цены клика)")

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    def read():
        q = ("SELECT campaign.name, campaign.status, campaign.bidding_strategy_type, "
             "campaign.maximize_conversions.target_cpa_micros, campaign.target_spend.cpc_bid_ceiling_micros "
             f"FROM campaign WHERE campaign.id = {args.campaign_id}")
        for r in ga.search(customer_id=cid, query=q):
            c = r.campaign
            return {"name": c.name, "status": E.CampaignStatusEnum.CampaignStatus.Name(c.status),
                    "strategy": E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(c.bidding_strategy_type),
                    "target_cpa": c.maximize_conversions.target_cpa_micros / 1e6,
                    "cpc_ceiling": c.target_spend.cpc_bid_ceiling_micros / 1e6}
        raise SystemExit("кампания не найдена")

    before = read()
    print("до:", before)
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_bidding_{args.campaign_id}_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps(before, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Снимок «до»:", snap)

    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{cid}/campaigns/{args.campaign_id}"
    if args.strategy == "MAXIMIZE_CLICKS":
        op.update.target_spend.cpc_bid_ceiling_micros = int(round(args.cpc_ceiling * 1_000_000))
        paths = ["target_spend.cpc_bid_ceiling_micros"]
    else:
        op.update.maximize_conversions.target_cpa_micros = 0
        paths = ["maximize_conversions.target_cpa_micros"]
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=paths))
    req = client.get_type("MutateCampaignsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not args.execute
    try:
        client.get_service("CampaignService").mutate_campaigns(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:5]:
            print("  -", err.message)
        raise SystemExit(1)
    if not args.execute:
        print(f"Проверка пройдена. НИЧЕГО не изменено (validate_only). Было бы: {before['strategy']} → {args.strategy}")
        return
    print("Прочитано обратно:", read())


if __name__ == "__main__":
    main()
