#!/usr/bin/env python
# coding: utf-8
"""Ringostat (аккаунт ProfiMet, в нём же звонки менеджеров EkspertAgro): ПОЛНАЯ выгрузка звонков, входящих И ИСХОДЯЩИХ, и сверка с таблицей клиента — ТОЛЬКО ЧТЕНИЕ.

Зачем: проверить, какие звонки таблица «Данные по продажам» записывает как обращения (строки), а какие нет: входящие отвеченные / пропущенные, исходящие
отвеченные / неотвеченные, по номерам. Номер клиента: у входящих — `caller`, у исходящих — `dst` (в `caller` у исходящих имя менеджера, из-за чего прежние
проверки по `caller` исходящие не видели). Сопоставление звонка со строкой-звонком таблицы: последние 9 цифр номера и время ±`--tol-min` минут, один к одному.
Ключ Ringostat — из `ringostat_stats_profimet.py`, в вывод не попадает.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python profimet_ringostat_full_export.py [--from 2026-08-01] [--tol-min 10] [--csv путь.csv] [--phones 609546589,570814360]
"""
import argparse
import re

import pandas as pd
import requests

from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from ringostat_stats_profimet import AUTH_KEY

FIELDS = "calldate,caller,dst,call_type,disposition,billsec,duration,uniqueid,n_alias,utm_source,utm_medium,utm_campaign,pool_name,unique_call"


def last9(x):
    d = re.sub(r"\D", "", str(x or ""))
    return d[-9:] if len(d) >= 9 else ""


def fetch(d0):
    r = requests.get("https://api.ringostat.net/calls/list",
                     params={"export_type": "json", "from": f"{d0} 00:00:00", "to": pd.Timestamp.now().strftime("%Y-%m-%d 23:59:59"), "fields": FIELDS},
                     headers={"Auth-key": AUTH_KEY, "Content-Type": "application/json; charset=utf-8"}, timeout=600)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    for c in ("utm_source", "utm_medium", "utm_campaign", "pool_name"):
        df[c] = df[c].fillna("")
    df["ts"] = pd.to_datetime(df["calldate"], errors="coerce", utc=True)
    df = df[df["ts"].notna()].copy()
    df["client9"] = [last9(d) if t == "out" else last9(c) for c, d, t in zip(df["caller"], df["dst"], df["call_type"])]
    df["manager"] = df.apply(lambda r: re.sub(r'["<>].*', "", str(r["caller"])).strip() if r["call_type"] == "out" else "", axis=1)
    df["billsec"] = pd.to_numeric(df["billsec"], errors="coerce").fillna(0).astype(int)
    return df.sort_values("ts", kind="mergesort").reset_index(drop=True)


def match(a, b, tol_min):
    """a, b с колонками p9 и ts; один к одному по ближайшему времени. Возвращает {индекс a: индекс b}."""
    tol, used, found = pd.Timedelta(minutes=tol_min), set(), {}
    by = {p: g.sort_values("ts") for p, g in b.groupby("p9") if p}
    for i, p, ts in zip(a.index, a["p9"], a["ts"]):
        g = by.get(p)
        if g is None:
            continue
        best, bd = None, None
        for j, t in zip(g.index, g["ts"]):
            if j in used:
                continue
            d = abs(t - ts)
            if d <= tol and (bd is None or d < bd):
                best, bd = j, d
        if best is not None:
            used.add(best)
            found[i] = best
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-08-01")
    ap.add_argument("--tol-min", type=float, default=10)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--phones", default="", help="через запятую последние 9 цифр: показать все звонки этих номеров")
    a = ap.parse_args()

    R = fetch(a.d0)
    R["p9"] = R["client9"]
    sheet = load_sheet(SHEET_ID)
    T = sheet[(sheet["type"] == "звонок") & (sheet["ts"] >= pd.Timestamp(a.d0, tz="UTC"))].copy()
    # два прохода: сначала входящие, потом исходящие на ещё не занятые строки (иначе в паре «исходящий + перезвон» строку забирает исходящий)
    f_in = match(R[(R["p9"] != "") & (R["call_type"] == "in")], T, a.tol_min)
    left = T.drop(index=list(f_in.values()))
    f_out = match(R[(R["p9"] != "") & (R["call_type"] != "in")], left, a.tol_min)
    found = {**f_in, **f_out}
    R["в_таблице"] = R.index.isin(found.keys())
    R["строка_таблицы_источник"] = R.index.map(lambda i: T.loc[found[i], "src"] if i in found else "")
    R["строка_таблицы_сайт"] = R.index.map(lambda i: T.loc[found[i], "site"] if i in found else "")
    R["статус_звонка"] = R["disposition"].str.upper().replace({"PROPER": "ANSWERED"})
    print(f"Ringostat {a.d0} … сейчас: звонков {len(R)}; по типу: {R['call_type'].value_counts().to_dict()}; строк-звонков в таблице клиента: {len(T)}")

    print("\n== 1. Какие звонки Ringostat есть в таблице клиента (по типу и статусу) ==")
    g = R.groupby(["call_type", "статус_звонка"]).agg(звонков=("в_таблице", "size"), в_таблице=("в_таблице", "sum"))
    g["доля"] = (100 * g["в_таблице"] / g["звонков"]).round(0).astype(int).astype(str) + "%"
    print(g.to_string())

    print("\n== 2. Входящие: какие попадают в таблицу ==")
    I = R[R["call_type"] == "in"].copy()
    I["категория"] = I["utm_source"].map(lambda s: "реклама/метка" if str(s).lower().strip() not in ("", "(direct)", "(none)") and "дзвінки" not in str(s).lower() and "сайт" not in str(s).lower() else "без метки/пул")
    print(I.groupby(["категория"]).agg(звонков=("в_таблице", "size"), в_таблице=("в_таблице", "sum")).to_string())
    print("\nВходящие, которых НЕТ в таблице, по статусу и длительности разговора:")
    miss = I[~I["в_таблице"]]
    print(miss.groupby("статус_звонка")["billsec"].agg(["size", "median", "max"]).to_string())
    print("\nВходящие в таблице: пул/источник строки (топ):", I[I["в_таблице"]]["строка_таблицы_источник"].value_counts().head(6).to_dict())

    print("\n== 3. Исходящие звонки менеджеров: есть ли они как строки таблицы ==")
    O = R[R["call_type"] == "out"]
    print(f"исходящих {len(O)}; найдено как строка таблицы: {int(O['в_таблице'].sum())}; по менеджерам:", O.groupby("manager")["в_таблице"].agg(["size", "sum"]).to_dict("index"))

    print("\n== 4. Строки-звонки таблицы: какому звонку Ringostat они соответствуют ==")
    T["есть_звонок_в_Ringostat"] = T.index.isin(set(found.values()))
    tt = {j: R.loc[i, "call_type"] for i, j in found.items()}
    T["тип_в_Ringostat"] = T.index.map(lambda j: tt.get(j, "нет звонка"))
    print(pd.crosstab(T["src"], T["тип_в_Ringostat"], margins=True).to_string())

    if a.phones:
        print("\n== 5. Все звонки (входящие и исходящие) по запрошенным номерам ==")
        for p in [x.strip() for x in a.phones.split(",") if x.strip()]:
            x = R[R["p9"] == p].sort_values("ts")
            print(f"\n…{p}: звонков {len(x)}")
            for _, r in x.iterrows():
                print("  ", str(r["ts"].tz_convert("Europe/Warsaw"))[:16], r["call_type"], r["статус_звонка"], f'{r["billsec"]}с', r["manager"] or r["utm_source"] or "—",
                      "| в таблице:" + (f' {r["строка_таблицы_источник"]} ({r["строка_таблицы_сайт"]})' if r["в_таблице"] else " нет"))
    if a.csv:
        R.drop(columns=["calldate"]).to_csv(a.csv, index=False, encoding="utf-8-sig")
        print("\nСохранено:", a.csv)


if __name__ == "__main__":
    main()
