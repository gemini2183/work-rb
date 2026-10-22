#!/usr/bin/env python
# coding: utf-8
"""Google Таблица «EkspertAgro — по источникам (дашборд)»: два режима («как у клиента» и «наш, по первому касанию») —
ЧТЕНИЕ внешних источников, ЗАПИСЬ только в эту таблицу (листы «Данные», «Заказы», «Дашборд», «Матрица», «Пояснения»).

Листы:
  Дашборд  — период (B2:B3), режим (B4), курс zł/€ (B5); таблица в колонках клиента; считается формулами по «Данные»/«Заказы».
  Данные   — по дням и источнику: расход, клики, показы (Google Ads API, Facebook BigQuery), звонки (первый звонок номера за
             всю историю; боевое правило 60 дней), формы (сеансы GA4 form_submit).
  Заказы   — по одному заказу: дата продажи, способ создания, метка клиента (из его списков или по правилу «звонок → Телефон,
             форма → её источник»), наше первое касание и как оно определено.
  Матрица  — «из чего сложились продажи»: метка клиента × первое касание за выбранный период.
Обновление: `python ea_sources_dashboard_sheet.py --sheet-id ID [--from 2026-09-01]` перезаписывает «Данные» и «Заказы»;
`--rebuild` пересоздаёт листы с формулами (сбрасывает период/режим). Сервисному аккаунту нужен «Редактор».
Определения — на листе «Пояснения» и в докстринге `ea_sources_dashboard.py`.
"""
import argparse
import datetime as dt
import json
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE
from ea_dashboard_reconcile import cat_of
from ea_ringostat_vs_sheet import SHEET_ID as CRM_SHEET_ID, fetch_ringostat, last9, prod_unique
from ea_sales_orders_check import load as load_crm
from ea_sources_dashboard import ADS_CUSTOMER, GA4_PROPERTY, TZ, ga4_session, ga4_src
from gads_stats import GOOGLE_ADS_YAML

DEFAULT_SHEET_ID = "1IoSAix2R2I1hIXxwvpZqdb2Y1FCf6Hl1tOls57KB20o"  # «EkspertAgro — по источникам (дашборд)», Drive пользователя
CLIENT_LISTS = r"d:\GitHub\work-rb\Клиенты\EkspertAgro\Статистика\client_dashboard_sales_lists_2026-10-01_2026-10-20.csv"
MODE_CLIENT, MODE_OUR = "Как у клиента", "Наш (первое касание)"
SERIAL0 = dt.date(1899, 12, 30)


def ser(d):
    return (pd.Timestamp(d).date() - SERIAL0).days


# ------------------------------------------------------------------ данные по дням
def ads_daily(d0, d1):
    cl = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    q = f"SELECT segments.date, metrics.cost_micros, metrics.clicks, metrics.impressions FROM customer WHERE segments.date BETWEEN '{d0}' AND '{d1}'"
    rows = {}
    for x in cl.get_service("GoogleAdsService").search(customer_id=ADS_CUSTOMER, query=q):
        rows[x.segments.date] = (x.metrics.cost_micros / 1e6, x.metrics.clicks, x.metrics.impressions)
    return rows


def fb_daily(d0, d1):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/bigquery"])
    c = bigquery.Client(project="redbird-196813", credentials=creds)
    q = (f"SELECT date, SUM(spend) s, SUM(clicks) c, SUM(impressions) i FROM `redbird-196813.adwhite.fb_stats_ekspertagro` "
         f"WHERE date BETWEEN '{d0}' AND '{d1}' GROUP BY date")
    return {str(r.date)[:10]: (float(r.s or 0), int(r.c or 0), int(r.i or 0)) for r in c.query(q).result()}


def ga4_report(s, d0, d1, dims, metrics, event):
    body = {"dateRanges": [{"startDate": d0, "endDate": d1}], "dimensions": [{"name": d} for d in dims],
            "metrics": [{"name": m} for m in metrics], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": event}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=180)
    r.raise_for_status()
    return [[v["value"] for v in x["dimensionValues"]] + [int(float(v["value"])) for v in x["metricValues"]] for x in r.json().get("rows", [])]


def build_daily(d0, d1, ringo, s):
    ads, fb = ads_daily(d0, d1), fb_daily(d0, d1)
    forms = {}
    for d, sm, n in ga4_report(s, d0, d1, ["date", "sessionSourceMedium"], ["sessions"], "form_submit"):
        k = (f"{d[:4]}-{d[4:6]}-{d[6:]}", ga4_src(sm))
        forms[k] = forms.get(k, 0) + n
    r = ringo.copy()
    r["day"] = r["ts"].dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")
    r = r[(r["day"] >= d0) & (r["day"] <= d1)]
    first = r[r["first_ever"]].groupby(["day", "category"]).size().to_dict()
    r60 = r[r["prod_unique"]].copy()
    r60["cat"] = r60["client"].map(lambda c: "Facebook" if c == "ФБ" else "Google Ads")
    sixty = r60.groupby(["day", "cat"]).size().to_dict()
    rows = []
    for d in pd.date_range(d0, d1):
        k = d.strftime("%Y-%m-%d")
        for src in ("Google Ads", "Facebook", "Нет метки"):
            a = ads.get(k) if src == "Google Ads" else fb.get(k) if src == "Facebook" else None
            rows.append([ser(d), src, round(a[0], 2) if a else None, a[1] if a else None, a[2] if a else None,
                         first.get((k, src), 0) if src != "Нет метки" else 0, sixty.get((k, src), 0) if src != "Нет метки" else 0,
                         forms.get((k, src), 0)])
    return rows


# ------------------------------------------------------------------ заказы и первое касание
def build_orders(df, ringo, gm):
    """Одна строка на заказ с датой продажи + заказы из списков клиента, которых нет в таблице (Allegro)."""
    df = df.copy()
    df["p9"] = df["phone"].map(last9)
    o = df[df["order"] != ""].sort_values("ts")
    g = o.groupby("order")
    od = pd.DataFrame({"first_type": g["type"].first(), "first_src": g["src"].first(), "camp": g["utm_campaign"].first(),
                       "created": g["ts"].min(), "sale": g["sale_date_dt"].max(), "cancel": g["cancel_date_dt"].max(),
                       "p9": g["p9"].first()}).reset_index()
    od = od[od["sale"].notna()].copy()
    od["key"] = od["order"].str[:8]
    L = pd.read_csv(CLIENT_LISTS, dtype=str)
    L["key"] = L["заказ"].str[:8]
    fact = dict(zip(L["key"], L["метка_клиента"]))
    touches_t = df[(df["p9"] != "") & (df["src"] != "Телефон")][["p9", "ts", "src", "type"]].rename(columns={"src": "s"})
    rg = ringo[ringo["category"].isin(["Google Ads", "Facebook", "No Source"])][["p9", "ts", "category"]].copy()
    rg["s"] = rg["category"].replace({"No Source": "Нет метки"})
    rg["type"] = "звонок Ringostat"
    allt = pd.concat([touches_t, rg[["p9", "ts", "s", "type"]]]).sort_values("ts")
    by_phone = {p: x for p, x in allt.groupby("p9")}
    rows = []
    for _, r in od.iterrows():
        t = by_phone.get(r["p9"])
        first_s, how = "Не определено", "нет данных"
        touch_ts = None
        if t is not None:
            t = t[t["ts"] <= r["created"] + pd.Timedelta(minutes=1)]
        if t is not None and len(t):
            e = t.iloc[0]
            touch_ts = e["ts"]
            first_s, how = e["s"], ("таблица" if e["type"] != "звонок Ringostat" else "Ringostat до заказа")
            if first_s == "Нет метки" and e["type"] == "форма":
                near = gm[(gm["ts"] - e["ts"]).abs() <= pd.Timedelta(minutes=3)]
                if len(near):
                    b = near.iloc[(near["ts"] - e["ts"]).abs().argsort().iloc[0]]["src"]
                    first_s, how = b, "GA4 по минуте" + ("" if b != "Нет метки" else " (прямой заход)")
                else:
                    first_s, how = "Не определено", "форма без метки, в GA4 нет"
        rule = "Телефон" if r["first_type"] == "звонок" else r["first_src"]
        label, lsrc = (fact[r["key"]], "список клиента") if r["key"] in fact else (rule, "правило")
        active = 1 if (pd.isna(r["cancel"]) or r["sale"] > r["cancel"]) else 0
        rows.append([r["key"], ser(r["sale"].tz_convert(None)), active, r["first_type"], r["first_src"], label, lsrc, first_s, how,
                     r["p9"], r["camp"].replace("+", " ") if isinstance(r["camp"], str) else "",
                     ser(r["cancel"].tz_convert(None)) if pd.notna(r["cancel"]) else None,
                     min(ser(r["created"].tz_convert(TZ)), ser(r["sale"].tz_convert(None))),  # не позже даты продажи
                     min(ser((touch_ts if touch_ts is not None else r["created"]).tz_convert(TZ)), ser(r["sale"].tz_convert(None)))])
    have = {x[0] for x in rows}
    for _, r in L[~L["key"].isin(have)].iterrows():  # заказы из списков клиента, которых нет в таблице (маркетплейсы)
        rows.append([r["key"], ser(r["дата_utc"][:10]), 1, "вне таблицы", r["площадка"], r["метка_клиента"], "список клиента",
                     "Вне таблицы", "площадка " + r["площадка"], last9(r["телефон"]), "", None,
                     ser(r["дата_utc"][:10]), ser(r["дата_utc"][:10])])
    return sorted(rows, key=lambda x: x[1])


# ------------------------------------------------------------------ листы и формулы
def sheet_requests_and_values(n_daily, n_orders):
    D = f"Данные!$A$2:$A${n_daily + 1}"
    def dsum(col, src, extra=""):
        return f"SUMIFS(Данные!${col}$2:${col}${n_daily + 1},Данные!$B$2:$B${n_daily + 1},{src},Данные!$A$2:$A${n_daily + 1},\">=\"&$B$2,Данные!$A$2:$A${n_daily + 1},\"<=\"&$B$3)"
    O = n_orders + 1
    def sales(src):
        DR = f"IF($B$4=\"{MODE_CLIENT}\",Заказы!$M$2:$M${O},Заказы!$N$2:$N${O})"  # дата для периода: клиент — создание заказа, наш — первое обращение
        per = f"{DR},\">=\"&$B$2,{DR},\"<=\"&$B$3,Заказы!$C$2:$C${O},1"
        return (f"IF($B$4=\"{MODE_CLIENT}\",COUNTIFS(Заказы!$F$2:$F${O},{src},{per}),COUNTIFS(Заказы!$H$2:$H${O},{src},{per}))")
    head = ["Источник", "Цена €", "Клики", "Показы", "Цена клика €", "CTR %", "Конверсии", "% конверсии", "Цена заявки €", "Звонки",
            "Звонки, правило 60 дн", "Продажи", "% продажи", "Цена продажи €"]
    srcs = ["Google Ads", "Facebook", "Нет метки", "Телефон", "Не определено", "Вне таблицы"]
    dash = [["EkspertAgro — по источникам"], ["Начало периода", ser("2026-10-01")], ["Конец периода", ser("2026-10-20")],
            ["Режим", MODE_CLIENT], ["Курс, zł за 1 €", 4.382], [], head]
    for i, s in enumerate(srcs):
        r = 8 + i
        ads = s in ("Google Ads", "Facebook")
        calls = s in ("Google Ads", "Facebook")
        dash.append([
            s,
            f"=IFERROR({dsum('C', f'$A{r}')}/$B$5,\"\")" if ads else "",
            f"={dsum('D', f'$A{r}')}" if ads else "",
            f"={dsum('E', f'$A{r}')}" if ads else "",
            f"=IFERROR(B{r}/C{r},\"\")" if ads else "",
            f"=IFERROR(C{r}/D{r},\"\")" if ads else "",
            f"=J{r}+{dsum('H', f'$A{r}')}" if s in ("Google Ads", "Facebook", "Нет метки") else "",
            f"=IFERROR(G{r}/C{r},\"\")" if ads else "",
            f"=IFERROR(B{r}/G{r},\"\")" if ads else "",
            f"={dsum('F', f'$A{r}')}" if calls else "",
            f"={dsum('G', f'$A{r}')}" if calls else "",
            f"={sales(f'$A{r}')}",
            f"=IFERROR(L{r}/G{r},\"\")" if s in ("Google Ads", "Facebook", "Нет метки") else "",
            f"=IFERROR(B{r}/L{r},\"\")" if ads else ""])
    t = 8 + len(srcs)
    dash.append(["Итого", f"=B8+B9", f"=C8+C9", f"=D8+D9", f"=IFERROR(B{t}/C{t},\"\")", f"=IFERROR(C{t}/D{t},\"\")",
                 f"=SUM(G8:G{t - 1})", f"=IFERROR(G{t}/C{t},\"\")", f"=IFERROR(B{t}/G{t},\"\")", f"=SUM(J8:J{t - 1})",
                 f"=SUM(K8:K{t - 1})", f"=SUM(L8:L{t - 1})", f"=IFERROR(L{t}/G{t},\"\")", f"=IFERROR(B{t}/L{t},\"\")"])
    dash += [[], ["Как читать. Режим «Как у клиента»: звонки — первый звонок номера за всю историю, формы — сеансы GA4, продажи — по метке заказа"
                  " в CRM (из списков клиента, а где их нет — по правилу «звонок → Телефон, форма → её источник»)."],
             ["Режим «Наш»: продажи — по ПЕРВОМУ КАСАНИЮ клиента (самое раннее обращение номера: звонок или форма); форма без метки определяется"
              " по Google Analytics (событие в ту же минуту). Подробности — листы «Матрица» и «Пояснения»."],
             ["«Клики» у клиента в строке «Нет метки» (809) не воспроизводятся, поэтому наши «Итого» по кликам ниже на эту величину."],
             ["К какому периоду относится продажа: в режиме «Как у клиента» — по дате создания заказа (так делает клиент: подтверждено на списках ProfiMet и EkspertAgro), в режиме «Наш» — по дате ПЕРВОГО ОБРАЩЕНИЯ человека (звонок или форма). Продажа, у которой первое обращение раньше начала периода, в период не попадает."]]
    mat = [["Из чего сложились продажи за выбранный период (активные продажи): метка клиента (строки) × наше первое касание (столбцы)"], [],
           ["Метка клиента \\ первое касание", "Google Ads", "Facebook", "Нет метки", "Не определено", "Вне таблицы", "Всего"]]
    DRm = f"IF(Дашборд!$B$4=\"{MODE_CLIENT}\",Заказы!$M$2:$M${O},Заказы!$N$2:$N${O})"
    per = f"{DRm},\">=\"&Дашборд!$B$2,{DRm},\"<=\"&Дашборд!$B$3,Заказы!$C$2:$C${O},1"
    for i, lab in enumerate(["Google Ads", "Facebook", "Нет метки", "Телефон"]):
        r = 4 + i
        mat.append([lab] + [f"=COUNTIFS(Заказы!$F$2:$F${O},$A{r},Заказы!$H$2:$H${O},{c}${3},{per})" for c in "BCDEF"] + [f"=SUM(B{r}:F{r})"])
    mat.append(["Всего"] + [f"=SUM({c}4:{c}7)" for c in "BCDEFG"])
    mat += [[], ["Как определено первое касание (активные продажи периода)", "Заказов"]]
    for i, h in enumerate(["таблица", "Ringostat до заказа", "GA4 по минуте", "GA4 по минуте (прямой заход)", "форма без метки, в GA4 нет", "нет данных"]):
        mat.append([h, f"=COUNTIFS(Заказы!$I$2:$I${O},A{11 + i},{per})"])
    mat.append(["площадка (вне таблицы)", f"=COUNTIFS(Заказы!$I$2:$I${O},\"площадка*\",{per})"])
    expl = [["Определения"], [],
            ["Звонки (как у клиента)", "Первый звонок номера за ВСЮ историю Ringostat (единое множество по отслеживаемым источникам; то же, что флаг unique_call). Проверено: 31 Google и 22 Facebook за 01–20.10 = цифры клиента."],
            ["Звонки, правило 60 дн", "Боевое правило нашей функции ringostat_ekspertagro: пара (клиент ФБ/Мерчант/Теплицы, номер), окно 60 дней от последнего засчитанного. С 21.10 кампания «test» отсекается только при точном совпадении названия."],
            ["Формы", "Сеансы GA4 с событием form_submit по источнику сеанса (google / cpc → Google Ads, facebook → Facebook, остальное → Нет метки). События в GA4 дублируются, считаются сеансы. Проверено на 01–20.10 (25 / 22 / 2)."],
            ["Конверсии", "Звонки + формы, без дедупликации (в GA4 нет телефонов)."],
            ["Продажи", "Заказы таблицы клиента «Данные по продажам» (лист Ekspertagro.pl) с датой в периоде: в режиме «Как у клиента» — дата создания заказа, в режиме «Наш» — дата первого обращения (самое раннее обращение номера до заказа). Продажа действует, если нет отмены или продажа позже отмены; дата продажи в расчёте периода не используется (колонка B листа «Заказы» только справочная). Заказы маркетплейсов из списков клиента добавлены отдельными строками."],
            ["Метка клиента", "Поле заказа в CRM. Где есть списки клиента (01–20.10) — оттуда; иначе правило: заказ из звонка (его создал менеджер) → «Телефон», заказ с сайта (создал скрипт) → источник по UTM, без UTM → «Нет метки». На 35 заказах 01–20.10 верно для 31: менеджеры поставили «Телефон» в 12 из 15 случаев (в 3 выбрали источник вручную), скрипт — по UTM в 18 из 20 (2 исключения: заказ Allegro и форма без UTM с меткой Facebook)."],
            ["Первое касание", "Самое раннее обращение номера до создания заказа: звонок (таблица или Ringostat) или форма. Форма без метки опознаётся по GA4 в ту же минуту (±3 мин); не нашлось — «Не определено»."],
            ["Цена", "Google Ads (весь аккаунт, API) и Facebook (BigQuery fb_stats_ekspertagro) в злотых, делится на курс B5 (≈ 4,382 — как у клиента)."],
            ["Ограничения", "Метки заказов вне 01–20.10 восстановлены правилом, не из CRM. Первое обращение берётся из всей истории номера (таблица клиента с 01.12.2025 и Ringostat), поэтому покупатель, обращавшийся давно, попадает в тот период, когда обратился впервые. Дата продажи в таблице — дата, когда заказ впервые стал продажей (если позже статус сняли, заказ может остаться продажей в нашем подсчёте). Данные обновляются запуском ea_sources_dashboard_sheet.py."]]
    orders_head = ["Заказ", "Дата продажи", "Активна (1/0)", "Способ создания", "Источник первой строки (таблица)", "Метка клиента", "Откуда метка",
                   "Первое касание (наше)", "Как определено", "Телефон (9 цифр)", "Кампания (utm)", "Дата отмены",
                   "Дата создания заказа", "Дата первого обращения"]
    data_head = ["Дата", "Источник", "Цена, zł", "Клики", "Показы", "Звонки (вся история)", "Звонки (правило 60 дн)", "Формы (сеансы GA4)"]
    return dash, mat, expl, orders_head, data_head


def write_all(sheet_id, daily, orders, rebuild):
    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    meta = s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in meta["sheets"]}
    need = ["Дашборд", "Матрица", "Данные", "Заказы", "Пояснения"]
    # формулы пишутся при en_US (запятые-разделители, иначе #ERROR!), русская локаль возвращается в конце
    reqs = [{"updateSpreadsheetProperties": {"properties": {"locale": "en_US", "timeZone": "Europe/Warsaw"}, "fields": "locale,timeZone"}}]
    for i, n in enumerate(need):
        if n not in ids:
            reqs.append({"addSheet": {"properties": {"title": n, "index": i}}})
    if reqs:
        s.post(base + ":batchUpdate", json={"requests": reqs}, timeout=60).raise_for_status()
        meta = s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()
        ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in meta["sheets"]}
    if "Лист1" in ids and "Sheet1" not in ids:
        s.post(base + ":batchUpdate", json={"requests": [{"deleteSheet": {"sheetId": ids["Лист1"]}}]}, timeout=60)
    dash, mat, expl, oh, dh = sheet_requests_and_values(len(daily), len(orders))

    def clean(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return v.item() if hasattr(v, "item") else v
    def put(name, rng, rows):
        rows = [[clean(x) for x in r] for r in rows]
        json.dumps(rows)  # упадёт на NaN до очистки листа
        return rows
    data_rows = put("Данные", "A1", [dh] + daily)
    order_rows = put("Заказы", "A1", [oh] + orders)
    for name in ("Данные", "Заказы"):
        s.post(base + f"/values/{name}!A1:Z20000:clear", json={}, timeout=60).raise_for_status()
    s.put(base + "/values/Данные!A1?valueInputOption=USER_ENTERED", json={"values": data_rows}, timeout=180).raise_for_status()
    s.put(base + "/values/Заказы!A1?valueInputOption=USER_ENTERED", json={"values": order_rows}, timeout=180).raise_for_status()
    if rebuild:
        for name, rows in (("Дашборд", dash), ("Матрица", mat), ("Пояснения", expl)):
            s.post(base + f"/values/{name}!A1:Z200:clear", json={}, timeout=60).raise_for_status()
            s.put(base + f"/values/{name}!A1?valueInputOption=USER_ENTERED", json={"values": rows}, timeout=60).raise_for_status()
        d = ids["Дашборд"]
        fmt = lambda sh, r0, r1, c0, c1, pat, typ="NUMBER": {"repeatCell": {"range": {"sheetId": sh, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1},
                            "cell": {"userEnteredFormat": {"numberFormat": {"type": typ, "pattern": pat}}}, "fields": "userEnteredFormat.numberFormat"}}
        bold = lambda sh, r0, r1, c0, c1: {"repeatCell": {"range": {"sheetId": sh, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}}
        r2 = [{"setDataValidation": {"range": {"sheetId": d, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 1, "endColumnIndex": 2},
                                    "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": MODE_CLIENT}, {"userEnteredValue": MODE_OUR}]},
                                             "strict": True, "showCustomUi": True, "inputMessage": "Как у клиента или наш (по первому касанию)."}}},
              fmt(d, 1, 3, 1, 2, "dd.mm.yyyy", "DATE"), fmt(d, 7, 14, 1, 2, "#,##0.00"), fmt(d, 7, 14, 4, 5, "0.00"), fmt(d, 7, 14, 5, 6, "0.00%"),
              fmt(d, 7, 14, 7, 8, "0.00%"), fmt(d, 7, 14, 8, 9, "#,##0.00"), fmt(d, 7, 14, 12, 13, "0.0%"), fmt(d, 7, 14, 13, 14, "#,##0.00"),
              bold(d, 0, 1, 0, 1), bold(d, 6, 7, 0, 14), bold(d, 13, 14, 0, 14), bold(ids["Матрица"], 2, 3, 0, 7), bold(ids["Матрица"], 7, 8, 0, 7),
              fmt(ids["Данные"], 1, len(daily) + 1, 0, 1, "dd.mm.yyyy", "DATE"), fmt(ids["Заказы"], 1, len(orders) + 1, 1, 2, "dd.mm.yyyy", "DATE"),
              fmt(ids["Заказы"], 1, len(orders) + 1, 11, 14, "dd.mm.yyyy", "DATE"),
              {"updateDimensionProperties": {"range": {"sheetId": d, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 190}, "fields": "pixelSize"}},
              {"updateDimensionProperties": {"range": {"sheetId": ids["Пояснения"], "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2}, "properties": {"pixelSize": 900}, "fields": "pixelSize"}},
              {"updateSheetProperties": {"properties": {"sheetId": ids["Данные"], "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
              {"updateSheetProperties": {"properties": {"sheetId": ids["Заказы"], "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
              {"setBasicFilter": {"filter": {"range": {"sheetId": ids["Заказы"], "startRowIndex": 0, "endRowIndex": len(orders) + 1, "startColumnIndex": 0, "endColumnIndex": 14}}}}]
        s.post(base + ":batchUpdate", json={"requests": r2}, timeout=60).raise_for_status()
    s.post(base + ":batchUpdate", json={"requests": [{"updateSpreadsheetProperties": {"properties": {"locale": "ru_RU", "timeZone": "Europe/Warsaw"},
                                                                                    "fields": "locale,timeZone"}}]}, timeout=60).raise_for_status()
    return len(daily), len(orders)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    ap.add_argument("--from", dest="d0", default="2026-09-01")
    ap.add_argument("--to", dest="d1", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--rebuild", action="store_true", help="пересоздать «Дашборд», «Матрица», «Пояснения» (период и режим сбросятся)")
    a = ap.parse_args()

    ringo = fetch_ringostat("2025-12-01")
    ringo["category"] = cat_of(ringo)
    ringo = ringo.sort_values("ts", kind="mergesort").reset_index(drop=True)
    tr = ringo[ringo["category"] != "Other"]
    seen, fl = set(), {}
    for i, p in zip(tr.index, tr["p9"]):
        fl[i] = p not in seen
        seen.add(p)
    ringo["first_ever"] = pd.Series(fl).reindex(ringo.index).fillna(False).astype(bool)
    ringo = prod_unique(ringo)
    s = ga4_session()
    daily = build_daily(a.d0, a.d1, ringo, s)
    ev = ga4_report(s, a.d0, a.d1, ["dateHourMinute", "sessionSourceMedium"], ["eventCount"], "form_submit")
    gm = pd.DataFrame([[pd.to_datetime(m, format="%Y%m%d%H%M"), ga4_src(sm)] for m, sm, _ in ev], columns=["t", "src"])
    gm["ts"] = gm["t"].dt.tz_localize(TZ).dt.tz_convert("UTC")
    crm = load_crm(CRM_SHEET_ID, "Ekspertagro.pl")
    orders = build_orders(crm, ringo, gm)
    nd, no = write_all(a.sheet_id, daily, orders, a.rebuild)
    print(f"Записано: «Данные» {nd} строк, «Заказы» {no} строк. Таблица: https://docs.google.com/spreadsheets/d/{a.sheet_id}")


if __name__ == "__main__":
    main()
