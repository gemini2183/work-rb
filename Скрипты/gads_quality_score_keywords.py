#!/usr/bin/env python
# coding: utf-8
"""Оценки качества ключей Google Ads Search по трём частям (только чтение).

Для каждого включённого ключа кампании(й) за период печатает и пишет в CSV:
  Quality Score (1-10), ожидаемый CTR, релевантность объявления, посадочная страница,
  а также показы, клики, расход и конверсии за период.

Зачем: до и после правок посадочной / объявлений видеть, какая из трёх частей изменилась.
Оценки приходят от Google как BELOW_AVERAGE / AVERAGE / ABOVE_AVERAGE; у ключей без
показов приходит UNSPECIFIED / 0 — это не ошибка.
Quality Score — диагностика Google, а не цель (справка Google).

Использование:
    python gads_quality_score_keywords.py --customer-id 953-486-5605 --client-folder LuxeBrokers \
        --campaign gold_ --since 2026-09-15 --until 2026-10-12
    несколько кампаний: --campaign gold_ --campaign "jewelry / non-lux"
    --min-impr 10   скрыть из печати ключи с меньшим числом показов (в CSV остаются все)
"""
import argparse
import sys
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", action="append", required=True, help="точное имя кампании, можно несколько раз")
    ap.add_argument("--since", help="начало периода ГГГГ-ММ-ДД (по умолчанию 28 дней назад)")
    ap.add_argument("--until", help="конец периода ГГГГ-ММ-ДД (по умолчанию вчера)")
    ap.add_argument("--min-impr", type=int, default=1)
    args = ap.parse_args()

    until = args.until or (date.today() - timedelta(days=1)).isoformat()
    since = args.since or (date.today() - timedelta(days=28)).isoformat()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    bucket = client.enums.QualityScoreBucketEnum.QualityScoreBucket
    mtype = client.enums.KeywordMatchTypeEnum.KeywordMatchType

    names = ", ".join("'" + c.replace("'", "\\'") + "'" for c in args.campaign)
    q = f"""
        SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
               ad_group_criterion.quality_info.quality_score,
               ad_group_criterion.quality_info.search_predicted_ctr,
               ad_group_criterion.quality_info.creative_quality_score,
               ad_group_criterion.quality_info.post_click_quality_score,
               metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM keyword_view
        WHERE campaign.name IN ({names}) AND ad_group_criterion.status = 'ENABLED'
          AND segments.date BETWEEN '{since}' AND '{until}'
    """
    agg = {}
    for r in ga.search(customer_id=cid, query=q):
        c = r.ad_group_criterion
        qi = c.quality_info
        k = (r.campaign.name, r.ad_group.name, c.keyword.text, mtype.Name(c.keyword.match_type))
        a = agg.setdefault(k, dict(qs=qi.quality_score, expected_ctr=bucket.Name(qi.search_predicted_ctr),
                                   ad_relevance=bucket.Name(qi.creative_quality_score),
                                   landing_page=bucket.Name(qi.post_click_quality_score),
                                   impr=0, clicks=0, cost=0.0, conv=0.0))
        a["impr"] += r.metrics.impressions
        a["clicks"] += r.metrics.clicks
        a["cost"] += r.metrics.cost_micros / 1e6
        a["conv"] += r.metrics.conversions

    rows = [dict(campaign=k[0], group=k[1], keyword=k[2], match=k[3], **v) for k, v in agg.items()]
    if not rows:
        sys.exit("Нет включённых ключей с данными за период")
    df = pd.DataFrame(rows).sort_values(["campaign", "impr"], ascending=[True, False])
    path = client_stats_dir(args.client_folder) / f"gads_quality_score_keywords_{until}.csv"
    df.to_csv(path, index=False, encoding="utf-8")

    shown = df[df.impr >= args.min_impr]
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 40)
    print(f"Период {since} - {until}; ключей: {len(df)}, показано (показы >= {args.min_impr}): {len(shown)}")
    print(shown[["campaign", "group", "keyword", "qs", "expected_ctr", "ad_relevance", "landing_page",
                 "impr", "clicks", "cost", "conv"]].round(1).to_string(index=False))
    print("\nСводка по трём частям среди ключей с показами:")
    for col in ("expected_ctr", "ad_relevance", "landing_page"):
        print(f"  {col}: " + ", ".join(f"{k} {v}" for k, v in shown[col].value_counts().items()))
    print(f"\nФайл: {path}")


if __name__ == "__main__":
    main()
