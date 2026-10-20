#!/usr/bin/env python
# coding: utf-8
"""Сверка продаж EkspertAgro, шаг 1: доступ к таблице продаж клиента, лист «О таблице», разметка по месяцам.

ТОЛЬКО ЧТЕНИЕ. Таблицу читает сервисный аккаунт (роль «Читатель»). Таблица та же, что у ProfiMet, лист `Ekspertagro.pl`.
Печатает: описание таблицы, число обращений, типы, статусы, заказы по месяцу создания × статус, источники по месяцам.
Порядок всей сверки — `База_знаний/Агенты/Сверка_продаж_и_дашборда_клиента.md`.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_sales_sheet_overview.py [--sheet-id ID] [--worksheet Ekspertagro.pl]
"""
import argparse

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"
COLS = ["ts_raw", "phone", "type", "src", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "gclid", "order", "status", "sale_date", "cancel_date", "reason"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=SHEET_ID)
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    args = ap.parse_args()

    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(args.sheet_id)
    print("Листы:", [(w.title, w.row_count) for w in sh.worksheets()])
    for ws in sh.worksheets():
        if "." not in ws.title:  # лист «О таблице»
            print(f"\n=== {ws.title} ===")
            for r in ws.get_all_values():
                print(" | ".join(c for c in r if c))

    vals = sh.worksheet(args.worksheet).get_all_values()
    print(f"\nШапка листа {args.worksheet}:", vals[0])
    df = pd.DataFrame(vals[1:], columns=COLS).replace("—", "")
    df["ts"] = pd.to_datetime(df["ts_raw"], utc=True, errors="coerce")
    df["month"] = df["ts"].dt.strftime("%Y-%m")
    print("Строк:", len(df), "| первая:", df["ts"].min(), "| последняя:", df["ts"].max())
    print("\nТипы обращений:\n", df["type"].value_counts())
    print("\nСтатусы (все строки):\n", df["status"].value_counts(dropna=False))

    # заказ = самая сильная строка: Продажа > заказ отменён > остальное
    orders = df[df["order"] != ""].copy()
    rank = {"Продажа": 3, "заказ отменён": 2}
    orders["rk"] = orders["status"].map(lambda s: rank.get(s, 1))
    best = orders.sort_values("rk", ascending=False).drop_duplicates("order")
    best["omonth"] = best["order"].map(orders.groupby("order")["ts"].min()).dt.strftime("%Y-%m")
    print("\nЗаказы по месяцу создания × статус:")
    print(pd.crosstab(best["omonth"], best["status"], margins=True))
    print("\nОбращения по месяцам × тип:")
    print(pd.crosstab(df["month"], df["type"], margins=True))
    print("\nИсточник (src) по месяцам:")
    print(pd.crosstab(df["month"], df["src"], margins=True))


if __name__ == "__main__":
    main()
