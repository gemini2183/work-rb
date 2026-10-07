#!/usr/bin/env python
# coding: utf-8
"""Создаёт ярлык и присваивает его кампаниям по ID из CSV (колонка id). ЗАПИСЬ в аккаунт.

Без --execute — validate_only (Google проверяет, ничего не создаёт). Статус кампаний НЕ меняется.
Если ярлык с таким именем уже есть — используется он. После записи читает обратно:
сколько кампаний реально несут ярлык. Только после согласования таблицы плана (CLAUDE.md).

    python gads_label_campaigns.py --customer-id 7552781705 --label "архив" \
        --ids-csv "../Клиенты/ProfiMet/Статистика/gads_old_campaigns_candidates_2026-10-07.csv" \
        --ids-csv "../Клиенты/ProfiMet/Статистика/gads_experiment_arms_2026-10-07.csv" [--execute]
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def labelled(ga, cid, label):
    q = (f"SELECT campaign.id FROM campaign_label WHERE label.name = '{label}' "
         f"AND campaign.status != REMOVED")
    return {r.campaign.id for b in ga.search_stream(customer_id=cid, query=q) for r in b.results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--ids-csv", action="append", required=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    ids = sorted({int(i) for p in args.ids_csv for i in pd.read_csv(p).id})
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    existing = [r.label.id for b in ga.search_stream(customer_id=cid, query=f"SELECT label.id FROM label WHERE label.name = '{args.label}' AND label.status = ENABLED") for r in b.results]
    already = labelled(ga, cid, args.label) if existing else set()
    todo = [i for i in ids if i not in already]
    print(f"Кампаний в списке: {len(ids)}; уже с ярлыком: {len(ids) - len(todo)}; присвоить: {len(todo)}; ярлык существует: {bool(existing)}")

    ops = []
    if existing:
        label_rn = f"customers/{cid}/labels/{existing[0]}"
    else:
        label_rn = f"customers/{cid}/labels/-1"
        o = client.get_type("MutateOperation")
        l = o.label_operation.create
        l.resource_name = label_rn
        l.name = args.label
        l.text_label.description = args.description
        l.text_label.background_color = "#999999"
        ops.append(o)
    for i in todo:
        o = client.get_type("MutateOperation")
        c = o.campaign_label_operation.create
        c.campaign = f"customers/{cid}/campaigns/{i}"
        c.label = label_rn
        ops.append(o)
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    req.mutate_operations.extend(ops)
    client.get_service("GoogleAdsService").mutate(request=req)
    print("ВЫПОЛНЕНО" if args.execute else "validate_only: ОК, ничего не изменено")

    after = labelled(ga, cid, args.label)
    print(f"Чтение обратно: кампаний с ярлыком «{args.label}»: {len(after)}; из списка получили: {len(set(ids) & after)} из {len(ids)}")


if __name__ == "__main__":
    main()
