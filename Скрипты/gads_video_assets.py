#!/usr/bin/env python
# coding: utf-8
"""Видео-ассеты аккаунта Google Ads (YOUTUBE_VIDEO). ТОЛЬКО ЧТЕНИЕ, записи в кабинет нет.

Зачем (2026-11-13, ProfiMet YouTube): ролики загружают через мастер Demand Gen / Upload, имя ассета может отличаться от имени файла;
в билдере gads_demand_gen_yt_cold_builder.py (VIDEOS) нужны asset.id и id ролика на YouTube. Скрипт показывает видео-ассеты аккаунта,
новые первыми (сортировка по asset.id по убыванию: id растут со временем создания; даты создания у ассета в API нет).

Что выводит: asset.id, asset.name, youtube_video_id, youtube_video_title, длительность (если поле есть в API, иначе «-»),
resource_name (для подстановки в билдер). Фильтр --name-contains работает по имени ассета ИЛИ названию ролика, без учёта регистра.
Вход: логин через менеджера берётся из secrets/google-ads.yaml (login_customer_id), как в других gads_*.py.

    PYTHONUTF8=1 python gads_video_assets.py --customer-id 7552781705 [--name-contains cold] [--limit 30] [--csv путь.csv]

Дата: 2026-11-13.
"""
import argparse
import csv

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

# Поле длительности в API не гарантировано: пробуем с ним, при отказе читаем без него.
Q_BASE = ("SELECT asset.id, asset.name, asset.resource_name, asset.youtube_video_asset.youtube_video_id, "
          "asset.youtube_video_asset.youtube_video_title{extra} FROM asset WHERE asset.type = 'YOUTUBE_VIDEO' ORDER BY asset.id DESC")
DURATION_FIELD = ", asset.youtube_video_asset.youtube_video_duration_millis"


def fetch(ga, cid):
    """Возвращает (строки, есть_ли_длительность)."""
    for extra, has_dur in ((DURATION_FIELD, True), ("", False)):
        try:
            rows = []
            for r in ga.search(customer_id=cid, query=Q_BASE.format(extra=extra)):
                y = r.asset.youtube_video_asset
                dur = getattr(y, "youtube_video_duration_millis", None) if has_dur else None
                rows.append({
                    "asset_id": r.asset.id,
                    "name": r.asset.name,
                    "youtube_video_id": y.youtube_video_id,
                    "title": y.youtube_video_title,
                    "duration_sec": round(dur / 1000) if dur else "",
                    "resource_name": r.asset.resource_name,
                })
            return rows, has_dur
        except GoogleAdsException as e:
            if not has_dur:
                raise
            print("(длительность в API недоступна: " + "; ".join(x.message for x in e.failure.errors)[:150] + " - читаю без неё)")
    return [], False


def main():
    ap = argparse.ArgumentParser(description="Видео-ассеты аккаунта Google Ads (только чтение), новые первыми")
    ap.add_argument("--customer-id", required=True, help="ID аккаунта, с дефисами или без (ProfiMet YouTube: 7552781705)")
    ap.add_argument("--name-contains", help="подстрока в имени ассета или названии ролика (без учёта регистра)")
    ap.add_argument("--limit", type=int, default=30, help="сколько строк показать (по умолчанию 30)")
    ap.add_argument("--csv", help="путь для выгрузки CSV (необязательно)")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    try:
        rows, has_dur = fetch(ga, cid)
    except GoogleAdsException as e:
        raise SystemExit("Ошибка API: " + "; ".join(x.message for x in e.failure.errors))

    total = len(rows)
    if a.name_contains:
        s = a.name_contains.lower()
        rows = [r for r in rows if s in r["name"].lower() or s in r["title"].lower()]
    rows.sort(key=lambda r: r["asset_id"], reverse=True)
    shown = rows[: a.limit]

    print(f"Аккаунт {cid}: видео-ассетов всего {total}, после фильтра {len(rows)}, показано {len(shown)}. "
          f"Сортировка: asset.id по убыванию (новые первыми). Длительность: {'есть' if has_dur else 'в API нет'}.")
    for r in shown:
        dur = f"{r['duration_sec']} с" if r["duration_sec"] != "" else "-"
        print(f"{r['asset_id']} | {r['name']!r} | yt={r['youtube_video_id']} | {r['title']!r} | {dur}")

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(shown[0].keys()) if shown else ["asset_id"])
            w.writeheader()
            w.writerows(shown)
        print(f"CSV: {a.csv} ({len(shown)} строк)")


if __name__ == "__main__":
    main()
