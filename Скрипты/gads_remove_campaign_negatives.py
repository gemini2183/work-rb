#!/usr/bin/env python
# coding: utf-8
"""Снимает кампанийные минус-слова по точному тексту И типу соответствия — только в одной кампании.

ЗАПИСЬ в аккаунт: без --execute — validate_only. Тексты и тип совпадения задаются явно (ничего «по похожести»),
поэтому, например, `--texts "near me" --match BROAD` снимет только broad «near me» и не тронет exact
«accident attorney near me». Снимок «до» — в Статистика/ клиента, после записи — чтение обратно.
Только после согласования таблицы плана (CLAUDE.md, протокол записи в кабинет).

    python gads_remove_campaign_negatives.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" --texts "near me" --match BROAD [--execute]
"""
import argparse
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

MATCH = {"EXACT": 2, "PHRASE": 3, "BROAD": 4}
MATCH_NAME = {v: k for k, v in MATCH.items()}


def read_negatives(ga, cid, campaign):
    q = (
        "SELECT campaign.name, campaign_criterion.resource_name, campaign_criterion.keyword.text, "
        "campaign_criterion.keyword.match_type FROM campaign_criterion "
        f"WHERE campaign.name = '{campaign}' AND campaign_criterion.type = KEYWORD "
        "AND campaign_criterion.negative = TRUE AND campaign_criterion.status != REMOVED"
    )
    rows = []
    for b in ga.search_stream(customer_id=cid, query=q):
        for r in b.results:
            c = r.campaign_criterion
            rows.append({"Campaign": r.campaign.name, "Text": c.keyword.text,
                         "Match": MATCH_NAME.get(int(c.keyword.match_type), str(c.keyword.match_type)),
                         "rn": c.resource_name})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True, help="точное имя кампании")
    ap.add_argument("--texts", required=True, help="тексты минус-слов через ';' (регистр не важен)")
    ap.add_argument("--match", required=True, choices=sorted(MATCH))
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    texts = {t.strip().lower() for t in args.texts.split(";") if t.strip()}
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    df = read_negatives(ga, cid, args.campaign)
    pick = df[(df.Text.str.lower().isin(texts)) & (df.Match == args.match)] if len(df) else df
    snap = client_stats_dir(args.client_folder) / f"gads_campaign_negatives_before_removal_{datetime.now():%Y%m%d_%H%M}.csv"
    df.to_csv(snap, index=False, encoding="utf-8")
    print(f"Всего кампанийных минус-слов: {len(df)} (снимок «до» всех: {snap.name})")
    print(f"К снятию: {len(pick)}")
    if not len(pick):
        return
    print(pick[["Campaign", "Text", "Match", "rn"]].to_string(index=False))

    req = client.get_type("MutateCampaignCriteriaRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for rn in pick.rn:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = rn
        req.operations.append(op)
    client.get_service("CampaignCriterionService").mutate_campaign_criteria(request=req)
    print("ВЫПОЛНЕНО (снято)" if args.execute else "validate_only: ОК, ничего не изменено")

    after = read_negatives(ga, cid, args.campaign)
    left = after[(after.Text.str.lower().isin(texts)) & (after.Match == args.match)] if len(after) else after
    print(f"После (чтение обратно): минус-слов всего {len(after)}, из выбранных осталось {len(left)}")


if __name__ == "__main__":
    main()
