#!/usr/bin/env python
# coding: utf-8
"""Продажи из CRM ↔ звонки Ringostat: чей на самом деле первый контакт — ТОЛЬКО ЧТЕНИЕ.

Зачем: клиент перезванивает сам тем, кому не ответил на входящий из рекламы, и продажа записывается на
источник «Телефон»/«Нет метки», а не на Google Ads / Facebook. Скрипт по каждому номеру из выгрузки продаж
находит всю историю звонков в Ringostat, определяет первый контакт (по схеме уникальности проекта мониторинга:
единое множество звонивших по всем отслеживаемым источникам, `sources/ringostat.py::_classify_calls`) и
сравнивает его с источником, под которым записана продажа.

Вход: xlsx продаж (колонки `Дата, Заказ, Телефон, Товар, Кол-во, Источник, UTM, Площадка, Автор`),
необязательно xlsx форм Tilda (`--forms`): форма с тем же телефоном до продажи тоже считается контактом.
Время: продажи — UTC (`--sales-tz`), формы Tilda — Москва (`--forms-tz`), звонки — со смещением из API; в отчёте всё в Europe/Warsaw.
Ключ Ringostat читается из конфига мониторинга клиента (`--monitoring-config`), в вывод не попадает.

Вердикты по продаже:
  СОВПАЛО            — источник продажи совпадает с первым рекламным контактом;
  НЕ_ПРИСВОЕНО       — источник продажи «Телефон»/«Нет метки»/пусто, а первый контакт — реклама (Google Ads / Facebook);
  ДРУГОЙ_ИСТОЧНИК    — источник продажи рекламный, но другой, чем у первого контакта;
  ПЕРВЫЙ_НЕ_РЕКЛАМА  — первый контакт в Ringostat — не реклама (органика, карты, без источника);
  НЕТ_ЗВОНКОВ        — номера нет в Ringostat до даты продажи (форма/заказ на сайте/другой канал).

Использование:
    python ringostat_sales_attribution.py --sales "C:/Users/.../ea- продажи.xlsx" [--forms "...ea-tilda forms.xlsx"] \
        [--out ../Клиенты/EkspertAgro/Статистика/sales_attribution_<дата>.csv]
"""
import argparse
import re
import sys
from collections import Counter

import openpyxl
import pandas as pd
import requests
import yaml

MONITORING_CONFIG = r"E:\PythonProjects\RedBird\monitoring scripts\monitoring\config\experagro.yaml"
UNTRACKED = {"Other"}  # как в проекте мониторинга: звонки категории Other в множество уникальности не входят
NO_LABEL_WORDS = ("телефон", "нет метки", "без метки", "—", "")


def categorize_source(utm_source, utm_medium, google_keywords):
    """Копия `sources.ringostat.categorize_source` (порядок условий важен)."""
    s, m = str(utm_source).lower(), str(utm_medium).lower()
    if "карты" in s:
        return "No Source"
    if "google" in s and "organic" in m:
        return "No Source"
    if "seomocna" in s:
        return "Google SEO"
    if "facebook" in s and "cpc" in m:
        return "Facebook"
    if any(k in s for k in google_keywords):
        return "Google Ads"
    return "Other"


def last9(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-9:] if len(d) >= 9 else d


def fetch_calls(cfg):
    rs = cfg["ringostat"]
    r = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": rs["date_from"],
                "to": pd.Timestamp.now().strftime("%Y-%m-%d 23:59:59"),
                "fields": "calldate,caller,disposition,billsec,duration,call_type,uniqueid,utm_source,"
                          "utm_medium,utm_campaign,utm_content,pool_name,unique_call"},
        headers={"Auth-key": rs["auth_key"], "Content-Type": "application/json; charset=utf-8"},
        timeout=180,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    for c in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "pool_name"):
        df[c] = df[c].fillna("")
    # calldate приходит с явным смещением (+0100/+0200) — приводим к UTC, чтобы сравнивать с продажами и формами
    df["ts"] = pd.to_datetime(df["calldate"], errors="coerce", utc=True)
    return df[df["ts"].notna()].copy()


def classify(df, cfg):
    sf = cfg["ringostat"].get("source_filter", {})
    kws = list(sf.get("include_keywords", ["google", "dspl", "kms"]))
    if "performance_max" not in kws:
        kws.append("performance_max")
    excluded = set(cfg["ringostat"].get("excluded_campaigns", []))
    df["category"] = [categorize_source(s, m, kws) for s, m in zip(df["utm_source"], df["utm_medium"])]
    df.loc[df["utm_campaign"].isin(excluded), "category"] = "No Source"
    df["p9"] = df["caller"].map(last9)
    # схема уникальности проекта: единое множество по всем отслеживаемым источникам, по времени
    tracked = df[~df["category"].isin(UNTRACKED)].sort_values("ts", kind="mergesort")
    seen, flag = set(), {}
    for idx, p in zip(tracked.index, tracked["p9"]):
        flag[idx] = "unique" if p not in seen else "repeat"
        seen.add(p)
    df["our_unique"] = pd.Series(flag)
    return df


def to_utc(ts, tz):
    t = pd.Timestamp(ts)
    return t.tz_localize(tz).tz_convert("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def load_sales(path, tz):
    ws = openpyxl.load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c) for c in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(r):
            continue
        d = dict(zip(hdr, r))
        d["ts"] = to_utc(pd.to_datetime(d["Дата"]), tz)
        d["p9"] = last9(d.get("Телефон"))
        out.append(d)
    return out


def load_forms(path, tz):
    """Формы Tilda: строки без фиксированных колонок — ищем телефон, дату и URL по содержимому."""
    ws = openpyxl.load_workbook(path, data_only=True).active
    out = []
    for r in ws.iter_rows(values_only=True):
        cells = [str(c) for c in r if c not in (None, "")]
        if not cells:
            continue
        date = next((c for c in cells if re.match(r"20\d\d-\d\d-\d\d \d\d:\d\d", c)), None)
        phones = [c for c in cells if c.strip().startswith("+") and len(re.sub(r"\D", "", c)) >= 9]
        url = next((c for c in cells if c.startswith("http")), "")
        form = next((c for c in cells if re.fullmatch(r"form\d+", c)), "")
        if date and phones:
            src = re.search(r"utm_source=([^&]+)", url)
            camp = re.search(r"utm_campaign=([^&]+)", url)
            out.append({"ts": to_utc(pd.to_datetime(date), tz), "p9": last9(phones[0]), "form": form,
                        "utm_source": src.group(1) if src else "", "utm_campaign": camp.group(1) if camp else ""})
    return out


def sale_label_kind(src):
    s = str(src or "").lower()
    if "facebook" in s:
        return "Facebook"
    if "google" in s or "pmax" in s or "merchant" in s or "shopping" in s:
        return "Google Ads"
    if any(w in s for w in ("телефон", "нет метки", "без метки")) or s.strip() in ("", "—"):
        return "нет"
    return "другое"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sales", required=True)
    ap.add_argument("--forms", default=None)
    ap.add_argument("--monitoring-config", default=MONITORING_CONFIG)
    ap.add_argument("--sales-tz", default="UTC", help="часовой пояс колонки «Дата» продаж (EkspertAgro 2026-10-14: UTC — подтверждено совпадением с началом звонков)")
    ap.add_argument("--forms-tz", default="Europe/Moscow", help="часовой пояс выгрузки Tilda (по умолчанию аккаунта — Москва, UTC+3)")
    ap.add_argument("--tol-hours", type=float, default=0.5, help="контакт, начавшийся не позже чем через N часов ПОСЛЕ продажи, тоже считается (шум часов)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cfg = yaml.safe_load(open(a.monitoring_config, encoding="utf-8"))
    calls = classify(fetch_calls(cfg), cfg)
    print(f"Ringostat: {len(calls)} звонков, {calls['ts'].min():%Y-%m-%d} — {calls['ts'].max():%Y-%m-%d} (UTC); "
          f"call_type: {dict(Counter(calls['call_type']))}")
    sales = load_sales(a.sales, a.sales_tz)
    forms = load_forms(a.forms, a.forms_tz) if a.forms else []
    by_phone = {p: g.sort_values("ts") for p, g in calls.groupby("p9")}

    result = []
    for s in sales:
        g = by_phone.get(s["p9"])
        before = g[g["ts"] <= s["ts"] + pd.Timedelta(hours=a.tol_hours)] if g is not None else None
        kind = sale_label_kind(s.get("Источник"))
        f_before = [f for f in forms if f["p9"] == s["p9"] and f["ts"] <= s["ts"] + pd.Timedelta(hours=a.tol_hours)]
        row = {"дата продажи": s["ts"].tz_convert("Europe/Warsaw").strftime("%Y-%m-%d %H:%M"), "заказ": s.get("Заказ"), "телефон": s.get("Телефон"),
               "источник продажи": s.get("Источник"), "UTM продажи": s.get("UTM"), "автор": s.get("Автор"),
               "звонков до продажи": 0 if before is None else len(before),
               "первый контакт": "", "контакт→продажа": "", "категория": "", "кампания/пул": "", "дозвон": "", "наш unique": "",
               "unique по Ringostat": "", "форма до продажи": ", ".join(
                   f"{f['ts'].tz_convert('Europe/Warsaw'):%m-%d %H:%M} {f['form']} {f['utm_source']}/{f['utm_campaign']}" for f in f_before)}
        if before is None or before.empty:
            verdict = "НЕТ_ЗВОНКОВ"
            if f_before and kind == "нет":
                verdict = "НЕТ_ЗВОНКОВ_ЕСТЬ_ФОРМА"
        else:
            first_all = before.iloc[0]
            ad = before[before["category"].isin(["Google Ads", "Facebook"])]
            first_ad = ad.iloc[0] if not ad.empty else None
            f = first_ad if first_ad is not None else first_all
            row.update({
                "первый контакт": f"{f['ts'].tz_convert('Europe/Warsaw'):%Y-%m-%d %H:%M} ({f['call_type']})",
                "контакт→продажа": f"{(s['ts'] - f['ts']).total_seconds() / 3600:.1f} ч",
                "категория": f["category"],
                "кампания/пул": f"{f['utm_campaign'] or '—'} | {f['pool_name'] or '—'}",
                "дозвон": f"{f['disposition']} {f['billsec']}с",
                "наш unique": f["our_unique"],
                "unique по Ringostat": f["unique_call"],
            })
            if first_ad is None:
                verdict = "ПЕРВЫЙ_НЕ_РЕКЛАМА"
            elif kind == "нет":
                verdict = "НЕ_ПРИСВОЕНО"
            elif kind == first_ad["category"]:
                verdict = "СОВПАЛО"
            else:
                verdict = "ДРУГОЙ_ИСТОЧНИК"
        row["вердикт"] = verdict
        result.append(row)

    out = pd.DataFrame(result)
    print("\nИсточники в продажах:", dict(Counter(out["источник продажи"])))
    print("Вердикты:", dict(Counter(out["вердикт"])))
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60):
        print("\n=== Продажи без рекламной метки (Телефон / Нет метки) ===")
        sub = out[out["источник продажи"].map(sale_label_kind) == "нет"]
        print(sub[["дата продажи", "заказ", "телефон", "источник продажи", "звонков до продажи", "первый контакт", "контакт→продажа",
                   "категория", "кампания/пул", "дозвон", "форма до продажи", "вердикт"]].to_string(index=False))
    if a.out:
        out.to_csv(a.out, index=False, encoding="utf-8-sig")
        print(f"\n(сохранено: {a.out})")


if __name__ == "__main__":
    main()
