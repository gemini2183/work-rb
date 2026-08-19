#!/usr/bin/env python
# coding: utf-8
"""Аудит трафика Google Ads по сетям (Search vs Search Partners vs Content).

Написан в контексте Клиенты/Andverpersonalinjury/ (Andverpersonalinjury) — жалоба на
много трафика с Search Partners без обращений, подозрение на бот/фрод-трафик
(см. Клиенты/Andverpersonalinjury/Решения.md, запись 2026-08-19, и
База_знаний/Паттерны/PPC-Personal-Injury-США-борьба-с-дорогим-и-мусорным-трафиком.md).
Общий скрипт, не завязан на конкретного клиента — как и gads_stats.py/gads_semantics.py.

Два отчёта за один запуск:
1. Сводка по кампаниям, сегментированная по segments.ad_network_type (campaign
   resource) — сколько кликов/стоимости/конверсий даёт SEARCH против
   SEARCH_PARTNERS против CONTENT по каждой кампании. Это отвечает на вопрос
   "сколько вообще уходит на Search Partners и что оттуда приходит".
2. Детальный список площадок внутри Search Partners
   (detail_content_suitability_placement_view, ресурс от авг. 2025) —
   конкретные домены/плейсменты и их показы (ТОЛЬКО impressions — API не
   отдаёт по этому ресурсу clicks/cost/conversions, см. docstring
   fetch_search_partner_placements). Отвечает на вопрос "какие именно сайты
   показывают наши объявления" — по нему уже вручную решать, есть ли среди
   них подозрительные (parked domains и т.п., см. паттерн в базе знаний).

Требует google-ads.yaml (см. Скрипты/README.md) — тот же service account/OAuth,
что и остальные gads_*.py скрипты, доступ уже настроен, ничего дополнительно
заводить не нужно.

Использование (по строке в таблице Google_Ads_API):
    python gads_search_partners_audit.py --client "Клиент - Google Ads" \
        --client-folder "Клиент" --days 30

Использование (customer_id напрямую — для клиентов вроде Andverpersonalinjury,
не заведённых строкой в таблице, см. Клиенты/Andverpersonalinjury/_project.md):
    python gads_search_partners_audit.py --customer-id 213-621-6123 \
        --client-folder "Юристы США" --days 30
    python gads_search_partners_audit.py --customer-id 213-621-6123 \
        --client-folder "Юристы США" --date-from 2026-07-01 --date-to 2026-08-18
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


def fetch_network_breakdown(ga_service, customer_id, date_from, date_to, campaign_filter=None):
    """Кампании x сеть показа (Search/Search Partners/Content) -> DataFrame."""
    query = f"""
        SELECT
            campaign.name,
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
            network = _enum_name("AdNetworkTypeEnum", "AdNetworkType", row.segments.ad_network_type)
            k = (row.campaign.name, network)
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
            "Network": k[1],
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
    return df.sort_values(["Campaign", "Cost"], ascending=[True, False]).reset_index(drop=True)


def fetch_search_partner_placements(ga_service, customer_id, date_from, date_to, campaign_filter=None):
    """Конкретные площадки внутри Search Partners -> DataFrame.

    Использует detail_content_suitability_placement_view — ресурс, которым
    Google в августе 2025 дал полную видимость по Search Partner Network
    (до этого площадки внутри SPN были скрыты, см. паттерн в базе знаний).
    Площадка попадает в отчёт, только если за период набрала хотя бы одно из:
    5+ показов, 1+ клик, 1+ просмотр видео, 1+ конверсию — площадки ниже
    порога в отчёте не видны (ограничение самого API).

    ВАЖНОЕ ОГРАНИЧЕНИЕ (проверено эмпирически 2026-08-19, не решается на
    нашей стороне): этот ресурс отдаёт ТОЛЬКО metrics.impressions — API
    отклоняет запрос с clicks/cost_micros/conversions в этом же SELECT
    ("metric is incompatible with the resource"). Т.е. по каждой площадке
    видно, сколько было показов, но НЕ видно, сколько кликов/денег/конверсий
    она принесла — это ограничение самого Google Ads API (аналогично уже
    задокументированному ограничению search_term_view на Performance Max,
    см. Скрипты/README.md), не самого скрипта. Для сопоставления "эта
    площадка = дорогая/бесполезная" данных из этого отчёта одних
    недостаточно — только для списка "куда вообще уходят показы".
    """
    # segments.ad_network_type НЕ поддерживается этим ресурсом (API отклоняет
    # запрос) — судя по всему, detail_content_suitability_placement_view уже
    # по своей природе относится только к Search Partner Network, отдельный
    # фильтр по сети не нужен и не принимается.
    query = f"""
        SELECT
            campaign.name,
            campaign.status,
            detail_content_suitability_placement_view.placement,
            detail_content_suitability_placement_view.display_name,
            detail_content_suitability_placement_view.target_url,
            detail_content_suitability_placement_view.placement_type,
            metrics.impressions
        FROM detail_content_suitability_placement_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """

    agg = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            pv = row.detail_content_suitability_placement_view
            k = (row.campaign.name, pv.placement, pv.display_name, pv.target_url)
            m = agg.setdefault(k, {"impressions": 0})
            m["impressions"] += row.metrics.impressions

    if not agg:
        return pd.DataFrame()

    rows = [
        {
            "Campaign": k[0],
            "Placement": k[1],
            "Display_name": k[2],
            "Target_url": k[3],
            "Impressions": int(m["impressions"]),
        }
        for k, m in agg.items()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values("Impressions", ascending=False).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без) — если клиент не заведён в таблице")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
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

    df_network = fetch_network_breakdown(ga_service, customer_id, date_from, date_to)
    network_path = out_dir / f"gads_network_breakdown_{date_from}_to_{date_to}.csv"
    df_network.to_csv(network_path, index=False, encoding="utf-8")
    print(f"Сохранено: {network_path} ({len(df_network)} строк campaign x network)")
    if not df_network.empty:
        totals = df_network.groupby("Network")[["Clicks", "Cost", "Conversions"]].sum()
        print("\nИтого по сетям (все кампании):")
        print(totals.to_string())

    df_placements = fetch_search_partner_placements(ga_service, customer_id, date_from, date_to)
    placements_path = out_dir / f"gads_search_partner_placements_{date_from}_to_{date_to}.csv"
    df_placements.to_csv(placements_path, index=False, encoding="utf-8")
    print(f"\nСохранено: {placements_path} ({len(df_placements)} площадок Search Partners)")
    if not df_placements.empty:
        print("Топ-10 площадок Search Partners по показам (только impressions — см. ограничение API в docstring):")
        print(df_placements.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
