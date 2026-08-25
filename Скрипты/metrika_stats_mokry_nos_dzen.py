#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики Метрики для "Франшиза Мокрый Нос Дзен" (Promo Pages).

Клиент-специфичный скрипт (спец-условия для сегмента трафика, см. README):
на общем счётчике франшизы "Мокрый Нос" (66145201) этот проект — трафик
и заявки именно с сервиса Яндекс Promo Pages, выделяется по условию
"UTM Source содержит promopages" (не заведён отдельной строкой в общей
таблице — используется токен любой активной строки с этим же счётчиком,
т.к. токен общий на весь аккаунт Redbird.Agency, см.
Клиенты/Франшиза Мокрый Нос Дзен/_project.md).

Отличия от общего metrika_stats.py:
  1. Фильтр "UTM Source содержит promopages" — передаётся напрямую в API
     (filters), а не постфильтрацией pandas, чтобы не тянуть лишнее.
  2. Атрибуция "первый источник, cross-device" (cross_device_first) вместо
     дефолтной cross_device_last_yandex_direct_click — см. Цели/goals.md,
     раздел "Атрибуция", договорённость с пользователем от 2026-08-25.
  3. Три ОТДЕЛЬНЫХ отчёта вместо одного с полным набором измерений: при
     попытке скомбинировать дату+источники+UTM+цель+пол+возраст+город в
     одном запросе (10 измерений) API отдаёт 200 с пустым телом без ошибки
     — при низкой кардинальности данных этого фильтра (61 визит по цели за
     8 мес.) настолько дробная группировка, видимо, превышает какой-то
     внутренний лимит числа групп. Проверено эмпирически: тот же фильтр с
     9 измерениями (без regionCity) отдаёт данные корректно, значит именно
     совместное присутствие всех UTM-полей + demo + geo ломает выборку, а
     не какое-то одно измерение само по себе. Решение: отчёт по статьям
     (UTMCampaign/UTMContent), отчёт по демографии (пол+возраст), отчёт по
     гео (город+страна) — раздельно, с одинаковым фильтром/целью/атрибуцией.
  4. Каждый отчёт выгружается ДВАЖДЫ — с фильтром по цели (конверсии,
     числитель) и без него (весь трафик Promo Pages, знаменатель) — нужно
     для расчёта CR% по каждому разрезу, не только сравнения абсолютных
     чисел заявок (файлы *_goals-<ID>_* и *_all-traffic_*).
  5. Максимальный период — с 2023-01-01, разбит на выгрузку по годам:
     весь диапазон 2023-01-01..сегодня одним запросом даёт 400 "Запрос
     слишком сложный" (see also лимит limit=10000 без пагинации в базовом
     fetch_metrika_report — на годовом окне безопаснее).

Важно: название статьи Promo Pages закодировано в UTM Campaign (не в UTM
Content) — пример значения: "Промостатья: Моя история 1 / Ж 25-54/
интерес_открытие бизнеса / рся / #dzen / 2603-1". UTM Content в этом
трафике несёт технический тег ("history" и т.п.), не текст статьи.

Использование:
    python metrika_stats_mokry_nos_dzen.py
    python metrika_stats_mokry_nos_dzen.py --date-from 2024-01-01 --date-to 2026-08-24
"""
import argparse
import io
from datetime import date, timedelta

import pandas as pd
import requests

from _config import get_client_row, client_stats_dir

CLIENT_FOLDER = "Франшиза Мокрый Нос Дзен"
# Токен общий на весь счётчик 66145201 (аккаунт Redbird.Agency) — берём из
# любой активной строки таблицы с этим счётчиком, этот проект отдельной
# строкой в таблице не заведён.
TOKEN_ANCHOR_CLIENT = "Мокрый Нос - Груминг Франшиза"
GOAL_ID = "143150284"
ATTRIBUTION = "cross_device_first"
UTM_SOURCE_FILTER = "promopages"
MIN_DATE = date(2023, 1, 1)  # раньше этой даты у счётчика 66145201 данных нет

# Каждый отчёт — пара (измерения с ym:s:goal для конверсий, измерения без
# него для общего трафика-знаменателя). Без ym:s:goal колонки те же минус
# "Достигнутая цель" — нужно для честного CR% (конверсии / все визиты), не
# только сравнения абсолютных чисел заявок.
REPORTS = {
    "articles": (
        "ym:s:date,ym:s:<attribution>SourceEngine,ym:s:UTMSource,"
        "ym:s:UTMCampaign,ym:s:UTMContent"
    ),
    "demographics": "ym:s:date,ym:s:UTMSource,ym:s:gender,ym:s:ageInterval",
    "geo": "ym:s:date,ym:s:UTMSource,ym:s:regionCity,ym:s:regionCountry",
}


def fetch(dimensions, counter, token, date_from, date_to, with_goal):
    dims = f"{dimensions},ym:s:goal" if with_goal else dimensions
    filters = f"ym:s:UTMSource=~'{UTM_SOURCE_FILTER}'"
    if with_goal:
        filters = f"ym:s:goal=.({GOAL_ID}) AND {filters}"
    params = {
        "dimensions": dims,
        "metrics": "ym:s:visits",
        "filters": filters,
        "date1": date_from,
        "date2": date_to,
        "attribution": ATTRIBUTION,
        "limit": 10000,
        "offset": 1,
        "language": "ru",
        "accuracy": "full",
        "ids": counter,
    }
    # requests urlencode-ит params сам — критично для filters (пробелы вокруг
    # AND, скобки, апострофы); сборка через f-string в готовый URL их не
    # энкодит и API молча возвращает 0 строк вместо ошибки.
    req = requests.get(
        "https://api-metrika.yandex.ru/stat/v1/data.csv",
        params=params, headers={"Authorization": f"OAuth {token}"}, timeout=300,
    )
    if req.status_code != 200:
        raise SystemExit(f"Ошибка {req.status_code}: {req.text[:500]}")
    return req.content.decode("utf-8")


def year_chunks(date_from: date, date_to: date):
    """Разбивает диапазон на годовые куски — весь период 2023..сегодня одним
    запросом превышает допустимую сложность запроса API (400 query_error)."""
    chunks = []
    start = date_from
    while start <= date_to:
        end = min(date(start.year, 12, 31), date_to)
        chunks.append((start, end))
        start = date(start.year + 1, 1, 1)
    return chunks


def quarter_chunks(date_from: date, date_to: date):
    """Более мелкое дробление (по кварталам) — нужно для отчётов без фильтра
    по цели: без ym:s:goal выборка не сужена целью (весь трафик Promo Pages
    за период), и на годовом окне это тоже превышает сложность запроса."""
    chunks = []
    start = date_from
    while start <= date_to:
        quarter_end_month = ((start.month - 1) // 3 + 1) * 3
        if quarter_end_month == 12:
            end = date(start.year, 12, 31)
        else:
            end = date(start.year, quarter_end_month + 1, 1) - timedelta(days=1)
        end = min(end, date_to)
        chunks.append((start, end))
        start = end + timedelta(days=1)
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", help="YYYY-MM-DD, по умолчанию 2023-01-01 (максимальный доступный период)")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(TOKEN_ANCHOR_CLIENT, tab="Metrika")
    counter = str(row.get("ym_counter", "")).strip()
    token = str(row.get("token", "")).strip()
    if not counter or not token:
        raise SystemExit(f"У '{TOKEN_ANCHOR_CLIENT}' на вкладке 'Metrika' пустой ym_counter/token")

    date_to = date.fromisoformat(args.date_to) if args.date_to else date.today() - timedelta(1)
    date_from = date.fromisoformat(args.date_from) if args.date_from else MIN_DATE

    print(f"Клиент: {CLIENT_FOLDER} | период {date_from} → {date_to} | атрибуция {ATTRIBUTION}")
    out_dir = client_stats_dir(CLIENT_FOLDER)

    for report_name, dimensions in REPORTS.items():
        for with_goal in (True, False):
            chunker = year_chunks if with_goal else quarter_chunks
            frames = []
            for chunk_from, chunk_to in chunker(date_from, date_to):
                csv_text = fetch(dimensions, counter, token, str(chunk_from), str(chunk_to), with_goal)
                df = pd.read_csv(io.StringIO(csv_text))
                df = df[df.iloc[:, 0] != "Итого и средние"]
                if len(df):
                    frames.append(df)

            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            if len(df) >= 10000:
                print(f"ВНИМАНИЕ [{report_name}, with_goal={with_goal}]: 10000+ строк за один год — возможна обрезка по лимиту API")

            if "Визиты" in df.columns:
                df["Визиты"] = pd.to_numeric(df["Визиты"], errors="coerce").fillna(0)

            suffix = f"goals-{GOAL_ID}" if with_goal else "all-traffic"
            out_path = out_dir / f"metrika_promopages_{report_name}_{date_from}_to_{date_to}_{suffix}.csv"
            df.to_csv(out_path, index=False, encoding="utf-8")
            total_visits = df["Визиты"].sum() if "Визиты" in df.columns else 0
            print(f"[{report_name}, {suffix}] сохранено: {out_path} ({len(df)} строк, {total_visits} визитов)")


if __name__ == "__main__":
    main()
