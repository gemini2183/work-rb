#!/usr/bin/env python
# coding: utf-8
"""Меняет режим цели «привлечение новых клиентов» у кампании. ЗАПИСЬ в аккаунт: без --execute — validate_only.

Режимы (CustomerAcquisitionOptimizationMode): TARGET_ALL_EQUALLY («всех одинаково»),
BID_HIGHER_FOR_NEW_CUSTOMER («ставить выше за новых»), TARGET_NEW_CUSTOMER («только новые»).
Меняется только режим (update_mask), значения value_settings не трогаются. Перед записью
печатает текущее состояние, после записи читает обратно. Только после согласования таблицы плана.

    python gads_set_acquisition_mode.py --customer-id 7552781705 --campaign "Search | Brand | Pl" \
        --mode TARGET_ALL_EQUALLY [--execute]
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def read_mode(ga, cid, campaign_id, names):
    q = (f"SELECT campaign_lifecycle_goal.resource_name, campaign_lifecycle_goal.customer_acquisition_goal_settings.optimization_mode "
         f"FROM campaign_lifecycle_goal WHERE campaign_lifecycle_goal.campaign = 'customers/{cid}/campaigns/{campaign_id}'")
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            g = r.campaign_lifecycle_goal
            return g.resource_name, names[g.customer_acquisition_goal_settings.optimization_mode]
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--mode", required=True, choices=["TARGET_ALL_EQUALLY", "BID_HIGHER_FOR_NEW_CUSTOMER", "TARGET_NEW_CUSTOMER"])
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)
    names = {k: v.name for k, v in client.enums.CustomerAcquisitionOptimizationModeEnum.DESCRIPTOR
             .enum_types_by_name["CustomerAcquisitionOptimizationMode"].values_by_number.items()}

    cids = [r.campaign.id for b in ga.search_stream(customer_id=cid, query=f"SELECT campaign.id FROM campaign WHERE campaign.name = '{args.campaign}' AND campaign.status != REMOVED") for r in b.results]
    if len(cids) != 1:
        print(f"Нашлось кампаний с таким именем: {len(cids)} — остановка")
        return
    rn, before = read_mode(ga, cid, cids[0], names)
    print(f"Кампания {args.campaign} (id {cids[0]}): сейчас {before}; будет {args.mode}")
    if rn is None:
        print("У кампании нет цели привлечения новых клиентов — остановка")
        return
    req = client.get_type("ConfigureCampaignLifecycleGoalsRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    op = req.operation
    op.update.resource_name = rn
    op.update.customer_acquisition_goal_settings.optimization_mode = getattr(client.enums.CustomerAcquisitionOptimizationModeEnum, args.mode)
    op.update_mask.paths.append("customer_acquisition_goal_settings.optimization_mode")
    client.get_service("CampaignLifecycleGoalService").configure_campaign_lifecycle_goals(request=req)
    print("ВЫПОЛНЕНО" if args.execute else "validate_only: ОК, ничего не изменено")
    _, after = read_mode(ga, cid, cids[0], names)
    print(f"Чтение обратно: режим сейчас {after}")


if __name__ == "__main__":
    main()
