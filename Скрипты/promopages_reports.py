#!/usr/bin/env python
# coding: utf-8
"""Отчёты API ПромоСтраниц Яндекс Дзена: «заголовок x обложка» и «Поиск против РСЯ».

Зачем. Внешний скрипт E:\\PythonProjects\\RedBird\\dev\\Promopages\\promopages.py запрашивает
только campaigns-daily-stats и campaigns-publications-daily-stats и всегда с trafficSource=total.
Здесь два недостающих среза (см. База_знаний/Инструменты/Promopages-отчёты-и-API.md, «Пробелы», п. 2):
  1. previews        : POST /reports/campaigns-previews-daily-stats - расход, показы, CTR,
                       дочитывания, переходы по каждой обложке (заголовок x картинка) по дням.
                       Заголовок и картинка подтягиваются из GET /campaigns (publications[].previews[]):
                       в самом отчёте только previewId.
  2. traffic-source  : POST /reports/campaigns-daily-stats с trafficSource=ya_search и rsya
                       (по документации параметр общий для всех трёх типов отчётов). С флагом
                       --with-total добавляется третий запрос total - для сверки Поиск + РСЯ = total.

Режим: ТОЛЬКО ЧТЕНИЕ. В API ПромоСтраниц методов записи нет; скрипт ничего не меняет в кабинете.
Создание отчёта (POST /reports/...) - это запрос на формирование выгрузки, не правка кабинета.

Запуск (по умолчанию «сухой»: печатает план запросов и имена файлов, API не вызывается):
    python promopages_reports.py --from 2026-10-01 --to 2026-10-27
    python promopages_reports.py --from 2026-10-01 --to 2026-10-27 --run      # реальный запрос
    python promopages_reports.py --from 2026-10-01 --reports previews --campaign-id <id> --campaign-id <id> --run
    python promopages_reports.py --from 2026-10-01 --reports traffic-source --with-total --run

Токен. Из переменной окружения PROMOPAGES_TOKEN (OAuth-токен приложения с правом promopages:api,
отдельный от токенов Директа/Метрики). В коде, файлах и выводе токена нет. Windows (один раз):
    setx PROMOPAGES_TOKEN "<токен>"      # затем открыть новое окно терминала
publisherId кабинета (не секрет): словарь CLIENTS ниже или --publisher-id.

Квоты и повторы (по документации API): у каждого метода «общее ограничение на количество запросов
в секунду», при превышении код 429, повторять через несколько минут; число в документации не названо.
Поэтому: пауза между запросами (--pause), повтор при 429/5xx/сетевой ошибке (--retries,
--rate-limit-wait), опрос готовности отчёта (код 202) раз в --poll-delay секунд. Отчёты на практике
формируются 5-15 минут. GET /campaigns - постранично (pageLimit 200, hasNextPage/pageLastId).
Отчёты хранятся 30 дней, но не более 1000 последних.

Файлы: <out-dir>/promopages_<previews|traffic_source>_daily_<from>_to_<to>_pulled-<дата>.csv;
существующие файлы не перезаписываются (добавляется _2, _3 ...). Скрипт только собирает данные,
выводов не делает.

Дата создания: 2026-11-13.
"""
import argparse
import csv
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

VAULT_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://promopages.yandex.ru/api/promo/v1"
TOKEN_ENV = "PROMOPAGES_TOKEN"

# publisherId - идентификатор кабинета (не секрет). Источник: внешний скрипт
# E:\PythonProjects\RedBird\dev\Promopages\promopages.py (PUBLISHER_ID) и
# База_знаний/Инструменты/Promopages-модерация.md (кабинет франшизы «Мокрый Нос»).
CLIENTS = {
    "mokry-nos-dzen": {
        "folder": "Франшиза Мокрый Нос Дзен",
        "publisher_id": "647eb24aea20462aa4536c7d",
    },
}

REPORT_TYPE_DAILY = "campaigns-daily-stats"
REPORT_TYPE_PREVIEWS = "campaigns-previews-daily-stats"
TRAFFIC_SOURCES = ("total", "ya_search", "rsya")

# Поля отчёта по документации (reference/get-reports) + реальные поля из наших выгрузок
# (views, clicks, fullReadTimeSec - в документации нет, см. Promopages-отчёты-и-API.md).
STAT_FIELDS = [
    "mskDate", "impressions", "reach", "budget", "cpm",
    "clickouts", "clickoutCost", "clickoutPercent",
    "fullReads", "fullReadPercent", "ctr",
    "videoExpands", "videoFullViews", "videoExpandPercent", "videoFullViewPercent",
    "metricaVisits", "metricaVisitPercent", "metricaVisitCost",
    "views", "clicks", "fullReadTimeSec",
]


# Ключи, которые скрипт добавляет к строке сам (не поля отчёта), и идентификаторы строки.
SERVICE_FIELDS = {
    "campaignId", "publicationId", "previewId", "campaignTitle", "trafficSource",
    "publicationTitle", "previewTitle", "imageId", "imageUrl", "previewDisabled", "previewDeleted",
}


# ── Токен ─────────────────────────────────────────────────────────────────────

def get_token():
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(
            f"Нет переменной окружения {TOKEN_ENV}. Задайте токен API ПромоСтраниц "
            f"(Windows: setx {TOKEN_ENV} \"<токен>\" и новое окно терминала). "
            "Значение токена в код и в вывод не пишется."
        )
    return token


# ── HTTP с повторами ──────────────────────────────────────────────────────────

class Api:
    def __init__(self, token, retries, rate_limit_wait, pause):
        self.headers = {"Authorization": f"OAuth {token}", "Content-Type": "application/json"}
        self.retries = retries
        self.rate_limit_wait = rate_limit_wait
        self.pause = pause

    def request(self, method, path, **kwargs):
        """Запрос с повтором на 429, 5xx и сетевые ошибки. 202 возвращается вызывающему."""
        url = f"{BASE_URL}{path}"
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.request(method, url, headers=self.headers, timeout=60, **kwargs)
            except requests.RequestException as exc:
                last = f"сетевая ошибка: {type(exc).__name__}"
                wait = self.rate_limit_wait
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                    wait = self.rate_limit_wait
                elif resp.status_code in (200, 202):
                    time.sleep(self.pause)
                    return resp
                else:
                    # 400/401/403/404/422 - повтор не поможет
                    raise SystemExit(f"{method} {path}: HTTP {resp.status_code}: {resp.text[:300]}")
            print(f"  {method} {path}: {last}, повтор {attempt}/{self.retries} через {wait} с")
            time.sleep(wait)
        raise SystemExit(f"{method} {path}: не удалось за {self.retries} попыток ({last})")


def get_all_campaigns(api, publisher_id):
    """Все кампании кабинета: GET /campaigns, pageLimit 200, hasNextPage/pageLastId."""
    campaigns, page_last_id = [], None
    while True:
        params = {"publisherId": publisher_id, "pageLimit": 200}
        if page_last_id:
            params["pageLastId"] = page_last_id
        data = api.request("GET", "/campaigns", params=params).json()
        campaigns.extend(data.get("campaigns", []))
        if not data.get("hasNextPage"):
            return campaigns
        page_last_id = data.get("pageLastId")


def create_report(api, report_type, publisher_id, campaign_ids, date_from, date_to, traffic_source):
    body = {
        "publisherId": publisher_id,
        "campaignIds": campaign_ids,
        "mskDateFrom": date_from,
        "mskDateTo": date_to,
    }
    if traffic_source:
        body["trafficSource"] = traffic_source
    return api.request("POST", f"/reports/{report_type}", json=body).json()["reportId"]


def fetch_report(api, report_id, poll_delay, max_polls):
    """GET /reports/{id}?format=json: 202 - не готов, ждём; 429 - ждём дольше."""
    for attempt in range(1, max_polls + 1):
        resp = api.request("GET", f"/reports/{report_id}", params={"format": "json"})
        if resp.status_code == 202:
            if attempt % 6 == 1:
                print(f"  отчёт формируется (опрос {attempt}/{max_polls})")
            time.sleep(poll_delay)
            continue
        data = resp.json()
        if "statistics" in data:
            return data["statistics"]
        print(f"  ответ 200 без 'statistics', ключи: {list(data.keys())} (опрос {attempt}/{max_polls})")
        time.sleep(poll_delay)
    raise SystemExit(f"Отчёт {report_id} не готов после {max_polls} опросов")


# ── План запросов ─────────────────────────────────────────────────────────────

def build_plan(reports, with_total, previews_traffic_source):
    """Список запросов: (группа, тип отчёта, trafficSource или None)."""
    plan = []
    if "previews" in reports:
        ts = None if previews_traffic_source == "total" else previews_traffic_source
        plan.append(("previews", REPORT_TYPE_PREVIEWS, ts))
    if "traffic-source" in reports:
        sources = ["ya_search", "rsya"] + (["total"] if with_total else [])
        for src in sources:
            plan.append(("traffic-source", REPORT_TYPE_DAILY, src))
    return plan


def unique_path(out_dir, name):
    """Не перезаписывать снапшоты: если файл есть, добавить _2, _3 ..."""
    path = out_dir / name
    stem, suffix = path.stem, path.suffix
    n = 2
    while path.exists():
        path = out_dir / f"{stem}_{n}{suffix}"
        n += 1
    return path


def output_name(group, date_from, date_to):
    slug = {"previews": "previews", "traffic-source": "traffic_source"}[group]
    return f"promopages_{slug}_daily_{date_from}_to_{date_to}_pulled-{date.today().isoformat()}.csv"


# ── Сборка строк CSV ──────────────────────────────────────────────────────────

def previews_index(campaigns):
    """previewId -> данные обложки и публикации из GET /campaigns."""
    idx = {}
    for camp in campaigns:
        for pub in camp.get("publications", []) or []:
            for prev in pub.get("previews", []) or []:
                idx[prev.get("id")] = {
                    "publicationTitle": pub.get("title", ""),
                    "previewTitle": prev.get("title", ""),
                    "imageId": prev.get("imageId", ""),
                    "imageUrl": prev.get("imageUrl", ""),
                    "previewDisabled": prev.get("isDisabled", ""),
                    "previewDeleted": prev.get("isDeleted", ""),
                }
    return idx


def stat_columns(rows):
    """Известные поля отчёта в фиксированном порядке, затем любые незнакомые из ответа."""
    present = set()
    for r in rows:
        present.update(r.keys())
    known = [f for f in STAT_FIELDS if f in present]
    extra = sorted(present - set(STAT_FIELDS) - SERVICE_FIELDS)
    return known + extra


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args():
    ap = argparse.ArgumentParser(
        description="ПромоСтраницы (Дзен): отчёты по обложкам и по источнику трафика (Поиск/РСЯ). "
                    "Только чтение. По умолчанию сухой режим - API не вызывается; реальный запрос с --run.",
    )
    ap.add_argument("--client", default="mokry-nos-dzen", choices=sorted(CLIENTS),
                    help="ключ клиента в CLIENTS (папка и publisherId)")
    ap.add_argument("--publisher-id", help="переопределить publisherId кабинета")
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD (mskDateFrom)")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD (mskDateTo), по умолчанию вчера")
    ap.add_argument("--campaign-id", action="append", default=[],
                    help="ID кампании (можно повторять); по умолчанию все кампании кабинета (GET /campaigns)")
    ap.add_argument("--reports", default="previews,traffic-source",
                    help="какие отчёты: previews, traffic-source (через запятую)")
    ap.add_argument("--with-total", action="store_true",
                    help="для traffic-source добавить запрос total (сверка Поиск + РСЯ = total)")
    ap.add_argument("--previews-traffic-source", choices=TRAFFIC_SOURCES, default="total",
                    help="trafficSource для отчёта по обложкам (по умолчанию total)")
    ap.add_argument("--out-dir", help="куда сохранить CSV (по умолчанию Клиенты/<клиент>/Статистика/)")
    ap.add_argument("--run", action="store_true", help="выполнить запросы к API (чтение); без флага - сухой режим")
    ap.add_argument("--pause", type=float, default=2.0, help="пауза после каждого запроса, сек")
    ap.add_argument("--retries", type=int, default=5, help="число попыток на запрос при 429/5xx/сетевой ошибке")
    ap.add_argument("--rate-limit-wait", type=int, default=60, help="пауза перед повтором при 429/5xx, сек")
    ap.add_argument("--poll-delay", type=int, default=10, help="интервал опроса готовности отчёта (202), сек")
    ap.add_argument("--max-polls", type=int, default=120, help="максимум опросов на отчёт (120 x 10 с = 20 мин)")
    return ap.parse_args()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()

    client = CLIENTS[args.client]
    publisher_id = args.publisher_id or client["publisher_id"]
    date_to = args.date_to or (date.today() - timedelta(days=1)).isoformat()
    try:
        d_from, d_to = date.fromisoformat(args.date_from), date.fromisoformat(date_to)
    except ValueError:
        raise SystemExit("Даты в формате YYYY-MM-DD")
    if d_from > d_to:
        raise SystemExit(f"--from {d_from} позже --to {d_to}")

    reports = [r.strip() for r in args.reports.split(",") if r.strip()]
    bad = [r for r in reports if r not in ("previews", "traffic-source")]
    if bad or not reports:
        raise SystemExit(f"--reports: допустимо previews, traffic-source; получено {args.reports!r}")

    out_dir = Path(args.out_dir) if args.out_dir else VAULT_ROOT / "Клиенты" / client["folder"] / "Статистика"
    plan = build_plan(reports, args.with_total, args.previews_traffic_source)
    groups = list(dict.fromkeys(g for g, _, _ in plan))
    files = {g: unique_path(out_dir, output_name(g, args.date_from, date_to)) for g in groups}

    print(f"Клиент: {args.client} | publisherId: {publisher_id} | период {args.date_from} -> {date_to}")
    print(f"Режим: {'ВЫПОЛНЕНИЕ (--run, только чтение)' if args.run else 'СУХОЙ (API не вызывается)'}")
    print(f"Токен: переменная {TOKEN_ENV} {'задана' if os.environ.get(TOKEN_ENV, '').strip() else 'НЕ задана'}")
    camp_txt = ", ".join(args.campaign_id) if args.campaign_id else "все кампании кабинета (GET /campaigns, pageLimit 200)"
    print(f"Кампании: {camp_txt}")
    print("Запросы:")
    if not args.campaign_id:
        print(f"  GET {BASE_URL}/campaigns?publisherId=...&pageLimit=200 (постранично)")
    for group, rtype, src in plan:
        print(f"  POST {BASE_URL}/reports/{rtype}  trafficSource={src or 'total (не передаётся)'}  -> {files[group].name}")
    print(f"Каталог вывода: {out_dir}")
    print("Было -> станет: в кабинете ничего не меняется (чтение); на диске появятся файлы выше.")

    if not args.run:
        print("\nСухой режим: API не вызывался, файлы не созданы. Для реального запроса добавьте --run.")
        return

    token = get_token()
    api = Api(token, args.retries, args.rate_limit_wait, args.pause)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n[1] Кампании кабинета...")
    campaigns = get_all_campaigns(api, publisher_id)
    by_id = {c["id"]: c for c in campaigns}
    print(f"  найдено кампаний: {len(campaigns)}")
    if args.campaign_id:
        missing = [c for c in args.campaign_id if c not in by_id]
        if missing:
            print(f"  ВНИМАНИЕ: нет в кабинете: {', '.join(missing)}")
        campaign_ids = [c for c in args.campaign_id if c in by_id]
    else:
        campaign_ids = [c["id"] for c in campaigns]
    if not campaign_ids:
        raise SystemExit("Нет кампаний для отчёта (проверьте токен, publisherId, --campaign-id)")
    prev_idx = previews_index(campaigns)

    collected = {g: [] for g in groups}
    totals = {}
    for n, (group, rtype, src) in enumerate(plan, start=2):
        print(f"\n[{n}] {rtype}, trafficSource={src or 'total'}...")
        report_id = create_report(api, rtype, publisher_id, campaign_ids, args.date_from, date_to, src)
        print(f"  reportId получен, ожидание готовности")
        stats = fetch_report(api, report_id, args.poll_delay, args.max_polls)
        print(f"  строк: {len(stats)}")
        totals[(group, src or "total")] = (len(stats), sum(num(r.get("budget")) for r in stats))
        for r in stats:
            row = dict(r)
            camp = by_id.get(r.get("campaignId"), {})
            row["campaignTitle"] = camp.get("title", "")
            row["trafficSource"] = src or "total"
            if group == "previews":
                row.update(prev_idx.get(r.get("previewId"), {}))
            collected[group].append(row)

    for group, rows in collected.items():
        cols = stat_columns(rows)
        if group == "previews":
            header = (["campaignId", "campaignTitle", "publicationId", "publicationTitle", "previewId",
                       "previewTitle", "imageId", "imageUrl", "previewDisabled", "previewDeleted",
                       "trafficSource"] + cols)
            unmatched = len({r.get("previewId") for r in rows if r.get("previewId") not in prev_idx})
            if unmatched:
                print(f"ВНИМАНИЕ: {unmatched} previewId из отчёта не найдены в GET /campaigns (заголовок/картинка пустые)")
        else:
            header = ["campaignId", "campaignTitle", "trafficSource"] + cols
        write_csv(files[group], header, rows)
        print(f"Сохранено: {files[group]} ({len(rows)} строк)")

    print("\nИтог по запросам (строк, сумма budget без НДС):")
    for (group, src), (cnt, budget) in totals.items():
        print(f"  {group} / {src}: {cnt} строк, budget {budget:.2f}")
    ts = {s: b for (g, s), (_, b) in totals.items() if g == "traffic-source"}
    if {"ya_search", "rsya", "total"} <= set(ts):
        diff = ts["total"] - ts["ya_search"] - ts["rsya"]
        print(f"  сверка: total - (ya_search + rsya) = {diff:.2f}")


if __name__ == "__main__":
    main()
