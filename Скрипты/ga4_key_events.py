#!/usr/bin/env python
# coding: utf-8
"""Ключевые события GA4 (раньше «конверсии») через Admin API. ЗАПИСЬ только с --execute.

Зачем: событие попадает в импорт конверсий Google Ads только если оно отмечено ключевым в GA4. Без --execute скрипт печатает
список ключевых событий ресурса и что будет создано; читает обратно после записи. Уже отмеченные пропускаются.

Ключ и роль — как у ga4_custom_definitions.py (сервисный аккаунт ga4-analytics, «Редактор»).

    python ga4_key_events.py --property 549802233 --event callback_request
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
    ap.add_argument("--event", action="append", default=[], help="имя события (повторяемый)")
    ap.add_argument("--counting", default="ONCE_PER_EVENT", choices=["ONCE_PER_EVENT", "ONCE_PER_SESSION"],
                    help="как считать: каждое событие или раз за сеанс")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("GA4_KEY_FILE", DEFAULT_KEY)
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(key, scopes=SCOPES))
    prop = f"properties/{a.property}"

    def listing():
        r = s.get(f"{BASE}{prop}/keyEvents", params={"pageSize": 200})
        if r.status_code != 200:
            raise SystemExit(f"GA4 Admin API keyEvents: {r.status_code} {r.text[:300]}")
        return {x["eventName"]: x for x in r.json().get("keyEvents", [])}

    have = listing()
    print(f"Ресурс {a.property}: ключевых событий {len(have)}")
    for n, x in have.items():
        print(f"  {n} | {x.get('countingMethod')} | custom={x.get('custom')}")
    todo = [e for e in a.event if e not in have]
    for e in a.event:
        if e in have:
            print(f"  уже ключевое: {e}")
    if not todo:
        return
    print("Будет отмечено ключевым:", ", ".join(todo), f"({a.counting})")
    if not a.execute:
        print("Ничего не изменено (нужен --execute).")
        return
    for e in todo:
        r = s.post(f"{BASE}{prop}/keyEvents", json={"eventName": e, "countingMethod": a.counting})
        print(f"  создание {e}: {r.status_code} {r.text[:300] if r.status_code != 200 else 'ок'}")
    after = listing()
    print("Чтение обратно:", {e: (after[e].get("countingMethod") if e in after else "НЕТ") for e in a.event})


if __name__ == "__main__":
    main()
