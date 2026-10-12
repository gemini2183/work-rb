#!/usr/bin/env python
# coding: utf-8
"""Голова спроса: самые частые поисковые запросы кампаний за период, с разбивкой по сети.

Только чтение. Ничего не пишет в кабинет — выводов тоже не делает: собирает
search_term_view с сегментами сеть показа (SEARCH / SEARCH_PARTNERS) и тип
соответствия запроса, складывает сырые строки в Статистика/ клиента и печатает
сводку: сколько показов в чистом поиске и у партнёров, топ запросов по показам
в чистом поиске, какая доля показов приходится на голову (топ-N).

Зачем: решение «завести самые частые запросы в точном соответствии» нельзя
принимать по общему списку — в партнёрской сети идут запросы, которых в чистом
поиске нет (там запрос набирает не человек в Google, а страница-поисковик
партнёра). Скрипт показывает расхождение между двумя списками.

Не включает PMax: search_term_view для Performance Max пуст (ограничение API,
см. Скрипты/README.md).

Использование:
    python gads_search_terms_head.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" \
        --date-from 2026-01-01 --date-to 2026-10-11 \
        --campaign-contains "search /" --top 40
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def fetch_terms(ga_client, ga_service, customer_id, date_from, date_to, campaign_contains):
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            search_term_view.search_term,
            search_term_view.status,
            segments.ad_network_type,
            segments.search_term_match_type,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            if campaign_contains and campaign_contains.lower() not in r.campaign.name.lower():
                continue
            rows.append({
                "Campaign": r.campaign.name,
                "Ad_group": r.ad_group.name,
                "Search_term": r.search_term_view.search_term,
                "Term_status": ga_client.enums.SearchTermTargetingStatusEnum.SearchTermTargetingStatus.Name(r.search_term_view.status),
                "Network": ga_client.enums.AdNetworkTypeEnum.AdNetworkType.Name(r.segments.ad_network_type),
                "Match_type": ga_client.enums.SearchTermMatchTypeEnum.SearchTermMatchType.Name(r.segments.search_term_match_type),
                "Impressions": r.metrics.impressions,
                "Clicks": r.metrics.clicks,
                "Cost": round(r.metrics.cost_micros / 1_000_000, 2),
                "Conversions": round(r.metrics.conversions, 2),
            })
    return pd.DataFrame(rows)


def fetch_campaign_totals(ga_client, ga_service, customer_id, date_from, date_to, campaign_contains):
    """Итоги по сети на уровне кампаний — чтобы увидеть, какую часть трафика
    search_term_view скрывает (запросы ниже порога приватности Google в нём не видны)."""
    query = f"""
        SELECT
            campaign.name,
            segments.ad_network_type,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
            AND campaign.advertising_channel_type = 'SEARCH'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            if campaign_contains and campaign_contains.lower() not in r.campaign.name.lower():
                continue
            rows.append({
                "Network": ga_client.enums.AdNetworkTypeEnum.AdNetworkType.Name(r.segments.ad_network_type),
                "Impressions": r.metrics.impressions,
                "Clicks": r.metrics.clicks,
                "Cost": round(r.metrics.cost_micros / 1_000_000, 2),
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help="Папка клиента в Клиенты/")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", default=str(date.today() - timedelta(1)))
    ap.add_argument("--campaign-contains", default="", help="Подстрока в названии кампании (без регистра)")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    if args.customer_id:
        customer_id = args.customer_id.replace("-", "").strip()
    elif args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    else:
        print("Нужен либо --client, либо --customer-id")
        return

    ga_client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga_service = get_ads_service(ga_client.login_customer_id)

    df = fetch_terms(ga_client, ga_service, customer_id, args.date_from, args.date_to, args.campaign_contains)
    if df.empty:
        print("Нет данных search_term_view за период/кампании")
        return

    out = client_stats_dir(args.client_folder) / f"gads_search_terms_head_{args.date_from}_to_{args.date_to}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"Сохранено: {out} ({len(df)} строк)")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 60)

    print("\nПо сети (все запросы, что отдаёт search_term_view):")
    seen = df.groupby("Network")[["Impressions", "Clicks", "Cost", "Conversions"]].sum()
    print(seen.to_string())

    totals = fetch_campaign_totals(ga_client, ga_service, customer_id, args.date_from, args.date_to, args.campaign_contains)
    if not totals.empty:
        tot = totals.groupby("Network")[["Impressions", "Clicks", "Cost"]].sum()
        cov = tot.join(seen[["Impressions", "Clicks", "Cost"]], rsuffix="_terms", how="left").fillna(0)
        for col in ("Impressions", "Clicks", "Cost"):
            cov[f"{col}_видно_%"] = (cov[f"{col}_terms"] / cov[col] * 100).round(1)
        print("\nИтоги кампаний (Search) vs видимое в search_term_view — охват отчёта запросов:")
        print(cov.to_string())
    print("\nПо типу соответствия внутри каждой сети (показы):")
    print(df.pivot_table(index="Match_type", columns="Network", values="Impressions", aggfunc="sum", fill_value=0).to_string())

    for net in ("SEARCH", "SEARCH_PARTNERS"):
        sub = df[df["Network"] == net]
        if sub.empty:
            continue
        agg = sub.groupby("Search_term")[["Impressions", "Clicks", "Cost", "Conversions"]].sum()
        agg = agg.sort_values("Impressions", ascending=False)
        total = agg["Impressions"].sum()
        agg["cum_share_%"] = (agg["Impressions"].cumsum() / total * 100).round(1)
        print(f"\n{net}: {len(agg)} уникальных запросов, {int(total)} показов. Топ-{args.top} по показам:")
        print(agg.head(args.top).to_string())
        for n in (10, 25, 50, 100):
            if len(agg) >= n:
                print(f"  топ-{n} = {agg['Impressions'].head(n).sum() / total * 100:.1f}% показов сети")


if __name__ == "__main__":
    main()
