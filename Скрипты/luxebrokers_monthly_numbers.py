#!/usr/bin/env python
# coding: utf-8
"""LuxeBrokers: ежемесячный Excel со всеми уникальными номерами за месяц (только чтение).

Источники:
  1. Формы сайта (Tilda → Google Sheets «Tilda_Jewelry_Fast_Sale»): все заявки месяца, все источники.
  2. Ringostat API `calls/list` (проект 141688): только Google-реклама (utm_source=google: пулы
     «Google CPC calls from ads» и «Only CPC»); SEO (пул/источник CEO) и прочее не берём.
  3. Google Ads → Reports → Calls → Call details (ручная выгрузка из кабинета, API полный номер не отдаёт):
     номера, которых нет в Ringostat, добавляются в сводку. Файл: --gads-details <csv|xml>; без него лист пропускается.

Границы месяца — по времени America/Los_Angeles (часовой пояс аккаунта клиента).
Ключ: `RINGOSTAT_KEY_LuxeBrokers` в `Скрипты/secrets/ringostat_keys.env`.
Номер для сравнения — последние 10 цифр.

    python luxebrokers_monthly_numbers.py --month 2026-10 [--gads-details "C:\\...\\Call details.csv"]
"""
import argparse
import calendar
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import gspread
import pandas as pd
import requests
from google.oauth2.service_account import Credentials

SECRETS = Path(__file__).resolve().parent / "secrets" / "ringostat_keys.env"
GD_CRED = Path(r"E:\PythonProjects\RedBird\month_stats\Google_Drive.json")
FORMS_SHEET_ID = "1Nc9ObnZh4FQf0oVx4SLsObRJZv-eQImJdMsYPRNWpms"
OUT_DIR = Path(r"E:\PythonProjects\RedBird\month_stats\reports")
TZ = "America/Los_Angeles"
FIELDS = "calldate,caller,dst,call_type,disposition,billsec,duration,uniqueid,utm_source,utm_medium,utm_campaign,pool_name"


def n10(x):
    d = re.sub(r"\D", "", str(x or ""))
    return d[-10:] if len(d) >= 10 else ""


def fmt(n):
    return f"+1 ({n[:3]}) {n[3:6]}-{n[6:]}" if len(n) == 10 else ""


def ringostat_key():
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        name, _, val = line.strip().partition("=")
        if name == "RINGOSTAT_KEY_LuxeBrokers" and val:
            return val
    raise SystemExit("Нет RINGOSTAT_KEY_LuxeBrokers в ringostat_keys.env")


def load_forms(start, end):
    creds = Credentials.from_service_account_file(str(GD_CRED), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    v = gspread.authorize(creds).open_by_key(FORMS_SHEET_ID).get_worksheet(0).get_all_values()
    df = pd.DataFrame(v[1:], columns=v[0])

    def parse(s):
        for f in ("%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return pd.to_datetime(s.strip(), format=f)
            except ValueError:
                pass
        return pd.NaT

    df["Дата"] = df["sent"].map(parse)
    df = df[(df["Дата"] >= start) & (df["Дата"] < end + pd.Timedelta(days=1))].copy()
    df["n10"] = df["Phone"].map(n10)
    out = df[["Дата", "name", "Phone", "n10", "Form name", "utm_source", "utm_medium", "utm_campaign", "utm_term", "Textarea"]]
    return out.rename(columns={"name": "Имя", "Phone": "Телефон (как в форме)", "Form name": "Форма", "Textarea": "Комментарий"}).sort_values("Дата")


def load_ringostat(start, end):
    # запас по краям, потом режем по времени Лос-Анджелеса
    r = requests.get("https://api.ringostat.net/calls/list",
                     params={"export_type": "json", "from": f"{(start - pd.Timedelta(days=2)).date()} 00:00:00",
                             "to": f"{(end + pd.Timedelta(days=2)).date()} 23:59:59", "fields": FIELDS},
                     headers={"Auth-key": ringostat_key(), "Content-Type": "application/json; charset=utf-8"}, timeout=300)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["local"] = pd.to_datetime(df["calldate"], utc=True).dt.tz_convert(TZ).dt.tz_localize(None)
    df = df[(df["local"] >= start) & (df["local"] < end + pd.Timedelta(days=1))].copy()
    df["n10"] = df["caller"].map(n10)
    all_n = len(df)
    google = df[df["utm_source"].str.lower() == "google"].copy()
    return google.sort_values("local"), all_n, df["utm_source"].value_counts().to_dict()


def load_gads_details(path):
    p = Path(path)
    if p.suffix.lower() == ".xml":
        rows = [{c.find("key").text: c.find("value").text for c in row.iter("cell")} for row in ET.parse(p).getroot().iter("row")]
        df = pd.DataFrame(rows)
    else:
        df = None
        for enc in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                raw = pd.read_csv(p, sep=None, engine="python", encoding=enc, skiprows=2, dtype=str)
                if "Caller phone number" in raw.columns:
                    df = raw
                    break
            except Exception:
                continue
        if df is None:
            raise SystemExit("Не смог прочитать Call details")
    df["n10"] = df["Caller phone number"].map(n10)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--gads-details")
    a = ap.parse_args()
    y, m = map(int, a.month.split("-"))
    start = pd.Timestamp(y, m, 1)
    end = pd.Timestamp(y, m, calendar.monthrange(y, m)[1])

    forms = load_forms(start, end)
    ring, ring_all, ring_src = load_ringostat(start, end)
    gads = load_gads_details(a.gads_details) if a.gads_details else None

    f_set, r_set = set(forms["n10"]) - {""}, set(ring["n10"]) - {""}
    g_set = (set(gads["n10"]) - {""}) if gads is not None else set()

    rows = []
    for n in sorted(f_set | r_set | g_set):
        rows.append({"Номер": fmt(n), "n10": n,
                     "Форма": n in f_set, "Ringostat Google": n in r_set, "Google Ads Call details": n in g_set,
                     "Заявок с формы": int((forms["n10"] == n).sum()),
                     "Звонков Ringostat": int((ring["n10"] == n).sum()),
                     "Звонков Google Ads": int((gads["n10"] == n).sum()) if gads is not None else 0})
    summ = pd.DataFrame(rows)
    for c in ("Форма", "Ringostat Google", "Google Ads Call details"):
        summ[c] = summ[c].map({True: "да", False: ""})

    ring_out = ring[["local", "caller", "n10", "pool_name", "utm_medium", "utm_campaign", "disposition", "billsec", "duration", "uniqueid"]].rename(
        columns={"local": "Дата (LA)", "caller": "Номер (как в Ringostat)", "pool_name": "Пул", "utm_medium": "Medium",
                 "utm_campaign": "Кампания (utm)", "disposition": "Статус", "billsec": "Разговор, сек", "duration": "Длительность, сек", "uniqueid": "ID"})

    notes = [
        ("Период", f"{start.date()} — {end.date()} (время Лос-Анджелеса)"),
        ("Форм-заявок", len(forms)), ("Уникальных номеров в формах", len(f_set)),
        ("Звонков Ringostat за месяц (все источники)", ring_all), ("Источники Ringostat", str(ring_src)),
        ("Звонков Ringostat Google (без SEO)", len(ring)), ("Уникальных номеров Ringostat Google", len(r_set)),
        ("Google Ads Call details", "не приложен" if gads is None else f"{len(gads)} строк, {len(g_set)} уникальных"),
        ("Всего уникальных номеров в сводке", len(summ)),
        ("Номера и в форме, и в Ringostat", len(f_set & r_set)),
    ]
    if gads is not None:
        notes.append(("Номера Google Ads, которых нет в Ringostat", len(g_set - r_set)))

    out = OUT_DIR / f"LuxeBrokers_Calls_{a.month}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        pd.DataFrame(notes, columns=["Параметр", "Значение"]).to_excel(xw, "Итоги", index=False)
        summ.drop(columns="n10").to_excel(xw, "Уникальные номера", index=False)
        forms.drop(columns="n10").assign(**{"Дата": forms["Дата"].dt.date}).to_excel(xw, "Формы", index=False)
        ring_out.drop(columns="n10").to_excel(xw, "Ringostat Google", index=False)
        if gads is not None:
            gads.drop(columns="n10").to_excel(xw, "Google Ads Call details", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(48, max(10, max(len(str(c.value or "")) for c in col[:60]) + 2))
            ws.freeze_panes = "A2"
    print(out)
    for k, v in notes:
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
