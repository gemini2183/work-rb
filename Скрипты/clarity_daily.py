#!/usr/bin/env python
# coding: utf-8
"""Ежедневная выгрузка сводки Microsoft Clarity (Data Export API) в Статистика/ клиента. ТОЛЬКО ЧТЕНИЕ Clarity.

Зачем: API отдаёт только последние 1–3 дня и не больше 10 запросов в сутки на проект, поэтому историю надо копить у себя.
За запуск делает до 4 запросов (по умолчанию за последние 24 часа): без разреза, по URL, по кампании (UTM), по устройству.
Сырые ответы — Статистика/clarity_<метка>/raw_<время>_<разрез>.json, плоская история — Статистика/clarity_<метка>.csv
(строки: pulled_at, num_days, dimension, dim_value, metric, field, value; время UTC, как в Clarity).
Защита квоты: счётчик запросов за сутки (UTC) в Статистика/clarity_<метка>/quota_<дата>.txt, стоп при лимите --max-per-day.

Токен проекта — переменная окружения (по умолчанию LANDVER_CLARITY_API_TOKEN_TILDA); если процесс её не видит
(VS Code не перезапускали после setx) — читается из пользовательской области Windows. Значение нигде не печатается.

Ограничения API (документация Microsoft, проверено 2026-10-15): numOfDays 1–3, до 3 разрезов, до 1 000 строк, 10 запросов
в сутки, данные в UTC; нет сессий поштучно, нет gclid — привязать к клику и заявке нельзя.

    python clarity_daily.py --client-folder Andverpersonalinjury --label tilda
    python clarity_daily.py --client-folder Andverpersonalinjury --label tilda --dims URL Campaign --num-days 3
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from _config import client_stats_dir

URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


def get_token(env):
    tok = os.environ.get(env)
    if not tok and sys.platform == "win32":
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                              f"[Environment]::GetEnvironmentVariable('{env}','User')"], capture_output=True, text=True)
        tok = out.stdout.strip()
    if not tok:
        sys.exit(f"Нет токена: задайте переменную {env} (setx) и перезапустите VS Code")
    return tok


def fetch(tok, num_days, dim):
    params = {"numOfDays": str(num_days)}
    if dim:
        params["dimension1"] = dim
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params),
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--label", default="tilda", help="метка проекта в именах файлов")
    ap.add_argument("--token-env", default="LANDVER_CLARITY_API_TOKEN_TILDA")
    ap.add_argument("--num-days", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--dims", nargs="*", default=["", "URL", "Campaign", "Device"],
                    help="разрезы; пустая строка = без разреза (в командной строке: --dims '' URL Campaign Device)")
    ap.add_argument("--max-per-day", type=int, default=8, help="предохранитель (лимит API 10 в сутки)")
    a = ap.parse_args()

    tok = get_token(a.token_env)
    now = datetime.now(timezone.utc)
    stats = client_stats_dir(a.client_folder)
    raw_dir = stats / f"clarity_{a.label}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    qfile = raw_dir / f"quota_{now:%Y-%m-%d}.txt"
    used = int(qfile.read_text().strip() or 0) if qfile.exists() else 0
    csv_path = stats / f"clarity_{a.label}.csv"
    new = not csv_path.exists()
    pulled = f"{now:%Y-%m-%d %H:%M}"
    rows_total = 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["pulled_at", "num_days", "dimension", "dim_value", "metric", "field", "value"])
        for dim in a.dims:
            if used >= a.max_per_day:
                print(f"СТОП: сегодня уже {used} запросов (предохранитель {a.max_per_day}, лимит API 10)")
                break
            try:
                data = fetch(tok, a.num_days, dim)
            except urllib.error.HTTPError as e:
                print(f"[{dim or 'без разреза'}] HTTP {e.code}: {e.read().decode('utf-8')[:200]}")
                used += 1
                continue
            used += 1
            qfile.write_text(str(used))
            (raw_dir / f"raw_{now:%Y%m%d_%H%M}_{dim or 'none'}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            n = 0
            for m in data:
                for info in m.get("information", []):
                    key = info.get(dim, "") if dim else ""
                    if dim and not key:  # имя поля разреза в ответе может отличаться регистром
                        key = next((v for k, v in info.items() if k.lower() == dim.lower()), "")
                    for field, value in info.items():
                        if dim and field.lower() == dim.lower():
                            continue
                        w.writerow([pulled, a.num_days, dim or "none", key, m.get("metricName"), field, value])
                        n += 1
            rows_total += n
            sess = sum(float(i.get("totalSessionCount") or 0)
                       for m in data if m.get("metricName") == "Traffic" for i in m.get("information", []))
            print(f"[{dim or 'без разреза'}] метрик {len(data)}, строк {n}, сессий в Traffic {sess:.0f}")
    print(f"\nЗапросов сегодня (UTC): {used} из 10. Строк добавлено: {rows_total}. История: {csv_path}")


if __name__ == "__main__":
    main()
