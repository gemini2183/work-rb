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
  3. Дополнительные измерения для разреза по статьям/демографии: UTM Content
     (статья Promo Pages), пол, возрастной интервал, регион (город).
  4. Максимальный период — с 2023-01-01 (задел с запасом на весь срок жизни
     счётчика; лишний хвост без данных просто не вернётся API).

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
from metrika_stats import DEFAULT_METRICS

CLIENT_FOLDER = "Франшиза Мокрый Нос Дзен"
# Токен общий на весь счётчик 66145201 (аккаунт Redbird.Agency) — берём из
# любой активной строки таблицы с этим счётчиком, этот проект отдельной
# строкой в таблице не заведён.
TOKEN_ANCHOR_CLIENT = "Мокрый Нос - Груминг Франшиза"
GOAL_ID = "143150284"
ATTRIBUTION = "cross_device_first"
UTM_SOURCE_FILTER = "promopages"

DIMENSIONS = (
    "ym:s:date,ym:s:<attribution>TrafficSource,ym:s:<attribution>SourceEngine,"
    "ym:s:UTMSource,ym:s:UTMCampaign,ym:s:UTMContent,ym:s:goal,"
    "ym:s:gender,ym:s:ageInterval,ym:s:regionCity"
)


def fetch_promopages_report(counter, token, date_from, date_to):
    """Как fetch_metrika_report, но с фильтром UTM Source прямо в API-запросе.

    Фильтрация на стороне API (а не постфильтрацией pandas после скачивания)
    важна из-за жёсткого limit=10000 без пагинации в общем скрипте — при
    таком наборе измерений (дата x источник x UTM x пол x возраст x город x
    цель) на большом периоде легко упереться в лимит и молча потерять
    строки, если тянуть весь трафик и фильтровать после.
    """
    params = {
        "dimensions": DIMENSIONS,
        "metrics": DEFAULT_METRICS,
        "filters": f"ym:s:goal=.({GOAL_ID}) AND ym:s:UTMSource=~'{UTM_SOURCE_FILTER}'",
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", default="2023-01-01", help="YYYY-MM-DD, по умолчанию 2023-01-01 (максимальный доступный период)")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(TOKEN_ANCHOR_CLIENT, tab="Metrika")
    counter = str(row.get("ym_counter", "")).strip()
    token = str(row.get("token", "")).strip()
    if not counter or not token:
        raise SystemExit(f"У '{TOKEN_ANCHOR_CLIENT}' на вкладке 'Metrika' пустой ym_counter/token")

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from

    print(f"Клиент: {CLIENT_FOLDER} | период {date_from} → {date_to} | атрибуция {ATTRIBUTION}")
    csv_text = fetch_promopages_report(counter, token, date_from, date_to)

    df = pd.read_csv(io.StringIO(csv_text))
    df = df[df["Дата визита"] != "Итого и средние"]
    df = df.rename(columns={
        "Дата визита": "Date",
        "Источник трафика": "TrafficSource",
        "Источник трафика (детально)": "Source",
        "UTM Source": "UTMSource",
        "UTM Campaign": "UTMCampaign",
        "UTM Content": "UTMContent",
        "Достигнутая цель": "Goal_name",
        "Пол": "Gender",
        "Возраст": "AgeInterval",
        "Город": "City",
        "Визиты": "Visits",
    })
    df["Visits"] = pd.to_numeric(df["Visits"], errors="coerce").fillna(0)

    if len(df) >= 10000:
        print("ВНИМАНИЕ: получено 10000+ строк — возможна обрезка по лимиту API "
              "(пагинация не реализована), сузьте период через --date-from/--date-to")

    out_dir = client_stats_dir(CLIENT_FOLDER)
    out_path = out_dir / f"metrika_promopages_{date_from}_to_{date_to}_goals-{GOAL_ID}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} строк, {df['Visits'].sum()} визитов)")


if __name__ == "__main__":
    main()
