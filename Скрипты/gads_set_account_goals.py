#!/usr/bin/env python
# coding: utf-8
"""Цели конверсий АККАУНТА по умолчанию (customer_conversion_goal.biddable) через Google Ads API.

Список пар «категория + источник» (например SUBMIT_LEAD_FORM:WEBSITE), по которым Google оптимизирует ставки во всех
кампаниях с уровнем целей CUSTOMER и которые попадают в колонку «Конверсии». Кампании с уровнем CAMPAIGN берут свои цели
(их правит gads_set_campaign_goals.py). Остальные пары не трогаются.

Без параметров --on/--off печатает текущие цели аккаунта и кампании, которые берут цели из аккаунта (CUSTOMER).
Снимок «до» пишется в --snapshot-dir (csv).

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.

Использование (из папки Скрипты):
    python gads_set_account_goals.py --customer-id 213-621-6123
    python gads_set_account_goals.py --customer-id 213-621-6123 --on SUBMIT_LEAD_FORM:WEBSITE --snapshot-dir "../Клиенты/Andverpersonalinjury/Статистика"
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


def name(enum, v):
    return v.name if hasattr(v, "name") else enum.Name(v)


def read_goals(client, ga, cid):
    cat = client.enums.ConversionActionCategoryEnum.ConversionActionCategory
    org = client.enums.ConversionOriginEnum.ConversionOrigin
    rows = []
    q = ("SELECT customer_conversion_goal.resource_name, customer_conversion_goal.category, "
         "customer_conversion_goal.origin, customer_conversion_goal.biddable FROM customer_conversion_goal")
    for r in ga.search(customer_id=cid, query=q):
        g = r.customer_conversion_goal
        rows.append({"resource_name": g.resource_name, "category": name(cat, g.category),
                     "origin": name(org, g.origin), "biddable": g.biddable})
    return sorted(rows, key=lambda x: (x["category"], x["origin"]))


def customer_level_campaigns(client, ga, cid):
    lvl = client.enums.GoalConfigLevelEnum.GoalConfigLevel
    st = client.enums.CampaignStatusEnum.CampaignStatus
    q = ("SELECT campaign.name, campaign.status, conversion_goal_campaign_config.goal_config_level "
         "FROM conversion_goal_campaign_config WHERE campaign.status != 'REMOVED'")
    out = []
    for r in ga.search(customer_id=cid, query=q):
        if name(lvl, r.conversion_goal_campaign_config.goal_config_level) == "CUSTOMER":
            out.append((name(st, r.campaign.status), r.campaign.name))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--on", nargs="*", default=[], help="КАТЕГОРИЯ:ИСТОЧНИК, включить в цели аккаунта")
    ap.add_argument("--off", nargs="*", default=[], help="КАТЕГОРИЯ:ИСТОЧНИК, выключить из целей аккаунта")
    ap.add_argument("--snapshot-dir", help="куда положить снимок «до» (csv)")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    before = read_goals(client, ga, cid)
    print("Цели аккаунта до:")
    for g in before:
        print(f"  {g['category']}:{g['origin']} biddable={g['biddable']}")
    users = customer_level_campaigns(client, ga, cid)
    print("Кампании, которые берут цели из аккаунта (уровень CUSTOMER):")
    for s, n in users:
        print(f"  {s} | {n}")

    if args.snapshot_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = Path(args.snapshot_dir) / f"gads_account_goals_before_{cid}_{ts}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "origin", "biddable"])
            for g in before:
                w.writerow([g["category"], g["origin"], g["biddable"]])
        print(f"Снимок «до»: {path}")

    wanted = {k: False for k in args.off}
    wanted.update({k: True for k in args.on})
    if not wanted:
        return
    by_key = {f"{g['category']}:{g['origin']}": g for g in before}
    unknown = [k for k in wanted if k not in by_key]
    if unknown:
        raise SystemExit(f"Нет таких целей в аккаунте: {unknown}")

    svc = client.get_service("CustomerConversionGoalService")
    ops = []
    for key, biddable in wanted.items():
        g = by_key[key]
        if g["biddable"] == biddable:
            continue
        op = client.get_type("CustomerConversionGoalOperation")
        op.update.resource_name = g["resource_name"]
        op.update.biddable = biddable
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["biddable"]))
        ops.append(op)
        print(f"  изменить {key}: {g['biddable']} → {biddable}")
    validate = not args.execute
    if not ops:
        print("Изменений нет.")
        return
    try:
        req = client.get_type("MutateCustomerConversionGoalsRequest")
        req.customer_id = cid
        req.operations.extend(ops)
        req.validate_only = validate
        svc.mutate_customer_conversion_goals(request=req)
        print(f"Изменений целей: {len(ops)}", "(validate_only, ничего не записано)" if validate else "(записано)")
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            print("  -", err.message)
        raise SystemExit(1)

    if args.execute:
        print("Прочитано обратно:")
        for g in read_goals(client, ga, cid):
            print(f"  после: {g['category']}:{g['origin']} biddable={g['biddable']}")


if __name__ == "__main__":
    main()
