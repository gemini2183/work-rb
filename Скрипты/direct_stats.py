#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики Яндекс.Директа для одного клиента в Статистика/клиента.

Адаптировано из E:/PythonProjects/RedBird/google-cloud-jobs (direct_stats_job_src),
но без BigQuery/Google Sheets — работает на один клиента за раз, локально,
для нужд этого проекта управления рекламой.

Использование:
    python direct_stats.py --client-key EGEMERLIN --client-folder "ЕГЭ Merlin" --days 30
    python direct_stats.py --client-key EGEMERLIN --client-folder "ЕГЭ Merlin" \
        --date-from 2026-07-01 --date-to 2026-07-16 --goals 123456,789012

Логин и токен берутся из .env в корне вики (см. _config.py), по префиксу
--client-key. Результат — TSV-файл с разбивкой по дням/кампаниям.
"""
import argparse
import sys
from datetime import date, timedelta
from time import sleep

import requests

from _config import load_client_env, client_stats_dir

REPORTS_URL = "https://api.direct.yandex.com/json/v5/reports"

DEFAULT_FIELDS = [
    "Date", "CampaignId", "CampaignName",
    "Impressions", "Clicks", "Cost", "Conversions", "Bounces",
]


def fetch_direct_report(login, token, date_from, date_to, fields, goals=None,
                         attribution=("LYDC",), source_type=("SEARCH", "AD_NETWORK")):
    import json
    import numpy as np

    headers = {
        "Authorization": "Bearer " + token,
        "Client-Login": login,
        "Accept-Language": "ru",
        "processingMode": "auto",
        "returnMoneyInMicros": "false",
        "skipReportHeader": "true",
        "skipReportSummary": "true",
    }

    body = {
        "params": {
            "SelectionCriteria": {
                "DateFrom": date_from,
                "DateTo": date_to,
                "Filter": [
                    {"Field": "AdNetworkType", "Operator": "IN", "Values": list(source_type)}
                ],
            },
            "FieldNames": fields,
            "ReportName": f"OTCHET{np.random.randint(1_000_000)}",
            "ReportType": "CUSTOM_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",
            "IncludeDiscount": "NO",
        }
    }
    if goals:
        body["params"]["Goals"] = goals
        body["params"]["AttributionModels"] = list(attribution)

    body_json = json.dumps(body, indent=4)

    while True:
        req = requests.post(REPORTS_URL, body_json, headers=headers)
        req.encoding = "utf-8"
        if req.status_code == 200:
            print("Отчёт получен")
            return req.content.decode("utf-8")
        elif req.status_code in (201, 202):
            retry_in = int(req.headers.get("retryIn", 30))
            print(f"Отчёт формируется, повтор через {retry_in}с")
            sleep(retry_in)
        else:
            print(f"Ошибка {req.status_code}: {req.text[:500]}")
            sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-key", required=True, help="Префикс в .env, напр. EGEMERLIN")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "ЕГЭ Merlin"')
    ap.add_argument("--days", type=int, default=30, help="Сколько последних дней взять (по умолчанию 30)")
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--goals", help="Список ID целей через запятую (для конверсий по атрибуции)")
    args = ap.parse_args()

    env = load_client_env(args.client_key)
    login = env.get("DIRECT_LOGIN")
    token = env.get("DIRECT_TOKEN")
    if not login or not token:
        print(f"Не найден {args.client_key}_DIRECT_LOGIN / {args.client_key}_DIRECT_TOKEN в .env")
        sys.exit(1)

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))

    goals = [g.strip() for g in args.goals.split(",")] if args.goals else None

    print(f"Клиент: {args.client_folder} | период {date_from} → {date_to}")
    tsv_text = fetch_direct_report(login, token, date_from, date_to, DEFAULT_FIELDS, goals=goals)

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / f"direct_{date_from}_to_{date_to}.tsv"
    out_path.write_text(tsv_text, encoding="utf-8")
    print(f"Сохранено: {out_path}")


if __name__ == "__main__":
    main()
