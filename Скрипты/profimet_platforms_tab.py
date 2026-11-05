#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: вкладка «Платформы» в Google Таблице дашборда — заявки по платформам против эталона BigQuery (2026-11-05).

Берёт данные у `profimet_leads_matrix.collect` (звонки: Ringostat / BigQuery / выгрузка CRM; формы: Tilda / Supabase / GA4 /
BigQuery / выгрузка CRM) и кладёт в таблицу дашборда два листа:
  «Платформы_данные» — длинная таблица (дата, вид, платформа, канал, группа, число);
  «Платформы»        — формулы: матрица «платформа × канал» за выбранный период + отклонение от BigQuery,
                       и таблица по дням с подсветкой ячеек, где число не равно BigQuery (канал выбирается списком).
Другие листы таблицы не трогает. ПО УМОЛЧАНИЮ НИЧЕГО НЕ ПИШЕТ (печатает, что записал бы); запись — только с `--execute`.
Выбор периода на листе «Платформы» свой (ячейки B3 и B4), от листа «Дашборд» не зависит.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python profimet_platforms_tab.py [--from 2026-10-01] [--to 2026-11-04] [--cache путь.pkl] [--execute]
После `profimet_sources_dashboard.py --rebuild-sheet` листы пропадают (таблица пересобирается из xlsx) — запустить снова с `--execute`.
"""
import argparse
import datetime
import json
import sys
from datetime import date, timedelta

import pandas as pd
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE
from profimet_leads_matrix import CALLS, FORMS, collect
from profimet_sources_dashboard import DASHBOARD_SHEET_ID

DATA, TAB = "Платформы_данные", "Платформы"
ADS = ["Google Ads", "Facebook", "Google SEO"]
OUT = "Вне эталона"
SERIAL0 = datetime.date(1899, 12, 30)
ser = lambda d: (d - SERIAL0).days


def long_table(df):
    d = df.copy()
    d["group"] = d["channel"].where(d["channel"].isin(ADS), OUT)
    d = d.groupby(["day", "kind", "platform", "channel", "group"], as_index=False)["n"].sum().sort_values(["day", "kind", "platform", "channel"])
    return [[ser(r.day), r.kind, r.platform, r.channel, r.group, int(r.n)] for r in d.itertuples(index=False)]


def build_tab(d0, d1):
    """Возвращает ячейки листа «Платформы»: dict {адрес: значение/формула}, число строк, строки с эталоном и границы таблицы по дням."""
    c = {}
    q = lambda col: f"'{DATA}'!${col}:${col}"
    period = f'{q("A")},">="&$B$3,{q("A")},"<="&$B$4'
    c["A1"] = "ProfiMet: заявки по платформам (эталон — BigQuery общего дашборда агентства)"
    c["A2"] = "Звонки: боевое правило Ringostat 60 дн = BigQuery. Формы: BigQuery = сеансы GA4 form_submit по Google Ads, Facebook и SEO. Красная ячейка = число не равно BigQuery."
    c["A3"], c["B3"] = "Начало периода (можно менять)", ser(date.fromisoformat(d0))
    c["A4"], c["B4"] = "Конец периода (можно менять)", ser(date.fromisoformat(d1))
    c["A5"], c["B5"] = "Данные платформ есть по", f"=MAX({q('A')})"
    r = 7
    refs = {}
    for kind, plats, title in (("Звонки", CALLS, "ЗВОНКИ за период"), ("Формы", FORMS, "ФОРМЫ за период")):
        c[f"A{r}"] = title
        hdr = r + 1
        for j, h in enumerate(["Платформа"] + ADS + [OUT], 0):
            c[f"{chr(65 + j)}{hdr}"] = h
        for j, h in enumerate(ADS):
            c[f"{chr(70 + j)}{hdr}"] = f"Отличие от BigQuery: {h}"
        ref = hdr + 1 + plats.index(plats[2] if kind == "Звонки" else FORMS[3])
        for i, p in enumerate(plats):
            rr = hdr + 1 + i
            c[f"A{rr}"] = p
            for j in range(4):
                col = chr(66 + j)
                c[f"{col}{rr}"] = f'=SUMIFS({q("F")},{period},{q("B")},"{kind}",{q("C")},$A{rr},{q("E")},{col}${hdr})'
            for j in range(3):
                c[f"{chr(70 + j)}{rr}"] = "эталон" if rr == ref else f"={chr(66 + j)}{rr}-{chr(66 + j)}${ref}"
        refs[kind] = (hdr, ref, hdr + len(plats))
        r = hdr + len(plats) + 2
    # --- по дням
    c[f"A{r}"] = "ПО ДНЯМ"
    sel = r + 1
    c[f"A{sel}"], c[f"B{sel}"] = "Канал для таблицы по дням", "Все (Google Ads + Facebook + Google SEO)"
    c[f"D{sel}"] = f'=IF(LEFT(B{sel},3)="Все","<>{OUT}",B{sel})'
    kinds, hdr = sel + 1, sel + 2
    c[f"A{hdr}"] = "Дата"
    cols = {}
    for i, p in enumerate(CALLS):
        cols[p, "Звонки"] = chr(66 + i)
    for i, p in enumerate(FORMS):
        cols[p, "Формы"] = chr(72 + i)
    c[f"B{kinds}"], c[f"H{kinds}"] = "ЗВОНКИ", "ФОРМЫ"
    for (p, kind), col in cols.items():
        c[f"{col}{hdr}"] = p
    first = hdr + 1
    days = pd.date_range(d0, d1).date
    for i, d in enumerate(days):
        rr = first + i
        c[f"A{rr}"] = ser(d)
        for (p, kind), col in cols.items():
            c[f"{col}{rr}"] = f'=SUMIFS({q("F")},{q("A")},$A{rr},{q("B")},"{kind}",{q("C")},{col}${hdr},{q("E")},$D${sel})'
    last = first + len(days) - 1
    # локаль таблицы ru_RU: разделитель аргументов в формулах — «;»
    c = {k: (v.replace(",", ";") if isinstance(v, str) and v.startswith("=") else v) for k, v in c.items()}
    c["_layout"] = dict(sel=sel, hdr=hdr, first=first, last=last, refs=refs, cols=cols)
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-10-01")
    ap.add_argument("--to", dest="d1", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--cache", default=None)
    ap.add_argument("--execute", action="store_true", help="записать листы в таблицу дашборда (без флага — только план)")
    ap.add_argument("--sheet-id", default=DASHBOARD_SHEET_ID)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    df, extra = collect(a.d0, a.d1, a.cache)
    rows = long_table(df)
    cells = build_tab(a.d0, a.d1)
    lay = cells.pop("_layout")
    json.dumps(rows), json.dumps(cells)
    print(f"Данные: {len(rows)} строк, период {a.d0} … {a.d1}; лист «{TAB}»: {len(cells)} ячеек, таблица по дням: строки {lay['first']}–{lay['last']}")
    if not a.execute:
        print("Без --execute ничего не записано.")
        return

    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{a.sheet_id}"
    meta = s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in meta["sheets"]}
    add = [{"addSheet": {"properties": {"title": t}}} for t in (TAB, DATA) if t not in ids]
    if add:
        resp = s.post(base + ":batchUpdate", json={"requests": add}, timeout=60)
        resp.raise_for_status()
        for rep in resp.json()["replies"]:
            p = rep["addSheet"]["properties"]
            ids[p["title"]] = p["sheetId"]
    # очистка только наших двух листов (+ старые правила подсветки и проверки данных)
    for t in (TAB, DATA):
        s.post(base + f"/values/{t}:clear", json={}, timeout=60).raise_for_status()
    old = s.get(base + "?fields=sheets(properties(sheetId,title),conditionalFormats)", timeout=60).json()["sheets"]
    drop = []
    for sh in old:
        if sh["properties"]["title"] == TAB:
            drop += [{"deleteConditionalFormatRule": {"sheetId": ids[TAB], "index": 0}} for _ in sh.get("conditionalFormats", [])]
    # данные
    s.put(base + f"/values/{DATA}!A1?valueInputOption=USER_ENTERED",
          json={"values": [["Дата", "Вид", "Платформа", "Канал", "Группа", "Число"]] + rows}, timeout=120).raise_for_status()
    # лист «Платформы»: только непустые ячейки
    data = [{"range": f"{TAB}!{k}", "values": [[v]]} for k, v in cells.items()]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()

    t, dsid = ids[TAB], ids[DATA]
    first, last, hdr, sel = lay["first"], lay["last"], lay["hdr"], lay["sel"]
    red = {"red": 1.0, "green": 0.8, "blue": 0.8}
    head = {"red": 0.87, "green": 0.92, "blue": 0.97}
    yellow = {"red": 1.0, "green": 0.95, "blue": 0.8}
    rng = lambda r0, r1, c0, c1, sid=t: {"sheetId": sid, "startRowIndex": r0 - 1, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}
    cf = lambda r0, r1, c0, c1, f: {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(r0, r1, c0, c1)], "booleanRule": {
        "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f}]}, "format": {"backgroundColor": red}}}}}
    bold = lambda r0, r1, c0, c1, bg=None: {"repeatCell": {"range": rng(r0, r1, c0, c1), "cell": {"userEnteredFormat": {
        "textFormat": {"bold": True}, **({"backgroundColor": bg} if bg else {}), "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}},
        "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy,verticalAlignment)"}}
    reqs = list(drop)
    reqs += [
        {"updateSpreadsheetProperties": {"properties": {"locale": "ru_RU", "timeZone": "Europe/Warsaw"}, "fields": "locale,timeZone"}},
        bold(1, 1, 0, 1), bold(3, 4, 0, 1),
        {"repeatCell": {"range": rng(3, 4, 1, 2), "cell": {"userEnteredFormat": {"backgroundColor": yellow, "numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}},
                        "fields": "userEnteredFormat(backgroundColor,numberFormat)"}},
        {"repeatCell": {"range": rng(5, 5, 1, 2), "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {"range": rng(sel, sel, 1, 2), "cell": {"userEnteredFormat": {"backgroundColor": yellow}}, "fields": "userEnteredFormat.backgroundColor"}},
        {"setDataValidation": {"range": rng(sel, sel, 1, 2), "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
            {"userEnteredValue": "Все (Google Ads + Facebook + Google SEO)"}, {"userEnteredValue": "Google Ads"}, {"userEnteredValue": "Facebook"},
            {"userEnteredValue": "Google SEO"}, {"userEnteredValue": OUT}]}, "strict": True, "showCustomUi": True}}},
        {"repeatCell": {"range": rng(first, last, 0, 1), "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {"range": rng(hdr, hdr, 0, 12), "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": head, "wrapStrategy": "WRAP",
                                                                                     "verticalAlignment": "MIDDLE", "horizontalAlignment": "CENTER"}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy,verticalAlignment,horizontalAlignment)"}},
        {"updateDimensionProperties": {"range": {"sheetId": t, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 270}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": t, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 12}, "properties": {"pixelSize": 120}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": t, "dimension": "ROWS", "startIndex": hdr - 1, "endIndex": hdr}, "properties": {"pixelSize": 64}, "fields": "pixelSize"}},
        {"updateSheetProperties": {"properties": {"sheetId": dsid, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": rng(2, len(rows) + 1, 0, 1, dsid), "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
    ]
    for kind, (h, ref, end) in lay["refs"].items():
        reqs += [bold(h - 1, h - 1, 0, 1), bold(h, h, 0, 8, head)]
        # красим отличия от BigQuery в блоке «отклонение» (F:H) и в самих числах (B:D)
        for a0, a1 in ((h + 1, ref - 1), (ref + 1, end)):  # строки до и после эталонной (без функций: формулы условного формата зависят от локали)
            if a0 <= a1:
                reqs += [cf(a0, a1, 5, 8, f'=F{a0}<>0'), cf(a0, a1, 1, 4, f'=B{a0}<>B${ref}')]
    # по дням: сравниваем с колонкой BigQuery
    cols = lay["cols"]
    bq_c, bq_f = cols[CALLS[2], "Звонки"], cols[FORMS[3], "Формы"]
    for (p, kind), col in cols.items():
        if p in (CALLS[2], FORMS[3]):
            continue
        bq = bq_c if kind == "Звонки" else bq_f
        ci = ord(col) - 65
        reqs.append(cf(first, last, ci, ci + 1, f'=${col}{first}<>${bq}{first}'))
    reqs.append(bold(lay["hdr"] - 1, lay["hdr"] - 1, 1, 2, head))
    resp = s.post(base + ":batchUpdate", json={"requests": reqs}, timeout=120)
    if not resp.ok:
        print("Ошибка форматирования:", resp.text[:600])
        resp.raise_for_status()
    print(f"Записано: https://docs.google.com/spreadsheets/d/{a.sheet_id}/edit#gid={t}")


if __name__ == "__main__":
    main()
