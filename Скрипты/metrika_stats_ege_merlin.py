#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики Метрики для ЕГЭ Merlin — со спец-фильтрацией под клиента.

Использует общий сбор данных из metrika_stats.py (fetch_metrika_report), затем
применяет фильтры, специфичные для этого клиента (1:1 логика прод-job
E:/PythonProjects/RedBird/google-cloud-jobs/redbird/func/ym2_merlin_ege/main.py):
  1. Только рекламный трафик (TrafficSource == "Переходы по рекламе").
  2. Только источник YaDirect (Яндекс: Директ / Яндекс: Не определено /
     Яндекс.Директ: Не определено — схлопываются в один YaDirect). GAds
     сюда не включаем — у этого клиента нет Google Ads, интересует только Директ.
  3. Исключить летнюю кампанию по условию "UTM Content не содержит letnie"
     (см. Клиенты/ЕГЭ Merlin/Цели/goals.md и вкладку "Metrika" общей таблицы,
     колонка conditions).

Для клиентов без спец-условий использовать общий metrika_stats.py напрямую,
этот скрипт — не общий, только под ЕГЭ Merlin.

Использование:
    python metrika_stats_ege_merlin.py --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
from datetime import date, timedelta

import pandas as pd

from _config import get_client_row, client_stats_dir
from metrika_stats import fetch_metrika_report

CLIENT = "ЕГЭ Merlin"
CLIENT_FOLDER = "ЕГЭ Merlin"
GOAL_ID = "222490461"


def apply_client_filters(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["TrafficSource"] == "Переходы по рекламе"]
    df = df.copy()
    df["Source"] = df["Source"].replace({
        "Яндекс: Директ": "YaDirect",
        "Яндекс: Не определено": "YaDirect",
        "Яндекс.Директ: Не определено": "YaDirect",
    })
    df = df[df["Source"] == "YaDirect"]
    df = df[~df["UTM Content"].astype(str).str.contains("letnie", na=False)]
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(CLIENT, tab="Metrika")
    counter = str(row.get("ym_counter", "")).strip()
    token = str(row.get("token", "")).strip()

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    print(f"Клиент: {CLIENT_FOLDER} | период {date_from} → {date_to}")
    csv_text = fetch_metrika_report(counter, token, date_from, date_to, goals=[GOAL_ID])

    import io
    df = pd.read_csv(io.StringIO(csv_text))
    df = df[df["Дата визита"] != "Итого и средние"]
    df["Визиты"] = pd.to_numeric(df["Визиты"], errors="coerce").fillna(0)
    df = df.rename(columns={
        "Дата визита": "Date",
        "Источник трафика": "TrafficSource",
        "Источник трафика (детально)": "Source",
        "Достигнутая цель": "Goal_name",
        "Визиты": "Goal_visits",
    })

    df = apply_client_filters(df)

    out_dir = client_stats_dir(CLIENT_FOLDER)
    out_path = out_dir / f"metrika_yadirect-core_{date_from}_to_{date_to}_goals-{GOAL_ID}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} строк, {df['Goal_visits'].sum()} визитов)")


if __name__ == "__main__":
    main()
