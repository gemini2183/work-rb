#!/usr/bin/env python
# coding: utf-8
"""Пользовательские определения GA4 (измерения и показатели событий) через Admin API. ЗАПИСЬ только с --execute.

Зачем: параметры событий (block_name, quiz_answer, ...) видны в отчётах GA4 только после регистрации как пользовательские
измерения/показатели. Раньше создавалось разовой командой (Landver И-049, 2026-10-15); теперь один скрипт: по умолчанию
печатает, что есть и что будет создано, ничего не меняя.

Определения задаются списком `--dim имя "Название в отчётах"` (измерение, область «событие») и `--metric имя "Название" [единица]`
(показатель, единица STANDARD или SECONDS). Уже существующие по `parameterName` пропускаются; чтение обратно — в конце.
Квота GA4: 50 измерений и 50 показателей уровня события на ресурс.

Ключ: сервисный аккаунт ga4-analytics (как у ga4_behavior.py), путь из GA4_KEY_FILE или значения по умолчанию; роль в ресурсе —
«Редактор» (чтение отчётов есть и без неё).

    python ga4_custom_definitions.py --property 549802233 --dim quiz_answer "Quiz answer" --dim cta_place "CTA place"
    ... --execute
"""
import argparse
import os

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

DEFAULT_KEY = r"E:\PythonProjects\RedBird\google-cloud-jobs\adwhite\func\ga4_profimet\redbird-196813-ga4.json"
BASE = "https://analyticsadmin.googleapis.com/v1beta/"
SCOPES = ["https://www.googleapis.com/auth/analytics.edit", "https://www.googleapis.com/auth/analytics.readonly"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", required=True, help="числовой id ресурса GA4")
    ap.add_argument("--dim", nargs=2, action="append", default=[], metavar=("ПАРАМЕТР", "НАЗВАНИЕ"))
    ap.add_argument("--metric", nargs="+", action="append", default=[], metavar="ПАРАМЕТР НАЗВАНИЕ [ЕДИНИЦА]")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("GA4_KEY_FILE", DEFAULT_KEY)
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(key, scopes=SCOPES))
    prop = f"properties/{a.property}"

    def listing(kind):
        r = s.get(f"{BASE}{prop}/{kind}", params={"pageSize": 200})
        if r.status_code != 200:
            raise SystemExit(f"GA4 Admin API {kind}: {r.status_code} {r.text[:300]}")
        return r.json().get(kind, [])

    have_d = {x["parameterName"]: x for x in listing("customDimensions")}
    have_m = {x["parameterName"]: x for x in listing("customMetrics")}
    print(f"Ресурс {a.property}: измерений {len(have_d)}, показателей {len(have_m)}")
    todo = []
    for name, title in a.dim:
        if name in have_d:
            print(f"  уже есть измерение {name} («{have_d[name]['displayName']}»)")
        else:
            todo.append(("customDimensions", {"parameterName": name, "displayName": title, "scope": "EVENT"}))
    for m in a.metric:
        name, title, unit = m[0], m[1], (m[2] if len(m) > 2 else "STANDARD")
        if name in have_m:
            print(f"  уже есть показатель {name} («{have_m[name]['displayName']}»)")
        else:
            todo.append(("customMetrics", {"parameterName": name, "displayName": title, "scope": "EVENT", "measurementUnit": unit}))
    for kind, body in todo:
        print(("  СОЗДАМ " if a.execute else "  создал бы ") + kind[:-1], body["parameterName"], "—", body["displayName"])
    if not a.execute:
        print("\nНичего не изменено (нужен --execute).")
        return
    for kind, body in todo:
        r = s.post(f"{BASE}{prop}/{kind}", json=body)
        print(f"  {body['parameterName']}: {r.status_code}" + ("" if r.status_code == 200 else " " + r.text[:300]))
    print("\nЧтение обратно:")
    for x in listing("customDimensions"):
        print("  измерение", x["parameterName"], "|", x["displayName"])
    for x in listing("customMetrics"):
        print("  показатель", x["parameterName"], "|", x["displayName"], "|", x.get("measurementUnit"))


if __name__ == "__main__":
    main()
