#!/usr/bin/env python
# coding: utf-8
"""Переключает кампанию на «свои цели конверсий» и выставляет, какие категории считаются
в основных конверсиях (biddable), через Google Ads API.

Делает два шага: (1) conversion_goal_campaign_config → уровень CAMPAIGN, (2) campaign_conversion_goal.biddable
по списку --off (выключить) и --on (включить). Категории задаются как КАТЕГОРИЯ:ИСТОЧНИК, например
DEFAULT:WEBSITE, PURCHASE:WEBSITE, DOWNLOAD:APP. Остальные категории не трогаются.

Снимок «до» (все цели кампании) пишется в Статистика/ клиента, если задан --snapshot-dir.

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.

Использование:
    python gads_set_campaign_goals.py --customer-id 7552781705 --campaign-id 24335049091 \\
        --off DEFAULT:WEBSITE PURCHASE:WEBSITE DOWNLOAD:APP --snapshot-dir "../Клиенты/ProfiMet/Статистика"
    ... --execute
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from gads_stats import GOOGLE_ADS_YAML


def read_goals(client, ga, cid, campaign_id):
    cat = client.enums.ConversionActionCategoryEnum.ConversionActionCategory
    org = client.enums.ConversionOriginEnum.ConversionOrigin
    rows = []
    q = ("SELECT campaign_conversion_goal.resource_name, campaign_conversion_goal.category, "
         "campaign_conversion_goal.origin, campaign_conversion_goal.biddable "
         f"FROM campaign_conversion_goal WHERE campaign.id = {campaign_id}")
    for r in ga.search(customer_id=cid, query=q):
        g = r.campaign_conversion_goal
        rows.append({"resource_name": g.resource_name, "category": cat.Name(g.category),
                     "origin": org.Name(g.origin), "biddable": g.biddable})
    return rows


def read_level(client, ga, cid, campaign_id):
    lvl = client.enums.GoalConfigLevelEnum.GoalConfigLevel
    q = ("SELECT conversion_goal_campaign_config.resource_name, conversion_goal_campaign_config.goal_config_level "
         f"FROM conversion_goal_campaign_config WHERE campaign.id = {campaign_id}")
    for r in ga.search(customer_id=cid, query=q):
        c = r.conversion_goal_campaign_config
        return c.resource_name, lvl.Name(c.goal_config_level)
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--off", nargs="*", default=[], help="КАТЕГОРИЯ:ИСТОЧНИК, выключить из основных конверсий")
    ap.add_argument("--on", nargs="*", default=[], help="КАТЕГОРИЯ:ИСТОЧНИК, включить в основные конверсии")
    ap.add_argument("--snapshot-dir", help="куда положить снимок «до» (csv)")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    lvl_enum = client.enums.GoalConfigLevelEnum.GoalConfigLevel

    cfg_rn, level_before = read_level(client, ga, cid, args.campaign_id)
    goals_before = read_goals(client, ga, cid, args.campaign_id)
    print(f"Уровень целей до: {level_before}")
    for g in goals_before:
        print(f"  до: {g['category']}:{g['origin']} biddable={g['biddable']}")

    if args.snapshot_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = Path(args.snapshot_dir) / f"gads_campaign_goals_before_{args.campaign_id}_{ts}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["campaign_id", "level", "category", "origin", "biddable"])
            for g in goals_before:
                w.writerow([args.campaign_id, level_before, g["category"], g["origin"], g["biddable"]])
        print(f"Снимок «до»: {path}")

    wanted = {k: False for k in args.off}
    wanted.update({k: True for k in args.on})
    by_key = {f"{g['category']}:{g['origin']}": g for g in goals_before}
    unknown = [k for k in wanted if k not in by_key]
    if unknown:
        raise SystemExit(f"Нет таких целей у кампании: {unknown}")

    cfg_svc = client.get_service("ConversionGoalCampaignConfigService")
    goal_svc = client.get_service("CampaignConversionGoalService")
    validate = not args.execute
    try:
        if level_before != "CAMPAIGN":
            op = client.get_type("ConversionGoalCampaignConfigOperation")
            op.update.resource_name = cfg_rn
            op.update.goal_config_level = lvl_enum.CAMPAIGN
            op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["goal_config_level"]))
            req = client.get_type("MutateConversionGoalCampaignConfigsRequest")
            req.customer_id = cid
            req.operations.append(op)
            req.validate_only = validate
            cfg_svc.mutate_conversion_goal_campaign_configs(request=req)
            print("Шаг 1: уровень целей → CAMPAIGN", "(validate_only)" if validate else "(записано)")
        ops = []
        for key, biddable in wanted.items():
            g = by_key[key]
            if g["biddable"] == biddable:
                continue
            op = client.get_type("CampaignConversionGoalOperation")
            op.update.resource_name = g["resource_name"]
            op.update.biddable = biddable
            op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["biddable"]))
            ops.append(op)
            print(f"  изменить {key}: {g['biddable']} → {biddable}")
        if ops:
            req = client.get_type("MutateCampaignConversionGoalsRequest")
            req.customer_id = cid
            req.operations.extend(ops)
            req.validate_only = validate
            goal_svc.mutate_campaign_conversion_goals(request=req)
        print(f"Шаг 2: изменений целей: {len(ops)}", "(validate_only, ничего не записано)" if validate else "(записано)")
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            print("  -", err.message)
        raise SystemExit(1)

    if args.execute:
        _, level_after = read_level(client, ga, cid, args.campaign_id)
        print(f"Прочитано обратно. Уровень целей: {level_after}")
        for g in read_goals(client, ga, cid, args.campaign_id):
            print(f"  после: {g['category']}:{g['origin']} biddable={g['biddable']}")


if __name__ == "__main__":
    main()
