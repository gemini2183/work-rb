#!/usr/bin/env python
# coding: utf-8
"""Сверка продаж EkspertAgro, шаги 2–3: звонки Ringostat ↔ строки таблицы продаж клиента — ТОЛЬКО ЧТЕНИЕ.

1. Полнота: каждый входящий звонок Ringostat аккаунта EkspertAgro (свой аккаунт, ключ из конфига мониторинга; номера
   сайта …222927145, …225987224, …225987216, …222565341 и пулы …172508541/694; `--dst` сужает) ищется в листе `Ekspertagro.pl`
   (последние 9 цифр номера, время ±`--tol-min` минут, соответствие «один к одному»). Что не нашлось — по месяцам и по
   категории источника. Обратное: звонки таблицы, которых нет в Ringostat.
2. Правило уникальности боевой функции `ringostat_ekspertagro` (google-cloud-jobs): клиент определяется по utm
   (Facebook cpc → ФБ; `shop`/`merchant` в кампании → Мерчант; иначе Теплицы; `test` в кампании отбрасывается; звонки без
   source и medium отбрасываются), уникальный = первый звонок пары (клиент, номер), следующий уникальный не раньше чем
   через 60 дней от последнего засчитанного. Сравнивается с флагом Ringostat `unique_call` и с числом уникальных
   рекламных номеров в таблице. Ключ Ringostat читается из конфига мониторинга, в вывод не попадает.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_ringostat_vs_sheet.py [--from 2025-12-01] [--dst 48579774289] [--tol-min 10] [--csv-dir путь]
"""
import argparse
import re
from pathlib import Path

import gspread
import pandas as pd
import requests
import yaml
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"
MONITORING_CONFIG = r"E:\PythonProjects\RedBird\monitoring scripts\monitoring\config\experagro.yaml"
COLS = ["ts_raw", "phone", "type", "src", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "gclid", "order", "status", "sale_date", "cancel_date", "reason"]
WINDOW_DAYS = 60


def last9(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-9:] if len(d) >= 9 else d


def load_sheet(sheet_id, worksheet):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    vals = gspread.authorize(creds).open_by_key(sheet_id).worksheet(worksheet).get_all_values()
    df = pd.DataFrame(vals[1:], columns=COLS).replace("—", "")
    df["ts"] = pd.to_datetime(df["ts_raw"], utc=True, errors="coerce")
    df["p9"] = df["phone"].map(last9)
    return df


def fetch_ringostat(date_from):
    key = yaml.safe_load(open(MONITORING_CONFIG, encoding="utf-8"))["ringostat"]["auth_key"]
    r = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": f"{date_from} 00:00:00",
                "to": pd.Timestamp.now().strftime("%Y-%m-%d 23:59:59"),
                "fields": "calldate,caller,dst,disposition,billsec,call_type,uniqueid,utm_source,utm_medium,"
                          "utm_campaign,pool_name,unique_call"},
        headers={"Auth-key": key, "Content-Type": "application/json; charset=utf-8"}, timeout=300)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    for c in ("utm_source", "utm_medium", "utm_campaign", "pool_name"):
        df[c] = df[c].fillna("")
    df["ts"] = pd.to_datetime(df["calldate"], errors="coerce", utc=True)
    df = df[df["ts"].notna()].copy()
    df["p9"] = df["caller"].map(last9)
    df["dst9"] = df["dst"].map(last9)
    df["unique_call"] = pd.to_numeric(df["unique_call"], errors="coerce").fillna(0).astype(int)
    return df


def prod_client(row):
    """Копия determine_client боевой функции (None = звонок отбрасывается)."""
    s, m, c = row["utm_source"].lower(), row["utm_medium"].lower(), row["utm_campaign"].lower()
    if not s and not m:
        return None
    if c.replace("+", " ").strip() == "test":  # как в боевой функции с 2026-10-21 (раньше `"test" in c` теряло FB «vid_test»)
        return None
    if "facebook" in s and "cpc" in m:
        return "ФБ"
    if "shop" in c or "merchant" in c:
        return "Мерчант"
    return "Теплицы"


def prod_unique(df):
    """Боевое правило: пара (клиент, номер), окно 60 дней от последнего засчитанного, сравнение по дате."""
    df = df.copy()
    df["client"] = df.apply(prod_client, axis=1)
    d = df[df["client"].notna()].sort_values("ts", kind="mergesort")
    last, flag = {}, {}
    for idx, cl, p, ts in zip(d.index, d["client"], d["caller"], d["ts"]):
        day = ts.tz_convert("Europe/Warsaw").date()
        prev = last.get((cl, p))
        if prev is not None and (day - prev).days <= WINDOW_DAYS:
            flag[idx] = False
            continue
        last[(cl, p)] = day
        flag[idx] = True
    df["prod_unique"] = pd.Series(flag).reindex(df.index).fillna(False).astype(bool)
    return df


def match_one_to_one(a, b, tol_min):
    """a, b: датафреймы с p9 и ts. Возвращает индексы a, нашедшие пару в b (жадно по времени, один к одному)."""
    tol = pd.Timedelta(minutes=tol_min)
    by_p = {p: g.sort_values("ts") for p, g in b.groupby("p9")}
    used, found = set(), {}
    for idx, p, ts in zip(a.index, a["p9"], a["ts"]):
        g = by_p.get(p)
        if g is None:
            continue
        best, bd = None, None
        for j, t in zip(g.index, g["ts"]):
            if j in used:
                continue
            dt = abs(t - ts)
            if dt <= tol and (bd is None or dt < bd):
                best, bd = j, dt
        if best is not None:
            used.add(best)
            found[idx] = best
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=SHEET_ID)
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    ap.add_argument("--from", dest="date_from", default="2025-12-01")
    ap.add_argument("--dst", default="", help="последние 9 цифр набранного номера; пусто = все номера аккаунта EkspertAgro")
    ap.add_argument("--tol-min", type=float, default=10)
    ap.add_argument("--csv-dir", default=None)
    args = ap.parse_args()

    sheet = load_sheet(args.sheet_id, args.worksheet)
    ringo = fetch_ringostat(args.date_from)
    print(f"Ringostat: звонков {len(ringo)} с {ringo['ts'].min():%Y-%m-%d}; типы: {ringo['call_type'].value_counts().to_dict()}")
    print("Набранные номера (топ):", ringo["dst9"].value_counts().head(8).to_dict())

    inc = ringo[ringo["call_type"] == "in"].copy()
    if args.dst:
        inc = inc[inc["dst9"] == last9(args.dst)].copy()
    print(f"Входящих в сверке: {len(inc)}" + (f" (набранный номер …{last9(args.dst)})" if args.dst else " (все номера аккаунта)"))
    inc = prod_unique(inc)

    calls = sheet[(sheet["type"] == "звонок")].copy()
    calls = calls[calls["ts"] >= pd.Timestamp(args.date_from, tz="UTC")]
    print(f"Звонков в таблице с {args.date_from}: {len(calls)} ({calls['src'].value_counts().to_dict()})")

    found = match_one_to_one(inc, calls, args.tol_min)
    inc["in_sheet"] = inc.index.isin(found.keys())
    inc["month"] = inc["ts"].dt.strftime("%Y-%m")
    inc["ad_like"] = inc["utm_source"].str.lower().str.contains("google|facebook|dspl|kms") | inc["pool_name"].str.contains("Google|Facebook", case=False)
    print("\n== 1. Полнота: входящие Ringostat → есть ли строка в таблице ==")
    print(pd.crosstab(inc["month"], inc["in_sheet"], margins=True).rename(columns={True: "есть", False: "НЕТ"}))
    print("\nНе найдены, с рекламной меткой (utm google/facebook/пул):")
    miss_ad = inc[~inc["in_sheet"] & inc["ad_like"]]
    print(miss_ad.groupby("month").size().to_dict(), "всего", len(miss_ad))
    print("Не найдены, без рекламной метки:", int((~inc["in_sheet"] & ~inc["ad_like"]).sum()))
    print("Не найдены по статусу звонка (disposition):", inc[~inc["in_sheet"]]["disposition"].value_counts().to_dict())

    back = match_one_to_one(calls, inc, args.tol_min)
    calls["in_ringo"] = calls.index.isin(back.keys())
    calls["month"] = calls["ts"].dt.strftime("%Y-%m")
    print("\n== 1б. Обратное: звонки таблицы → есть ли входящий в Ringostat ==")
    print(pd.crosstab(calls["month"], [calls["src"], calls["in_ringo"]]))

    print("\n== 2. Уникальность ==")
    inc["pu_ad"] = inc["prod_unique"]
    print("Боевое правило (клиент+номер, 60 дн) по месяцам и клиентам:")
    print(pd.crosstab(inc[inc["prod_unique"]]["month"], inc[inc["prod_unique"]]["client"], margins=True))
    print("Флаг Ringostat unique_call=1 по месяцам:", inc[inc["unique_call"] == 1].groupby("month").size().to_dict())
    sc = calls[calls["src"].isin(["Google Ads", "Facebook"])]
    uniq_sheet = sc.sort_values("ts").drop_duplicates(["src", "p9"])
    print("Уникальные номера рекламных звонков в таблице (первый по номеру и источнику) по месяцам:",
          uniq_sheet.groupby("month").size().to_dict())

    if args.csv_dir:
        out = Path(args.csv_dir)
        out.mkdir(parents=True, exist_ok=True)
        inc[~inc["in_sheet"]][["ts", "caller", "dst", "disposition", "billsec", "utm_source", "utm_medium", "utm_campaign",
                               "pool_name", "client", "prod_unique", "unique_call"]].to_csv(
            out / "ea_ringostat_missing_in_sheet.csv", index=False, encoding="utf-8-sig")
        print("Сохранено:", out / "ea_ringostat_missing_in_sheet.csv")


if __name__ == "__main__":
    main()
