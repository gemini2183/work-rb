#!/usr/bin/env python
# coding: utf-8
"""Снапшот семантики Google Ads (ключевые слова + поисковые запросы) для одного клиента.

Дополняет gads_stats.py (трафик/конверсии по кампаниям) разбивкой на уровень
ключевого слова и уровень реального поискового запроса — нужно для анализа
"какие ключи загружены и работают" и "что искали пользователи, чего нет в
семантическом ядре".

conversions_date_from/conversions_date_to может отличаться от date_from/date_to:
если по клиенту часть периода признана ненадёжной для конверсий (см.
Клиенты/<клиент>/Цели/goals.md), трафик/клики берутся за весь период, а
конверсии — только за надёжный отрезок, чтобы не занижать конверсии по ключам
без искусственного укорачивания всего окна сбора.

Использование:
    python gads_semantics.py --client "Клиент - Google Ads" --client-folder "Клиент" --days 60
    python gads_semantics.py --client "Клиент - Google Ads" --client-folder "Клиент" \
        --date-from 2026-05-28 --date-to 2026-07-26 \
        --conversions-date-from 2026-07-09
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

# Enum-поля (match_type, status) приходят из search_stream как int, не как
# объект с .name — резолвятся через дескриптор enum-сообщения. Клиент для
# резолва не привязан к login_customer_id, поэтому создаётся отдельно и лениво.
_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def fetch_keywords(ga_service, customer_id, date_from, date_to, conversions_date_from=None,
                    campaign_filter=None):
    """Ключевые слова (ad_group_criterion) с метриками -> DataFrame.

    Клики/показы/стоимость — за [date_from, date_to]. Конверсии считаются
    отдельным запросом за [conversions_date_from or date_from, date_to], чтобы
    не занижать конверсии из-за ненадёжного хвоста периода (см. docstring модуля).
    """
    base_select = """
            campaign.name,
            ad_group.name,
            ad_group_criterion.criterion_id,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status
    """

    traffic_query = f"""
        SELECT
            {base_select},
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM keyword_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
            AND ad_group_criterion.status != 'REMOVED'
    """

    agg = {}

    def key_of(row):
        return (
            row.campaign.name,
            row.ad_group.name,
            row.ad_group_criterion.criterion_id,
            row.ad_group_criterion.keyword.text,
            _enum_name("KeywordMatchTypeEnum", "KeywordMatchType", row.ad_group_criterion.keyword.match_type),
            _enum_name("AdGroupCriterionStatusEnum", "AdGroupCriterionStatus", row.ad_group_criterion.status),
        )

    for batch in ga_service.search_stream(customer_id=customer_id, query=traffic_query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            k = key_of(row)
            m = agg.setdefault(k, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["impressions"] += row.metrics.impressions
            m["clicks"] += row.metrics.clicks
            m["cost"] += row.metrics.cost_micros / 1_000_000

    conv_date_from = conversions_date_from or date_from
    conv_query = f"""
        SELECT
            {base_select},
            metrics.conversions
        FROM keyword_view
        WHERE segments.date BETWEEN '{conv_date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
            AND ad_group_criterion.status != 'REMOVED'
    """
    for batch in ga_service.search_stream(customer_id=customer_id, query=conv_query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            k = key_of(row)
            m = agg.setdefault(k, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["conversions"] += row.metrics.conversions

    if not agg:
        return pd.DataFrame()

    rows = [
        {
            "Campaign": k[0],
            "AdGroup": k[1],
            "Criterion_id": k[2],
            "Keyword": k[3],
            "MatchType": k[4],
            "Status": k[5],
            "Impressions": int(m["impressions"]),
            "Clicks": int(m["clicks"]),
            "Cost": round(m["cost"], 2),
            "Conversions_period_from": conv_date_from,
            "Conversions": round(m["conversions"], 2),
        }
        for k, m in agg.items()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values(["Clicks", "Conversions"], ascending=False).reset_index(drop=True)


def fetch_search_terms(ga_service, customer_id, date_from, date_to, conversions_date_from=None,
                        campaign_filter=None):
    """Реальные поисковые запросы (search_term_view) с метриками -> DataFrame.

    Та же логика раздельных периодов для трафика и конверсий, что и в
    fetch_keywords — см. docstring модуля.
    """
    # ВАЖНО: segments.keyword.info.* здесь намеренно не запрашивается. Для
    # Shopping-кампаний поисковые запросы не привязаны к ключевому слову
    # (таргетинг по фиду, не по ключам) — включение этих полей в SELECT
    # молча обнуляет все строки таких кампаний (проверено на аккаунте
    # Корогвы: Merchant_Shopping давал 13848 строк без этих полей и 0 с
    # ними). Сопоставление с загруженными ключами при необходимости лучше
    # делать отдельно, сравнивая текст SearchTerm с списком из fetch_keywords.
    base_select = """
            campaign.name,
            ad_group.name,
            search_term_view.search_term
    """

    traffic_query = f"""
        SELECT
            {base_select},
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """

    agg = {}

    def key_of(row):
        return (
            row.campaign.name,
            row.ad_group.name,
            row.search_term_view.search_term,
        )

    for batch in ga_service.search_stream(customer_id=customer_id, query=traffic_query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            k = key_of(row)
            m = agg.setdefault(k, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["impressions"] += row.metrics.impressions
            m["clicks"] += row.metrics.clicks
            m["cost"] += row.metrics.cost_micros / 1_000_000

    conv_date_from = conversions_date_from or date_from
    conv_query = f"""
        SELECT
            {base_select},
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{conv_date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """
    for batch in ga_service.search_stream(customer_id=customer_id, query=conv_query):
        for row in batch.results:
            if campaign_filter and not campaign_filter(row.campaign.name):
                continue
            k = key_of(row)
            m = agg.setdefault(k, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["conversions"] += row.metrics.conversions

    if not agg:
        return pd.DataFrame()

    rows = [
        {
            "Campaign": k[0],
            "AdGroup": k[1],
            "SearchTerm": k[2],
            "Impressions": int(m["impressions"]),
            "Clicks": int(m["clicks"]),
            "Cost": round(m["cost"], 2),
            "Conversions_period_from": conv_date_from,
            "Conversions": round(m["conversions"], 2),
        }
        for k, m in agg.items()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values(["Clicks", "Conversions"], ascending=False).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Значение колонки 'client' на вкладке Google_Ads_API")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Корогва"')
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--conversions-date-from", help="YYYY-MM-DD, если конверсии надёжны не с самого date-from")
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

    print(f"Клиент: {args.client_folder} | трафик {date_from} → {date_to}"
          + (f" | конверсии с {args.conversions_date_from}" if args.conversions_date_from else ""))

    out_dir = client_stats_dir(args.client_folder)

    df_keywords = fetch_keywords(ga_service, customer_id, date_from, date_to, args.conversions_date_from)
    keywords_path = out_dir / f"gads_keywords_{date_from}_to_{date_to}.csv"
    df_keywords.to_csv(keywords_path, index=False, encoding="utf-8")
    print(f"Сохранено: {keywords_path} ({len(df_keywords)} ключей)")

    df_terms = fetch_search_terms(ga_service, customer_id, date_from, date_to, args.conversions_date_from)
    terms_path = out_dir / f"gads_searchterms_{date_from}_to_{date_to}.csv"
    df_terms.to_csv(terms_path, index=False, encoding="utf-8")
    print(f"Сохранено: {terms_path} ({len(df_terms)} запросов)")


if __name__ == "__main__":
    main()
