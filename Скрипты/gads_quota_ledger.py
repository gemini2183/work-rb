#!/usr/bin/env python
# coding: utf-8
"""Журнал операций Google Ads API: сколько операций потратили НАШИ скрипты за сутки (basic access: 15 000 операций в день на токен).

Зачем: 10.11.2026 суточный лимит закрылся посреди записи (П-001), а что съело остаток — неизвестно: счётчика не было.
Считаем так, как считает Google (docs: quotas / rate sheet): search и search_stream — 1 операция за запрос (не за строку),
mutate — по 1 за каждую операцию внутри запроса; отклонённые запросы тоже считаются. validate_only пишем отдельным тегом
(тратит ли он квоту — не проверено).

Что журнал НЕ видит: веб-интерфейс, Editor, чужие инструменты на том же токене. Это нижняя оценка, не остаток лимита.

Использование в скрипте:
    from gads_quota_ledger import wrap_ga, record_mutate
    ga = wrap_ga(client.get_service("GoogleAdsService"), "имя_скрипта")   # читающие запросы считаются сами
    record_mutate("имя_скрипта", len(ops), validate_only=not execute)     # перед svc.mutate(...)
Сводка за сегодня: python gads_quota_ledger.py [--days 3]
Файл: Скрипты/secrets/gads_ops_ledger.csv (вне git): время, скрипт, вид, операций, validate_only.
"""
import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path

LEDGER = Path(__file__).resolve().parent / "secrets" / "gads_ops_ledger.csv"
DAILY_LIMIT_BASIC = 15000   # basic access, docs developers.google.com/google-ads/api/docs/best-practices/quotas


def _append(script, kind, n, validate_only=False):
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        new = not LEDGER.exists()
        with open(LEDGER, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "script", "kind", "ops", "validate_only"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), script, kind, n, int(bool(validate_only))])
    except OSError:
        pass   # журнал не должен ронять рабочий скрипт


def record_mutate(script, n_ops, validate_only=False):
    _append(script, "mutate", n_ops, validate_only)


class _GaWrap:
    def __init__(self, ga, script):
        self._ga, self._script = ga, script

    def search(self, *a, **kw):
        _append(self._script, "search", 1)
        return self._ga.search(*a, **kw)

    def search_stream(self, *a, **kw):
        _append(self._script, "search_stream", 1)
        return self._ga.search_stream(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._ga, name)


def wrap_ga(ga, script):
    return _GaWrap(ga, script)


def summary(days=1):
    if not LEDGER.exists():
        print("журнала ещё нет (ни один скрипт не писал в него)")
        return
    since = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    per_day = {}
    with open(LEDGER, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            day = r["time"][:10]
            if day < since:
                continue
            key = (day, r["script"], r["kind"], r["validate_only"])
            per_day[key] = per_day.get(key, 0) + int(r["ops"])
    totals = {}
    for (day, script, kind, vo), n in sorted(per_day.items()):
        print(f"{day}  {script:28s} {kind:14s} {'validate' if vo == '1' else '        '}  {n:>6d}")
        if vo != "1":
            totals[day] = totals.get(day, 0) + n
    for day, n in sorted(totals.items()):
        print(f"{day}  ИТОГО наших скриптов: {n} из {DAILY_LIMIT_BASIC} ({n / DAILY_LIMIT_BASIC:.0%}); сторожа и интерфейс сюда попадут, только когда подключены")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    summary(ap.parse_args().days)
