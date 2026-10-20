#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: НАШ дашборд «По источникам» из выгрузки продаж CRM, Google Ads и BigQuery — ТОЛЬКО ЧТЕНИЕ.

Те же строки и колонки, что в клиентском дашборде (Источник, Цена, Клики, Показы, Цена клика, CTR, Конверсии, % конверсии,
Цена заявки, Звонки, Продажи, % продажи, Цена продажи), но все определения собственные и выписаны под таблицей. Нужен, чтобы
человек сравнил его с клиентским глазами; сами расхождения скрипт не разбирает (решение пользователя 2026-10-20).

Откуда данные и как считаем (лист `mocnaszklarnia.pl` выгрузки CRM):
  • Цена / Клики / Показы — Google Ads: из API по аккаунту (все кампании) за даты периода; Facebook: BigQuery
    `redbird-196813.adwhite.fb_stats_profimet` (в таблице хранится в долларах, пересчёт в евро — параметр `--usd-eur`).
    У «Нет метки», «Телефон», «Прочее» рекламных показателей нет.
  • Конверсии — обращения (звонки + формы) выгрузки, НОВЫЕ по правилу 60 дней: обращение новое, если у этого номера на
    этом сайте не было засчитанного нового обращения за последние 60 дней (окно считается от последнего засчитанного, повторы
    окно не продлевают — как в боевом скрипте ringostat_profimet2; в памяти все источники и формы). Источник обращения — как в выгрузке.
  • Звонки — из конверсий те, что звонки.
  • Продажи — проданные заказы (в выгрузке есть «Дата продажи» в периоде; количество товара в выгрузке нет, поэтому это заказы,
    не единицы). Источник продажи — источник ПЕРВОГО обращения этого номера за 60 дней до первой строки заказа (правило клиента).
  • % конверсии = Конверсии ÷ Клики; Цена заявки = Цена ÷ Конверсии; % продажи = Продажи ÷ Конверсии; Цена продажи = Цена ÷ Продажи;
    CTR = Клики ÷ Показы; Цена клика = Цена ÷ Клики. «Итого»: цена и показатели Google + Facebook, конверсии и продажи по всем строкам.
  • Справочно под таблицей: звонки Google/Facebook по боевому правилу Ringostat (только входящие, в памяти 4 канала) — те же, что в
    таблице агентства `ringostat_calls_profimet2`.

Использование:
    PYTHONIOENCODING=utf-8 python profimet_sources_dashboard.py [--from 2026-08-01] [--to 2026-10-19] [--by month|week]
        [--usd-eur 0.85] [--cache путь.pkl]
Пишет `Клиенты/ProfiMet/Статистика/dashboard_sources_<с>_<по>.csv`. Запускать без -I.
"""
import argparse
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE, client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_season_audit import W, fetch_ringostat_full, prod_unique

SITE = "mocnaszklarnia.pl"
ADS_CUSTOMER = "7552781705"
SOURCES = ["Google Ads", "Facebook", "Нет метки", "Телефон", "Прочее"]
WINDOW = 60


def ads_daily(frm, to):
    c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    q = (f"SELECT segments.date, metrics.cost_micros, metrics.clicks, metrics.impressions FROM customer "
         f"WHERE segments.date BETWEEN '{frm}' AND '{to}'")
    rows = [(r.segments.date, r.metrics.cost_micros / 1e6, r.metrics.clicks, r.metrics.impressions)
            for r in c.get_service("GoogleAdsService").search(customer_id=ADS_CUSTOMER, query=q)]
    d = pd.DataFrame(rows, columns=["date", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def fb_daily(frm, to):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/bigquery"])
    c = bigquery.Client(project="redbird-196813", credentials=creds)
    q = (f"SELECT date, SUM(spend) cost, SUM(clicks) clicks, SUM(impressions) impr FROM `redbird-196813.adwhite.fb_stats_profimet` "
         f"WHERE date BETWEEN '{frm}' AND '{to}' GROUP BY date")
    d = pd.DataFrame([dict(r.items()) for r in c.query(q).result()], columns=["date", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def contacts_with_new_flag(sheet):
    """Обращения (звонок/форма) листа с флагом «новое по правилу 60 дн» (лестница: окно от последнего засчитанного)."""
    s = sheet[(sheet["site"] == SITE) & sheet["type"].isin(["звонок", "форма"]) & (sheet["p9"] != "")].copy()
    s["src2"] = s["src"].replace("", "Нет метки")
    s.loc[~s["src2"].isin(SOURCES), "src2"] = "Прочее"
    s["day"] = s["ts"].dt.tz_convert(W).dt.date
    s = s.sort_values("ts", kind="mergesort")
    last, flags = {}, []
    for p9, day in zip(s["p9"], s["day"]):
        prev = last.get(p9)
        new = prev is None or (day - prev).days > WINDOW
        if new:
            last[p9] = day
        flags.append(new)
    s["new"] = flags
    return s


def sales_with_source(sheet):
    """Проданные заказы: дата продажи, источник первого обращения номера за 60 дн до первой строки заказа."""
    s = sheet[sheet["site"] == SITE]
    by_phone = {p: g for p, g in s.groupby("p9") if p}
    rows = []
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd:
            continue
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        parts = [by_phone[p] for p in set(grp["p9"]) if p in by_phone]
        t = pd.concat(parts) if parts else grp
        t = t[(t["ts"] >= t0 - pd.Timedelta(days=WINDOW)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        src = (t.iloc[0]["src"] if not t.empty else grp.iloc[0]["src"]) or "Нет метки"
        rows.append({"order": order, "sale_date": pd.Timestamp(min(sd)).date(), "src2": src if src in SOURCES else "Прочее"})
    return pd.DataFrame(rows)


def build(frm, to, ads, fb, contacts, sales, usd_eur):
    f, t = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
    a = ads[(ads["date"] >= f) & (ads["date"] <= t)]
    b = fb[(fb["date"] >= f) & (fb["date"] <= t)]
    paid = {"Google Ads": (a["cost"].sum(), a["clicks"].sum(), a["impr"].sum()),
            "Facebook": (b["cost"].sum() * usd_eur, b["clicks"].sum(), b["impr"].sum())}
    c = contacts[contacts["new"] & (contacts["day"] >= f) & (contacts["day"] <= t)]
    sl = sales[(sales["sale_date"] >= f) & (sales["sale_date"] <= t)]
    out, notes = [], []
    for src in SOURCES:
        cost, clk, imp = paid.get(src, (None, None, None))
        cc = c[c["src2"] == src]
        conv, calls = len(cc), int((cc["type"] == "звонок").sum())
        # Структура колонок как у клиентского дашборда: конверсиями считаются Google Ads, Facebook, «Нет метки» (звонки — только
        # у Google и Facebook); перезвоны «Телефон» и «Прочее» в конверсии не входят. Убранное из колонок печатается под таблицей.
        if src in ("Телефон", "Прочее"):
            notes.append(f"{src}: новых обращений {conv} (из них звонков {calls}) — в «Конверсии» и «Звонки» не включены")
            conv = calls = None
        elif src == "Нет метки":
            notes.append(f"Нет метки: из {conv} конверсий звонков {calls} — в колонке «Звонки» не показаны")
            calls = None
        out.append({"Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": conv, "Звонки": calls,
                    "Продажи": int((sl["src2"] == src).sum())})
    df = pd.DataFrame(out)
    tot_cost = sum(v[0] for v in paid.values())
    tot = {"Источник": "Итого", "Цена": tot_cost, "Клики": sum(v[1] for v in paid.values()), "Показы": sum(v[2] for v in paid.values()),
           "Конверсии": int(df["Конверсии"].sum()), "Звонки": int(df["Звонки"].sum()), "Продажи": int(df["Продажи"].sum())}
    df = pd.concat([df, pd.DataFrame([tot])], ignore_index=True)
    df["Цена клика"] = df["Цена"] / df["Клики"]
    df["CTR %"] = df["Клики"] / df["Показы"] * 100
    df["% конверсии"] = df["Конверсии"] / df["Клики"] * 100
    df["Цена заявки"] = df["Цена"] / df["Конверсии"].where(df["Конверсии"] > 0)
    df["% продажи"] = df["Продажи"] / df["Конверсии"].where(df["Конверсии"] > 0) * 100
    df["Цена продажи"] = df["Цена"] / df["Продажи"].where(df["Продажи"] > 0)
    # «Итого»: клики/показы только Google+Facebook, поэтому % конверсии у строк без рекламы не считаем
    df.loc[df["Клики"].isna(), ["Цена клика", "CTR %", "% конверсии"]] = None
    cols = ["Источник", "Цена", "Клики", "Показы", "Цена клика", "CTR %", "Конверсии", "% конверсии", "Цена заявки", "Звонки",
            "Продажи", "% продажи", "Цена продажи"]
    df = df[cols]
    df.attrs["notes"] = notes
    return df


def show(df, title):
    print(f"\n=== {title} ===")
    fmt = df.copy()
    for c in ("Цена", "Цена клика", "Цена заявки", "Цена продажи"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:,.2f} €".replace(",", " "))
    for c in ("Клики", "Показы", "Конверсии", "Звонки"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", " "))
    for c in ("CTR %", "% конверсии", "% продажи"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}%")
    print(fmt.to_string(index=False))
    for n in df.attrs.get("notes", []):
        print("  *", n)


def periods(frm, to, by):
    f, t = pd.Timestamp(frm), pd.Timestamp(to)
    if by == "month":
        cur = f
        while cur <= t:
            end = min((cur + pd.offsets.MonthEnd(0)), t)
            yield cur.date(), end.date(), cur.strftime("%Y-%m")
            cur = end + pd.Timedelta(days=1)
    elif by == "week":
        cur = f - pd.Timedelta(days=f.weekday())
        while cur <= t:
            s, e = max(cur, f), min(cur + pd.Timedelta(days=6), t)
            yield s.date(), e.date(), f"неделя {cur.strftime('%d.%m')}"
            cur += pd.Timedelta(days=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--to", dest="to", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--by", choices=["month", "week"], default=None)
    ap.add_argument("--usd-eur", type=float, default=0.85, help="курс для расхода Facebook (в BigQuery — доллары); ПАРАМЕТР, не факт")
    ap.add_argument("--cache", default=None, help="pickle (sheet, ringo_full), как у profimet_season_audit.py")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    ads, fb = ads_daily(a.frm, a.to), fb_daily(a.frm, a.to)
    contacts, sales = contacts_with_new_flag(sheet), sales_with_source(sheet)

    total = build(a.frm, a.to, ads, fb, contacts, sales, a.usd_eur)
    show(total, f"ProfiMet, по источникам, {a.frm} — {a.to}")
    out_dir = client_stats_dir("ProfiMet")
    total.to_csv(out_dir / f"dashboard_sources_{a.frm}_{a.to}.csv", index=False, encoding="utf-8-sig")
    if a.by:
        for s, e, label in periods(a.frm, a.to, a.by):
            show(build(s, e, ads, fb, contacts, sales, a.usd_eur), f"{label}: {s} — {e}")

    pu = prod_unique(ringo, count_other=False, date_to=a.to)
    pu = pu[(pu["date"] >= pd.Timestamp(a.frm).date()) & (pu["date"] <= pd.Timestamp(a.to).date())]
    print("\nСправочно: звонки по боевому правилу Ringostat (ringostat_profimet2) за период:",
          {k: int((pu["category"] == k).sum()) for k in ("Google Ads", "Facebook", "Google SEO")})
    print(f"Расход Facebook в BigQuery хранится в долларах; пересчёт в евро по курсу {a.usd_eur} (параметр --usd-eur). "
          f"Последняя дата в выгрузке CRM: {sheet['ts'].max().tz_convert(W):%Y-%m-%d %H:%M}.")


if __name__ == "__main__":
    main()
