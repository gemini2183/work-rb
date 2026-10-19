#!/usr/bin/env python
# coding: utf-8
"""Таблица продаж ProfiMet (выгрузка CRM) ↔ Ringostat — ТОЛЬКО ЧТЕНИЕ, в кабинеты и в таблицу ничего не пишет.

Две проверки (запрос пользователя 2026-10-19):

1. АТРИБУЦИЯ ПРОДАЖ. Не уходит ли продажа источнику, который не был первым касанием по номеру телефона
   (перезвон менеджера «Телефон», «Нет метки», SEO) вместо Google Ads / Facebook. Для каждого проданного заказа
   берём все касания того же номера на том же сайте за `--window-days` (по умолчанию 60, как у клиента в дашборде)
   до первой строки, привязанной к заказу, и сравниваем «учтённый» источник (источник первой строки заказа)
   с первым касанием. Дополнительно показываем первый звонок этого номера в Ringostat (касания, которых нет
   в таблице: звонки на маркетплейсы в таблицу не входят, поэтому полной картины нет ни там, ни там).

2. ПОЛНОТА. Все ли уникальные звонки Ringostat (Google Ads и Facebook) есть в таблице продаж. «Уникальный» —
   по признаку `unique_call` из API Ringostat (история с 2023-08-31) и, для сравнения, по нашему множеству
   «первый звонок номера по всем отслеживаемым источникам» (с тем же полным хвостом истории).
   Звонок считается найденным, если в любом листе есть строка «звонок» с тем же номером (последние 9 цифр)
   и временем в пределах `--tol-min` минут.

Ключ Ringostat берётся из `ringostat_stats_profimet.py` (тот же аккаунт ProfiMet), в вывод не попадает.
Таблицу читает сервисный аккаунт (роль «Читатель»).

Использование:
    python profimet_sales_vs_ringostat.py [--window-days 60] [--tol-min 10] [--cache путь.pkl]
Результаты — в `Клиенты/ProfiMet/Статистика/`: sales_attribution_check_<дата>.csv, ringostat_unique_missing_<дата>.csv.
"""
import argparse
import bisect
import pickle
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import gspread
import pandas as pd
import requests
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE, client_stats_dir
from ringostat_stats_profimet import AUTH_KEY, categorize_source

SHEET_ID = "1JsSG9WFOtCht_l3imagYI6SiBFHiRBA0EdHwPbYqUwI"
SHEET_COLS = ["ts_raw", "phone", "type", "src", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
              "gclid", "order", "status", "sale_date", "cancel_date", "reason"]
ATTRIBUTION_SITES = ["mocnaszklarnia.pl", "szklarniaprofimet.pl"]  # Ekspertagro.pl — другой клиент
AD = {"Google Ads", "Facebook"}
RINGO_HISTORY_FROM = "2023-08-31 00:00:00"
COMPARE_FROM = pd.Timestamp("2025-08-01", tz="UTC")


def last9(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-9:] if len(d) >= 9 else d


def load_sheet(sheet_id):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(sheet_id)
    frames = []
    for ws in sh.worksheets():
        if "." not in ws.title:  # лист «О таблице»
            continue
        values = ws.get_all_values()
        df = pd.DataFrame(values[1:], columns=SHEET_COLS)
        df["site"] = ws.title
        frames.append(df)
    df = pd.concat(frames, ignore_index=True).replace("—", "")
    df["ts"] = pd.to_datetime(df["ts_raw"], utc=True)
    df["p9"] = df["phone"].map(last9)
    return df.sort_values("ts", kind="mergesort").reset_index(drop=True)


def fetch_ringostat():
    r = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": RINGO_HISTORY_FROM,
                "to": pd.Timestamp.now().strftime("%Y-%m-%d 23:59:59"),
                "fields": "calldate,caller,disposition,billsec,duration,call_type,uniqueid,utm_source,utm_medium,"
                          "utm_campaign,utm_content,pool_name,unique_call"},
        headers={"Auth-key": AUTH_KEY, "Content-Type": "application/json; charset=utf-8"},
        timeout=300,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    for c in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "pool_name"):
        df[c] = df[c].fillna("")
    df["ts"] = pd.to_datetime(df["calldate"], errors="coerce", utc=True)
    df = df[df["ts"].notna()].copy()
    df["category"] = df.apply(categorize_source, axis=1)
    df["p9"] = df["caller"].map(last9)
    # наше множество: первый звонок номера среди отслеживаемых категорий (как в проде), но с ПОЛНОЙ историей
    tracked = df[df["category"].isin(["Google Ads", "Google SEO", "Facebook", "No Source"])].sort_values("ts", kind="mergesort")
    seen, flag = set(), {}
    for idx, p in zip(tracked.index, tracked["p9"]):
        flag[idx] = p not in seen
        seen.add(p)
    df["our_unique"] = pd.Series(flag).reindex(df.index).fillna(False).astype(bool)
    df["unique_call"] = pd.to_numeric(df["unique_call"], errors="coerce").fillna(0).astype(int)
    return df.sort_values("ts", kind="mergesort").reset_index(drop=True)


# ------------------------------------------------------------------ проверка 1: атрибуция продаж
def check_attribution(sheet, ringo, window_days):
    win = pd.Timedelta(days=window_days)
    by_phone_ringo = {p: g for p, g in ringo[ringo["category"].isin(["Google Ads", "Facebook", "Google SEO", "No Source"])].groupby("p9")}
    rows = []
    for site in ATTRIBUTION_SITES:
        s = sheet[sheet["site"] == site]
        by_phone = {p: g for p, g in s.groupby("p9")}
        for order, grp in s[s["order"] != ""].groupby("order"):
            sale_dates = [d for d in grp["sale_date"] if d]
            if not sale_dates:
                continue  # заказ не дошёл до статуса продажи
            grp = grp.sort_values("ts", kind="mergesort")
            first_linked = grp.iloc[0]
            t0 = first_linked["ts"]
            phones = set(grp["p9"])
            touches = pd.concat([by_phone[p] for p in phones if p in by_phone])
            touches = touches[(touches["ts"] >= t0 - win) & (touches["ts"] <= t0)].sort_values("ts", kind="mergesort")
            first_touch = touches.iloc[0]
            ads = touches[touches["src"].isin(AD)]
            first_ad = ads.iloc[0] if not ads.empty else None
            credited = first_linked["src"] or "Нет метки"
            first_src = first_touch["src"] or "Нет метки"
            if first_ad is None:
                verdict = "НЕТ_РЕКЛАМНОГО_КАСАНИЯ" if credited not in AD else "СОВПАЛО"
            elif credited in AD and credited == first_ad["src"] and first_ad["ts"] <= first_touch["ts"]:
                verdict = "СОВПАЛО"
            elif credited in AD:
                verdict = "ДРУГОЙ_РЕКЛАМНЫЙ_ИСТОЧНИК"
            else:
                verdict = "НЕ_ПРИСВОЕНО"  # учтён не-реклама, а раньше был рекламный контакт
            # то же по Ringostat: первый звонок номера до заказа (в том числе то, чего нет в таблице)
            rg_first = None
            for p in phones:
                g = by_phone_ringo.get(p)
                if g is not None:
                    g = g[(g["ts"] >= t0 - win) & (g["ts"] <= t0)]
                    if not g.empty and (rg_first is None or g.iloc[0]["ts"] < rg_first["ts"]):
                        rg_first = g.iloc[0]
            rows.append({
                "сайт": site, "заказ": order, "телефон": first_linked["phone"],
                "дата продажи": min(sale_dates), "отмена": next((d for d in grp["cancel_date"] if d), ""),
                "первая строка заказа": t0.tz_convert("Europe/Warsaw").strftime("%Y-%m-%d %H:%M"),
                "тип первой строки": first_linked["type"], "учтённый источник": credited,
                "строк у заказа": len(grp), "источники строк заказа": ", ".join(sorted({x or "Нет метки" for x in grp["src"]})),
                "касаний за окно": len(touches), "первое касание": first_touch["ts"].tz_convert("Europe/Warsaw").strftime("%Y-%m-%d %H:%M"),
                "источник первого касания": first_src, "тип первого касания": first_touch["type"],
                "первое рекл. касание": "" if first_ad is None else first_ad["ts"].tz_convert("Europe/Warsaw").strftime("%Y-%m-%d %H:%M"),
                "рекл. источник": "" if first_ad is None else first_ad["src"],
                "кампания рекл. касания": "" if first_ad is None else first_ad["utm_campaign"],
                "рекл. касание→заказ, ч": "" if first_ad is None else round((t0 - first_ad["ts"]).total_seconds() / 3600, 1),
                "Ringostat: первый звонок": "" if rg_first is None else rg_first["ts"].tz_convert("Europe/Warsaw").strftime("%Y-%m-%d %H:%M"),
                "Ringostat: категория": "" if rg_first is None else rg_first["category"],
                "Ringostat: кампания": "" if rg_first is None else rg_first["utm_campaign"],
                "вердикт": verdict,
            })
    return pd.DataFrame(rows)


def print_attribution(res, window_days):
    print(f"\n=== ПРОВЕРКА 1. Атрибуция проданных заказов (окно {window_days} дн. до первой строки заказа) ===")
    print("Учтённый источник = источник первой строки заказа; сравнение с первым касанием по номеру на том же сайте.")
    for site, g in res.groupby("сайт"):
        print(f"\n--- {site}: проданных заказов {len(g)} ---")
        print("Вердикты:", dict(Counter(g["вердикт"])))
        print("Учтённый источник:", dict(Counter(g["учтённый источник"])))
        print("Источник первого касания:", dict(Counter(g["источник первого касания"])))
        m = pd.crosstab(g["учтённый источник"], g["источник первого касания"])
        print("Учтённый (строки) × первое касание (столбцы):")
        print(m.to_string())
        g2 = g.assign(месяц=g["дата продажи"].str[:7])
        t = pd.crosstab(g2["месяц"], g2["вердикт"])
        print("\nПо месяцам продажи:")
        print(t.to_string())
        if (g["вердикт"] == "НЕ_ПРИСВОЕНО").any():
            na = g[g["вердикт"] == "НЕ_ПРИСВОЕНО"]
            print("\nНЕ_ПРИСВОЕНО по рекламному источнику первого рекламного касания:", dict(Counter(na["рекл. источник"])))
            print("Через сколько часов после рекламного касания открыт заказ (медиана / p75 / макс):",
                  na["рекл. касание→заказ, ч"].astype(float).median(), na["рекл. касание→заказ, ч"].astype(float).quantile(.75),
                  na["рекл. касание→заказ, ч"].astype(float).max())
        # то же, но по Ringostat: первый звонок номера
        rg = g[g["Ringostat: категория"] != ""]
        print(f"\nRingostat знает первый звонок (в окне) у {len(rg)} из {len(g)} заказов; категории:", dict(Counter(rg["Ringostat: категория"])))


# ------------------------------------------------------------------ проверка 2: полнота уникальных звонков
def check_completeness(sheet, ringo, tol_min):
    calls_sheet = sheet[sheet["type"] == "звонок"]
    # на номер: отсортированные секунды, источники, листы (calls_sheet уже отсортирован по времени)
    idx = {p: (list(g["ts"].astype("int64") // 10**9), list(g["src"]), list(g["site"])) for p, g in calls_sheet.groupby("p9")}
    any_idx = set(sheet["p9"])

    sel = ringo[(ringo["ts"] >= COMPARE_FROM) & (ringo["category"].isin(AD))].copy()
    gaps, found_src, found_site = [], [], []
    for p9, ts in zip(sel["p9"], sel["ts"]):
        t = int(ts.timestamp())
        best = None
        arr = idx.get(p9)
        if arr:
            times = arr[0]
            i = bisect.bisect_left(times, t)
            for j in (i - 1, i):
                if 0 <= j < len(times):
                    d = times[j] - t
                    if best is None or abs(d) < abs(best[0]):
                        best = (d, j)
        if best is None:
            gaps.append(None); found_src.append(""); found_site.append("")
        else:
            gaps.append(best[0] / 60)
            found_src.append(arr[1][best[1]] or "Нет метки")
            found_site.append(arr[2][best[1]])
    sel["gap_min"] = gaps
    sel["sheet_src"] = found_src
    sel["sheet_site"] = found_site
    sel["found"] = sel["gap_min"].map(lambda x: x is not None and abs(x) <= tol_min)
    sel["phone_anywhere"] = sel["p9"].isin(any_idx)
    return sel


def print_completeness(sel, tol_min):
    print(f"\n=== ПРОВЕРКА 2. Уникальные звонки Ringostat (Google Ads и Facebook) в таблице продаж; допуск ±{tol_min} мин ===")
    print("call_type в выборке:", dict(Counter(sel["call_type"])))
    near = sel["gap_min"].dropna().abs()
    print("Распределение |разница по времени| до ближайшей строки «звонок» с тем же номером, доля звонков:",
          {f"≤{m} мин": round(float((near <= m).sum()) / len(sel), 3) for m in (1, 2, 5, 10, 30, 60, 1440)})
    for label, mask in (("unique_call=1 (признак Ringostat)", sel["unique_call"] == 1),
                        ("наше множество (первый звонок номера, полная история)", sel["our_unique"]),
                        ("ВСЕ звонки категории (для контраста)", sel["unique_call"] >= 0)):
        sub = sel[mask]
        print(f"\n--- {label}: {len(sub)} звонков ---")
        t = sub.assign(месяц=sub["ts"].dt.tz_convert("Europe/Warsaw").dt.strftime("%Y-%m"))
        rep = t.groupby(["месяц", "category"]).agg(всего=("found", "size"), найдено=("found", "sum")).reset_index()
        rep["нет в файле"] = rep["всего"] - rep["найдено"]
        rep["доля найдено"] = (rep["найдено"] / rep["всего"]).round(3)
        print(rep.to_string(index=False))
        tot = sub.groupby("category").agg(всего=("found", "size"), найдено=("found", "sum"))
        tot["нет в файле"] = tot["всего"] - tot["найдено"]
        print("Итого по категориям:\n" + tot.to_string())
    miss = sel[(sel["unique_call"] == 1) & (~sel["found"])]
    print(f"\nУникальные (unique_call=1), которых нет в файле: {len(miss)}")
    print(" disposition:", dict(Counter(miss["disposition"])))
    print(" call_type:", dict(Counter(miss["call_type"])))
    print(" номер вообще есть в файле (любой лист, другое время):", int(miss["phone_anywhere"].sum()), "из", len(miss))
    print(" длительность разговора, сек: 0 =", int((pd.to_numeric(miss["billsec"], errors='coerce').fillna(0) == 0).sum()),
          "; >0 =", int((pd.to_numeric(miss["billsec"], errors='coerce').fillna(0) > 0).sum()))
    ok = sel[(sel["unique_call"] == 1) & sel["found"]]
    print("\nИсточник в таблице у НАЙДЕННЫХ уникальных (Ringostat-категория → источник строки в CRM):")
    print(pd.crosstab(ok["category"], ok["sheet_src"]).to_string())
    return miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=SHEET_ID)
    ap.add_argument("--window-days", type=int, default=60)
    ap.add_argument("--tol-min", type=float, default=10)
    ap.add_argument("--cache", default=None, help="pickle с (sheet, ringo): читается, если есть, иначе создаётся (для повторных прогонов)")
    ap.add_argument("--client-folder", default="ProfiMet")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(a.sheet_id), fetch_ringostat()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    print(f"Таблица: {len(sheet)} строк, {sheet['ts'].min():%Y-%m-%d} — {sheet['ts'].max():%Y-%m-%d}; по листам: {dict(Counter(sheet['site']))}")
    print(f"Ringostat: {len(ringo)} звонков, {ringo['ts'].min():%Y-%m-%d} — {ringo['ts'].max():%Y-%m-%d}; категории: {dict(Counter(ringo['category']))}")

    out_dir = client_stats_dir(a.client_folder)
    stamp = date.today().isoformat()

    res = check_attribution(sheet, ringo, a.window_days)
    print_attribution(res, a.window_days)
    p1 = out_dir / f"sales_attribution_check_{stamp}.csv"
    res.to_csv(p1, index=False, encoding="utf-8-sig")

    sel = check_completeness(sheet, ringo, a.tol_min)
    miss = print_completeness(sel, a.tol_min)
    p2 = out_dir / f"ringostat_unique_missing_{stamp}.csv"
    cols = ["ts", "caller", "category", "call_type", "disposition", "billsec", "unique_call", "our_unique", "utm_campaign", "pool_name",
            "gap_min", "sheet_src", "sheet_site", "phone_anywhere"]
    miss[cols].assign(ts=miss["ts"].dt.tz_convert("Europe/Warsaw").dt.strftime("%Y-%m-%d %H:%M:%S")).to_csv(p2, index=False, encoding="utf-8-sig")
    print(f"\n(сохранено: {p1}\n            {p2})")


if __name__ == "__main__":
    main()
