#!/usr/bin/env python
# coding: utf-8
"""EkspertAgro: формы в GA4 против форм в CRM (таблица клиента) по месяцам и источникам — ТОЛЬКО ЧТЕНИЕ.

Вопрос: доходят ли все отправки форм до CRM и распределяются ли по источникам одинаково (в GA4 — сеансы и события
`form_submit` по источнику СЕАНСА; в CRM — строки-формы листа `Ekspertagro.pl`, каждая = заказ, созданный скриптом сайта).
Для каждого месяца: GA4 сеансы / события, CRM формы, их источник «как в CRM» против GA4 по минуте (±3 мин, одно событие на
форму), сколько форм CRM не нашлось в GA4 и сколько событий GA4 не нашлось в CRM; плюс события `crm_purchase` GA4 по источнику.
Использование (из папки Скрипты): PYTHONUTF8=1 python ea_forms_ga4_vs_crm.py [--from 2026-06-01] [--to 2026-10-20]
"""
import argparse

import pandas as pd

from ea_sales_orders_check import load as load_sheet
from ea_sources_dashboard import GA4_PROPERTY, SHEET_ID, TZ, ga4_session, ga4_src


def ga4_report(s, d0, d1, dims, metrics, event):
    body = {"dateRanges": [{"startDate": d0, "endDate": d1}], "dimensions": [{"name": d} for d in dims],
            "metrics": [{"name": m} for m in metrics], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": event}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=180)
    r.raise_for_status()
    rows = [[v["value"] for v in x["dimensionValues"]] + [int(float(v["value"])) for v in x["metricValues"]] for x in r.json().get("rows", [])]
    return pd.DataFrame(rows, columns=dims + metrics)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-06-01")
    ap.add_argument("--to", dest="d1", default="2026-10-20")
    a = ap.parse_args()
    s = ga4_session()

    ses = ga4_report(s, a.d0, a.d1, ["yearMonth", "sessionSourceMedium"], ["sessions", "eventCount"], "form_submit")
    ses["src"] = ses["sessionSourceMedium"].map(ga4_src)
    g = ses.groupby(["yearMonth", "src"])[["sessions", "eventCount"]].sum().unstack(fill_value=0)
    print("== GA4 form_submit: сеансы / события по месяцам и источнику сеанса ==")
    print(g.to_string())

    pur = ga4_report(s, a.d0, a.d1, ["yearMonth", "sessionSourceMedium"], ["eventCount"], "crm_purchase")
    pur["src"] = pur["sessionSourceMedium"].map(ga4_src)
    print("\n== GA4 crm_purchase: события по месяцам и источнику сеанса ==")
    print(pur.groupby(["yearMonth", "src"])["eventCount"].sum().unstack(fill_value=0).to_string())

    ev = ga4_report(s, a.d0, a.d1, ["dateHourMinute", "sessionSourceMedium"], ["eventCount"], "form_submit")
    ev["ts"] = pd.to_datetime(ev["dateHourMinute"], format="%Y%m%d%H%M").dt.tz_localize(TZ).dt.tz_convert("UTC")
    ev["src"] = ev["sessionSourceMedium"].map(ga4_src)
    ev["month"] = ev["ts"].dt.tz_convert(TZ).dt.strftime("%Y-%m")

    df = load_sheet(SHEET_ID, "Ekspertagro.pl")
    f = df[(df["type"] == "форма") & (df["ts"] >= pd.Timestamp(a.d0, tz=TZ)) & (df["ts"] < pd.Timestamp(a.d1, tz=TZ) + pd.Timedelta(days=1))].copy()
    f["month"] = f["ts"].dt.tz_convert(TZ).dt.strftime("%Y-%m")
    print("\n== CRM: строки-формы по месяцам и источнику «как в CRM» ==")
    print(pd.crosstab(f["month"], f["src"], margins=True).to_string())

    # сопоставление: каждой форме CRM — ближайшее ещё не занятое событие-минута GA4 (±3 мин)
    used, rows = set(), []
    ev_rows = ev.sort_values("ts")
    for i, r in f.sort_values("ts").iterrows():
        near = ev_rows[((ev_rows["ts"] - r["ts"]).abs() <= pd.Timedelta(minutes=3)) & ~ev_rows.index.isin(used)]
        if len(near):
            j = (near["ts"] - r["ts"]).abs().idxmin()
            used.add(j)
            rows.append((r["month"], r["src"], ev.loc[j, "src"]))
        else:
            rows.append((r["month"], r["src"], "нет в GA4"))
    m = pd.DataFrame(rows, columns=["month", "crm_src", "ga4_src"])
    print("\n== Формы CRM: источник в CRM × источник в GA4 (по минуте) ==")
    for mon, x in m.groupby("month"):
        print(f"\n{mon}: форм CRM {len(x)}, найдено в GA4 {int((x['ga4_src'] != 'нет в GA4').sum())}")
        print(pd.crosstab(x["crm_src"], x["ga4_src"], margins=True).to_string())
    # события GA4 (минуты с событиями), которым не нашлось формы CRM
    free = ev[~ev.index.isin(used)]
    print("\n== События GA4 (минуты), которым не нашлось формы CRM, по месяцам и источнику ==")
    print(free.groupby(["month", "src"])["eventCount"].sum().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
