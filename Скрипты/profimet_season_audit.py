#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: проверка выгрузки продаж CRM за сезон — ТОЛЬКО ЧТЕНИЕ (решение пользователя 2026-10-20).

Сезон = с `--season-from` (по умолчанию 2026-08-01). История для правила повторного обращения берётся с начала выгрузки
(01.08.2025), чтобы обращение 5 августа не считалось «новым», если тот же номер обращался в июле.

Проверка 1. Полнота и источники:
  а) каждый звонок Ringostat сезона (входящие и исходящие; номер клиента — `caller` у входящих, `dst` у исходящих)
     ищется в выгрузке по номеру и времени (допуск `--tol-min`); таблицы: найдено / нет в файле по типу и категории Ringostat;
  б) обратно: звонки выгрузки, которых нет в Ringostat, и что за звонок Ringostat стоит за каждым источником выгрузки
     (особенно «Телефон» и «Нет метки»: исходящий менеджера или входящий с рекламной меткой);
  в) формы: согласованность источника строки с UTM и gclid той же строки (источник «Нет метки» при gclid и т.п.).
Проверка 2. Повторное обращение по правилу `--window-days` (60): обращение (звонок или форма) повторное, если у того же
  номера на том же сайте было любое обращение за предыдущие N дней; сравнение с `unique_call` Ringostat и с нашим множеством.

Использование:
    PYTHONIOENCODING=utf-8 python profimet_season_audit.py [--season-from 2026-08-01] [--cache путь.pkl] > вывод.txt
Запускать без -I. Результаты — `Клиенты/ProfiMet/Статистика/season_audit_*.csv`.
"""
import argparse
import bisect
import pickle
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from _config import client_stats_dir
from profimet_sales_vs_ringostat import AD, SHEET_ID, last9, load_sheet
from ringostat_stats_profimet import AUTH_KEY, categorize_source

W = "Europe/Warsaw"
RINGO_FROM = "2023-08-31 00:00:00"


def fetch_ringostat_full():
    r = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": RINGO_FROM, "to": pd.Timestamp.now().strftime("%Y-%m-%d 23:59:59"),
                "fields": "calldate,caller,dst,disposition,billsec,duration,call_type,uniqueid,utm_source,utm_medium,"
                          "utm_campaign,utm_content,pool_name,unique_call"},
        headers={"Auth-key": AUTH_KEY, "Content-Type": "application/json; charset=utf-8"}, timeout=300)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    for c in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "pool_name", "dst", "caller"):
        df[c] = df[c].fillna("")
    df["ts"] = pd.to_datetime(df["calldate"], errors="coerce", utc=True)
    df = df[df["ts"].notna()].copy()
    df["category"] = df.apply(categorize_source, axis=1)
    df["unique_call"] = pd.to_numeric(df["unique_call"], errors="coerce").fillna(0).astype(int)
    # номер клиента: входящий — caller, исходящий — dst
    df["p9"] = [last9(c) if t != "out" else last9(d) for c, d, t in zip(df["caller"], df["dst"], df["call_type"])]
    # наше множество: первый звонок номера среди отслеживаемых входящих категорий, полная история
    tracked = df[(df["call_type"] == "in") & df["category"].isin(["Google Ads", "Google SEO", "Facebook", "No Source"])].sort_values("ts", kind="mergesort")
    seen, flag = set(), {}
    for idx, p in zip(tracked.index, tracked["p9"]):
        flag[idx] = p not in seen
        seen.add(p)
    df["our_unique"] = pd.Series(flag).reindex(df.index).astype("boolean").fillna(False).astype(bool)
    return df.sort_values("ts", kind="mergesort").reset_index(drop=True)


# Набранные номера, которые ведут на другие листы выгрузки (проверено 2026-10-20 по соответствию звонок→строка с 01.08.2025):
# SEO-номер пула SeoMocna → szklarniaprofimet.pl (2194 из 2196), свободный номер без пула → Ekspertagro.pl (1266 из 1266).
OTHER_SITE_NUMBERS = {"48794715855": "szklarniaprofimet.pl (SEO, пул SeoMocna)", "48579774289": "Ekspertagro.pl (номер без пула)"}


def prod_unique(ringo, count_other=False, date_to=None, window_days=60, history_from="2025-08-01", new_scheme_from="2026-08-01"):
    """Копия алгоритма боевого скрипта ringostat_profimet2/main.py (схема с 2026-10-16): только входящие, единая уникальность
    по caller среди учитываемых категорий (при count_other=False — только Google Ads / Google SEO / Facebook / No Source),
    окно window_days дней от ПОСЛЕДНЕГО засчитанного звонка (даты календарные, повторы окно не продлевают), в результат
    только засчитанные звонки с new_scheme_from. date_to — последняя дата включительно (в бою: вчера)."""
    d = ringo[(ringo["call_type"] == "in")].copy()
    d["local"] = d["ts"].dt.tz_convert(W).dt.tz_localize(None)
    d = d[d["local"] >= pd.Timestamp(history_from)]
    if date_to is not None:
        d = d[d["local"] < pd.Timestamp(date_to) + pd.Timedelta(days=1)]
    if not count_other:
        d = d[d["category"].isin(["Google Ads", "Google SEO", "Facebook", "No Source"])]
    last, rows = {}, []
    for r in d.sort_values("local", kind="mergesort").itertuples(index=False):
        day = r.local.date()
        prev = last.get(r.caller)
        if prev is not None and (day - prev).days <= window_days:
            continue
        last[r.caller] = day
        if r.category in ("Google Ads", "Google SEO", "Facebook", "No Source") and day >= pd.Timestamp(new_scheme_from).date():
            rows.append({"date": day, "category": r.category, "caller": r.caller, "uniqueid": r.uniqueid, "dst": r.dst, "ts": r.ts})
    return pd.DataFrame(rows)


def check_prod_unique(ringo):
    print("\n=== Боевое правило уникальности (копия ringostat_profimet2): проверка на контрольных числах из комментария скрипта ===")
    print("Контроль из комментария боевого скрипта за 01.08–15.10: Google Ads 261 (False) / 253 (True), SEO 110 / 101, Facebook 60 / 60")
    for flag in (False, True):
        u = prod_unique(ringo, count_other=flag, date_to="2026-10-15")
        print(f"  count_other={flag}:", dict(Counter(u["category"])))
    return prod_unique(ringo, count_other=False, date_to=pd.Timestamp.now(tz=W).date() - pd.Timedelta(days=1))


def match_calls(ringo_season, sheet_calls, tol_min):
    """Соответствие «один к одному»: каждому звонку Ringostat — ближайшая ещё не занятая строка-звонок выгрузки с тем же
    номером в пределах допуска. Входящие обрабатываются раньше исходящих (иначе исходящий менеджера «прилипает» к строке
    только что состоявшегося входящего). Колонки результата: gap_min, sheet_src, sheet_site, sheet_row, found."""
    idx = {p: (list(g["ts"].astype("int64") // 10**9), list(g["src"]), list(g["site"]), list(g.index)) for p, g in sheet_calls.groupby("p9")}
    used = set()
    tol = tol_min * 60
    res = {}
    order = sorted(range(len(ringo_season)), key=lambda i: (ringo_season["call_type"].iloc[i] != "in", ringo_season["ts"].iloc[i]))
    for i in order:
        p9, ts = ringo_season["p9"].iloc[i], ringo_season["ts"].iloc[i]
        t = int(ts.timestamp())
        arr = idx.get(p9)
        best = None
        if arr:
            k = bisect.bisect_left(arr[0], t)
            for j in range(max(0, k - 6), min(len(arr[0]), k + 6)):
                d = arr[0][j] - t
                if abs(d) <= tol and arr[3][j] not in used and (best is None or abs(d) < abs(best[0])):
                    best = (d, j)
            if best is None:  # для отчёта: ближайшая строка вне допуска или занятая
                for j in (k - 1, k):
                    if 0 <= j < len(arr[0]):
                        d = arr[0][j] - t
                        if best is None or abs(d) < abs(best[0]):
                            best = (d, j)
                        res[i] = (d / 60, "", "", None, False)
                if i in res:
                    continue
        if best is None:
            res[i] = (None, "", "", None, False)
        else:
            d, j = best
            ok = abs(d) <= tol
            if ok:
                used.add(arr[3][j])
            res[i] = (d / 60, arr[1][j] or "Нет метки" if ok else "", arr[2][j] if ok else "", arr[3][j] if ok else None, ok)
    out = ringo_season.copy()
    out["gap_min"] = [res[i][0] for i in range(len(out))]
    out["sheet_src"] = [res[i][1] for i in range(len(out))]
    out["sheet_site"] = [res[i][2] for i in range(len(out))]
    out["sheet_row"] = [res[i][3] for i in range(len(out))]
    out["found"] = [res[i][4] for i in range(len(out))]
    return out


def is_market(pool):
    p = str(pool).lower()
    return "маркетплейс" in p or "allegro" in p or "olx" in p or "erli" in p or "ceneo" in p


def check_calls(sheet_all, ringo, season_from, tol_min, out_dir, stamp):
    s0 = pd.Timestamp(season_from, tz=W)
    sheet_calls = sheet_all[(sheet_all["type"] == "звонок")]  # все листы: звонки SEO лежат в szklarniaprofimet.pl
    rs = ringo[(ringo["ts"] >= s0) & (ringo["call_type"].isin(["in", "out"]))].copy()
    # один аккаунт Ringostat обслуживает три сайта; лист mocnaszklarnia.pl — всё, кроме номеров других сайтов
    other = rs["dst"].isin(OTHER_SITE_NUMBERS) & (rs["call_type"] == "in")
    print(f"Звонков на номера других сайтов (в проверку не входят): {int(other.sum())}; по номерам:", dict(Counter(rs[other]['dst'])))
    rs = rs[~other]
    m = match_calls(rs, sheet_calls, tol_min)
    print(f"\n=== ПРОВЕРКА 1а. Звонки Ringostat с {season_from} (входящие и исходящие) → есть ли строка в выгрузке (±{tol_min} мин) ===")
    t = m.groupby(["call_type", "category"]).agg(всего=("found", "size"), найдено=("found", "sum")).reset_index()
    t["нет в файле"] = t["всего"] - t["найдено"]
    t["доля найдено"] = (t["найдено"] / t["всего"]).round(3)
    print(t.to_string(index=False))
    mi = m[(m["call_type"] == "in") & (~m["found"])]
    print(f"\nВходящие, которых нет в файле: {len(mi)} из {int((m['call_type']=='in').sum())}")
    print(" по категории:", dict(Counter(mi["category"])), "\n по ответу:", dict(Counter(mi["disposition"])))
    print(" по пулу номеров (первые):", dict(Counter(mi["pool_name"]).most_common(8)))
    print(" по месяцу:", dict(Counter(mi["ts"].dt.tz_convert(W).dt.strftime("%Y-%m"))))
    mk = mi[mi["pool_name"].map(is_market)]
    print(f" на номера маркетплейсов (по описанию выгрузки в неё не входят): {len(mk)}")
    mi2 = mi[~mi["pool_name"].map(is_market)]
    print(" последние 2 суток (возможен лаг ночной синхронизации):", int((mi2["ts"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)).sum()))
    mi_old = mi2[mi2["ts"] < pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)]
    print(" без маркетплейсов и без последних 2 суток:", len(mi_old), "; из них уникальные (unique_call=1):", int((mi_old["unique_call"] == 1).sum()),
          "; рекламные Google/Facebook:", int(mi_old["category"].isin(AD).sum()), "; категории:", dict(Counter(mi_old["category"])))
    print(" их пулы номеров:", dict(Counter(mi_old["pool_name"]).most_common(8)), "\n их ответ:", dict(Counter(mi_old["disposition"])),
          "\n разговор > 0 сек:", int((pd.to_numeric(mi_old["billsec"], errors="coerce").fillna(0) > 0).sum()))
    ino = m[(m["call_type"] == "in") & (m["category"] == "Other") & m["found"]]
    print("\n Входящие категории Other (нет рекламной метки в Ringostat), найденные в файле: пул номеров × источник в выгрузке")
    print(pd.crosstab(ino["pool_name"].replace("", "(нет пула)"), ino["sheet_src"]).to_string())
    mo = m[(m["call_type"] == "out") & (~m["found"])]
    print(f"\nИсходящие звонки менеджеров, которых нет в файле: {len(mo)} из {int((m['call_type']=='out').sum())} (в выгрузку исходящие, возможно, не входят — проверить в описании)")
    cols = ["ts", "call_type", "caller", "dst", "category", "disposition", "billsec", "unique_call", "utm_source", "utm_campaign", "pool_name", "gap_min"]
    m[(~m["found"]) & (m["call_type"] == "in")][cols].to_csv(out_dir / f"season_audit_ringostat_in_missing_{stamp}.csv", index=False, encoding="utf-8-sig")

    print("\n=== ПРОВЕРКА 1б. Что стоит за источником строки выгрузки (найденные звонки): тип и категория Ringostat × источник в выгрузке ===")
    f = m[m["found"]]
    print(pd.crosstab([f["call_type"], f["category"]], f["sheet_src"]).to_string())

    # обратно: строки-звонки выгрузки сезона, которым нет пары в Ringostat
    sc = sheet_calls[sheet_calls["ts"] >= s0].copy()
    used = set(f["sheet_row"].dropna().astype(int))
    sc["paired"] = [i in used for i in sc.index]
    # то же, но в обратную сторону по ближайшему звонку любого типа (чтобы не терять звонки, спаренные другим звонком Ringostat)
    r_idx = {p: sorted(g["ts"].astype("int64") // 10**9) for p, g in ringo[ringo["call_type"].isin(["in", "out"])].groupby("p9")}
    near = []
    for p9, ts in zip(sc["p9"], sc["ts"]):
        arr = r_idx.get(p9)
        t = int(ts.timestamp())
        if not arr:
            near.append(None); continue
        i = bisect.bisect_left(arr, t)
        c = [abs(arr[j] - t) / 60 for j in (i - 1, i) if 0 <= j < len(arr)]
        near.append(min(c))
    sc["near_ringostat_min"] = near
    sc["has_ringostat"] = sc["near_ringostat_min"].map(lambda x: x is not None and x <= tol_min)
    print(f"\nСтроки-звонки выгрузки с {season_from}: {len(sc)}; без звонка в Ringostat (±{tol_min} мин): {int((~sc['has_ringostat']).sum())}")
    print(" по источнику:", dict(Counter(sc[~sc["has_ringostat"]]["src"].replace("", "Нет метки"))))
    sc[~sc["has_ringostat"]][["ts", "phone", "src", "utm_source", "utm_campaign", "order", "status", "near_ringostat_min"]].to_csv(
        out_dir / f"season_audit_sheet_calls_not_in_ringostat_{stamp}.csv", index=False, encoding="utf-8-sig")
    return m


def check_forms(sheet, season_from):
    s0 = pd.Timestamp(season_from, tz=W)
    f = sheet[(sheet["type"] == "форма") & (sheet["ts"] >= s0)].copy()
    f["src"] = f["src"].replace("", "Нет метки")
    f["gclid_есть"] = f["gclid"] != ""
    low = f["utm_source"].str.lower()
    f["utm_класс"] = ["google" if "google" in u else "facebook" if ("facebook" in u or "fb" == u or u.startswith("fb")) else "пусто" if u == "" else "другое" for u in low]
    print(f"\n=== ПРОВЕРКА 1в. Формы сайта с {season_from}: {len(f)} ===")
    print("по источнику в выгрузке:", dict(Counter(f["src"])))
    print("\nИсточник × (gclid есть?) × UTM-источник:")
    print(f.groupby(["src", "gclid_есть", "utm_класс"]).size().to_string())
    bad = f[((f["gclid_есть"]) | (f["utm_класс"] == "google")) & (f["src"] != "Google Ads")]
    bad2 = f[(f["utm_класс"] == "facebook") & (f["src"] != "Facebook")]
    bad3 = f[(f["src"] == "Google Ads") & (~f["gclid_есть"]) & (f["utm_класс"] != "google")]
    print(f"\nГугл-признак (gclid или utm google) у строки, а источник не Google Ads: {len(bad)}; источники таких строк:", dict(Counter(bad['src'])))
    print(f"Facebook-признак, а источник не Facebook: {len(bad2)}")
    print(f"Источник Google Ads без gclid и без utm google: {len(bad3)}")
    return f


def check_unique(sheet, ringo_m, ringo, season_from, window_days, out_dir, stamp, site):
    s0 = pd.Timestamp(season_from, tz=W)
    d = sheet[sheet["site"] == site].sort_values("ts", kind="mergesort").copy()
    d["src2"] = d["src"].replace("", "Нет метки")
    win = pd.Timedelta(days=window_days)
    times = {}
    gap_any, gap_cust = [], []
    # gap_any: прошлое обращение любого типа и источника; gap_cust: без строк «Телефон» (перезвоны менеджера)
    by_phone = {p: g for p, g in d.groupby("p9")}
    for p9, g in by_phone.items():
        prev_any, prev_cust = None, None
        for idx, ts, s2 in zip(g.index, g["ts"], g["src2"]):
            gap_any.append((idx, None if prev_any is None else (ts - prev_any)))
            gap_cust.append((idx, None if prev_cust is None else (ts - prev_cust)))
            prev_any = ts
            if s2 != "Телефон":
                prev_cust = ts
    d["gap_any"] = pd.Series({i: v for i, v in gap_any})
    d["gap_cust"] = pd.Series({i: v for i, v in gap_cust})
    d["new60_any"] = d["gap_any"].map(lambda x: pd.isna(x) or x > win)
    d["new60_cust"] = d["gap_cust"].map(lambda x: pd.isna(x) or x > win)
    s = d[d["ts"] >= s0].copy()
    s["мес"] = s["ts"].dt.tz_convert(W).dt.strftime("%Y-%m")

    # unique_call Ringostat для найденных звонков (по паре звонок→строка)
    pair = ringo_m[ringo_m["found"] & (ringo_m["call_type"] == "in")].dropna(subset=["sheet_row"])
    uc = dict(zip(pair["sheet_row"].astype(int), pair["unique_call"]))
    ou = dict(zip(pair["sheet_row"].astype(int), pair["our_unique"]))
    s["unique_call"] = s.index.map(lambda i: uc.get(i))
    s["our_unique"] = s.index.map(lambda i: ou.get(i))

    print(f"\n=== ПРОВЕРКА 2. Повторное обращение по правилу {window_days} дн ({site}, с {season_from}; история выгрузки с {d['ts'].min():%Y-%m-%d}) ===")
    print("Строк-обращений сезона:", len(s), "; звонков:", int((s['type'] == 'звонок').sum()), "; форм:", int((s['type'] == 'форма').sum()))
    for name, mask in (("все обращения", s["type"].isin(["звонок", "форма"])), ("только звонки", s["type"] == "звонок")):
        x = s[mask]
        t = x.groupby("src2").agg(обращений=("ts", "size"), новых_A_любое_прошлое=("new60_any", "sum"), новых_B_без_Телефон=("new60_cust", "sum")).reset_index()
        tot = pd.DataFrame([{"src2": "ИТОГО", "обращений": len(x), "новых_A_любое_прошлое": int(x["new60_any"].sum()), "новых_B_без_Телефон": int(x["new60_cust"].sum())}])
        print(f"\n{name} (А: любое прошлое обращение сбрасывает счётчик; B: перезвоны «Телефон» не считаются прошлым):")
        print(pd.concat([t, tot]).to_string(index=False))
    # Ringostat unique_call против правила 60 дн — только для звонков с парой в Ringostat
    c = s[(s["type"] == "звонок") & s["unique_call"].notna()].copy()
    c["unique_call"] = c["unique_call"].astype(int)
    print(f"\nЗвонки с парой в Ringostat: {len(c)}. Правило 60 дн (A) × unique_call Ringostat:")
    print(pd.crosstab(c["new60_any"], c["unique_call"], rownames=["новое по 60 дн (A)"], colnames=["unique_call"]).to_string())
    print("То же (B, без «Телефон»):")
    print(pd.crosstab(c["new60_cust"], c["unique_call"], rownames=["новое по 60 дн (B)"], colnames=["unique_call"]).to_string())
    print("\nПо месяцам и источникам — звонки: всего / новых по 60 дн (A) / unique_call=1 / наше множество:")
    tt = c.groupby(["мес", "src2"]).agg(всего=("ts", "size"), новых_60=("new60_any", "sum"), unique_call=("unique_call", "sum"), наше=("our_unique", "sum")).reset_index()
    print(tt.to_string(index=False))
    s[["ts", "phone", "type", "src2", "utm_campaign", "gclid", "order", "status", "new60_any", "new60_cust", "unique_call", "our_unique"]].assign(
        ts=s["ts"].dt.tz_convert(W).dt.strftime("%Y-%m-%d %H:%M:%S")).to_csv(out_dir / f"season_audit_contacts_{stamp}.csv", index=False, encoding="utf-8-sig")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-from", default="2026-08-01")
    ap.add_argument("--tol-min", type=float, default=10)
    ap.add_argument("--window-days", type=int, default=60)
    ap.add_argument("--site", default="mocnaszklarnia.pl")
    ap.add_argument("--cache", default=None, help="pickle (sheet, ringo_full): читается, если есть, иначе создаётся")
    ap.add_argument("--client-folder", default="ProfiMet")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    sheet_all = sheet
    sheet = sheet[sheet["site"] == a.site].copy()
    print(f"Выгрузка {a.site}: {len(sheet)} строк, {sheet['ts'].min():%Y-%m-%d} — {sheet['ts'].max():%Y-%m-%d %H:%M} (UTC); все листы: {dict(Counter(sheet_all['site']))}; Ringostat: {len(ringo)} звонков до {ringo['ts'].max():%Y-%m-%d %H:%M}")
    out_dir, stamp = client_stats_dir(a.client_folder), date.today().isoformat()
    m = check_calls(sheet_all, ringo, a.season_from, a.tol_min, out_dir, stamp)
    check_forms(sheet, a.season_from)
    prod = check_prod_unique(ringo)
    check_unique(sheet, m, ringo, a.season_from, a.window_days, out_dir, stamp, a.site)


if __name__ == "__main__":
    main()
