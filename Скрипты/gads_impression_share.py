#!/usr/bin/env python
# coding: utf-8
"""Impression Share и Lost IS (Budget vs Rank) по кампаниям Google Ads.

Отвечает на вопрос "почему кампания мало откручивается — бюджет или ставка/
Quality Score" без гадания. search_budget_lost_impression_share близко к 0
означает, что бюджет НЕ является узким местом, даже если кампания тратит
намного меньше дневного лимита — тогда причина в
search_rank_lost_impression_share (ставка или Quality Score), и поднимать
бюджет бессмысленно. См. шаг 7 в
База_знаний/Паттерны/Google-Ads-аудит-кампании-алгоритм-и-ошибки-смешения-данных.md.

Метрики Impression Share доступны только для Search-кампаний (не PMax/Display)
и только на уровне campaign, не campaign x network — см. документацию Google
Ads API (search_impression_share и т.п. поддерживаются ресурсом campaign без
сегментации по ad_network_type в этом же запросе).

Использование:
    python gads_impression_share.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" --days 7
    python gads_impression_share.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" --days 2 \
        --campaigns "search / all injuries / geo - la specific,search / all injuries / kw -  la specific"
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def fetch_impression_share(ga_service, customer_id, date_from, date_to, campaign_names=None):
    query = f"""
        SELECT
            campaign.name,
            campaign.status,
            metrics.impressions,
            metrics.clicks,
            metrics.search_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share,
            metrics.search_exact_match_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
            AND campaign.advertising_channel_type = 'SEARCH'
    """

    agg = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_names and row.campaign.name not in campaign_names:
                continue
            m = agg.setdefault(row.campaign.name, {
                "impressions": 0, "clicks": 0,
                "is_sum": 0.0, "is_n": 0,
                "lost_budget_sum": 0.0, "lost_rank_sum": 0.0,
            })
            m["impressions"] += row.metrics.impressions
            m["clicks"] += row.metrics.clicks
            # IS-метрики приходят по дням — усредняем по дням с данными, не по кликам
            if row.metrics.search_impression_share or row.metrics.impressions:
                m["is_sum"] += row.metrics.search_impression_share
                m["lost_budget_sum"] += row.metrics.search_budget_lost_impression_share
                m["lost_rank_sum"] += row.metrics.search_rank_lost_impression_share
                m["is_n"] += 1

    if not agg:
        return pd.DataFrame()

    rows = [
        {
            "Campaign": name,
            "Impressions": m["impressions"],
            "Clicks": m["clicks"],
            "Impression_share": round(m["is_sum"] / m["is_n"], 4) if m["is_n"] else None,
            "Lost_IS_budget": round(m["lost_budget_sum"] / m["is_n"], 4) if m["is_n"] else None,
            "Lost_IS_rank": round(m["lost_rank_sum"] / m["is_n"], 4) if m["is_n"] else None,
        }
        for name, m in agg.items()
    ]
    return pd.DataFrame(rows).sort_values("Campaign").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Andverpersonalinjury"')
    ap.add_argument("--campaigns", help="Список названий кампаний через запятую (без — все Search-кампании)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    if args.customer_id:
        customer_id = args.customer_id.replace("-", "").strip()
    elif args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
        if not customer_id:
            print(f"У клиента '{args.client}' на вкладке 'Google_Ads_API' пустой client_id")
            return
    else:
        print("Нужен либо --client, либо --customer-id")
        return

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))
    campaign_names = {c.strip() for c in args.campaigns.split(",")} if args.campaigns else None

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | период {date_from} → {date_to}")
    df = fetch_impression_share(ga_service, customer_id, date_from, date_to, campaign_names)

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / f"gads_impression_share_{date_from}_to_{date_to}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} кампаний)")
    if not df.empty:
        print(df.to_string(index=False))
        print(
            "\nЧтение: Lost_IS_budget близко к 0 -> бюджет НЕ узкое место, даже если"
            " потрачено намного меньше дневного лимита. Высокий Lost_IS_rank ->"
            " проблема в ставке/Quality Score, поднимать бюджет бессмысленно."
        )


if __name__ == "__main__":
    main()
