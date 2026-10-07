#!/usr/bin/env python
# coding: utf-8
"""Снимает метку «Customer Type» (по умолчанию PURCHASERS) со списков по ID. ЗАПИСЬ: без --execute — validate_only.

Метка влияет на цель «привлечение новых клиентов» на уровне аккаунта (списки с меткой считаются
«существующими клиентами»), см. База_знаний/Инструменты/Google-Ads-списки-аудиторий-из-GA4-...
Перед записью сохраняет снимок меток в Статистика/ клиента, после — читает обратно.
Только после согласования таблицы плана (CLAUDE.md).

    python gads_remove_customer_type_labels.py --customer-id 7552781705 --client-folder ProfiMet \
        --ids 8153403621,8637051524 [--category PURCHASERS] [--execute]
"""
import argparse
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def read_labels(ga, cid):
    rows = []
    q = "SELECT user_list_customer_type.resource_name, user_list_customer_type.user_list FROM user_list_customer_type"
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            rn = r.user_list_customer_type.resource_name
            rows.append({"List_id": int(r.user_list_customer_type.user_list.split("/")[-1]),
                         "Category": rn.split("~")[-1], "rn": rn})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--category", default="PURCHASERS")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    ids = {int(x) for x in args.ids.split(",")}
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    df = read_labels(ga, cid)
    snap = client_stats_dir(args.client_folder) / f"gads_customer_type_labels_before_{datetime.now():%Y%m%d_%H%M}.csv"
    df.to_csv(snap, index=False, encoding="utf-8")
    todo = df[df.List_id.isin(ids) & (df.Category == args.category)]
    print(f"Меток всего: {len(df)}; к снятию: {len(todo)} (снимок {snap.name})")
    if not len(todo):
        return
    req = client.get_type("MutateUserListCustomerTypesRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for rn in todo.rn:
        op = client.get_type("UserListCustomerTypeOperation")
        op.remove = rn
        req.operations.append(op)
    client.get_service("UserListCustomerTypeService").mutate_user_list_customer_types(request=req)
    print("ВЫПОЛНЕНО (снято)" if args.execute else "validate_only: ОК, ничего не изменено")
    after = read_labels(ga, cid)
    print(f"Чтение обратно: меток осталось {len(after)}")
    if len(after):
        print(after[["List_id", "Category"]].to_string(index=False))


if __name__ == "__main__":
    main()
