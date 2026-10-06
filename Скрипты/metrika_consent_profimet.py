#!/usr/bin/env python
# coding: utf-8
"""Цели cookie-баннера ProfiMet в Яндекс.Метрике: сколько визитов увидели баннер и что выбрали.

Только сбор и подсчёт. Баннер на mocnaszklarnia.pl самописный; GTM-контейнер GTM-TKGN4NT шлёт в
счётчик 75073231 цели `show_popup`, `must_have_cookies`, `all_cookies`, `settings`, `confirmed`
(id целей — ниже). Метрика грузится ДО согласия, поэтому видит всех посетителей — подходит как
знаменатель к сессиям GA4 (GA4 стартует только после "принять все").

Считаются ВИЗИТЫ с целью (`goalNvisits`), а не срабатывания (`goalNreaches`): без выбора посетитель
видит баннер на каждой странице визита, и срабатываний `show_popup` больше, чем визитов (~1.07 на визит).

Срез по умолчанию: google / cpc, НОВЫЕ посетители (баннер видят те, у кого нет cookie согласия). Можно
сузить до кампании по id (`--campaign-id`, ищется в utm_campaign) или взять весь трафик (`--all-traffic`).

Известные оговорки (по результатам использования 2026-10-06): визитов с целью `show_popup` меньше, чем
новых посетителей (64% у cpc) — часть визитов уходит за 0 секунд до показа баннера, остальное не объяснено;
цели не проверены на живом сайте (запрос Метрики в headless-браузере не удалось поймать).

Токен Яндекс OAuth берётся из переменной окружения YM_TOKEN (в вики/репозиторий не записывать).

Использование:
    set YM_TOKEN=...          (PowerShell: $env:YM_TOKEN="...")
    python metrika_consent_profimet.py --date-from 2026-08-03 --date-to 2026-10-05
    python metrika_consent_profimet.py --date-from 2026-08-03 --date-to 2026-10-05 --campaign-id 19158580966
"""
import argparse
import os
import sys

import pandas as pd
import requests

from _config import client_stats_dir

COUNTER = 75073231
GOALS = {
    "show_popup": 326188549,
    "must_have_cookies": 326189789,
    "all_cookies": 326190412,
    "settings_opened": 326191579,
    "confirmed": 326191580,  # "Принял согласие с настройками"
}


def api(token, metrics, date_from, date_to, flt, dims=None):
    params = {"ids": COUNTER, "metrics": ",".join(metrics), "date1": date_from, "date2": date_to,
              "limit": 10000, "accuracy": "full", "filters": flt}
    if dims:
        params["dimensions"] = dims
    r = requests.get("https://api-metrika.yandex.net/stat/v1/data", params=params,
                     headers={"Authorization": "OAuth " + token}, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD (цели существуют с 2026-08-03)")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--campaign-id", help="id кампании Google Ads (ищется в utm_campaign)")
    ap.add_argument("--all-traffic", action="store_true", help="весь трафик вместо google / cpc")
    ap.add_argument("--include-returning", action="store_true", help="не ограничиваться новыми посетителями")
    args = ap.parse_args()
    token = os.environ.get("YM_TOKEN")
    if not token:
        sys.exit("Нет токена: задайте переменную окружения YM_TOKEN")

    parts = []
    if not args.all_traffic:
        parts.append("ym:s:UTMSource=='google' AND ym:s:UTMMedium=='cpc'")
    if not args.include_returning:
        parts.append("ym:s:isNewUser=='Yes'")
    if args.campaign_id:
        parts.append(f"ym:s:UTMCampaign=~'{args.campaign_id}'")
    flt = " AND ".join(parts) if parts else "ym:s:visits>0"
    label = ("весь трафик" if args.all_traffic else "google / cpc") \
        + ("" if args.include_returning else ", новые посетители") \
        + (f", кампания {args.campaign_id}" if args.campaign_id else "")

    metrics = ["ym:s:visits"] + [f"ym:s:goal{g}visits" for g in GOALS.values()] \
        + [f"ym:s:goal{g}reaches" for g in GOALS.values()]
    t = api(token, metrics, args.date_from, args.date_to, flt)["totals"]
    visits = t[0]
    by_visits = dict(zip(GOALS, t[1:1 + len(GOALS)]))
    by_reaches = dict(zip(GOALS, t[1 + len(GOALS):]))

    print(f"Счётчик {COUNTER}, период {args.date_from} — {args.date_to}, срез: {label}")
    print(f"Визитов: {int(visits)}\n")
    print("Цель                 визитов с целью (доля визитов) | срабатываний | на визит")
    for k in GOALS:
        v, r = by_visits[k], by_reaches[k]
        print(f"  {k:18s} {int(v):8d} ({v / visits:5.1%})            | {int(r):8d}     | {r / max(v, 1):.2f}")

    shown = by_visits["show_popup"]
    decided = by_visits["must_have_cookies"] + by_visits["all_cookies"] + by_visits["confirmed"]
    if shown:
        print(f"\nВизитов с показом баннера: {int(shown)} ({shown / visits:.0%} визитов)")
        print(f"  выбор сделан: {int(decided)} ({decided / shown:.0%} от визитов с показом); без выбора: {int(shown - decided)} ({1 - decided / shown:.0%})")
        print(f"  из визитов с показом: принять все {by_visits['all_cookies'] / shown:.0%}, "
              f"только обязательные {by_visits['must_have_cookies'] / shown:.0%}, с настройками {by_visits['confirmed'] / shown:.0%}")

    # по дням — в CSV для сравнения с GA4
    j = api(token, ["ym:s:visits"] + [f"ym:s:goal{g}visits" for g in GOALS.values()],
            args.date_from, args.date_to, flt, dims="ym:s:date")
    rows = [[r["dimensions"][0]["name"]] + r["metrics"] for r in j["data"]]
    df = pd.DataFrame(rows, columns=["date", "visits"] + [f"{k}_visits" for k in GOALS])
    suffix = f"_{args.campaign_id}" if args.campaign_id else ""
    path = client_stats_dir("ProfiMet") / f"metrika_consent_{args.date_from}_to_{args.date_to}{suffix}.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"\nСохранено по дням: {path}")


if __name__ == "__main__":
    main()
