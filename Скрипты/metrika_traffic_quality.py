#!/usr/bin/env python
# coding: utf-8
"""Качество трафика из Яндекс.Метрики: отказы, глубина, время, достижения цели.

Зачем: готовые скрипты дают только визиты или заявки. Чтобы понять, какой
трафик приходит из источника (напр. ПромоСтраницы), нужны отказы, глубина,
время на сайте и достижения цели в разрезах: период, utm_content, utm_term,
устройство, регион, час, посадочная.

Что делает: читает Reporting API Метрики (stat/v1/data.csv), ТОЛЬКО чтение.
Метрики: визиты, отказы %, глубина просмотра, время на сайте (сек),
достижения цели <--goal-id>. Фильтр: first-click источник
(ym:s:firstUTMSource =~ --first-utm-source-regex; пусто = все визиты).
Один отчёт = (период) + ровно ОДИН разрез. Разрезы идут отдельными запросами
(в одном запросе много измерений API отдаёт пустой ответ, см. README, Дзен;
скрипт держит не больше 3 измерений в запросе, жёсткий предел 4).

Периоды (--month / --week; без них - один итог за весь период):
  --month  ym:s:startOfMonth   --week  ym:s:startOfWeek
Разрезы (--dimensions, через запятую; по умолчанию все):
  content (firstUTMContent), term (firstUTMTerm), device (deviceCategory),
  region (regionCity), hour (hour), landing (startURL)
Для разреза без периода - просто итог по разрезу.

Без --run - сухой режим: печатает план запросов (без токена), в API не ходит.
С --run - читает данные, пишет CSV в Клиенты/<--client-folder>/Статистика/ и
печатает сводку. Записей в Метрику/кабинеты нет. Токен - из таблицы агентства
(_config.py, вкладка Metrika) по --token-client, в вывод не печатается.

Пример:
  python metrika_traffic_quality.py --counter-id 66145201 --goal-id 143150284 \\
      --from 2026-04-01 --to 2026-11-18 --first-utm-source-regex promopages \\
      --client-folder "Франшиза Мокрый Нос Дзен" \\
      --token-client "Мокрый Нос - Груминг Франшиза" --month --run

Файлы: metrika_traffic_quality_<период>_<разрез>_goal<ID>_<from>_to_<to>.csv
Дата создания: 2026-11-18.
"""
import argparse
import io
from datetime import date

API_URL = "https://api-metrika.yandex.ru/stat/v1/data.csv"
PAGE = 10000
MAX_DIMS = 4  # жёсткий предел на запрос (10 даёт пустой ответ)

DIM_MAP = {
    "content": "ym:s:firstUTMContent",
    "term": "ym:s:firstUTMTerm",
    "device": "ym:s:deviceCategory",
    "region": "ym:s:regionCity",
    "hour": "ym:s:hour",
    "landing": "ym:s:startURL",
}
PERIOD_MAP = {"month": "ym:s:startOfMonth", "week": "ym:s:startOfWeek"}


def metrics(goal_id):
    return (f"ym:s:visits,ym:s:bounceRate,ym:s:pageDepth,"
            f"ym:s:avgVisitDurationSeconds,ym:s:goal{goal_id}reaches")


def build_filter(args):
    if not args.first_utm_source_regex:
        return ""
    rx = args.first_utm_source_regex.replace("'", "\\'")
    return f"ym:s:firstUTMSource=~'{rx}'"


def plan_reports(args):
    """Список (имя_периода, имя_разреза, строка измерений)."""
    period = "month" if args.month else "week" if args.week else "all"
    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()]
    for d in dims:
        if d not in DIM_MAP:
            raise SystemExit(f"Неизвестный разрез '{d}'. Допустимы: {', '.join(DIM_MAP)}")
    out = []
    if period != "all":
        out.append((period, "total", PERIOD_MAP[period]))  # итог по периоду
    for d in dims:
        parts = ([PERIOD_MAP[period]] if period != "all" else []) + [DIM_MAP[d]]
        if len(parts) > MAX_DIMS:
            raise SystemExit("Слишком много измерений в запросе")
        out.append((period, d, ",".join(parts)))
    if period == "all":
        out.insert(0, ("all", "total", ""))
    return out


def build_params(args, dims, offset=1):
    p = {
        "ids": args.counter_id,
        "metrics": metrics(args.goal_id),
        "date1": args.date_from,
        "date2": args.date_to,
        "limit": PAGE,
        "offset": offset,
        "language": "ru",
        "accuracy": "full",
    }
    if dims:
        p["dimensions"] = dims
        p["sort"] = "-ym:s:visits" if "startOf" not in dims else dims.split(",")[0]
    flt = build_filter(args)
    if flt:
        p["filters"] = flt
    return p


def fetch_all(args, dims, token):
    import pandas as pd
    import requests
    frames, offset = [], 1
    while True:
        r = requests.get(API_URL, params=build_params(args, dims, offset),
                         headers={"Authorization": f"OAuth {token}"}, timeout=300)
        if r.status_code != 200:
            raise SystemExit(f"Ошибка {r.status_code}: {r.text[:500]}")
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
        df = df[df.iloc[:, 0].astype(str) != "Итого и средние"]
        frames.append(df)
        if len(df) < PAGE:
            break
        offset += PAGE
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser(description="Качество трафика Метрики (только чтение)")
    ap.add_argument("--counter-id", required=True)
    ap.add_argument("--goal-id", required=True)
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--first-utm-source-regex", default="",
                    help="regex по firstUTMSource; пусто = все визиты (пример: promopages)")
    ap.add_argument("--client-folder", required=True, help="папка клиента в Клиенты/")
    ap.add_argument("--dimensions", default=",".join(DIM_MAP),
                    help="разрезы через запятую: " + ",".join(DIM_MAP))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--month", action="store_true", help="разбивка по месяцам")
    g.add_argument("--week", action="store_true", help="разбивка по неделям")
    ap.add_argument("--token-client", default="",
                    help="строка таблицы агентства (вкладка Metrika); нужна для --run")
    ap.add_argument("--run", action="store_true", help="выполнить чтение API (без флага - план)")
    args = ap.parse_args()
    date.fromisoformat(args.date_from)
    date.fromisoformat(args.date_to)

    reports = plan_reports(args)
    print("План (только чтение Reporting API Метрики):")
    print(f"  ids: {args.counter_id}  период: {args.date_from}..{args.date_to}")
    print(f"  metrics: {metrics(args.goal_id)}")
    print(f"  filters: {build_filter(args) or '(нет)'}")
    for period, name, dims in reports:
        print(f"  запрос [{period}/{name}] dimensions: {dims or '(нет)'}")
    if not args.run:
        print("Сухой режим: запросы не выполнялись. Для выполнения добавьте --run.")
        return
    if not args.token_client:
        raise SystemExit("Для --run нужен --token-client (строка вкладки Metrika)")

    import pandas as pd
    from _config import get_client_row, client_stats_dir
    row = get_client_row(args.token_client, tab="Metrika")
    token = str(row.get("token", "")).strip()
    if not token:
        raise SystemExit(f"У '{args.token_client}' пустой token")

    outdir = client_stats_dir(args.client_folder)
    for period, name, dims in reports:
        df = fetch_all(args, dims, token)
        path = outdir / (f"metrika_traffic_quality_{period}_{name}_goal{args.goal_id}_"
                         f"{args.date_from}_to_{args.date_to}.csv")
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"Сохранено: {path} ({len(df)} строк)")
        if name == "total":
            with pd.option_context("display.width", 200, "display.max_columns", 20):
                print(df.to_string(index=False))


if __name__ == "__main__":
    main()
