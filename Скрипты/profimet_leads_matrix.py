#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: ЗАЯВКИ ПО ВСЕМ ПЛАТФОРМАМ в одной матрице — ТОЛЬКО ЧТЕНИЕ (2026-11-05).

Цель: наш дашборд считает заявки так же, как общий дашборд агентства (BigQuery), а каждое расхождение между платформами видно
сразу — по каналу и по дню, — чтобы быстро показать клиенту и оспорить.

Платформы (строки матрицы) и канал (столбцы: Google Ads / Facebook / Google SEO / Нет метки и прочее / Телефон):
  ЗВОНКИ
    Ringostat, все входящие            — API Ringostat, категории Google Ads / Google SEO / Facebook / No Source (без Other)
    Ringostat, боевое правило 60 дн    — копия `ringostat_profimet2/main.py` (`prod_unique`)
    BigQuery (общий дашборд)           — `adwhite.ringostat_calls_profimet2`
    Выгрузка CRM, все звонки           — листы mocnaszklarnia.pl + szklarniaprofimet.pl, type=звонок
    Выгрузка CRM, новые по 60 дн       — обращение новое, если у номера на этом сайте не было засчитанного за 60 дн (лестница)
  ФОРМЫ
    Tilda (реальные)                   — Google-таблица «Tilda_Leads…», без тестов; канал по UTM самой Tilda
    Supabase                           — `profimet_leads` без пачек-мусора; канал по UTM строки
    GA4, сеансы form_submit            — Data API, канал по sessionSourceMedium
    BigQuery (общий дашборд)           — `adwhite.profimet_goals`, цель form_submit (конверсии GA4), канал по Source
    Выгрузка CRM, формы                — type=форма, канал по колонке «Источник»

Использование (из папки Скрипты):
    PYTHONUTF8=1 python profimet_leads_matrix.py [--from 2026-10-01] [--to 2026-11-04] [--cache путь.pkl]
Пишет `Клиенты/ProfiMet/Статистика/leads_matrix_<с>_<по>.csv` (длинный формат: день, платформа, канал, число).
"""
import argparse
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE, client_stats_dir
from forms_funnel_reconcile import CLIENTS, GA4_KEY, W, chan, ga4_minutes, load_supabase, load_tilda
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_season_audit import fetch_ringostat_full, prod_unique

CH = ["Google Ads", "Facebook", "Google SEO", "Нет метки/прочее", "Телефон"]
CRM_SITES = {"mocnaszklarnia.pl", "szklarniaprofimet.pl"}
WINDOW = 60
CALLS = ["Ringostat, все входящие", "Ringostat, боевое правило 60 дн", "BigQuery (общий дашборд)", "Выгрузка CRM, все звонки",
         "Выгрузка CRM, новые по 60 дн"]
FORMS = ["Tilda (реальные)", "Supabase", "GA4, сеансы form_submit", "BigQuery (общий дашборд)", "Выгрузка CRM, формы"]


def bq():
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/bigquery"])
    return bigquery.Client(project="redbird-196813", credentials=creds)


def ch_crm(src):
    return {"Google Ads": "Google Ads", "Facebook": "Facebook", "Google SEO": "Google SEO", "Телефон": "Телефон"}.get(src, "Нет метки/прочее")


def ch_ringo(cat):
    return {"Google Ads": "Google Ads", "Facebook": "Facebook", "Google SEO": "Google SEO", "No Source": "Нет метки/прочее"}.get(cat)


def ch_utm(src, med=""):
    s = str(src).lower()
    if "seomocna" in s or (s.startswith("google") and "organic" in str(med).lower()):
        return "Google SEO"
    c = chan(src, med)
    return c if c in ("Google Ads", "Facebook") else "Нет метки/прочее"


def ch_sm(sm):
    s = str(sm).lower()
    if s == "google / cpc":
        return "Google Ads"
    if "facebook" in s:
        return "Facebook"
    if "organic" in s:
        return "Google SEO"
    return "Нет метки/прочее"


def ch_bq(src):
    return {"GAds": "Google Ads", "Google Ads": "Google Ads", "Facebook": "Facebook", "Google SEO": "Google SEO"}.get(src, "Нет метки/прочее")


def new_by_60(crm):
    """Флаг «новое по 60 дн» (лестница: окно от последнего засчитанного) отдельно по каждому сайту выгрузки."""
    crm = crm.sort_values("ts", kind="mergesort").copy()
    crm["day"] = crm["ts"].dt.tz_convert(W).dt.date
    flags = pd.Series(False, index=crm.index)
    for _, g in crm[crm["p9"] != ""].groupby("site"):
        last = {}
        for i, p, d in zip(g.index, g["p9"], g["day"]):
            prev = last.get(p)
            if prev is None or (d - prev).days > WINDOW:
                last[p] = d
                flags[i] = True
    crm["new"] = flags
    return crm


GA4_SEO = "504222847"  # ресурс сайта szklarniaprofimet.pl (из таблицы «GA4» агентства; те же формы идут в BigQuery как «ProfiMet SEO»)


def ga4_sessions(frm, to, prop=None):
    s = AuthorizedSession(Credentials.from_service_account_file(GA4_KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))
    body = {"dateRanges": [{"startDate": str(frm), "endDate": str(to)}], "dimensions": [{"name": "date"}, {"name": "sessionSourceMedium"}],
            "metrics": [{"name": "sessions"}], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{prop or CLIENTS['ProfiMet']['ga4']}:runReport", json=body, timeout=120)
    r.raise_for_status()
    rows = [{"day": pd.Timestamp(x["dimensionValues"][0]["value"]).date(), "channel": ch_sm(x["dimensionValues"][1]["value"]),
             "sm": x["dimensionValues"][1]["value"], "n": int(float(x["metricValues"][0]["value"]))} for x in r.json().get("rows", [])
            if not any(k in x["dimensionValues"][1]["value"].lower() for k in ("test", "tagassistant"))]
    return pd.DataFrame(rows, columns=["day", "channel", "sm", "n"])


def long_rows(kind, platform, days, channels):
    return pd.DataFrame({"kind": kind, "platform": platform, "day": list(days), "channel": list(channels), "n": 1})


def collect(d0, d1, cache=None):
    d0d, d1d = pd.Timestamp(d0).date(), pd.Timestamp(d1).date()
    lo = pd.Timestamp(d0, tz=W).tz_convert("UTC")
    hi = (pd.Timestamp(d1, tz=W) + pd.Timedelta(days=1)).tz_convert("UTC")
    if cache and Path(cache).exists():
        sheet, ringo = pickle.load(open(cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if cache:
            pickle.dump((sheet, ringo), open(cache, "wb"))
    parts = []

    def inrange(d):
        return d0d <= d <= d1d

    # --- ЗВОНКИ ---
    r = ringo[(ringo["call_type"] == "in") & ringo["category"].isin(["Google Ads", "Google SEO", "Facebook", "No Source"])].copy()
    r["day"] = r["ts"].dt.tz_convert(W).dt.date
    r = r[r["day"].map(inrange)]
    parts.append(long_rows("Звонки", CALLS[0], r["day"], r["category"].map(ch_ringo)))
    pu = prod_unique(ringo, count_other=False, date_to=d1d)
    pu = pu[pu["date"].map(inrange)]
    parts.append(long_rows("Звонки", CALLS[1], pu["date"], pu["category"].map(ch_ringo)))
    c = bq()
    q = (f"SELECT Date, Source, SUM(Calls) n FROM `redbird-196813.adwhite.ringostat_calls_profimet2` "
         f"WHERE Date BETWEEN '{d0}' AND '{d1}' GROUP BY 1,2")
    b = pd.DataFrame([dict(x.items()) for x in c.query(q).result()], columns=["Date", "Source", "n"])
    b["day"] = pd.to_datetime(b["Date"]).dt.date
    b["channel"] = b["Source"].map(ch_bq)
    b = b.rename(columns={"n": "n"})[["day", "channel", "n"]]
    b.insert(0, "platform", CALLS[2]); b.insert(0, "kind", "Звонки")
    parts.append(b)
    crm = sheet[sheet["site"].isin(CRM_SITES) & sheet["type"].isin(["звонок", "форма"]) & (sheet["ts"] >= lo) & (sheet["ts"] < hi)].copy()
    crm = new_by_60(sheet[sheet["site"].isin(CRM_SITES) & sheet["type"].isin(["звонок", "форма"])]).loc[lambda x: x.index.isin(crm.index)]
    crm["channel"] = crm["src"].map(ch_crm)
    cc = crm[crm["type"] == "звонок"]
    parts.append(long_rows("Звонки", CALLS[3], cc["day"], cc["channel"]))
    cn = cc[cc["new"]]
    parts.append(long_rows("Звонки", CALLS[4], cn["day"], cn["channel"]))

    # --- ФОРМЫ ---
    cfg = CLIENTS["ProfiMet"]
    t = load_tilda(cfg)
    sb = load_supabase(cfg, d0, d1)
    m = t[~t["test"] & (t["p9"] != "")].merge(sb[sb["p9"] != ""][["p9", "ts"]].drop_duplicates("p9"), on="p9")
    off_h = round(((m["sent"] - m["ts"].dt.tz_localize(None)).dt.total_seconds() / 3600).median()) if len(m) else 0
    t["ts"] = (t["sent"] - pd.Timedelta(hours=off_h)).dt.tz_localize("UTC")
    t = t[(t["ts"] >= lo) & (t["ts"] < hi) & ~t["test"]]
    t_day = t["ts"].dt.tz_convert(W).dt.date
    parts.append(long_rows("Формы", FORMS[0], t_day, [ch_utm(s, mm) if s else "Нет метки/прочее" for s, mm in zip(t["t_src"], t["t_med"])]))
    sbp = sb[(sb["ts"] >= lo) & (sb["ts"] < hi) & ~sb["burst"]]
    parts.append(long_rows("Формы", FORMS[1], sbp["ts"].dt.tz_convert(W).dt.date,
                           [ch_utm(s, mm) if s else "Нет метки/прочее" for s, mm in zip(sbp["utm_source"], sbp["utm_medium"])]))
    ga = ga4_sessions(d0, d1)
    try:
        gs = ga4_sessions(d0, d1, GA4_SEO)
        gs = gs[gs["channel"] == "Google SEO"]
    except Exception as e:  # нет доступа к ресурсу SEO
        print("GA4 SEO недоступен:", str(e)[:120], file=sys.stderr)
        gs = ga.iloc[0:0]
    extra_sm = ga.groupby(["channel", "sm"])["n"].sum().sort_values(ascending=False)
    ga = pd.concat([ga, gs], ignore_index=True)
    ga4 = ga.groupby(["day", "channel"], as_index=False)["n"].sum()
    ga4.insert(0, "platform", FORMS[2]); ga4.insert(0, "kind", "Формы")
    parts.append(ga4)
    q = (f"SELECT Date, Client, Source, SUM(Goal_visits) n FROM `redbird-196813.adwhite.profimet_goals` "
         f"WHERE Date BETWEEN '{d0}' AND '{d1}' AND Goal_name='form_submit' GROUP BY 1,2,3")
    g = pd.DataFrame([dict(x.items()) for x in c.query(q).result()], columns=["Date", "Client", "Source", "n"])
    g["day"] = pd.to_datetime(g["Date"]).dt.date
    g["channel"] = g["Source"].map(ch_bq)
    g = g.groupby(["day", "channel"], as_index=False)["n"].sum()
    g.insert(0, "platform", FORMS[3]); g.insert(0, "kind", "Формы")
    parts.append(g)
    cf = crm[crm["type"] == "форма"]
    parts.append(long_rows("Формы", FORMS[4], cf["day"], cf["channel"]))
    extra = dict(tilda_offset=off_h, tilda_last=t_day.max() if len(t_day) else None, ga_sm=extra_sm,
                 sb_last=sbp["ts"].dt.tz_convert(W).dt.date.max() if len(sbp) else None)
    return pd.concat(parts, ignore_index=True), extra


def show(df, kind, order):
    d = df[df["kind"] == kind].groupby(["platform", "channel"])["n"].sum().unstack(fill_value=0).reindex(order).fillna(0).astype(int)
    d = d.reindex(columns=[c for c in CH if c in d.columns])
    d["Итого"] = d.sum(axis=1)
    print(d.to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-10-01")
    ap.add_argument("--to", dest="d1", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--cache", default=None)
    ap.add_argument("--by-day", action="store_true", help="построчно по дням")
    a = ap.parse_args()
    df, extra = collect(a.d0, a.d1, a.cache)
    df = df.groupby(["kind", "platform", "day", "channel"], as_index=False)["n"].sum()
    out = client_stats_dir("ProfiMet") / f"leads_matrix_{a.d0}_{a.d1}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"=== ProfiMet: заявки по платформам {a.d0} … {a.d1} (Tilda: сдвиг времени UTC{extra['tilda_offset']:+d}) ===")
    print(f"Последняя заявка в Tilda: {extra['tilda_last']}; в Supabase: {extra['sb_last']}; период до {a.d1}")
    print("\n--- ЗВОНКИ ---"); show(df, "Звонки", CALLS)
    print("\n--- ФОРМЫ ---"); show(df, "Формы", FORMS)
    print("\nGA4 (сайт mocnaszklarnia.pl), сеансы form_submit по источнику сеанса:")
    print(extra["ga_sm"].to_string())
    if a.by_day:
        for kind, order in (("Звонки", CALLS), ("Формы", FORMS)):
            p = df[df["kind"] == kind].groupby(["day", "platform"])["n"].sum().unstack(fill_value=0).reindex(columns=order).fillna(0).astype(int)
            print(f"\n--- {kind.upper()} ПО ДНЯМ (все каналы) ---"); print(p.to_string())
    print("\nCSV:", out)


if __name__ == "__main__":
    main()
