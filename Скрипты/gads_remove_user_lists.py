#!/usr/bin/env python
# coding: utf-8
"""Удаляет списки аудиторий (user_list) по ID. ЗАПИСЬ в аккаунт: без --execute — validate_only.

Перед удалением сохраняет снимок «до» (список + все подключения в кампаниях/группах) в
Статистика/ клиента, после — читает обратно: какие списки остались, какие подключения
пережили удаление. Удаляются только типы, которые API разрешает менять (Similar/Look-alike
и read_only отклоняются Google). Только после согласования таблицы плана (CLAUDE.md).

    python gads_remove_user_lists.py --customer-id 7552781705 --client-folder ProfiMet \
        --ids 6900848825,6984957041 [--execute]
"""
import argparse
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def read_state(ga, cid, ids):
    lists = []
    idl = ",".join(str(i) for i in ids)
    for b in ga.search_stream(customer_id=cid, query=f"SELECT user_list.id, user_list.name, user_list.size_for_display FROM user_list WHERE user_list.id IN ({idl})"):
        for r in b.results:
            lists.append({"List_id": r.user_list.id, "Name": r.user_list.name})
    use = []
    for lvl, q in (("campaign", "SELECT campaign.name, campaign.status, campaign_criterion.user_list.user_list, campaign_criterion.status FROM campaign_criterion WHERE campaign_criterion.type = USER_LIST"),
                   ("ad_group", "SELECT campaign.name, campaign.status, ad_group.name, ad_group_criterion.user_list.user_list, ad_group_criterion.status FROM ad_group_criterion WHERE ad_group_criterion.type = USER_LIST")):
        for b in ga.search_stream(customer_id=cid, query=q):
            for r in b.results:
                c = r.campaign_criterion if lvl == "campaign" else r.ad_group_criterion
                lid = int(c.user_list.user_list.split("/")[-1])
                if lid in ids:
                    use.append({"Level": lvl, "Campaign": r.campaign.name, "List_id": lid, "Criterion_status": int(c.status)})
    return pd.DataFrame(lists), pd.DataFrame(use)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--ids", required=True, help="ID списков через запятую")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    ids = [int(x) for x in args.ids.split(",")]
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    lists, use = read_state(ga, cid, ids)
    out = client_stats_dir(args.client_folder)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    lists.to_csv(out / f"gads_userlists_before_removal_{ts}.csv", index=False, encoding="utf-8")
    use.to_csv(out / f"gads_userlists_usage_before_removal_{ts}.csv", index=False, encoding="utf-8")
    print(f"До: списков {len(lists)}, подключений {len(use)}")

    svc = client.get_service("UserListService")
    req = client.get_type("MutateUserListsRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for i in ids:
        op = client.get_type("UserListOperation")
        op.remove = f"customers/{cid}/userLists/{i}"
        req.operations.append(op)
    try:
        svc.mutate_user_lists(request=req)
    except GoogleAdsException as e:
        print("ОШИБКА:", e.failure.errors[0].message)
        return
    print("ВЫПОЛНЕНО (удалено)" if args.execute else "validate_only: ОК, ничего не изменено")

    lists2, use2 = read_state(ga, cid, ids)
    print(f"После (чтение обратно): списков осталось {len(lists2)}, подключений осталось {len(use2)}")
    if len(lists2):
        print(lists2.to_string(index=False))
    if len(use2):
        print(use2.groupby(["List_id", "Criterion_status"]).size().to_string())


if __name__ == "__main__":
    main()
