#!/usr/bin/env python
# coding: utf-8
"""Регулярный инструмент: по каждой размерной группе товаров (Ad Group) в
Shopping-кампании находит поисковые запросы на размеры, которых нет в фиде,
и сразу генерирует готовый список минус-фраз (все варианты написания) для
занесения в минус-слова.

Зачем отдельно от `gads_shopping_size_gap_monitor.py`: тот скрипт даёт общую
картину по всей кампании (сколько денег уходит на запросы вне фида). Этот —
для регулярной рабочей рутины: у EkspertAgro `shop_search` разбита на
Ad Group по размеру (`3x4`, `3x6`, `2x4`, `4x6`, `all products` для
остального — см. `Клиенты/EkspertAgro/Мерчант/Решения.md`, запись
2026-09-28), и в каждой такой группе полезно отдельно видеть, залетают ли
туда запросы на размеры, которых нет в каталоге вообще — их сразу минусовать
готовым списком, а не собирать формулировки вручную по одной.

Как определяется "новый" размер: сравнение идёт с ПОЛНЫМ списком размеров
из фида (через `shopping_performance_view` по всей кампании, не только по
этой Ad Group) — не с ожидаемым размером самой группы. Это специально:
если в группу "3x4" зашёл трафик по "3x6" (который есть в фиде, но должен
показываться в другой группе) — это проблема таргетинга группы, не тема
этого инструмента; если зашёл по "2x3" (которого нет нигде в каталоге) —
это и есть "новый размер", который здесь ищем.

Хранение состояния между запусками: дата последнего запроса сохраняется в
маленьком JSON рядом с остальными файлами клиента (`<client-folder>/
Статистика/shopping_size_negatives_state_<кампания>.json`), чтобы каждый
следующий регулярный запуск сам продолжал с той даты, на которой
остановился предыдущий, без ручного ввода периода каждый раз. Первый
запуск без сохранённого состояния берёт последние 30 дней.

Использование:
    python gads_shopping_size_negatives_by_group.py --customer-id 882-613-4558 \
        --client-folder "EkspertAgro/Мерчант" --campaign "shop_search"

    # первый запуск/переопределение периода вручную
    python gads_shopping_size_negatives_by_group.py --customer-id 882-613-4558 \
        --client-folder "EkspertAgro/Мерчант" --campaign "shop_search" --days 30

    # не трогать сохранённое состояние (для разового пересчёта без сдвига даты)
    python gads_shopping_size_negatives_by_group.py --customer-id 882-613-4558 \
        --client-folder "EkspertAgro/Мерчант" --campaign "shop_search" --no-save-state

Результат:
    - CSV в Статистика/ с разбивкой запрос x группа x размер x есть ли в фиде
    - CSV с готовыми минус-фразами по каждому новому размеру (все варианты
      написания — слитно/раздельно, запятая/точка/пробел для дробных,
      суффикс m/м, см. `_generate_negative_phrases`)
    - обновлённый state-файл с датой этого запуска (если не --no-save-state)

Не заливает минус-слова в аккаунт сам — только готовит список для ручного
или последующего автоматического добавления.
"""
import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from gads_shopping_size_gap_monitor import (
    extract_size_from_term,
    fetch_feed_sizes,
)


def fetch_search_terms_by_ad_group(ga_service, customer_id, campaign, date_from, date_to):
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
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
                "ad_group": r.ad_group.name,
                "date": r.segments.date,
                "term": r.search_term_view.search_term,
                "impressions": r.metrics.impressions,
                "clicks": r.metrics.clicks,
                "cost": r.metrics.cost_micros / 1_000_000,
                "conversions": r.metrics.conversions,
            })
    return pd.DataFrame(rows)


def _num_variants(n: str):
    """'2' -> ['2']; '2.5' -> ['2.5', '2,5', '2 5'] — три способа, которыми
    Google Ads реально режет/люди реально пишут дробную часть размера (см.
    `gads_shopping_size_gap_monitor.py`, `_SPACED_DECIMAL_RE`)."""
    if "." in n:
        whole, frac = n.split(".")
        return [n, n.replace(".", ","), f"{whole} {frac}"]
    return [n]


def generate_negative_phrases(size: str):
    """Все варианты написания размера 'AxB' для минус-фраз: слитно/раздельно
    вокруг x, с/без суффикса m, плюс варианты дробной части (см.
    `_num_variants`). Нижний регистр, без кириллической "х" — по явному
    решению пользователя 2026-09-27 (система нечувствительна к регистру,
    кириллица оставлена только для поиска/детектирования, не для минус-слов,
    которые пользователь предпочитает вводить латиницей)."""
    a, b = size.split("x")
    combos = set()
    for av in _num_variants(a):
        for bv in _num_variants(b):
            for sep_a in ("", " "):
                for sep_b in ("", " "):
                    for suffix in ("", "m", " m"):
                        combos.add(f"{av}{sep_a}x{sep_b}{bv}{suffix}")
    return sorted(combos)


def _state_path(out_dir: Path, campaign: str) -> Path:
    safe_campaign = re.sub(r"[^\w-]+", "_", campaign)
    return out_dir / f"shopping_size_negatives_state_{safe_campaign}.json"


def load_last_run_date(out_dir: Path, campaign: str):
    p = _state_path(out_dir, campaign)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("last_date_to")
    except (json.JSONDecodeError, OSError):
        return None


def save_last_run_date(out_dir: Path, campaign: str, date_to: str):
    p = _state_path(out_dir, campaign)
    p.write_text(json.dumps({"last_date_to": date_to}, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без) — если клиент не заведён в таблице")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "EkspertAgro/Мерчант"')
    ap.add_argument("--campaign", required=True, help="Точное название Shopping-кампании в Поиске")
    ap.add_argument("--days", type=int, default=30, help="Использовать, только если нет сохранённого состояния или задан явно")
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет автоматический расчёт от состояния/--days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--no-save-state", action="store_true", help="Не обновлять файл состояния (для разового пересчёта без сдвига даты следующего запуска)")
    ap.add_argument("--exclude-ad-group", action="append", default=[], help="Название Ad Group, которую пропустить (можно повторять) — напр. общую 'all products'")
    ap.add_argument("--hide-zero-impressions", action="store_true", help="Скрыть новые размеры без единого показа (по умолчанию показаны все — включая 0 кликов, т.к. 0 кликов не значит 0 показов/сигнала)")
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

    out_dir = client_stats_dir(args.client_folder)

    date_to = args.date_to or str(date.today() - timedelta(1))
    if args.date_from:
        date_from = args.date_from
    else:
        last_run = load_last_run_date(out_dir, args.campaign)
        if last_run:
            date_from = str(date.fromisoformat(last_run) + timedelta(1))
            print(f"Найдено состояние предыдущего запуска: продолжаем с {date_from} (после {last_run})")
        else:
            date_from = str(date.today() - timedelta(args.days))
            print(f"Состояния не найдено — берём последние {args.days} дней от {date_from}")

    if date_from > date_to:
        print(f"Период уже полностью проверен (следующий доступный день {date_from} позже {date_to}) — новых данных нет.")
        return

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | кампания '{args.campaign}' | период {date_from} -> {date_to}")

    feed_sizes, _ = fetch_feed_sizes(ga_service, customer_id, args.campaign, date_from, date_to)
    print(f"Размеров в фиде: {len(feed_sizes)} — {sorted(feed_sizes)}")

    df = fetch_search_terms_by_ad_group(ga_service, customer_id, args.campaign, date_from, date_to)
    if df.empty:
        print("Нет данных search_term_view за период.")
        if not args.no_save_state:
            save_last_run_date(out_dir, args.campaign, date_to)
        return

    if args.exclude_ad_group:
        df = df[~df["ad_group"].isin(args.exclude_ad_group)]

    df["size"] = df["term"].apply(extract_size_from_term)
    df["in_feed"] = df["size"].apply(lambda s: (s in feed_sizes) if s is not None else None)

    safe_campaign = re.sub(r"[^\w-]+", "_", args.campaign)
    terms_out = out_dir / f"gads_shopping_size_by_adgroup_{safe_campaign}_{date_from}_to_{date_to}.csv"
    df.to_csv(terms_out, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {terms_out} ({len(df)} строк search_term_view)")

    sized = df[df["size"].notna()]
    print("\n=== По группам: запросы с размером, есть ли размер в фиде? ===")
    by_group = sized.groupby(["ad_group", "in_feed"]).agg(
        clicks=("clicks", "sum"), cost=("cost", "sum"), conversions=("conversions", "sum")
    )
    print(by_group.to_string())

    new_sizes_rows = sized[sized["in_feed"] == False]
    if args.hide_zero_impressions:
        new_sizes_rows = new_sizes_rows[new_sizes_rows["impressions"] > 0]
    if new_sizes_rows.empty:
        print("\nНовых размеров (вне фида) за период не найдено ни в одной группе.")
        if not args.no_save_state:
            save_last_run_date(out_dir, args.campaign, date_to)
        return

    per_group_size = new_sizes_rows.groupby(["ad_group", "size"]).agg(
        impressions=("impressions", "sum"), clicks=("clicks", "sum"), cost=("cost", "sum"), conversions=("conversions", "sum")
    ).reset_index().sort_values(["ad_group", "impressions"], ascending=[True, False])

    print("\n=== НОВЫЕ РАЗМЕРЫ (нет в фиде) по группам ===")
    print(per_group_size.to_string(index=False))

    new_sizes = sorted(new_sizes_rows["size"].unique())
    phrase_rows = []
    for size in new_sizes:
        for phrase in generate_negative_phrases(size):
            phrase_rows.append({"new_size": size, "negative_phrase": phrase, "match_type": "phrase"})
    phrases_df = pd.DataFrame(phrase_rows)
    phrases_out = out_dir / f"gads_shopping_new_size_negatives_{safe_campaign}_{date_from}_to_{date_to}.csv"
    phrases_df.to_csv(phrases_out, index=False, encoding="utf-8-sig")
    print(f"\nСохранено {len(phrases_df)} минус-фраз для {len(new_sizes)} новых размеров: {phrases_out}")

    if not args.no_save_state:
        save_last_run_date(out_dir, args.campaign, date_to)
        print(f"\nСостояние обновлено: следующий запуск продолжит с {str(date.fromisoformat(date_to) + timedelta(1))}")


if __name__ == "__main__":
    main()
