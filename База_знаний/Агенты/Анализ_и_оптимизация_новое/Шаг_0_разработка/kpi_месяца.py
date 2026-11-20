#!/usr/bin/env python
# coding: utf-8
"""Шаг 0, «KPI месяца» — ТОЛЬКО ЧТЕНИЕ (в таблицу, кабинеты и вики ничего не пишет).

Что делает: берёт клиента и месяц, находит в таблице «Цели2» лист этого месяца и строку этого клиента,
отдаёт план: бюджет, число заявок, плановая цена заявки. Ничего больше не читает и не считает.

Откуда берёт данные:
  - клиент: аргумент --client (имя папки в Клиенты/);
  - месяц: аргумент --month ГГГГ-ММ; не задан = текущий месяц по часовому поясу клиента;
  - таблица, имя строки клиента, столбец бюджета, часовой пояс: Клиенты/<клиент>/analysis_config.yaml
    (секции plan: sheet_id, client_name, budget_column; timezone);
  - доступ к таблице: SERVICE_ACCOUNT_FILE из Скрипты/_config.py (как в готовом campaign_analyzer.sources.read_plan).
Лист называется «<Месяц по-русски> <гг>», например «Ноябрь 26». Нет листа, нет строки, строка не одна,
нет значения: остановка с сообщением, без подстановок.

Выход (в --out-dir):
  kpi.csv      одна строка: клиент, месяц, лист, бюджет, заявки, цена заявки, источник
  kpi_row.json вся найденная строка таблицы как есть (для проверки, что взяли нужные столбцы)

Использование (из папки Скрипты, PYTHONUTF8=1):
    python ../База_знаний/Агенты/Анализ_и_оптимизация_новое/Шаг_0_разработка/kpi_месяца.py --client ProfiMet --out-dir "<папка задачи>"
    ... --month 2026-10   # другой месяц
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "Скрипты"))
sys.stdout.reconfigure(encoding="utf-8")

import gspread  # noqa: E402
import yaml  # noqa: E402
from google.oauth2.service_account import Credentials  # noqa: E402

from _config import SCOPES, SERVICE_ACCOUNT_FILE, VAULT_ROOT  # noqa: E402

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
             "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def load_client_cfg(client: str) -> dict:
    path = VAULT_ROOT / "Клиенты" / client / "analysis_config.yaml"
    if not path.exists():
        raise SystemExit(f"Пробел: нет файла {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    plan = cfg.get("plan") or {}
    for k in ("sheet_id", "client_name", "budget_column"):
        if not plan.get(k):
            raise SystemExit(f"Пробел: в {path} нет plan.{k}")
    return cfg


def to_num(v, name):
    s = str(v).replace(",", ".").replace(" ", "").replace("\xa0", "")
    try:
        x = float(s)
    except ValueError:
        raise SystemExit(f"Пробел: в таблице «{name}» не число: {v!r}")
    if x <= 0:
        raise SystemExit(f"Пробел: в таблице «{name}» ноль или меньше: {v!r}")
    return x


def main():
    ap = argparse.ArgumentParser(description="Шаг 0: KPI месяца из таблицы «Цели2» (только чтение)")
    ap.add_argument("--client", required=True, help="имя папки клиента в Клиенты/")
    ap.add_argument("--month", help="ГГГГ-ММ; по умолчанию текущий месяц по часовому поясу клиента")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    cfg = load_client_cfg(a.client)
    plan_cfg = cfg["plan"]

    if a.month:
        try:
            y, m = (int(x) for x in a.month.split("-"))
            assert 1 <= m <= 12
        except Exception:
            raise SystemExit("--month в формате ГГГГ-ММ, например 2026-11")
    else:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(cfg.get("timezone", "Europe/Warsaw")))
        y, m = now.year, now.month
    tab = f"{MONTHS_RU[m - 1]} {y % 100:02d}"

    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(plan_cfg["sheet_id"])
    try:
        ws = sh.worksheet(tab)
    except gspread.WorksheetNotFound:
        names = ", ".join(w.title for w in sh.worksheets())
        raise SystemExit(f"Пробел: в таблице нет листа «{tab}». Листы: {names}")

    rows = ws.get_all_records()
    found = [r for r in rows if str(r.get("Client", "")).strip() == plan_cfg["client_name"]]
    if not found:
        raise SystemExit(f"Пробел: в листе «{tab}» нет строки клиента «{plan_cfg['client_name']}»")
    if len(found) > 1:
        raise SystemExit(f"Пробел: в листе «{tab}» {len(found)} строк клиента «{plan_cfg['client_name']}», нужна одна")
    row = found[0]

    bcol = plan_cfg["budget_column"]
    for col in (bcol, "Conversions", "CPA"):
        if col not in row:
            raise SystemExit(f"Пробел: в листе «{tab}» нет столбца «{col}»")
    budget = to_num(row[bcol], bcol)
    leads = to_num(row["Conversions"], "Conversions")
    cpa = to_num(row["CPA"], "CPA")

    notes = []
    check = budget / leads
    if abs(check - cpa) / cpa > 0.01:
        notes.append(f"бюджет ÷ заявки = {check:.2f}, а в таблице цена заявки {cpa:.2f}: расхождение больше 1 %")

    src = f"Цели2, лист «{tab}», строка «{plan_cfg['client_name']}», столбцы {bcol} / Conversions / CPA"
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "kpi.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["client", "month", "tab", "plan_budget", "plan_leads", "plan_cpa", "source", "notes"])
        w.writerow([a.client, f"{y}-{m:02d}", tab, budget, leads, cpa, src, "; ".join(notes)])
    (out / "kpi_row.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Клиент {a.client}, месяц {y}-{m:02d}, лист «{tab}»")
    print(f"KPI: бюджет {budget:g}, заявки {leads:g}, цена заявки {cpa:g}")
    print(f"Источник: {src}")
    for n in notes:
        print("ПРИМЕЧАНИЕ:", n)
    print(f"Файлы: {out / 'kpi.csv'}, {out / 'kpi_row.json'}")


if __name__ == "__main__":
    main()
