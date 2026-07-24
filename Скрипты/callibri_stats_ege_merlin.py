#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики звонков Callibri для ЕГЭ Merlin — со спец-фильтрацией под клиента.

Использует общий сбор данных из callibri_stats.py (fetch_callibri_calls), затем
применяет обработку, специфичную для этого клиента (1:1 логика прод-job
E:/PythonProjects/RedBird/google-cloud-jobs/redbird/func/callibri2_merlin_ege/main.py):
  1. Классификация Source по traffic_type/utm_source:
     - "Контекст": traffic_type пустой И conversations_number == 1.
     - "YaDirect": traffic_type непустой И utm_source содержит "yandex".
     Звонки, не попавшие ни в одну категорию, отбрасываются.
  2. Исключить летнюю кампанию по условию "utm_content содержит letnie"
     (см. Клиенты/ЕГЭ Merlin/Цели/goals.md и вкладку "Metrika" общей таблицы,
     колонка conditions — то же условие letnie, что и для Метрики, так как
     счётчик/канал Callibri общий для core и letnie).
  3. Дедупликация звонков по (phone, месяц) — один и тот же звонящий в один
     месяц считается одной конверсией, не пере-считывается на каждый повторный
     звонок.

Для клиентов без спец-условий использовать общий callibri_stats.py напрямую,
этот скрипт — не общий, только под ЕГЭ Merlin.

Использование:
    python callibri_stats_ege_merlin.py --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
from datetime import date, timedelta

import pandas as pd

from _config import client_stats_dir, get_client_row
from callibri_stats import fetch_callibri_calls

CLIENT = "ЕГЭ Merlin"
CLIENT_FOLDER = "ЕГЭ Merlin"


def apply_client_filters(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def classify(row):
        tt = row["traffic_type"]
        tt_empty = pd.isna(tt) or tt == ""
        if tt_empty and row["conversations_number"] == 1:
            return "Контекст"
        if not tt_empty and isinstance(row["utm_source"], str) and "yandex" in row["utm_source"]:
            return "YaDirect"
        return None

    df["Source"] = df.apply(classify, axis=1)
    df = df[df["Source"].isin(["Контекст", "YaDirect"])]

    df["utm_content"] = df["utm_content"].fillna("")
    df = df[~df["utm_content"].str.contains("letnie", na=False)]

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df["duplicated"] = df[["phone", "month"]].duplicated()
    df = df[~df["duplicated"]].drop(columns=["duplicated"])

    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(CLIENT, tab="Calibri")
    login = str(row.get("login", "")).strip()
    token = str(row.get("token", "")).strip()
    site_id = str(row.get("project_id", "")).strip()
    raw_channel_id = str(row.get("channel_id", "")).strip()
    if not login or not token or not site_id:
        print(f"У клиента '{CLIENT}' на вкладке 'Calibri' пустой login/token/project_id")
        return

    channel_ids = [int(x) for x in raw_channel_id.split(";")] if raw_channel_id else []

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    print(f"Клиент: {CLIENT_FOLDER} | период {date_from} → {date_to}")
    calls = fetch_callibri_calls(login, token, site_id, channel_ids, date_from, date_to)

    out_dir = client_stats_dir(CLIENT_FOLDER)
    out_path = out_dir / f"callibri_ege-merlin-core_{date_from}_to_{date_to}.csv"

    if calls.empty:
        print("Звонков за период не найдено")
        calls.to_csv(out_path, index=False, encoding="utf-8")
        print(f"Сохранено: {out_path}")
        return

    calls = calls[[
        "date", "channel_id", "conversations_number", "traffic_type",
        "utm_source", "utm_content", "phone", "landing_page",
    ]]
    calls = apply_client_filters(calls)
    calls = calls.sort_values(by=["date"])

    calls.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(calls)} звонков)")


if __name__ == "__main__":
    main()
