#!/usr/bin/env python
# coding: utf-8
"""Поведение на посадочной по GA4 Data API — ТОЛЬКО ЧТЕНИЕ.

Зачем: после установки поведенческих событий в GTM (Landver, версия 6, 15.10.2026: block_view, block_time,
faq_open, click_tel + click_place, engaged_30s/90s) нужен один повторяемый срез «кто приходил, что делал»,
без тестовых заходов пользователя (Испания) — иначе доли блоков считаются по самим тестам.

Что печатает (и пишет в Статистика/ga4_behavior_<с>_<по>.txt):
  1. состав сеансов по стране и городу (чтобы увидеть тестовый трафик);
  2. сеансы по источнику/каналу и устройству после исключения стран;
  3. события по названиям (сколько сеансов дошло до block_view, faq_open, click_tel, engaged_*, form_submit);
  4. блоки: сколько сеансов увидели блок (block_view) и сколько секунд провели (block_seconds);
  5. клики по телефону по местам (click_place) и вопросы FAQ.

Исключение тестов: --exclude-countries "Spain" (по умолчанию), можно ещё --exclude-cities "Vilnius".
Ключ: путь к ключу сервисного аккаунта ga4-analytics (тот же, что у ProfiMet) берётся из переменной
окружения GA4_KEY_FILE или из значения по умолчанию ниже; в вики ключ не копировать.

Использование:
    python ga4_behavior.py --property 549802233 --client-folder Andverpersonalinjury --from 2026-10-15 --to 2026-10-19
"""
import argparse
import os
from pathlib import Path

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Filter, FilterExpression, FilterExpressionList, Metric, OrderBy, RunReportRequest,
)
from google.oauth2 import service_account

from _config import client_stats_dir

DEFAULT_KEY = r"E:\PythonProjects\RedBird\google-cloud-jobs\adwhite\func\ga4_profimet\redbird-196813-ga4.json"


def run(client, prop, d1, d2, dims, mets, exclude, event=None, limit=100):
    exprs = []
    for field, values in exclude:
        for v in values:
            exprs.append(FilterExpression(not_expression=FilterExpression(
                filter=Filter(field_name=field, string_filter=Filter.StringFilter(value=v, match_type=Filter.StringFilter.MatchType.EXACT)))))
    if event:
        exprs.append(FilterExpression(filter=Filter(field_name="eventName", string_filter=Filter.StringFilter(value=event))))
    flt = FilterExpression(and_group=FilterExpressionList(expressions=exprs)) if exprs else None
    req = RunReportRequest(
        property=f"properties/{prop}", date_ranges=[DateRange(start_date=d1, end_date=d2)],
        dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name=m) for m in mets],
        dimension_filter=flt, limit=limit,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=mets[0]), desc=True)])
    resp = client.run_report(req)
    rows = []
    for r in resp.rows:
        rows.append([x.value for x in r.dimension_values] + [x.value for x in r.metric_values])
    return rows


def show(out, title, header, rows):
    out.append(f"\n== {title}")
    out.append(" | ".join(header))
    if not rows:
        out.append("(нет данных)")
    for r in rows:
        out.append(" | ".join(str(x) for x in r))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--from", dest="d1", required=True)
    ap.add_argument("--to", dest="d2", required=True)
    ap.add_argument("--exclude-countries", default="Spain")
    ap.add_argument("--exclude-cities", default="")
    args = ap.parse_args()

    key = os.environ.get("GA4_KEY_FILE", DEFAULT_KEY)
    creds = service_account.Credentials.from_service_account_file(key)
    client = BetaAnalyticsDataClient(credentials=creds)
    countries = [c.strip() for c in args.exclude_countries.split(",") if c.strip()]
    cities = [c.strip() for c in args.exclude_cities.split(",") if c.strip()]
    excl = [("country", countries), ("city", cities)]
    excl = [(f, v) for f, v in excl if v]
    out = [f"GA4 {args.property} | {args.d1} → {args.d2} | исключено: страны {countries or '—'}, города {cities or '—'}"]

    show(out, "1. Состав сеансов по стране и городу (БЕЗ исключений) — тестовый трафик виден здесь",
         ["страна", "город", "сеансы", "вовлечённые"],
         run(client, args.property, args.d1, args.d2, ["country", "city"], ["sessions", "engagedSessions"], [], limit=25))
    show(out, "2. Источник/канал и устройство (после исключений)",
         ["источник / канал", "устройство", "сеансы", "вовлечённые", "ср. время вовлечения, с"],
         run(client, args.property, args.d1, args.d2, ["sessionSourceMedium", "deviceCategory"],
             ["sessions", "engagedSessions", "userEngagementDuration"], excl))
    show(out, "3. События (после исключений): число событий и сеансов с событием",
         ["событие", "событий", "пользователей"],
         run(client, args.property, args.d1, args.d2, ["eventName"], ["eventCount", "totalUsers"], excl, limit=60))
    show(out, "4. Блоки: показ блока (block_view) и секунды (block_time)",
         ["блок", "block_view событий", "block_view пользователей"],
         run(client, args.property, args.d1, args.d2, ["customEvent:block_name"], ["eventCount", "totalUsers"], excl, event="block_view", limit=30))
    show(out, "4b. Секунды по блокам (block_time)",
         ["блок", "событий", "секунд всего"],
         run(client, args.property, args.d1, args.d2, ["customEvent:block_name"], ["eventCount", "customEvent:block_seconds"], excl, event="block_time", limit=30))
    show(out, "5. Клики по телефону по местам",
         ["место", "кликов", "пользователей"],
         run(client, args.property, args.d1, args.d2, ["customEvent:click_place"], ["eventCount", "totalUsers"], excl, event="click_tel"))
    show(out, "5b. Вопросы FAQ, которые открывали",
         ["вопрос", "раз", "пользователей"],
         run(client, args.property, args.d1, args.d2, ["customEvent:faq_question"], ["eventCount", "totalUsers"], excl, event="faq_open", limit=20))

    text = "\n".join(out)
    print(text)
    path = client_stats_dir(args.client_folder) / f"ga4_behavior_{args.d1}_to_{args.d2}.txt"
    Path(path).write_text(text, encoding="utf-8")
    print(f"\nСохранено: {path}")


if __name__ == "__main__":
    main()
