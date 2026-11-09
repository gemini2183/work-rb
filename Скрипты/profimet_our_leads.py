#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: заявки «по-нашему» (режим «Наш, 60 дней» дашборда) — ТОЛЬКО ЧТЕНИЕ (решение пользователя 2026-11-09).

Правила (по порядку):
  1. Обращения = входящие звонки Ringostat (Google Ads, Google SEO, Facebook, No Source) + формы выгрузки CRM (лист сайта, без тестовых номеров).
  2. ОДНА лестница 60 дней на номер для звонков и форм вместе: первое обращение номера засчитывается, всё, что позже и не дальше 60 календарных
     дней от ПОСЛЕДНЕГО засчитанного, — повтор (повторы окно не продлевают). В один день первым считается то, что пришло раньше по времени.
     В лестнице участвуют и обращения без рекламного источника (SEO, органика, форма «без метки»): номер уже обращался — повтор есть повтор.
  3. Звонок засчитывается заявкой, только если его канал Google Ads или Facebook (SEO и No Source в лестнице стоят, в заявки не входят).
  4. Форма с меткой Google Ads / Facebook в CRM засчитывается как есть. Форма «Нет метки» проверяется по независимым следам:
     gclid в CRM; Supabase `profimet_leads` по телефону (gclid, utm_source, адрес); таблица заявок Tilda по телефону (referer);
     GA4 `form_submit` в ту же минуту (±6 мин; если событий несколько — неоднозначно, не используется).
     Нашли рекламу → форма идёт в Google Ads / Facebook. Нашли «не реклама» (прямой заход, органика, реферал…) или не нашли ничего → не засчитывается.
  4а. Facebook — ТОЛЬКО cpc (решение 2026-11-09): звонок — utm_source=facebook и utm_medium=cpc (категория Ringostat); форма с меткой CRM Facebook — только при
      utm_medium=cpc (facebook / free и т.п. не считаются); форма без метки — только GA4 `facebook / cpc` или адрес с facebook и utm_medium=cpc
      (fbclid без cpc, `facebook.com / referral`, переход из мессенджера не считаются).
  5. Засчитываются обращения с 2026-08-01 (как боевое правило ringostat_profimet2); история лестницы — с 2025-08-01.

Использование как модуль: `our_leads(ringo, sheet, date_to, ga4_key, ga4_property)` → объект с `.counted`, `.contacts`.
Печать сводки: PYTHONUTF8=1 python profimet_our_leads.py --from 2026-11-01 --to 2026-11-08 [--list]   (из папки Скрипты)
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

W = "Europe/Warsaw"
WINDOW = 60
HISTORY_FROM = date(2025, 8, 1)
COUNT_FROM = date(2026, 8, 1)
TRACKED = ["Google Ads", "Google SEO", "Facebook", "No Source"]
AD = ("Google Ads", "Facebook")
SITE = "mocnaszklarnia.pl"
# тестовые номера форм — те же, что в profimet_forms_reconcile.py
TEST_PHONES = {"111111111", "123456789", "222222222", "444444444", "445454444", "123123123", "333333333", "111113691"}
GA_TOL_MIN = 6        # допуск совпадения формы с событием GA4, минут
SUP_BACK_DAYS = 10    # строка Supabase/Tilda с тем же телефоном: не раньше чем за N дней до строки CRM (CRM бывает отстаёт на дни)
SUP_FWD_HOURS = 2     # и не позже чем через N часов


def _verdict_from(text, gclid=""):
    """Google Ads — по gclid / gbraid / wbraid / roistat. Facebook — ТОЛЬКО cpc (решение пользователя 2026-11-09): в адресе нужны и facebook, и utm_medium=cpc;
    один fbclid (переход по ссылке из поста, мессенджера, `sfnsn=wa` — «поделиться»), facebook.com как реферер и utm_medium=free рекламой не считаются."""
    t = (text or "").lower()
    if gclid or "gclid=" in t or "roistat=google" in t or "gbraid=" in t or "wbraid=" in t:
        return "Google Ads"
    if "facebook" in t and "utm_medium=cpc" in t:
        return "Facebook"
    return ""


def _fb_without_cpc(text):
    t = (text or "").lower()
    return ("fbclid=" in t or "facebook" in t) and "utm_medium=cpc" not in t


def _load_supabase():
    """Строки `profimet_leads` (Supabase из конфига мониторинга) — ТОЛЬКО ЧТЕНИЕ."""
    import gads_spend_guard_cpa as G
    from leads_standard import MON_DIR, _p9
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
    sup = pd.DataFrame(rows, columns=["created_at", "phone", "utm_source", "gclid", "page_url"])
    sup["p9"] = sup["phone"].map(_p9)
    sup["ts"] = pd.to_datetime(sup["created_at"], utc=True)
    return sup


def _load_ga4_minutes(d0, d1, ga4_key, ga4_property):
    """События form_submit по минутам (GA4 хранит минутный срез около 60 дней). Возвращает (таблица, первая дата покрытия)."""
    s = AuthorizedSession(Credentials.from_service_account_file(ga4_key, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))
    start = max(d0 - timedelta(days=7), date.today() - timedelta(days=58))
    dims = ["dateHourMinute", "sessionSource", "sessionMedium", "sessionCampaignName"]
    body = {"dateRanges": [{"startDate": str(start), "endDate": str(d1)}], "dimensions": [{"name": d} for d in dims],
            "metrics": [{"name": "eventCount"}], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{ga4_property}:runReport", json=body, timeout=120)
    r.raise_for_status()
    ga = pd.DataFrame([[v["value"] for v in x["dimensionValues"]] for x in r.json().get("rows", [])], columns=dims)
    ga["t"] = pd.to_datetime(ga["dateHourMinute"], format="%Y%m%d%H%M").dt.tz_localize(W, ambiguous="NaT", nonexistent="NaT")
    ga = ga[~ga["sessionSource"].str.contains("test|tagassistant", case=False)]
    return ga, start


def resolve_unlabeled(forms, ga4_key, ga4_property, d0, d1):
    """forms: строки CRM (ts UTC, p9, gclid). Вердикт по каждой: Google Ads / Facebook / не реклама / не установлен + следы."""
    import forms_funnel_reconcile as F
    sup = _load_supabase()
    til = F.load_tilda(F.CLIENTS["ProfiMet"])
    til["ts"] = til["sent"].dt.tz_localize(W, ambiguous="NaT", nonexistent="NaT") if til["sent"].dt.tz is None else til["sent"]
    try:
        ga, ga_from = _load_ga4_minutes(d0, d1, ga4_key, ga4_property)
    except Exception as ex:  # GA4 недоступен — вердикт по остальным следам, об этом печатаем
        print(f"(GA4 минутный срез не прочитан: {ex})")
        ga, ga_from = pd.DataFrame(columns=["t", "sessionSource", "sessionMedium", "sessionCampaignName"]), None
    back, fwd, tol = pd.Timedelta(days=SUP_BACK_DAYS), pd.Timedelta(hours=SUP_FWD_HOURS), pd.Timedelta(minutes=GA_TOL_MIN)
    out = []
    for f in forms.itertuples(index=False):
        evid, paid, nonpaid = [], "", ""
        t_ref = [f.ts]
        if f.gclid:
            paid = "Google Ads"
            evid.append("gclid в CRM")
        s = sup[(sup["p9"] == f.p9) & (sup["ts"] >= f.ts - back) & (sup["ts"] <= f.ts + fwd)]
        if len(s):
            x = s.iloc[(s["ts"] - f.ts).abs().argmin()]
            t_ref.append(x["ts"])
            v = _verdict_from(x["page_url"], x["gclid"]) or ("Google Ads" if str(x["utm_source"]).lower() == "google" else "")
            if v:
                paid = paid or v
                evid.append(f"Supabase {x['ts'].tz_convert(W):%d.%m %H:%M}: {v}")
            elif _fb_without_cpc(x["page_url"]):
                nonpaid = nonpaid or "Facebook без cpc"
                evid.append("Supabase: Facebook без cpc (fbclid / facebook в адресе)")
            elif str(x["utm_source"] or "").strip():
                nonpaid = nonpaid or f"utm_source={x['utm_source']}"
                evid.append(f"Supabase: utm_source={x['utm_source']}")
            else:
                evid.append("Supabase: строка есть, меток нет")
        t = til[(til["p9"] == f.p9) & (til["ts"] >= f.ts - back) & (til["ts"] <= f.ts + pd.Timedelta(days=1))]  # часовой пояс `sent` не знаем точно — окно с запасом
        if len(t):
            v = _verdict_from(t.iloc[-1]["referer"])
            if v:
                paid = paid or v
                evid.append(f"Tilda referer: {v}")
            elif _fb_without_cpc(t.iloc[-1]["referer"]):
                nonpaid = nonpaid or "Facebook без cpc"
                evid.append("Tilda referer: Facebook без cpc (fbclid / facebook в адресе)")
        ga_hit = None
        if ga_from is not None and f.ts.tz_convert(W).date() >= ga_from:
            cand = ga[ga["t"].notna() & pd.concat([(ga["t"] - r).abs() <= tol for r in t_ref], axis=1).any(axis=1)]
            if len(cand) == 1:
                ga_hit = cand.iloc[0]
            elif len(cand) > 1:
                evid.append(f"GA4: {len(cand)} события рядом, неоднозначно")
        elif ga_from is not None:
            evid.append("GA4: минутный срез за эту дату уже не хранится")
        if ga_hit is not None:
            sm = f"{ga_hit['sessionSource']} / {ga_hit['sessionMedium']}"
            evid.append(f"GA4 {sm}")
            if ga_hit["sessionSource"].lower() == "google" and ga_hit["sessionMedium"].lower() == "cpc":
                paid = paid or "Google Ads"
            elif "facebook" in ga_hit["sessionSource"].lower() and ga_hit["sessionMedium"].lower() == "cpc":
                paid = paid or "Facebook"
            else:
                nonpaid = nonpaid or sm
        verdict = paid or ("не реклама" if nonpaid else "не установлен")
        out.append({"verdict": verdict, "evidence": "; ".join(evid) or "следов нет"})
    return pd.DataFrame(out, index=forms.index)


class OurLeads:
    def __init__(self, contacts, counted):
        self.contacts, self.counted = contacts, counted

    def window(self, frm, to):
        f, t = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
        c = self.contacts
        return c[(c["day"] >= f) & (c["day"] <= t) & (c["day"] >= COUNT_FROM)]


def our_leads(ringo, sheet, date_to, ga4_key, ga4_property, site=SITE, resolve=True):
    d1 = pd.Timestamp(date_to).date()
    # --- обращения: звонки Ringostat и формы CRM
    c = ringo[(ringo["call_type"] == "in") & ringo["category"].isin(TRACKED)].copy()
    c["day"] = c["ts"].dt.tz_convert(W).dt.date
    c = c[(c["day"] >= HISTORY_FROM) & (c["day"] <= d1)]
    calls = pd.DataFrame({"ts": c["ts"], "day": c["day"], "key": [p or r for p, r in zip(c["p9"], c["caller"])], "p9": c["p9"], "type": "звонок",
                          "crm_src": c["category"], "gclid": "", "id": c["uniqueid"].astype(str)})
    f = sheet[(sheet["site"] == site) & (sheet["type"] == "форма") & (sheet["p9"] != "") & ~sheet["p9"].isin(TEST_PHONES)].copy()
    f["day"] = f["ts"].dt.tz_convert(W).dt.date
    f = f[(f["day"] >= HISTORY_FROM) & (f["day"] <= d1)]
    forms = pd.DataFrame({"ts": f["ts"], "day": f["day"], "key": f["p9"], "p9": f["p9"], "type": "форма",
                          "crm_src": f["src"].replace("", "Нет метки"), "gclid": f["gclid"], "medium": f["utm_medium"].str.lower(), "id": f["ts_raw"].astype(str) + "|" + f["phone"].astype(str)})
    a = pd.concat([calls, forms], ignore_index=True).sort_values(["ts", "type"], kind="mergesort").reset_index(drop=True)
    # --- одна лестница 60 дней на номер
    last, new, prev_day, prev_type = {}, [], [], []
    for key, day, typ in zip(a["key"], a["day"], a["type"]):
        p = last.get(key)
        if p is not None and (day - p[0]).days <= WINDOW:
            new.append(False)
            prev_day.append(p[0])
            prev_type.append(p[1])
        else:
            last[key] = (day, typ)
            new.append(True)
            prev_day.append(None)
            prev_type.append("")
    a["new"], a["prev_day"], a["prev_type"] = new, prev_day, prev_type
    # --- итоговый источник и причина
    a["final"], a["reason"], a["evidence"] = "", "", ""
    in_scope = a["new"] & (a["day"] >= COUNT_FROM)
    for i in a.index[~a["new"]]:
        a.at[i, "reason"] = f"повтор: тот же номер уже обращался ({a.at[i, 'prev_type']}) {a.at[i, 'prev_day']:%d.%m.%Y}, не дальше {WINDOW} дн"
    isc = a["type"] == "звонок"
    for i in a.index[in_scope & isc]:
        cat = a.at[i, "crm_src"]
        a.at[i, "final"] = cat if cat in AD else ""
        if cat not in AD:
            a.at[i, "reason"] = f"звонок {cat}: не реклама Google Ads / Facebook"
    isf = a["type"] == "форма"
    for i in a.index[in_scope & isf & a["crm_src"].isin(AD)]:
        if a.at[i, "crm_src"] == "Facebook" and "cpc" not in str(a.at[i, "medium"]):  # Facebook — только cpc
            a.at[i, "reason"] = f"форма Facebook: не cpc (utm_medium={a.at[i, 'medium'] or 'пусто'})"
            continue
        a.at[i, "final"] = a.at[i, "crm_src"]
    other = a.index[in_scope & isf & ~a["crm_src"].isin(AD) & (a["crm_src"] != "Нет метки")]
    for i in other:
        a.at[i, "reason"] = f"форма: источник в CRM «{a.at[i, 'crm_src']}»"
    unl = a.index[in_scope & isf & (a["crm_src"] == "Нет метки")]
    if len(unl) and resolve:
        r = resolve_unlabeled(a.loc[unl], ga4_key, ga4_property, a.loc[unl, "day"].min(), d1)
        for i in unl:
            v = r.at[i, "verdict"]
            a.at[i, "evidence"] = r.at[i, "evidence"]
            if v in AD:
                a.at[i, "final"] = v
            else:
                a.at[i, "reason"] = f"форма без метки: {v}"
    elif len(unl):
        for i in unl:
            a.at[i, "reason"] = "форма без метки: не проверялась"
    a["counted"] = in_scope & a["final"].isin(AD)
    return OurLeads(a, a[a["counted"]].copy())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-11-01")
    ap.add_argument("--to", dest="to", default=str(date.today() - timedelta(days=1)))
    ap.add_argument("--list", action="store_true", help="напечатать каждую форму без метки и каждый повтор")
    a = ap.parse_args()
    from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
    from profimet_season_audit import fetch_ringostat_full
    from profimet_sources_dashboard import GA4_KEY, GA4_PROPERTY
    ol = our_leads(fetch_ringostat_full(), load_sheet(SHEET_ID), a.to, GA4_KEY, GA4_PROPERTY)
    w = ol.window(a.frm, a.to)
    print(f"=== Заявки по-нашему {a.frm} — {a.to} ===")
    cnt = w[w["counted"]]
    print(cnt.groupby(["final", "type"]).size().unstack(fill_value=0).to_string())
    print("\nНе засчитано:")
    print(w[~w["counted"]].groupby(["type", "reason"]).size().to_string())
    if a.list:
        print("\nФормы без метки и повторы:")
        for r in w[(w["type"] == "форма") & ((w["crm_src"] == "Нет метки") | ~w["new"])].itertuples():
            print(f"{r.ts.tz_convert(W):%d.%m %H:%M} {r.p9} CRM={r.crm_src} -> {r.final or 'не засчитана'} | {r.reason} | {r.evidence}")


if __name__ == "__main__":
    main()
