#!/usr/bin/env python
# coding: utf-8
"""Общая выгрузка по ВСЕМ кампаниям Google Ads клиента — трафик и конверсии.

Отдельный от gads_search_partners_audit.py скрипт. Тот написан узко под
проверку площадок Search Partner Network (detail_content_suitability_placement_view)
и остаётся как есть под свою задачу — не трогать/не расширять. Этот скрипт —
для другого вопроса: "сколько всего аккаунт потратил/принёс по каждой
кампании за период", без привязки к теме Search Partners.

Ключевое отличие от gads_stats.py: явно тянет campaign.advertising_channel_type
(PERFORMANCE_MAX / SEARCH / DISPLAY / ...) рядом с segments.ad_network_type.
Причина: у Performance Max Google Ads API возвращает segments.ad_network_type
с разбивкой по факту показа (SEARCH/SEARCH_PARTNERS/CONTENT/...), НО в
интерфейсе Google Ads эта разбивка для PMax скрыта под одной строкой
"Межсетевой показатель" — в PMax "Network=SEARCH" это НЕ то же самое, что
Network=SEARCH у обычной Search-кампании, это трафик внутри Performance Max.
Смешивание строк "Network=SEARCH" по разным advertising_channel_type в одну
сумму — подтверждённая на практике ошибка (см.
Клиенты/Andverpersonalinjury/Решения.md, запись 2026-08-19 про пересбор
данных): дало ложный вывод "чистый Search — здоровый канал, $39/конверсия",
хотя на самом деле все 32 конверсии были из pmax/ca, а обычный Search дал 0
конверсий за тот же период — ровно как показывает сам кабинет Google Ads.
Чтобы не повторить ту же ошибку, вывод этого скрипта группирует
Cost/Clicks/Conversions ПО advertising_channel_type в первую очередь, и
только внутри него — по ad_network_type; в CSV оба поля — отдельные колонки,
их нельзя случайно слить, не заметив.

Использование (customer_id напрямую — для клиентов не заведённых строкой в
общей таблице, см. Клиенты/Andverpersonalinjury/_project.md):
    python gads_campaigns_breakdown.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" --date-from 2026-06-01 --date-to 2026-08-19

Использование (по строке в таблице Google_Ads_API):
    python gads_campaigns_breakdown.py --client "Клиент - Google Ads" \
        --client-folder "Клиент" --days 30
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def fetch_campaigns_breakdown(ga_service, customer_id, date_from, date_to, campaign_filter=None):
    """Campaign x channel_type x network -> DataFrame, без слияния PMax и Search."""
    query = f"""
        SELECT
            campaign.name,
            campaign.advertising_channel_type,
            campaign.status,
            segments.ad_network_type,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """

    agg = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            channel = _enum_name(
                "AdvertisingChannelTypeEnum", "AdvertisingChannelType",
                row.campaign.advertising_channel_type,
            )
            network = _enum_name("AdNetworkTypeEnum", "AdNetworkType", row.segments.ad_network_type)
            k = (row.campaign.name, channel, network)
            m = agg.setdefault(k, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["impressions"] += row.metrics.impressions
            m["clicks"] += row.metrics.clicks
            m["cost"] += row.metrics.cost_micros / 1_000_000
            m["conversions"] += row.metrics.conversions

    if not agg:
        return pd.DataFrame()

    rows = [
        {
            "Campaign": k[0],
            "Channel_type": k[1],
            "Network": k[2],
            "Impressions": int(m["impressions"]),
            "Clicks": int(m["clicks"]),
            "Cost": round(m["cost"], 2),
            "Conversions": round(m["conversions"], 2),
            "CPC": round(m["cost"] / m["clicks"], 2) if m["clicks"] else None,
            "Cost_per_conversion": round(m["cost"] / m["conversions"], 2) if m["conversions"] else None,
        }
        for k, m in agg.items()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values(["Channel_type", "Campaign", "Cost"], ascending=[True, True, False]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без) — если клиент не заведён в таблице")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Andverpersonalinjury"')
    ap.add_argument("--days", type=int, default=30)
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
        print("Нужен либо --client (строка в таблице Google_Ads_API), либо --customer-id напрямую")
        return

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | период {date_from} → {date_to}")

    out_dir = client_stats_dir(args.client_folder)
    df = fetch_campaigns_breakdown(ga_service, customer_id, date_from, date_to)
    out_path = out_dir / f"gads_campaigns_breakdown_{date_from}_to_{date_to}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} строк campaign x channel_type x network)")

    if not df.empty:
        print("\nИтого по типу кампании (advertising_channel_type) — НЕ смешивать разные типы между собой:")
        totals_channel = df.groupby("Channel_type")[["Clicks", "Cost", "Conversions"]].sum()
        print(totals_channel.to_string())

        print("\nИтого по типу кампании x сеть показа:")
        totals_full = df.groupby(["Channel_type", "Network"])[["Clicks", "Cost", "Conversions"]].sum()
        print(totals_full.to_string())


if __name__ == "__main__":
    main()
