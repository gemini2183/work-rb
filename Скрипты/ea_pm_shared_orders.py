#!/usr/bin/env python
# coding: utf-8
"""Общие заказы листов `Ekspertagro.pl` и `mocnaszklarnia.pl` таблицы продаж клиента — ТОЛЬКО ЧТЕНИЕ.

Зачем: звонок на номер EkspertAgro по резервной схеме переадресации принимается в проекте ProfiMet (номер 48579774289),
а один человек может звонить и на номер ProfiMet. Один заказ тогда виден в обоих листах. Скрипт показывает: сколько заказов
общих, в каком листе заказ создан первым, продан ли он в каждом листе (по «Дате продажи»/«Дате отмены»), как часто совпадает
сумма/дата, и не попадает ли одна продажа в оба листа.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_pm_shared_orders.py [--csv путь.csv] [--from 2026-08-01]
"""
import argparse

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"
COLS = ["ts_raw", "phone", "type", "src", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "gclid", "order", "status", "sale_date", "cancel_date", "reason", "order_date"]


def load(ws_name):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet(ws_name)
    vals = ws.get_all_values()
    n = len(COLS)
    df = pd.DataFrame([(r + [""] * n)[:n] for r in vals[1:]], columns=COLS).replace("—", "")
    df["ts"] = pd.to_datetime(df["ts_raw"], utc=True, errors="coerce")
    for c in ("sale_date", "cancel_date"):
        df[c + "_dt"] = pd.to_datetime(df[c], utc=True, errors="coerce")
    df["sheet"] = ws_name
    return df


def orders_of(df):
    o = df[df["order"] != ""].sort_values("ts")
    g = o.groupby("order")
    return pd.DataFrame({
        "created": g["ts"].min(), "rows": g.size(), "first_src": g["src"].first(), "first_type": g["type"].first(),
        "campaign": g["utm_campaign"].first(), "phone": g["phone"].first(),
        "sale": g["sale_date_dt"].max(), "cancel": g["cancel_date_dt"].max(), "status_last": g["status"].last(),
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--from", dest="d0", default=None, help="только заказы, созданные не раньше (ГГГГ-ММ-ДД)")
    a = ap.parse_args()

    ea, pm = load("Ekspertagro.pl"), load("mocnaszklarnia.pl")
    oe, op = orders_of(ea), orders_of(pm)
    if a.d0:
        t = pd.Timestamp(a.d0, tz="UTC")
        oe, op = oe[oe["created"] >= t], op[op["created"] >= t]
    common = oe.index.intersection(op.index)
    print(f"Заказов: EkspertAgro {len(oe)}, ProfiMet {len(op)}, общих {len(common)}")
    if not len(common):
        return
    m = oe.loc[common].join(op.loc[common], lsuffix="_ea", rsuffix="_pm")
    m["first"] = (m["created_ea"] <= m["created_pm"]).map({True: "EA", False: "PM"})
    m["phone_same"] = m["phone_ea"].str[-9:] == m["phone_pm"].str[-9:]
    m["sold_ea"] = m["sale_ea"].notna() & m["cancel_ea"].isna()
    m["sold_pm"] = m["sale_pm"].notna() & m["cancel_pm"].isna()
    m["sold_both"] = m["sold_ea"] & m["sold_pm"]
    m["sold_diff_date"] = m["sold_both"] & (m["sale_ea"] != m["sale_pm"])

    print("\nКто создал заказ первым:", m["first"].value_counts().to_dict())
    print("Телефон первой строки совпадает:", int(m["phone_same"].sum()), "из", len(m))
    print("Продан (по «Дате продажи», не отменён): в EA", int(m["sold_ea"].sum()), "| в PM", int(m["sold_pm"].sum()),
          "| в обоих листах", int(m["sold_both"].sum()), "| только в EA", int((m["sold_ea"] & ~m["sold_pm"]).sum()),
          "| только в PM", int((m["sold_pm"] & ~m["sold_ea"]).sum()))
    print("Продан в обоих, но даты продажи разные:", int(m["sold_diff_date"].sum()))
    print("\nСтрок заказа в EA / в PM (сумма):", int(m["rows_ea"].sum()), "/", int(m["rows_pm"].sum()))
    print("\nТип первой строки EA (форма/звонок):", m["first_type_ea"].value_counts().to_dict())
    print("Тип первой строки PM:", m["first_type_pm"].value_counts().to_dict())
    print("\nИсточник первой строки в EA :", m["first_src_ea"].value_counts().head(6).to_dict())
    print("Источник первой строки в PM :", m["first_src_pm"].value_counts().head(6).to_dict())
    m["month"] = m[["created_ea", "created_pm"]].min(axis=1).dt.strftime("%Y-%m")
    print("\nОбщих заказов по месяцам создания:", m["month"].value_counts().sort_index().to_dict())
    print("Продан хотя бы в одном листе, по месяцам:",
          m[m["sold_ea"] | m["sold_pm"]]["month"].value_counts().sort_index().to_dict())
    if a.csv:
        m.reset_index().to_csv(a.csv, index=False, encoding="utf-8-sig")
        print("CSV:", a.csv)


if __name__ == "__main__":
    main()
