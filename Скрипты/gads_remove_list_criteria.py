#!/usr/bin/env python
# coding: utf-8
"""Снимает подключения списков аудиторий (критерии USER_LIST) в кампаниях — по ID списков.

ЗАПИСЬ в аккаунт: без --execute — validate_only. Затрагивает только кампании со статусом
ENABLED (кампании на паузе/удалённые не трогает). Снимок «до» — в Статистика/ клиента,
после записи — чтение обратно. Только после согласования таблицы плана (CLAUDE.md).

    python gads_remove_list_criteria.py --customer-id 7552781705 --client-folder ProfiMet \
        --ids 6986227657,6986257626 [--execute]
"""
import argparse
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def read_criteria(ga, cid, ids):
    rows = []
    qs = (
        ("campaign", "SELECT campaign.name, campaign_criterion.resource_name, campaign_criterion.user_list.user_list "
                     "FROM campaign_criterion WHERE campaign_criterion.type = USER_LIST AND campaign_criterion.status != REMOVED "
                     "AND campaign.status = ENABLED"),
        ("ad_group", "SELECT campaign.name, ad_group_criterion.resource_name, ad_group_criterion.user_list.user_list "
                     "FROM ad_group_criterion WHERE ad_group_criterion.type = USER_LIST AND ad_group_criterion.status != REMOVED "
                     "AND campaign.status = ENABLED"),
    )
    for lvl, q in qs:
        for b in ga.search_stream(customer_id=cid, query=q):
            for r in b.results:
                c = r.campaign_criterion if lvl == "campaign" else r.ad_group_criterion
                lid = int(c.user_list.user_list.split("/")[-1])
                if lid in ids:
                    rows.append({"Level": lvl, "Campaign": r.campaign.name, "List_id": lid, "rn": c.resource_name})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    ids = {int(x) for x in args.ids.split(",")}
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    df = read_criteria(ga, cid, ids)
    snap = client_stats_dir(args.client_folder) / f"gads_list_criteria_before_removal_{datetime.now():%Y%m%d_%H%M}.csv"
    df.to_csv(snap, index=False, encoding="utf-8")
    print(f"К снятию: {len(df)} подключений (снимок {snap.name})")
    if len(df):
        print(df.groupby(["Campaign", "Level"]).size().to_string())
    else:
        return

    req_ag, req_c = (client.get_type(n) for n in ("MutateAdGroupCriteriaRequest", "MutateCampaignCriteriaRequest"))
    for req, lvl in ((req_c, "campaign"), (req_ag, "ad_group")):
        req.customer_id = cid
        req.validate_only = not args.execute
        for rn in df[df.Level == lvl].rn:
            if lvl == "campaign":
                op = client.get_type("CampaignCriterionOperation")
            else:
                op = client.get_type("AdGroupCriterionOperation")
            op.remove = rn
            req.operations.append(op)
    if len(req_c.operations):
        client.get_service("CampaignCriterionService").mutate_campaign_criteria(request=req_c)
    if len(req_ag.operations):
        client.get_service("AdGroupCriterionService").mutate_ad_group_criteria(request=req_ag)
    print("ВЫПОЛНЕНО (снято)" if args.execute else "validate_only: ОК, ничего не изменено")

    after = read_criteria(ga, cid, ids)
    print(f"После (чтение обратно): подключений в включённых кампаниях осталось {len(after)}")


if __name__ == "__main__":
    main()
