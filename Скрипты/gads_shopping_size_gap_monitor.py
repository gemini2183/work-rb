#!/usr/bin/env python
# coding: utf-8
"""Мониторинг Shopping-кампаний: поисковые запросы на размеры товара
(теплицы/тоннели у EkspertAgro, но логика общая для любого товара с размером
в title вида "NxM<единица>"), которых НЕТ в текущем фиде.

Зачем: `search_term_view` считает метрики по ТЕКСТУ запроса, а не по
показанному товару. Если в запросе указан размер, которого нет в каталоге,
Google Shopping всё равно может показать ближайший товар-заменитель — клик
и (изредка) конверсия при этом засчитываются под текстом исходного запроса.
Из-за этого разовый анализ может принять "конверсии по запросу 3x5" за
"продажи товара 3x5", хотя такого товара нет (см. Клиенты/EkspertAgro/
Мерчант/Решения.md, запись 2026-09-24, раздел ИСПРАВЛЕНИЕ — с этого кейса
и родился этот скрипт). Регулярный запуск нужен, чтобы вовремя увидеть
случай, когда расход на такие "запросы-сироты" растёт, а конверсий по ним
по-прежнему нет — это сигнал добавить их минус-словами, в отличие от случая
с устойчивыми конверсиями через товар-заменитель, который вместо этого
сигнализирует "спрос есть, стоит рассмотреть добавление размера в фид".

Источник списка размеров фида — не отдельный XML-файл, а сами показанные
товары за период (shopping_performance_view, поле segments.product_title) —
так список всегда соответствует тому, что реально сейчас в Merchant Center
для этого аккаунта, без риска устареть относительно последнего разбора XML.

Разбор размера учитывает варианты написания, реально встреченные в данных
этого клиента (не гипотетические): слитно "3x6", с пробелами "3 x 6",
кириллическая "х" вместо латинской "x", десятичная часть через запятую или
точку "2,5x4"/"2.5x4", с пробелом вместо разделителя дробной части "3 5x6"
(значит "3.5x6" — Google иногда режет запрос на токены по пробелу),
суффикс "m"/"м" на конце размера теплицы ("3x6m") — используется, чтобы
отличить реальный размер от паразитного второго числового паттерна в
title вида "profil 40x20mm" (профиль трубы, не размер теплицы: единственное
отличие в тексте — "mm" после профиля против "m" после размера теплицы).

Использование:
    python gads_shopping_size_gap_monitor.py --customer-id 882-613-4558 \
        --client-folder "EkspertAgro/Мерчант" --campaign "shop_search" --days 30

    python gads_shopping_size_gap_monitor.py --client "Клиент - Google Ads" \
        --client-folder "Клиент" --campaign "Merchant_Shopping" --days 14

Результат — CSV в Статистика/ клиента с разбивкой по размеру запроса
(в фиде / не в фиде) + сводка в консоль с топом "запросов-сирот" по расходу.
Не заливает и не редактирует ничего в аккаунте — только отчёт для решения
человеком (минус-слова или расширение фида).
"""
import argparse
import re
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

# Реальный размер теплицы: два числа с "x"/"х" между ними (возможны пробелы
# и запятая/точка как разделитель дробной части), сразу за которым идёт "m"
# или "м" (не "mm" — это профиль трубы, см. docstring).
_SIZE_WITH_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(?:m|м)(?![a-zа-я])",
    re.IGNORECASE,
)
# Fallback для текста запроса, где "m" на конце часто отсутствует
# ("szklarnia 3x6", не "szklarnia 3x6m") — берём первый NxM без требования
# суффикса, но по-прежнему исключаем очевидные "NxMmm" (профиль).
_SIZE_ANY_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[xх]\s*(\d+(?:[.,]\d+)?)(?!\s*mm)",
    re.IGNORECASE,
)
# "3 5x6" / "2 5 x 4" — пробел вместо точки в дробной части (Google иногда
# режет запрос на токены по пробелу). Наблюдаемо на реальных данных только
# как "N 5" с однозначным N (2/3, изредка 1), СРАЗУ ЗА КОТОРЫМ идёт "x"/"х"
# (иначе не отличить от обычного "цифра пробел цифра", напр. "2 x 3", где
# пробел вокруг "x", а не внутри числа) — теплицы этой ширины (2.5м, 3.5м)
# действительно существуют в ассортименте, а "5" как отдельная целая ширина
# ни разу не встречена в данных. \b после "5" не работает как граница перед
# "x" (обе части \w) — поэтому вместо lookahead на \b здесь явно требуем
# "x"/"х" следующим символом.
_SPACED_DECIMAL_RE = re.compile(r"\b(\d)\s+5(?=\s*[xх])", re.IGNORECASE)


def _join_spaced_decimals(text: str) -> str:
    return _SPACED_DECIMAL_RE.sub(r"\1.5", text)


def _strip_trailing_zeros(n: str) -> str:
    """'10' -> '10' (целое, не трогаем), '2.50' -> '2.5', '2.0' -> '2'."""
    if "." not in n:
        return n
    return n.rstrip("0").rstrip(".")


def _normalize_size(a: str, b: str) -> str:
    a = _strip_trailing_zeros(a.replace(",", "."))
    b = _strip_trailing_zeros(b.replace(",", "."))
    return f"{a}x{b}"


def extract_size_from_title(title: str):
    """Размер товара из title фида — требует суффикс m/м, чтобы не путать
    с профилем трубы (40x20mm)."""
    text = _join_spaced_decimals(str(title))
    m = _SIZE_WITH_UNIT_RE.search(text)
    if not m:
        return None
    return _normalize_size(m.group(1), m.group(2))


def extract_size_from_term(term: str):
    """Размер из текста поискового запроса — суффикс m/м необязателен
    (люди часто пишут "szklarnia 3x6" без единиц), но паттерн профиля
    "NxNmm" всё равно исключаем на случай, если кто-то ищет по профилю."""
    text = _join_spaced_decimals(str(term))
    m = _SIZE_ANY_RE.search(text)
    if not m:
        return None
    return _normalize_size(m.group(1), m.group(2))


def fetch_search_terms(ga_service, customer_id, campaign, date_from, date_to):
    query = f"""
        SELECT
            campaign.name,
            segments.date,
            search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.name = '{campaign}'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            rows.append({
                "date": r.segments.date,
                "term": r.search_term_view.search_term,
                "impressions": r.metrics.impressions,
                "clicks": r.metrics.clicks,
                "cost": r.metrics.cost_micros / 1_000_000,
                "conversions": r.metrics.conversions,
            })
    return pd.DataFrame(rows)


def fetch_feed_sizes(ga_service, customer_id, campaign, date_from, date_to):
    """Размеры, реально присутствующие в фиде — по title товаров, которые
    показывались в кампании за период (а не по отдельному XML-файлу фида,
    см. docstring модуля)."""
    query = f"""
        SELECT
            campaign.name,
            segments.product_item_id,
            segments.product_title
        FROM shopping_performance_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.name = '{campaign}'
    """
    titles = set()
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for r in batch.results:
            titles.add(r.segments.product_title)

    sizes = set()
    for title in titles:
        sz = extract_size_from_title(title)
        if sz:
            sizes.add(sz)
    return sizes, titles


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без) — если клиент не заведён в таблице")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "EkspertAgro/Мерчант"')
    ap.add_argument("--campaign", required=True, help="Точное название Shopping-кампании в Поиске")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--min-cost", type=float, default=0.0, help="Показать в сводке только размеры-сироты с расходом от этой суммы (PLN и т.п., валюта аккаунта)")
    ap.add_argument("--show-zero-clicks", action="store_true", help="Включить в сводку размеры-сироты с 0 кликов (обычно случайный текстовый шум вроде толщины поликарбоната в мм) — по умолчанию скрыты")
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

    print(f"Клиент: {args.client_folder} | кампания '{args.campaign}' | период {date_from} -> {date_to}")

    feed_sizes, feed_titles = fetch_feed_sizes(ga_service, customer_id, args.campaign, date_from, date_to)
    print(f"Размеров в фиде (по показанным товарам за период): {len(feed_sizes)} — {sorted(feed_sizes)}")

    df = fetch_search_terms(ga_service, customer_id, args.campaign, date_from, date_to)
    if df.empty:
        print("Нет данных search_term_view за период.")
        return

    df["size"] = df["term"].apply(extract_size_from_term)
    df["in_feed"] = df["size"].apply(lambda s: (s in feed_sizes) if s is not None else None)

    out_dir = client_stats_dir(args.client_folder)
    safe_campaign = re.sub(r"[^\w-]+", "_", args.campaign)
    out_path = out_dir / f"gads_shopping_size_gap_{safe_campaign}_{date_from}_to_{date_to}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {out_path} ({len(df)} строк search_term_view)")

    sized = df[df["size"].notna()]
    summary = sized.groupby("in_feed").agg(
        clicks=("clicks", "sum"), cost=("cost", "sum"), conversions=("conversions", "sum")
    )
    print("\n=== Запросы с размером: есть ли такой размер в фиде? ===")
    print(summary.to_string())

    orphans = sized[sized["in_feed"] == False]
    if orphans.empty:
        print("\nЗапросов на размеры вне фида за период не найдено.")
        return

    orphan_agg = orphans.groupby("size").agg(
        clicks=("clicks", "sum"), cost=("cost", "sum"), conversions=("conversions", "sum")
    ).reset_index()
    orphan_agg["cost_per_conv"] = orphan_agg["cost"] / orphan_agg["conversions"]
    orphan_agg = orphan_agg.sort_values("cost", ascending=False)
    if not args.show_zero_clicks:
        orphan_agg = orphan_agg[orphan_agg["clicks"] > 0]
    orphan_agg = orphan_agg[orphan_agg["cost"] >= args.min_cost]

    print(f"\n=== РАЗМЕРЫ-СИРОТЫ (нет в фиде), расход от {args.min_cost} ===")
    print(orphan_agg.to_string(index=False))

    no_conv = orphan_agg[orphan_agg["conversions"] == 0]
    if not no_conv.empty:
        total_wasted = no_conv["cost"].sum()
        print(f"\nВНИМАНИЕ: {len(no_conv)} размер(ов)-сирот без единой конверсии, суммарный расход {total_wasted:.2f} — кандидаты на минус-слова, если расход продолжит расти:")
        print(no_conv[["size", "clicks", "cost"]].to_string(index=False))


if __name__ == "__main__":
    main()
