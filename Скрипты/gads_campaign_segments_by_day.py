#!/usr/bin/env python
# coding: utf-8
"""Сборщик "кампания x день x измерение" для Шага 2 блок-схемы анализа
(База_знаний/Паттерны/Алгоритм-анализа-эффективности-кампании-блок-схема.md).

Зачем отдельный скрипт: Шаг 2 для находки-аномалии ("что отличало структуру
трафика именно 21.09 от обычного дня") и для находки-тренда ("какой срез тянет
CPA вверх") требует одних и тех же срезов, но С ДАТОЙ — чтобы потом сравнить
день/окно с базовой линией ("14 дней вокруг") тем же кодом. Существующие
скрипты отдают либо срез без даты (gads_search_terms_wordfreq), либо срез по
неделям для байесовской модели (gads_bayesian_slice_analysis) — не то и не
другое здесь не подходит.

Скрипт ТОЛЬКО собирает данные (как и остальные в Скрипты/), выводов не делает.

Измерения (--dimension):
    device            Desktop/Mobile/Tablet (segments.device)
    hour              час суток 0-23 (segments.hour)
    ad_group          группа объявлений
    search_term       фактический поисковый запрос (search_term_view)
    conversion_action название конверсионного действия — ТОЛЬКО Conversions/
                      All_conversions: Google Ads API не допускает metrics.clicks/
                      impressions/cost вместе с segments.conversion_action_name

Использование:
    python gads_campaign_segments_by_day.py --customer-id 7552781705 \
        --client-folder "ProfiMet" --campaign "Search | Poliweglan | Pl" \
        --dimension search_term --date-from 2026-08-01 --date-to 2026-10-04
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, sanitize_filename
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None

DIMENSIONS = ("device", "hour", "ad_group", "search_term", "conversion_action")


def _enum_name(enum_type_name, field_name, value):
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def _build_query(dimension, campaign_name, date_from, date_to):
    # Имя кампании вставляется в GAQL строкой — одинарные кавычки в имени
    # экранируем (в именах кампаний встречаются "|" и пробелы, кавычек обычно нет)
    camp = campaign_name.replace("'", "\\'")
    where = (
        f"campaign.name = '{camp}' "
        f"AND segments.date BETWEEN '{date_from}' AND '{date_to}'"
    )
    traffic = ("metrics.impressions, metrics.clicks, metrics.cost_micros, "
               "metrics.conversions")
    if dimension == "device":
        return f"SELECT segments.date, segments.device, {traffic} FROM campaign WHERE {where}"
    if dimension == "hour":
        return f"SELECT segments.date, segments.hour, {traffic} FROM campaign WHERE {where}"
    if dimension == "ad_group":
        return f"SELECT segments.date, ad_group.name, {traffic} FROM ad_group WHERE {where}"
    if dimension == "search_term":
        return (f"SELECT segments.date, ad_group.name, search_term_view.search_term, "
                f"{traffic} FROM search_term_view WHERE {where}")
    if dimension == "conversion_action":
        return (f"SELECT segments.date, segments.conversion_action_name, "
                f"metrics.conversions, metrics.all_conversions "
                f"FROM campaign WHERE {where} AND metrics.all_conversions > 0")
    raise ValueError(dimension)


def fetch(ga_service, customer_id, campaign_name, dimension, date_from, date_to):
    query = _build_query(dimension, campaign_name, date_from, date_to)
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            row = {"Date": r.segments.date}
            if dimension == "device":
                row["Device"] = _enum_name("DeviceEnum", "Device", r.segments.device)
            elif dimension == "hour":
                row["Hour"] = r.segments.hour
            elif dimension == "ad_group":
                row["Ad_group"] = r.ad_group.name
            elif dimension == "search_term":
                row["Ad_group"] = r.ad_group.name
                row["Search_term"] = r.search_term_view.search_term
            elif dimension == "conversion_action":
                row["Conversion_action"] = r.segments.conversion_action_name
                row["Conversions"] = r.metrics.conversions
                row["All_conversions"] = r.metrics.all_conversions
                rows.append(row)
                continue
            row["Impressions"] = r.metrics.impressions
            row["Clicks"] = r.metrics.clicks
            row["Cost"] = round(r.metrics.cost_micros / 1_000_000, 2)
            row["Conversions"] = r.metrics.conversions
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True, help="customer_id (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/')
    ap.add_argument("--campaign", required=True, help="Точное имя кампании")
    ap.add_argument("--dimension", required=True, choices=DIMENSIONS)
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    customer_id = args.customer_id.replace("-", "").strip()
    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    df = fetch(ga_service, customer_id, args.campaign, args.dimension, args.date_from, args.date_to)

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / (
        f"gads_{args.dimension}_by_day_{sanitize_filename(args.campaign)}"
        f"_{args.date_from}_to_{args.date_to}.csv"
    )
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} строк)")


if __name__ == "__main__":
    main()
