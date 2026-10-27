#!/usr/bin/env python
# coding: utf-8
"""Заявки → продажи и цена заявки / продажи Google Ads EkspertAgro — ТОЛЬКО ЧТЕНИЕ (Google Ads API + выгрузка CRM клиента).

Заявка (лид) — уникальный номер телефона, ПЕРВОЕ касание которого за всю историю выгрузки — Google Ads (звонок или форма).
Продажа — у номера есть заказ с «Датой продажи» и без «Даты отмены». Кампания лида — по `utm_campaign` первой строки номера
(ID по regex `_(\\d+)_`, иначе название; общая метка PMax «Google CPC General - pm» не сопоставляется — остаётся отдельной строкой).
Печатает: A) по месяцам; B) по кампаниям с --campaigns-from; C) по неделям; D) по дням за последние 14 дней;
E) кампании по месяцам (где лидов ≥ 3) — что давало дешёвые заявки раньше.
Ограничения: последние недели не созрели (продажи приходят с лагом); у кампании 3–10 продаж — различия в десятки процентов
внутри шума; лиды без телефона не учитываются; расход — весь Google Ads клиента в zł, пересчёт по --rate.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python ea_lead_to_sale_trend.py [--from 2025-12-01] [--campaigns-from 2026-09-01] [--customer-id 8826134558] [--rate 4.3691]
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from ea_sales_by_campaign import GOOGLE_ADS_YAML, SHEET_ID, resolve
from ea_sales_orders_check import load as load_sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", default="2025-12-01")
    ap.add_argument("--campaigns-from", default="2026-09-01")
    ap.add_argument("--customer-id", default="8826134558")
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    ap.add_argument("--rate", type=float, default=4.3691, help="zł за 1 EUR")
    a = ap.parse_args()
    eur = lambda zl: zl / a.rate  # noqa: E731
    today = pd.Timestamp.now().normalize()

    ga = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).get_service("GoogleAdsService")
    names = {}
    for b in ga.search_stream(customer_id=a.customer_id, query="SELECT campaign.id, campaign.name FROM campaign"):
        for r in b.results:
            names[str(r.campaign.id)] = r.campaign.name
    by_name = {n.strip().lower().rstrip("_"): n for n in names.values()}
    q = (f"SELECT segments.date, campaign.name, metrics.cost_micros FROM campaign "
         f"WHERE segments.date >= '{a.date_from}' AND segments.date <= '{today:%Y-%m-%d}'")
    sp = [(pd.Timestamp(r.segments.date), r.campaign.name, r.metrics.cost_micros / 1e6)
          for b in ga.search_stream(customer_id=a.customer_id, query=q) for r in b.results]
    S = pd.DataFrame(sp, columns=["date", "camp", "cost"])
    S = S[S["cost"] > 0]

    df = load_sheet(SHEET_ID, a.worksheet)
    df["ph"] = df["phone"].astype(str).str.replace(r"\D", "", regex=True).str[-9:]
    df = df[(df["ph"].str.len() == 9) & df["ts"].notna()].sort_values("ts")
    df["net"] = df["sale_date_dt"].notna() & df["cancel_date_dt"].isna()
    first = df.groupby("ph").first()
    L = first[["ts", "src", "type", "utm_campaign"]].copy()
    L["sale"] = df.groupby("ph")["net"].any()
    L["camp"] = [resolve(u, names, by_name) if s == "Google Ads" else "" for u, s in zip(L["utm_campaign"], L["src"])]
    G = L[(L["src"] == "Google Ads") & (L["ts"] >= pd.Timestamp(a.date_from, tz="UTC"))].copy()
    G["date"] = G["ts"].dt.tz_localize(None).dt.normalize()
    for X in (S, G):
        X["month"] = X["date"].dt.strftime("%Y-%m")
        X["week"] = X["date"].dt.to_period("W-SUN").dt.start_time
    print(f"Выгрузка CRM: последняя строка {df['ts'].max():%Y-%m-%d %H:%M}; лидов Google с {a.date_from}: {len(G)}")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 300)

    def frame(spend_g, lead_g, key):
        t = pd.DataFrame({"расход_zl": spend_g.groupby(key)["cost"].sum(), "лиды": lead_g.groupby(key).size(),
                          "продажи": lead_g.groupby(key)["sale"].sum()}).fillna(0)
        t["цена_лида_EUR"] = (eur(t["расход_zl"]) / t["лиды"]).replace(float("inf"), float("nan")).round(1)
        t["лид→продажа_%"] = (t["продажи"] / t["лиды"] * 100).round(0)
        t["цена_продажи_EUR"] = (eur(t["расход_zl"]) / t["продажи"]).replace(float("inf"), float("nan")).round(0)
        t["расход_zl"] = t["расход_zl"].round(0)
        return t

    print("\n=== A. По месяцам ===")
    print(frame(S, G, "month").to_string())
    print(f"\n=== B. По кампаниям с {a.campaigns_from} ===")
    print(frame(S[S["date"] >= a.campaigns_from], G[G["date"] >= a.campaigns_from], "camp")
          .sort_values("расход_zl", ascending=False).to_string())
    print("\n=== C. По неделям (с понедельника), последние 10 ===")
    print(frame(S, G, "week").tail(10).to_string())
    print("\n=== D. По дням, последние 14 ===")
    d = pd.DataFrame({"расход_zl": S.groupby("date")["cost"].sum(), "лиды": G.groupby("date").size()}).fillna(0)
    d = d[d.index >= today - pd.Timedelta(days=14)]
    d["цена_лида_EUR"] = (eur(d["расход_zl"]) / d["лиды"]).replace(float("inf"), float("nan")).round(1)
    d["расход_zl"] = d["расход_zl"].round(0)
    print(d.to_string())
    print("\n=== E. Кампании по месяцам (лидов ≥ 3) ===")
    mc = pd.DataFrame({"расход": S.groupby(["month", "camp"])["cost"].sum(), "лиды": G.groupby(["month", "camp"]).size(),
                       "прод": G.groupby(["month", "camp"])["sale"].sum()}).fillna(0)
    mc["цена_лида_EUR"] = (eur(mc["расход"]) / mc["лиды"]).replace(float("inf"), float("nan")).round(1)
    mc["расход"] = mc["расход"].round(0)
    print(mc[mc["лиды"] >= 3].to_string())


if __name__ == "__main__":
    main()
