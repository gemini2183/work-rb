#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики Google Ads (трафик + конверсии) для одного клиента.

Адаптировано из E:/PythonProjects/RedBird/google-cloud-jobs/adwhite (образец
gads_luxebrokers/main.py), без BigQuery — один клиент за раз, снапшот сразу
кладётся в Клиенты/<client_folder>/Статистика/.

В отличие от Директа/Метрики этот источник использует Google Ads API
(библиотека google-ads, OAuth через google-ads.yaml), а не REST + токен из
Google Sheets. customer_id/login_customer_id клиента берутся с вкладки
"Google_Ads_API" общей таблицы (та же, что и Директ/Метрика, см. _config.py).

Конверсии тянутся с разбивкой по segments.conversion_action_name — это
позволяет учитывать смену основной цели конверсии во времени (если у клиента
конверсия была переопределена в середине периода, в снапшоте видно оба
названия отдельными строками, не слито в одну сумму).

Если у клиента есть спец-условия (например, Корогва: один аккаунт, разбитый на
подпроекты "Google Ads"/"Merchant Center" по названию кампании) — используется
клиент-специфичный скрипт (gads_stats_<клиент>.py), который вызывает функции
отсюда с доп. фильтром по campaign.name, как это устроено для Директа/Метрики.

Использование:
    python gads_stats.py --client "Клиент - Google Ads" --client-folder "Клиент" --days 30
    python gads_stats.py --client "Клиент - Google Ads" --client-folder "Клиент" \
        --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row

GOOGLE_ADS_YAML = "secrets/google-ads.yaml"


def get_ads_service(login_customer_id):
    ads_client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ads_client.login_customer_id = login_customer_id
    return ads_client.get_service("GoogleAdsService")


def fetch_traffic(ga_service, customer_id, date_from, date_to, campaign_filter=None):
    """Трафик по дням -> DataFrame формата total_gads.

    campaign_filter(name: str) -> bool, если задан, оставляет только кампании,
    для которых он возвращает True (клиент-специфичный фильтр по названию).
    """
    query = f"""
        SELECT
            campaign.name,
            segments.date,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """

    daily = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            d = row.segments.date
            agg = daily.setdefault(
                d, {"cost": 0.0, "impressions": 0, "clicks": 0, "conversions": 0.0}
            )
            agg["cost"] += row.metrics.cost_micros / 1_000_000
            agg["impressions"] += row.metrics.impressions
            agg["clicks"] += row.metrics.clicks
            agg["conversions"] += row.metrics.conversions

    if not daily:
        return pd.DataFrame()

    rows = [
        {
            "Date": d,
            "Source": "GAds",
            "Impressions": int(m["impressions"]),
            "Clicks": int(m["clicks"]),
            "Cost": round(m["cost"], 2),
            "Conversions": round(m["conversions"], 2),
        }
        for d, m in daily.items()
    ]
    df = pd.DataFrame(rows)
    df["Date"] = df["Date"].astype(str)
    return df.sort_values("Date").reset_index(drop=True)


def fetch_conversions(ga_service, customer_id, date_from, date_to, campaign_filter=None):
    """Конверсии по дате и типу действия (conversion_action_name) -> DataFrame."""
    query = f"""
        SELECT
            campaign.name,
            segments.date,
            segments.conversion_action_name,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
            AND metrics.conversions > 0
    """

    agg = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            d = row.segments.date
            action = row.segments.conversion_action_name or "(не определено)"
            agg[(d, action)] = agg.get((d, action), 0.0) + row.metrics.conversions

    if not agg:
        return pd.DataFrame()

    rows = [
        {"Date": str(d), "Goal_name": action, "Goal_visits": round(conv, 2)}
        for (d, action), conv in agg.items()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values("Date").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Значение колонки 'client' на вкладке Google_Ads_API")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Корогва"')
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
    customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    if not customer_id:
        print(f"У клиента '{args.client}' на вкладке 'Google_Ads_API' пустой client_id")
        return

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | период {date_from} → {date_to}")
    df_traffic = fetch_traffic(ga_service, customer_id, date_from, date_to)
    df_goals = fetch_conversions(ga_service, customer_id, date_from, date_to)

    out_dir = client_stats_dir(args.client_folder)
    traffic_path = out_dir / f"gads_{date_from}_to_{date_to}.csv"
    goals_path = out_dir / f"gads_goals_{date_from}_to_{date_to}.csv"

    df_traffic.to_csv(traffic_path, index=False, encoding="utf-8")
    df_goals.to_csv(goals_path, index=False, encoding="utf-8")
    print(f"Сохранено: {traffic_path} ({len(df_traffic)} дней)")
    print(f"Сохранено: {goals_path} ({len(df_goals)} строк)")


if __name__ == "__main__":
    main()
