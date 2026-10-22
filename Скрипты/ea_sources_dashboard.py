#!/usr/bin/env python
# coding: utf-8
"""НАШ дашборд «По источникам» EkspertAgro в том же виде, что клиентский — ТОЛЬКО ЧТЕНИЕ.

Колонки как у клиента: Цена, Клики, Показы, Цена клика, CTR, Конверсии, % конверсии, Цена заявки, Звонки, Продажи,
% продажи, Цена продажи. Определения (расшифрованы по скрину клиента за 01–20.10.2026 и подтверждены на данных):
  Цена / Клики / Показы — Google Ads API (аккаунт целиком) и BigQuery `adwhite.fb_stats_ekspertagro` (Facebook); в таблицах
      злоты, клиент показывает евро: курс `--rate` (по умолчанию 4.382, подобран по его расходу: 4776.70 zł = 1090.07 €).
  Звонки — первый звонок номера за ВСЮ историю Ringostat (единое множество по отслеживаемым источникам; то же, что флаг
      Ringostat `unique_call`), по категории источника звонка.
  Конверсии — звонки + формы; формы — СЕАНСЫ GA4 с событием `form_submit` по источнику сеанса (google / cpc → Google Ads,
      любой facebook → Facebook, остальное → «Нет метки»). Телефонов в GA4 нет, дедупликации форм со звонками нет.
  Продажи — заказы таблицы клиента с «Датой продажи» в периоде, не отменённые (отмена позже продажи снимает заказ;
      отмена раньше продажи — заказ продан снова и считается). Сверено со списками заказов клиента 21.10: из 35 заказов
      клиента 32 совпали с нашими (см. Хронику 21.10), расхождения — Allegro, неотмеченная продажа, 3 лишних у нас.
      Источник продажи — в нашем режиме ПЕРВОЕ КАСАНИЕ (источник первой строки заказа; если это форма «Нет метки» —
      источник по GA4, события form_submit ±3 мин; не нашлось — остаётся «Нет метки»). У клиента источник — метка заказа
      в CRM (форма по UTM, заказ из звонка → «Телефон»); ТАК ЕЁ НЕ ВОСПРОИЗВЕСТИ без списков заказов клиента.
  % продажи = продажи ÷ конверсии; Цена продажи = цена ÷ продажи. Строка «Итого» делит ВЕСЬ расход (Google + Facebook).
Не воспроизводится: «Клики» в строке «Нет метки» у клиента (809) — откуда, неизвестно; они входят в его «Итого» (7130 + 10308 + 809 =
18247), поэтому наш «Итого» по кликам, CTR и цене клика ниже/выше на эту величину.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_sources_dashboard.py [--from 2026-10-01] [--to 2026-10-20] [--rate 4.382] [--csv путь]
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE
from ea_dashboard_reconcile import cat_of
from ea_ringostat_vs_sheet import SHEET_ID, fetch_ringostat, last9
from ea_sales_orders_check import load as load_sheet
from gads_stats import GOOGLE_ADS_YAML

TZ = "Europe/Warsaw"
ADS_CUSTOMER = "8826134558"
GA4_KEY = r"E:/PythonProjects/RedBird/google-cloud-jobs/adwhite/func/ga4_profimet/redbird-196813-ga4.json"  # ga4-analytics (в вики не копировать)
GA4_PROPERTY = "514863743"
SRC = ["Google Ads", "Facebook", "Нет метки"]
# эталон: клиентский дашборд за 01–20.10.2026 (скрин пользователя 21.10)
CLIENT_REF = {"Google Ads": dict(cost=1090.07, clicks=7130, impr=230403, conv=56, calls=31, sales=4),
              "Facebook": dict(cost=645.23, clicks=10308, impr=235245, conv=44, calls=22, sales=9),
              "Нет метки": dict(conv=2, sales=10), "ИТОГО": dict(cost=1735.30, clicks=18247, impr=465648, conv=102, calls=53, sales=35)}


def google_ads(d0, d1):
    cl = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    q = f"SELECT metrics.cost_micros, metrics.clicks, metrics.impressions FROM customer WHERE segments.date BETWEEN '{d0}' AND '{d1}'"
    cost = clicks = impr = 0
    for x in cl.get_service("GoogleAdsService").search(customer_id=ADS_CUSTOMER, query=q):
        cost += x.metrics.cost_micros / 1e6
        clicks += x.metrics.clicks
        impr += x.metrics.impressions
    return dict(cost=cost, clicks=clicks, impr=impr)


def facebook(d0, d1):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/bigquery"])
    c = bigquery.Client(project="redbird-196813", credentials=creds)
    q = (f"SELECT SUM(spend) s, SUM(clicks) c, SUM(impressions) i FROM `redbird-196813.adwhite.fb_stats_ekspertagro` "
         f"WHERE date BETWEEN '{d0}' AND '{d1}'")
    r = list(c.query(q).result())[0]
    return dict(cost=float(r.s or 0), clicks=int(r.c or 0), impr=int(r.i or 0))


def ga4_session():
    return AuthorizedSession(Credentials.from_service_account_file(GA4_KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))


def ga4_src(sm):
    sm = str(sm).lower()
    return "Google Ads" if sm == "google / cpc" else "Facebook" if "facebook" in sm else "Нет метки"


def ga4_forms(s, d0, d1):
    body = {"dateRanges": [{"startDate": d0, "endDate": d1}], "dimensions": [{"name": "sessionSourceMedium"}],
            "metrics": [{"name": "sessions"}], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=120)
    r.raise_for_status()
    out = {k: 0 for k in SRC}
    for x in r.json().get("rows", []):
        out[ga4_src(x["dimensionValues"][0]["value"])] += int(x["metricValues"][0]["value"])
    return out


def ga4_minutes(s, d0, d1):
    body = {"dateRanges": [{"startDate": d0, "endDate": d1}],
            "dimensions": [{"name": "dateHourMinute"}, {"name": "sessionSourceMedium"}], "metrics": [{"name": "eventCount"}],
            "limit": 100000, "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=120)
    r.raise_for_status()
    g = pd.DataFrame([[x["dimensionValues"][0]["value"], ga4_src(x["dimensionValues"][1]["value"])] for x in r.json().get("rows", [])],
                     columns=["m", "src"])
    g["ts"] = pd.to_datetime(g["m"], format="%Y%m%d%H%M").dt.tz_localize(TZ).dt.tz_convert("UTC")
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-10-01")
    ap.add_argument("--to", dest="d1", default="2026-10-20")
    ap.add_argument("--rate", type=float, default=4.382, help="zł за 1 €")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    t0, t1 = pd.Timestamp(a.d0, tz=TZ), pd.Timestamp(a.d1, tz=TZ) + pd.Timedelta(days=1)

    ads = {"Google Ads": google_ads(a.d0, a.d1), "Facebook": facebook(a.d0, a.d1)}
    for v in ads.values():
        v["cost"] = v["cost"] / a.rate

    # звонки: первый звонок номера за всю историю
    ringo = fetch_ringostat("2025-12-01")
    ringo["category"] = cat_of(ringo)
    ringo = ringo.sort_values("ts", kind="mergesort").reset_index(drop=True)
    tracked = ringo[ringo["category"] != "Other"]
    seen, flag = set(), {}
    for i, p in zip(tracked.index, tracked["p9"]):
        flag[i] = p not in seen
        seen.add(p)
    ringo["first_ever"] = pd.Series(flag).reindex(ringo.index).fillna(False).astype(bool)
    w = ringo[(ringo["ts"] >= t0) & (ringo["ts"] < t1) & ringo["first_ever"]]
    calls = {k: int((w["category"] == k).sum()) for k in SRC}

    s = ga4_session()
    forms = ga4_forms(s, a.d0, a.d1)
    gm = ga4_minutes(s, a.d0, a.d1)

    # продажи: первое касание
    df = load_sheet(SHEET_ID, "Ekspertagro.pl")
    o = df[df["order"] != ""].sort_values("ts")
    g = o.groupby("order")
    orders = pd.DataFrame({"created": g["ts"].min(), "first_type": g["type"].first(), "first_src": g["src"].first(),
                           "sale": g["sale_date_dt"].max(), "cancel": g["cancel_date_dt"].max()})
    day = orders["sale"].dt.tz_convert(None).dt.normalize()
    # продажа действует, если отмены нет или продажа позже отмены (заказ отменили и продали снова: 21128488, 2026-10)
    active = orders["cancel"].isna() | (orders["sale"] > orders["cancel"])
    sold = orders[(day >= pd.Timestamp(a.d0)) & (day <= pd.Timestamp(a.d1)) & active].copy()

    def attribute(row):
        src, how = row["first_src"], "таблица"
        if row["first_type"] == "форма" and src == "Нет метки":
            near = gm[(gm["ts"] - row["created"]).abs() <= pd.Timedelta(minutes=3)]
            if len(near):
                best = near.iloc[(near["ts"] - row["created"]).abs().argsort().iloc[0]]
                return best["src"], "GA4 по минуте"
        return (src if src in SRC else "Нет метки"), how

    att = sold.apply(attribute, axis=1, result_type="expand")
    sold["src"], sold["how"] = att[0], att[1]
    sales = {k: int((sold["src"] == k).sum()) for k in SRC}

    rows = []
    for k in SRC:
        c = ads.get(k, {})
        conv = calls[k] + forms[k]
        rows.append({"Источник": k, "Цена €": round(c["cost"], 2) if c else None, "Клики": c.get("clicks"), "Показы": c.get("impr"),
                     "Цена клика €": round(c["cost"] / c["clicks"], 2) if c and c["clicks"] else None,
                     "CTR %": round(100 * c["clicks"] / c["impr"], 2) if c and c["impr"] else None,
                     "Конверсии": conv, "% конв.": round(100 * conv / c["clicks"], 2) if c and c["clicks"] else None,
                     "Цена заявки €": round(c["cost"] / conv, 2) if c and conv else None, "Звонки": calls[k],
                     "Продажи": sales[k], "% продажи": round(100 * sales[k] / conv, 1) if conv else None,
                     "Цена продажи €": round(c["cost"] / sales[k], 2) if c and sales[k] else None})
    tc = sum(v["cost"] for v in ads.values())
    tk, ti = sum(v["clicks"] for v in ads.values()), sum(v["impr"] for v in ads.values())
    tconv, tsales = sum(calls.values()) + sum(forms.values()), sum(sales.values())
    rows.append({"Источник": "ИТОГО", "Цена €": round(tc, 2), "Клики": tk, "Показы": ti, "Цена клика €": round(tc / tk, 2),
                 "CTR %": round(100 * tk / ti, 2), "Конверсии": tconv, "% конв.": round(100 * tconv / tk, 2),
                 "Цена заявки €": round(tc / tconv, 2), "Звонки": sum(calls.values()), "Продажи": tsales,
                 "% продажи": round(100 * tsales / tconv, 1), "Цена продажи €": round(tc / tsales, 2)})
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(f"НАШ дашборд «По источникам», EkspertAgro, {a.d0} … {a.d1}, курс {a.rate} zł/€ (продажи — по ПЕРВОМУ КАСАНИЮ)\n")
    print(out.to_string(index=False))
    print("\nПродажи по способу определения источника:", sold["how"].value_counts().to_dict(),
          "| форм «Нет метки», опознанных GA4 как реклама, остаются отдельно в строке своего источника")
    if (a.d0, a.d1) == ("2026-10-01", "2026-10-20"):
        print("\nСравнение с клиентским дашбордом (скрин 21.10): наше − клиента")
        for k, ref in CLIENT_REF.items():
            r = out[out["Источник"] == k].iloc[0]
            m = {"cost": "Цена €", "clicks": "Клики", "impr": "Показы", "conv": "Конверсии", "calls": "Звонки", "sales": "Продажи"}
            print(f"  {k}: " + "; ".join(f"{lab} {r[lab]} против {ref[f]}" for f, lab in m.items() if f in ref and pd.notna(r[lab])))
    if a.csv:
        out.to_csv(a.csv, index=False, encoding="utf-8-sig")
        print("Сохранено:", a.csv)


if __name__ == "__main__":
    main()
