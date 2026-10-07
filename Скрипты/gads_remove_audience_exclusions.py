#!/usr/bin/env python
# coding: utf-8
"""Снимает исключения аудиторий (negative user list) на уровне кампаний, кроме списка(ов) --keep.

ЗАПИСЬ в аккаунт: по умолчанию validate_only (Google проверяет, ничего не меняет).
Реальное удаление — только с --execute и только после согласования таблицы плана
(см. CLAUDE.md, протокол записи). Критерии берутся из свежего чтения аккаунта,
не из старого CSV; снимок «до» сохраняется в Статистика/ клиента для отката.

Использование:
    python gads_remove_audience_exclusions.py --customer-id 7552781705 --client-folder ProfiMet \
        --campaigns "Search | Brand | Pl,Search | Poliweglan | Pl,pmax1_test" --keep 9441800617
    ... --execute
"""
import argparse
from datetime import date

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def read_negatives(ga, cid, campaigns):
    names = ",".join("'" + c.replace("'", "\\'") + "'" for c in campaigns)
    q = f"""SELECT campaign.name, campaign_criterion.criterion_id, campaign_criterion.resource_name,
                   campaign_criterion.user_list.user_list
            FROM campaign_criterion
            WHERE campaign_criterion.type = USER_LIST AND campaign_criterion.negative = TRUE
              AND campaign_criterion.status = ENABLED AND campaign.name IN ({names})"""
    rows = []
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            c = r.campaign_criterion
            rows.append({"Campaign": r.campaign.name, "crit_id": c.criterion_id,
                         "List_id": c.user_list.user_list.split("/")[-1], "rn": c.resource_name})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaigns", required=True, help="Имена кампаний через запятую")
    ap.add_argument("--keep", default="", help="ID списков, которые оставить исключениями, через запятую")
    ap.add_argument("--execute", action="store_true", help="Реально удалить (по умолчанию validate_only)")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "")
    keep = {k.strip() for k in args.keep.split(",") if k.strip()}
    campaigns = [c.strip() for c in args.campaigns.split(",")]
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    df = read_negatives(ga, cid, campaigns)
    snap = client_stats_dir(args.client_folder) / f"gads_exclusions_snapshot_{date.today()}.csv"
    df.to_csv(snap, index=False, encoding="utf-8")
    to_remove = df[~df.List_id.isin(keep)]
    print(f"Исключений сейчас: {len(df)}; оставить: {len(df) - len(to_remove)}; снять: {len(to_remove)}. Снимок: {snap}")
    print(to_remove.groupby("Campaign").size().to_string())

    svc = client.get_service("CampaignCriterionService")
    req = client.get_type("MutateCampaignCriteriaRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for rn in to_remove.rn:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = rn
        req.operations.append(op)
    svc.mutate_campaign_criteria(request=req)
    print("ВЫПОЛНЕНО (удалено)" if args.execute else "validate_only: ОК, ничего не изменено")

    after = read_negatives(ga, cid, campaigns)
    print("\nОсталось исключений после операции (чтение обратно):" if args.execute else "\nИсключений сейчас:")
    print(after.groupby(["Campaign", "List_id"]).size().to_string() if len(after) else "нет")


if __name__ == "__main__":
    main()
