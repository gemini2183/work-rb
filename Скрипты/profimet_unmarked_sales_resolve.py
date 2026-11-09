#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: что на самом деле стоит за продажами с источником «Нет метки» — ТОЛЬКО ЧТЕНИЕ (09.11.2026).

Берёт проданные заказы (таблица CRM клиента, без отмен, дата продажи в окне), у которых первое обращение за 60 дн — «Нет метки», и для каждой ФОРМЫ
ищет настоящий источник по независимым следам:
  1) CRM: поле gclid при пустой метке (значит клик по рекламе Google);
  2) Supabase `profimet_leads` по телефону: gclid / utm_source / page_url (в адресе `?roistat=google4_…`, `fbclid=`, `gclid=`);
  3) живая таблица заявок Tilda по телефону: referer (те же признаки);
  4) GA4 Data API: событие form_submit в ту же минуту (±6 мин, Варшава) → sessionSource / sessionMedium / sessionCampaignName.
Вердикт: Google Ads / Facebook / не реклама (direct, organic, bing…) / не установлен. Звонки на номер сайта (пул «САЙТ mocnaszklarnia.pl») по этим
следам не разрешаются: у звонка нет UTM, `client_id` Ringostat не равен cid GA4, а визиты `profimet_visits` пишутся только с 05.11 — они печатаются списком «не установлен».

Запуск (из папки Скрипты): PYTHONUTF8=1 python profimet_unmarked_sales_resolve.py --from 2026-11-01 --to 2026-11-07
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

import forms_funnel_reconcile as F
import gads_spend_guard_cpa as G
from leads_standard import MON_DIR, _p9
from profimet_forms_reconcile import EVENT_FILTER, GA4_KEY, GA4_PROPERTY
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet

W = "Europe/Warsaw"


def verdict_from(text, gclid):
    t = (text or "").lower()
    if gclid or "gclid=" in t or "roistat=google" in t or "gbraid=" in t or "wbraid=" in t:
        return "Google Ads"
    if "fbclid=" in t or "facebook" in t:
        return "Facebook"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    a = ap.parse_args()
    d0, d1 = date.fromisoformat(a.frm), date.fromisoformat(a.to)
    sh = load_sheet(SHEET_ID)
    sh = sh[sh["site"] == "mocnaszklarnia.pl"]
    by = {p: g for p, g in sh.groupby("p9") if p}
    items = []
    for order, grp in sh[sh["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd or any(grp["cancel_date"] != ""):
            continue
        sale = pd.Timestamp(min(sd)).date()
        if not (d0 <= sale <= d1):
            continue
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        ps = sorted(p for p in set(grp["p9"]) if p)
        t = pd.concat([by[p] for p in ps if p in by]) if any(p in by for p in ps) else grp
        t = t[(t["ts"] >= t0 - pd.Timedelta(days=60)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        first = t.iloc[0] if not t.empty else grp.iloc[0]
        if (first["src"] or "Нет метки") != "Нет метки":
            continue
        items.append({"order": order, "sale": sale, "ps": ps, "ts": first["ts"].tz_convert(W), "type": first["type"], "crm_gclid": first["gclid"]})

    gc = yaml.safe_load((Path(__file__).resolve().parent.parent / "Клиенты" / "ProfiMet" / "guard_config.yaml").read_text(encoding="utf-8"))
    _, _, _, cfg = G.load_monitoring(MON_DIR, str(Path(MON_DIR) / "config" / gc["monitoring_config"]))
    sb = cfg["supabase"]
    h = {"apikey": sb["secret_key"], "Authorization": f"Bearer {sb['secret_key']}"}
    rows, off = [], 0
    while True:
        r = requests.get(f"{sb['url']}/rest/v1/{sb['table']}", headers={**h, "Range": f"{off}-{off + 999}"}, timeout=60,
                         params={"select": "created_at,phone,utm_source,gclid,page_url", "order": "created_at.asc"})
        r.raise_for_status()
        rows += r.json()
        if len(r.json()) < 1000:
            break
        off += 1000
    sup = pd.DataFrame(rows)
    sup["p9"] = sup["phone"].map(_p9)
    sup["ts"] = pd.to_datetime(sup["created_at"], utc=True).dt.tz_convert(W)
    til = F.load_tilda(F.CLIENTS["ProfiMet"])

    s = AuthorizedSession(Credentials.from_service_account_file(GA4_KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))
    dims = ["dateHourMinute", "sessionSource", "sessionMedium", "sessionCampaignName"]
    body = {"dateRanges": [{"startDate": str(d0 - pd.Timedelta(days=7).to_pytimedelta()), "endDate": str(d1)}],
            "dimensions": [{"name": d} for d in dims], "metrics": [{"name": "eventCount"}], "limit": 100000, "dimensionFilter": EVENT_FILTER}
    rr = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=120)
    rr.raise_for_status()
    ga = pd.DataFrame([[v["value"] for v in x["dimensionValues"]] for x in rr.json().get("rows", [])], columns=dims)
    ga["t"] = pd.to_datetime(ga["dateHourMinute"], format="%Y%m%d%H%M").dt.tz_localize(W, ambiguous="NaT", nonexistent="NaT")
    ga = ga[~ga["sessionSource"].str.contains("test|tagassistant", case=False)]

    print(f"=== «Нет метки» среди продаж {d0} … {d1}: {len(items)} (только чтение) ===")
    out = {}
    for it in sorted(items, key=lambda x: x["sale"]):
        if it["type"] != "форма":
            out.setdefault("не установлен (звонок на номер сайта)", []).append(it["order"])
            print(f"{it['order']} продажа {it['sale']} {it['ts']:%m-%d %H:%M} ЗВОНОК на номер сайта -> не установлен")
            continue
        evid, v = [], ""
        if it["crm_gclid"]:
            evid.append("gclid в CRM")
            v = "Google Ads"
        for _, x in sup[sup["p9"].isin(it["ps"])].iterrows():
            vv = verdict_from(x["page_url"], x["gclid"]) or ("Google Ads" if str(x["utm_source"]).lower() == "google" else "")
            if vv:
                evid.append(f"Supabase {x['ts']:%m-%d %H:%M}: {vv}")
                v = v or vv
        for _, x in til[til["p9"].isin(it["ps"])].iterrows():
            vv = verdict_from(x["referer"], "")
            if vv:
                evid.append(f"Tilda referer: {vv}")
                v = v or vv
        cand = ga[(ga["t"] - it["ts"]).abs() <= pd.Timedelta(minutes=6)]
        for _, x in cand.iterrows():
            src = f"{x['sessionSource']}/{x['sessionMedium']}/{x['sessionCampaignName'][:30]}"
            evid.append(f"GA4 {src}")
            if x["sessionMedium"] == "cpc" and x["sessionSource"] == "google":
                v = "Google Ads"
            elif "facebook" in x["sessionSource"].lower() and not v:
                v = "Facebook"
            elif not v:
                v = "не реклама"
        v = v or "не установлен"
        out.setdefault(v, []).append(it["order"])
        print(f"{it['order']} продажа {it['sale']} форма {it['ts']:%m-%d %H:%M} -> {v}  [{'; '.join(evid) or 'следов нет'}]")
    print("\nИтого:", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
