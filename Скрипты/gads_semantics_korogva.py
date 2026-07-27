#!/usr/bin/env python
# coding: utf-8
"""Снапшот семантики Google Ads для Корогвы — со спец-фильтрацией под клиента.

Один аккаунт Google Ads (client_id 845-234-6433), тот же спец-фильтр
Merchant/не-Merchant, что и в gads_stats_korogva.py (см. is_merchant там):
  - Ключевые слова тянутся ТОЛЬКО по обычным (не-Merchant) кампаниям — у
    Merchant Center/Shopping своих текстовых ключей нет, там таргетинг по фиду.
  - Поисковые запросы тянутся по ВСЕМ кампаниям (Merchant и не-Merchant) — нужно
    видеть, что реально ищут по товарным кампаниям тоже, чтобы найти запросы,
    которые стоит добавить как ключи в обычные Search-кампании.

Конверсии: по решению пользователя (см. Клиенты/Корогва/Цели/goals.md) данные
до 2026-07-09 признаны ненадёжными — трафик/клики берутся за всё окно --days,
конверсии считаются только с 2026-07-09 (или --conversions-date-from, если
передан явно).

Использование:
    python gads_semantics_korogva.py --days 60
    python gads_semantics_korogva.py --date-from 2026-05-28 --date-to 2026-07-26
"""
import argparse
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from gads_semantics import fetch_keywords, fetch_search_terms
from gads_stats_korogva import CLIENT_FOLDER, CLIENT_GADS, is_merchant, is_not_merchant

# Дата, с которой конверсия custom_purchase признана надёжной для расчётов
# (см. Клиенты/Корогва/Цели/goals.md, решение 2026-07-26). До этой даты старая
# цель конверсии в данных клиента считается некорректной.
DEFAULT_CONVERSIONS_DATE_FROM = "2026-07-09"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--conversions-date-from", default=DEFAULT_CONVERSIONS_DATE_FROM,
                     help=f"YYYY-MM-DD, по умолчанию {DEFAULT_CONVERSIONS_DATE_FROM}")
    args = ap.parse_args()

    row = get_client_row(CLIENT_GADS, tab="Google_Ads_API", agency="adwhite")
    customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    if not customer_id:
        print(f"У клиента '{CLIENT_GADS}' на вкладке 'Google_Ads_API' пустой client_id")
        return

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {CLIENT_FOLDER} | трафик {date_from} → {date_to} | "
          f"конверсии с {args.conversions_date_from}")
    out_dir = client_stats_dir(CLIENT_FOLDER)

    # Ключевые слова — только не-Merchant (обычные Search-кампании)
    df_keywords = fetch_keywords(
        ga_service, customer_id, date_from, date_to,
        conversions_date_from=args.conversions_date_from,
        campaign_filter=is_not_merchant,
    )
    keywords_path = out_dir / f"gads_korogva-gads-keywords_{date_from}_to_{date_to}.csv"
    df_keywords.to_csv(keywords_path, index=False, encoding="utf-8")
    print(f"Сохранено: {keywords_path} ({len(df_keywords)} ключей)")

    # Поисковые запросы — по всем кампаниям, с пометкой подпроекта
    for suffix, campaign_filter in (("gads", is_not_merchant), ("merchant", is_merchant)):
        df_terms = fetch_search_terms(
            ga_service, customer_id, date_from, date_to,
            conversions_date_from=args.conversions_date_from,
            campaign_filter=campaign_filter,
        )
        terms_path = out_dir / f"gads_korogva-{suffix}-searchterms_{date_from}_to_{date_to}.csv"
        df_terms.to_csv(terms_path, index=False, encoding="utf-8")
        print(f"Сохранено: {terms_path} ({len(df_terms)} запросов)")


if __name__ == "__main__":
    main()
