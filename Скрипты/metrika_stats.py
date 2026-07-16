#!/usr/bin/env python
# coding: utf-8
"""Снапшот статистики Яндекс.Метрики (визиты/цели) для одного клиента.

Адаптировано из E:/PythonProjects/RedBird/google-cloud-jobs (metrika-stats-job_src),
без BigQuery — один клиент за раз. Счётчик/токен берутся напрямую из общей
Google-таблицы (вкладка "Metrika"), результат кладётся в
Клиенты/<client_folder>/Статистика/.

Использование:
    python metrika_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" --days 30
    python metrika_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" \
        --date-from 2026-07-01 --date-to 2026-07-16 --goals 123456,789012
"""
import argparse
import sys
from datetime import date, timedelta

import requests

from _config import get_client_row, client_stats_dir

DEFAULT_DIMENSIONS = (
    "ym:s:date,ym:s:<attribution>TrafficSource,ym:s:<attribution>SourceEngine,"
    "ym:s:<attribution>DirectClickOrder,ym:s:UTMCampaign,ym:s:goal"
)
DEFAULT_METRICS = "ym:s:visits"


def fetch_metrika_report(counter, token, date_from, date_to, goals=None,
                          dimensions=DEFAULT_DIMENSIONS, metrics=DEFAULT_METRICS,
                          attribution="cross_device_last_yandex_direct_click"):
    filtering = f"ym:s:goal=.({','.join(goals)})" if goals else ""
    url = (
        f"https://api-metrika.yandex.ru/stat/v1/data.csv"
        f"?dimensions={dimensions}&metrics={metrics}&filters={filtering}"
        f"&date1={date_from}&date2={date_to}&attribution={attribution}"
        f"&limit=10000&offset=1&language=ru&accuracy=full&ids={counter}&oauth_token={token}"
    )
    req = requests.get(url, headers={"Authorization": f"OAuth {token}"}, timeout=300)
    if req.status_code != 200:
        print(f"Ошибка {req.status_code}: {req.text[:500]}")
        sys.exit(1)
    return req.content.decode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Значение колонки 'client' на вкладке Metrika")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "ЕГЭ Merlin"')
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--date-from", help="YYYY-MM-DD, переопределяет --days")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию вчера")
    ap.add_argument("--goals", help="Список ID целей через запятую, см. Клиенты/<клиент>/Цели/goals.md")
    args = ap.parse_args()

    row = get_client_row(args.client, tab="Metrika")
    counter = str(row.get("ym_counter", "")).strip()
    token = str(row.get("token", "")).strip()
    if not counter or not token:
        print(f"У клиента '{args.client}' на вкладке 'Metrika' пустой ym_counter/token")
        sys.exit(1)

    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.today() - timedelta(args.days))
    goals = [g.strip() for g in args.goals.split(",")] if args.goals else None

    print(f"Клиент: {args.client_folder} | период {date_from} → {date_to}")
    csv_text = fetch_metrika_report(counter, token, date_from, date_to, goals=goals)

    out_dir = client_stats_dir(args.client_folder)
    suffix = f"_goals-{'-'.join(goals)}" if goals else ""
    out_path = out_dir / f"metrika_{date_from}_to_{date_to}{suffix}.csv"
    out_path.write_text(csv_text, encoding="utf-8")
    print(f"Сохранено: {out_path}")


if __name__ == "__main__":
    main()
