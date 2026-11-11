#!/usr/bin/env python
# coding: utf-8
"""GA4: события по названиям — realtime (последние 30 минут) или по часам за дни (ТОЛЬКО ЧТЕНИЕ).

Зачем: после тестовой заявки/фокуса в форму быстро увидеть, дошли ли события (`lead_form_start`, `form_submit`,
`cta_click`…) до GA4. Realtime API не режет события по странице: счёт идёт по всему ресурсу за 30 минут, поэтому
сравнивать «до» и «после» теста (запуск до и после) и учитывать, что на ресурсе есть живой трафик. Дневной режим режет по
`pagePath` и источнику/каналу (там видна метка `claude_form_test`), но данные приходят с задержкой (часы).

Пояс ресурса Landver (549802233) — America/Los_Angeles: `dateHour` в этом поясе, ноябрь (PST) = Варшава − 9 ч.

Ключ: переменная GA4_KEY_FILE или значение по умолчанию как в ga4_behavior.py (в вики ключ не копировать).

Использование:
    python ga4_realtime_events.py --property 549802233 --realtime
    python ga4_realtime_events.py --property 549802233 --realtime --events lead_form_start form_submit
    python ga4_realtime_events.py --property 549802233 --from 2026-11-10 --to 2026-11-11 --page-contains abogado --events lead_form_start form_submit form_start
"""
import argparse
import os

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Filter, FilterExpression, Metric, MinuteRange,
    RunRealtimeReportRequest, RunReportRequest,
)
from google.oauth2 import service_account

DEFAULT_KEY = r"E:\PythonProjects\RedBird\google-cloud-jobs\adwhite\func\ga4_profimet\redbird-196813-ga4.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", required=True)
    ap.add_argument("--realtime", action="store_true", help="последние 30 минут по ресурсу, события по названиям")
    ap.add_argument("--from", dest="d1")
    ap.add_argument("--to", dest="d2")
    ap.add_argument("--page-contains", default="", help="подстрока pagePath (только дневной режим)")
    ap.add_argument("--events", nargs="*", default=[], help="показать только эти события")
    args = ap.parse_args()

    key = os.environ.get("GA4_KEY_FILE", DEFAULT_KEY)
    client = BetaAnalyticsDataClient(credentials=service_account.Credentials.from_service_account_file(key))
    prop = f"properties/{args.property}"

    if args.realtime:
        r = client.run_realtime_report(RunRealtimeReportRequest(
            property=prop, dimensions=[Dimension(name="eventName")], metrics=[Metric(name="eventCount")],
            minute_ranges=[MinuteRange(start_minutes_ago=29, end_minutes_ago=0)]))
        for row in r.rows:
            name = row.dimension_values[0].value
            if not args.events or name in args.events:
                print(name, row.metric_values[0].value)
        print("строк:", len(r.rows), "(ресурс целиком, последние 30 минут)")
        return

    if not (args.d1 and args.d2):
        raise SystemExit("нужны --realtime или --from/--to")
    req = RunReportRequest(
        property=prop, date_ranges=[DateRange(start_date=args.d1, end_date=args.d2)],
        dimensions=[Dimension(name="dateHour"), Dimension(name="pagePath"), Dimension(name="eventName"),
                    Dimension(name="sessionSourceMedium")],
        metrics=[Metric(name="eventCount")], limit=10000)
    if args.page_contains:
        req.dimension_filter = FilterExpression(filter=Filter(
            field_name="pagePath",
            string_filter=Filter.StringFilter(match_type=Filter.StringFilter.MatchType.CONTAINS, value=args.page_contains)))
    r = client.run_report(req)
    n = 0
    for row in sorted(r.rows, key=lambda x: x.dimension_values[0].value):
        d = [x.value for x in row.dimension_values]
        if args.events and d[2] not in args.events:
            continue
        n += 1
        print(d, row.metric_values[0].value)
    print("строк:", n, "(dateHour = ГГГГММДДЧЧ в поясе ресурса)")


if __name__ == "__main__":
    main()
