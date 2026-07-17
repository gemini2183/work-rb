#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики звонков Callibri (колл-трекинг) для одного клиента.

Адаптировано из E:/PythonProjects/RedBird/google-cloud-jobs
(redbird/func/callibri2_merlin_ege/main.py), без BigQuery — один клиент за
раз. Логин/токен/site_id/channel_id берутся из вкладки "Calibri" общей
Google-таблицы (см. _config.py), результат кладётся в
Клиенты/<client_folder>/Статистика/.

API Callibri отдаёт максимум 7 дней за один запрос — период автоматически
бьётся на недельные диапазоны.

Использование:
    python callibri_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" --days 30
    python callibri_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" \
        --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from time import sleep

import numpy as np
import pandas as pd
import requests

from _config import client_stats_dir, get_client_row

API_URL = "https://api.callibri.ru/site_get_statistics"


def _week_ranges(date_from: str, date_to: str):
    d_from = datetime.strptime(date_from, "%Y-%m-%d")
    d_to = datetime.strptime(date_to, "%Y-%m-%d")
    num = int(np.ceil(((d_to - d_from).days + 1) / 7))

    ranges = []
    for _ in range(num):
        d1 = d_from.strftime("%d.%m.%Y")
        d2 = (d_from + timedelta(6)).strftime("%d.%m.%Y") if (d_from + timedelta(6)) < d_to else d_to.strftime("%d.%m.%Y")
        ranges.append((d1, d2))
        d_from = d_from + timedelta(7)
    return ranges


def fetch_callibri_calls(login, token, site_id, channel_ids, date_from, date_to):
    frames = []
    for d1, d2 in _week_ranges(date_from, date_to):
        url = (
            f"{API_URL}?user_email={login}&user_token={token}"
            f"&site_id={site_id}&date1={d1}&date2={d2}"
        )
        resp = requests.get(url, verify=False, timeout=300)
        if resp.status_code != 200:
            print(f"Ошибка {resp.status_code}: {resp.text[:500]}")
            sys.exit(1)

        res = json.loads(resp.text)
        calls_data = []
        for ch in res.get("channels_statistics", []):
            calls_data += ch["calls"]

        if calls_data:
            frames.append(pd.DataFrame(calls_data))
        sleep(2)

    if not frames:
        return pd.DataFrame()

    calls = pd.concat(frames, ignore_index=True)
    calls = calls[calls["channel_id"].isin(channel_ids)]
    return calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Значение колонки 'client' на вкладке Calibri")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "ЕГЭ Merlin"')
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    args = ap.parse_args()

    row = get_client_row(args.client, tab="Calibri")
    login = str(row.get("login", "")).strip()
    token = str(row.get("token", "")).strip()
    site_id = str(row.get("project_id", "")).strip()
    raw_channel_id = str(row.get("channel_id", "")).strip()
    if not login or not token or not site_id:
        print(f"У клиента '{args.client}' на вкладке 'Calibri' пустой login/token/project_id")
        sys.exit(1)

    channel_ids = [int(x) for x in raw_channel_id.split(";")] if raw_channel_id else []

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    print(f"Клиент: {args.client_folder} | период {date_from} → {date_to}")
    calls = fetch_callibri_calls(login, token, site_id, channel_ids, date_from, date_to)

    if calls.empty:
        print("Звонков за период не найдено")
    else:
        calls = calls[[
            "date", "channel_id", "conversations_number", "traffic_type",
            "utm_source", "utm_content", "phone", "landing_page",
        ]]
        calls = calls.sort_values(by=["date"])

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / f"callibri_{date_from}_to_{date_to}.csv"
    calls.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path}")


if __name__ == "__main__":
    main()
