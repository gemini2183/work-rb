#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: список ПРОДАННЫХ заказов выгрузки CRM с признаками — для сверки с продажами клиентского дашборда на уровне заказов. ТОЛЬКО ЧТЕНИЕ
(кроме записи вкладки «Заказы» в нашу Google Таблицу дашборда, если указан --update-sheet).

Одна строка = один проданный заказ листа `mocnaszklarnia.pl` (есть «Дата продажи»). Колонки: номер заказа, телефон, дата продажи, дата первой строки
заказа (≈ создание), чем начат заказ (форма/звонок), источник и статус первой строки, все источники и число строк заказа, дата отмены, источник по
НАШЕМУ правилу (первое обращение номера за 60 дн до заказа) и «метка по гипотезе клиента» (есть строка-форма → источник формы по UTM, иначе «Телефон»).
Нужен, чтобы по списку заказов за числами клиентского дашборда (Google 17 / Нет метки 18 / Телефон 40 за 01.10–19.10) увидеть, какие заказы он
не считает, и вывести правило отбора.

Использование:
    PYTHONIOENCODING=utf-8 python profimet_orders_list.py [--from 2026-08-01] [--to 2026-10-19] [--update-sheet [ID]] [--cache путь.pkl]
Пишет `Клиенты/ProfiMet/Статистика/orders_list_<с>_<по>.csv`. Запускать без -I.
"""
import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE, client_stats_dir
from profimet_season_audit import W
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_sources_dashboard import DASHBOARD_SHEET_ID, SITE, SOURCES, WINDOW

COLS = ["Заказ", "Телефон", "Дата продажи", "Первая строка заказа", "Заказ начат", "Источник первой строки", "Статус первой строки",
        "Все источники строк заказа", "Строк у заказа", "Дата отмены", "Источник по нашему правилу", "Метка по гипотезе клиента"]


def orders_table(sheet, frm, to):
    s = sheet[sheet["site"] == SITE].copy()
    s["src2"] = s["src"].replace("", "Нет метки")
    s.loc[~s["src2"].isin(SOURCES), "src2"] = "Прочее"
    by_phone = {p: g for p, g in s.groupby("p9") if p}
    rows = []
    for order, g in s[s["order"] != ""].groupby("order"):
        sd = [d for d in g["sale_date"] if d]
        if not sd:
            continue
        sale = pd.Timestamp(min(sd)).date()
        if not (pd.Timestamp(frm).date() <= sale <= pd.Timestamp(to).date()):
            continue
        g = g.sort_values("ts", kind="mergesort")
        f = g.iloc[0]
        t0 = f["ts"]
        parts = [by_phone[p] for p in set(g["p9"]) if p in by_phone]
        t = pd.concat(parts) if parts else g
        t = t[(t["ts"] >= t0 - pd.Timedelta(days=WINDOW)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        our = (t.iloc[0]["src2"] if not t.empty else f["src2"])
        forms = g[g["type"] == "форма"]
        rows.append({
            "Заказ": order, "Телефон": f["phone"], "Дата продажи": sale.isoformat(),
            "Первая строка заказа": t0.tz_convert(W).strftime("%Y-%m-%d %H:%M"), "Заказ начат": f["type"],
            "Источник первой строки": f["src2"], "Статус первой строки": f["status"],
            "Все источники строк заказа": ", ".join(sorted(set(g["src2"]))), "Строк у заказа": len(g),
            "Дата отмены": next((d for d in g["cancel_date"] if d), ""), "Источник по нашему правилу": our,
            "Метка по гипотезе клиента": forms.iloc[0]["src2"] if not forms.empty else "Телефон"})
    return pd.DataFrame(rows, columns=COLS).sort_values(["Дата продажи", "Первая строка заказа"]).reset_index(drop=True)


def write_tab(file_id, df):
    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    meta = s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in meta["sheets"]}
    if "Заказы" not in ids:
        r = s.post(base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": "Заказы", "gridProperties": {"frozenRowCount": 1}}}}]}, timeout=60)
        r.raise_for_status()
        ids["Заказы"] = r.json()["replies"][0]["addSheet"]["properties"]["sheetId"]
    values = [list(df.columns)] + [[("" if (isinstance(v, float) and pd.isna(v)) else (v.item() if hasattr(v, "item") else v)) for v in row] for row in df.itertuples(index=False)]
    s.post(base + "/values/Заказы!A1:Z5000:clear", json={}, timeout=60).raise_for_status()
    s.put(base + "/values/Заказы!A1?valueInputOption=USER_ENTERED", json={"values": values}, timeout=120).raise_for_status()
    s.post(base + ":batchUpdate", json={"requests": [
        {"repeatCell": {"range": {"sheetId": ids["Заказы"], "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.87, "green": 0.92, "blue": 0.97}}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"setBasicFilter": {"filter": {"range": {"sheetId": ids["Заказы"], "startRowIndex": 0, "endRowIndex": len(values), "startColumnIndex": 0, "endColumnIndex": len(COLS)}}}},
        {"autoResizeDimensions": {"dimensions": {"sheetId": ids["Заказы"], "dimension": "COLUMNS", "startIndex": 0, "endIndex": len(COLS)}}}]}, timeout=60).raise_for_status()
    return len(values) - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--to", dest="to", default="2026-10-19")
    ap.add_argument("--update-sheet", nargs="?", const=DASHBOARD_SHEET_ID, default=None, metavar="ID", help="записать вкладку «Заказы» в Google Таблицу дашборда")
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cache and Path(a.cache).exists():
        sheet = pickle.load(open(a.cache, "rb"))[0]
    else:
        sheet = load_sheet(SHEET_ID)
    df = orders_table(sheet, a.frm, a.to)
    out = client_stats_dir("ProfiMet") / f"orders_list_{a.frm}_{a.to}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Проданных заказов {a.frm} — {a.to}: {len(df)}; CSV: {out}")
    for lab, a1, b1 in (("01.10–19.10", "2026-10-01", "2026-10-19"), ("весь период", a.frm, a.to)):
        x = df[(df["Дата продажи"] >= a1) & (df["Дата продажи"] <= b1)]
        print(f"  {lab}: {len(x)}; заказ начат: {x['Заказ начат'].value_counts().to_dict()}; метка по гипотезе клиента: {x['Метка по гипотезе клиента'].value_counts().to_dict()}")
    if a.update_sheet:
        n = write_tab(a.update_sheet, df)
        print(f"Вкладка «Заказы» записана: {n} строк — https://docs.google.com/spreadsheets/d/{a.update_sheet}/edit")


if __name__ == "__main__":
    main()
