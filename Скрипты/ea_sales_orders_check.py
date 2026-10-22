#!/usr/bin/env python
# coding: utf-8
"""Сверка продаж EkspertAgro, шаг 1б: заказы таблицы клиента по колонкам «Дата продажи» / «Дата отмены», ТОЛЬКО ЧТЕНИЕ.

Зачем: статус в строке таблицы — статус заказа НА МОМЕНТ ОБРАЩЕНИЯ (лист «О таблице»), поэтому заказ, созданный формой
в статусе «Заявка» и проданный позже, остаётся «предзаказом» в строке формы. Истина о продаже — колонки «Дата продажи»
и «Дата отмены заказа» (одинаковые во всех строках заказа). Скрипт считает заказы по ним и сравнивает с подсчётом по статусам.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_sales_orders_check.py [--sheet-id ID] [--worksheet Ekspertagro.pl] [--csv путь]
"""
import argparse

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"
COLS = ["ts_raw", "phone", "type", "src", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "gclid", "order", "status", "sale_date", "cancel_date", "reason"]


def load(sheet_id, worksheet):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    vals = gspread.authorize(creds).open_by_key(sheet_id).worksheet(worksheet).get_all_values()
    df = pd.DataFrame(vals[1:], columns=COLS).replace("—", "")
    df["ts"] = pd.to_datetime(df["ts_raw"], utc=True, errors="coerce")
    for c in ("sale_date", "cancel_date"):
        df[c + "_dt"] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=SHEET_ID)
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    ap.add_argument("--csv", default=None, help="сохранить таблицу заказов")
    args = ap.parse_args()

    df = load(args.sheet_id, args.worksheet)
    o = df[df["order"] != ""].copy()
    print(f"Строк {len(df)}, из них с заказом {len(o)}, заказов {o['order'].nunique()}")

    # есть ли внутри заказа расхождения дат продажи/отмены между строками
    nun = o.groupby("order").agg(sale_n=("sale_date", lambda s: s[s != ""].nunique()),
                                 cancel_n=("cancel_date", lambda s: s[s != ""].nunique()))
    print("Заказов с разными датами продажи в строках:", int((nun["sale_n"] > 1).sum()),
          "| с разными датами отмены:", int((nun["cancel_n"] > 1).sum()))

    g = o.sort_values("ts").groupby("order")
    orders = pd.DataFrame({
        "created": g["ts"].min(),
        "rows": g.size(),
        "first_src": g["src"].first(),
        "first_type": g["type"].first(),
        "first_campaign": g["utm_campaign"].first(),
        "sale": g["sale_date_dt"].max(),
        "cancel": g["cancel_date_dt"].max(),
        "status_last": g["status"].last(),
        "phone": g["phone"].first(),
    })
    orders["by_dates"] = "в работе / не обработан"
    orders.loc[orders["cancel"].notna(), "by_dates"] = "отменён"
    orders.loc[orders["sale"].notna(), "by_dates"] = "продан"
    orders.loc[orders["sale"].notna() & orders["cancel"].notna(), "by_dates"] = "продан и отменён"
    orders["cmonth"] = orders["created"].dt.strftime("%Y-%m")
    orders["smonth"] = orders["sale"].dt.strftime("%Y-%m")

    print("\nЗаказы по месяцу создания × итог по датам продажи/отмены:")
    print(pd.crosstab(orders["cmonth"], orders["by_dates"], margins=True))
    print("\nПроданные заказы по месяцу ПРОДАЖИ:")
    print(orders["smonth"].value_counts().sort_index())
    print("\nПроверка: статус последней строки заказа × итог по датам:")
    print(pd.crosstab(orders["status_last"], orders["by_dates"], margins=True))
    print("\nПроданные заказы: источник первой строки × месяц создания:")
    print(pd.crosstab(orders[orders["by_dates"] == "продан"]["first_src"],
                      orders[orders["by_dates"] == "продан"]["cmonth"], margins=True))
    if args.csv:
        orders.to_csv(args.csv, encoding="utf-8-sig")
        print("Сохранено:", args.csv)


if __name__ == "__main__":
    main()
