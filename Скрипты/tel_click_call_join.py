#!/usr/bin/env python
# coding: utf-8
"""EkspertAgro: сопоставление звонков Ringostat с нажатиями на tel: из Supabase (expertagro_tel_clicks) по времени. ТОЛЬКО ЧТЕНИЕ (2026-11-12).

Зачем: у статических пулов звонок приходит без gclid, `client_id` звонка не равен cookie посетителя. Здесь звонок связывается с нажатием по окну в
секундах до звонка. Меряет то, что в заготовке задачи помечено «не измерено»: (1) задержка нажатие → звонок; (2) сколько нажатий в окне
(неоднозначность: нажатий разных посетителей); (3) сколько звонков на статические пулы PMax приходит; (4) совпала ли кампания звонка и нажатия.

Правило пары: нажатие не позже звонка (допуск вперёд 5 с на расхождение часов), ближайшее до звонка в окне N секунд. «Однозначная» пара — в окне
ровно одно нажатие (или одно с тем же номером, если номер нажатия совпал с n_alias звонка). Окна: 5 / 15 / 30 / 60 / 120 секунд.
Звонки раньше запуска тега (первая строка таблицы) пары иметь не могут и в долю не входят. Время звонка — `calldate` (в ответе API с поясом, +0100;
сверено с `uniqueid`, он содержит UNIX-время начала звонка). Секунды в `calldate` целые: точность пары ±1 с.

    PYTHONUTF8=1 python tel_click_call_join.py [--from 2026-11-13] [--to СЕГОДНЯ] [--client EkspertAgro] [--pool-filter pmax]
Пишет Клиенты/<клиент>/Статистика/tel_click_call_join_<с>_<по>.csv.
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml

CFG = {"EkspertAgro": ("E:/PythonProjects/RedBird/monitoring scripts/monitoring/config/experagro.yaml", "expertagro_tel_clicks")}
ROOT = Path(__file__).resolve().parent.parent
FIELDS = "calldate,caller,call_type,disposition,pool_name,client_id,utm_source,utm_campaign,utm_content,unique_call,uniqueid,n_alias,duration"
WINDOWS = [5, 15, 30, 60, 120]


def digits(x):
    return "".join(ch for ch in str(x) if ch.isdigit())


def load_calls(key, d0, d1, pool_filter):
    r = requests.get("https://api.ringostat.net/calls/list", timeout=600,
                     params={"export_type": "json", "from": f"{d0} 00:00:00", "to": f"{d1} 23:59:59", "fields": FIELDS},
                     headers={"Auth-key": key, "Content-Type": "application/json; charset=utf-8"})
    r.raise_for_status()
    if not r.text.strip():
        return pd.DataFrame()
    df = pd.DataFrame(r.json()).fillna("")
    if df.empty:
        return df
    df = df[(df["call_type"] == "in") & (df["utm_source"].str.lower() == "google")].copy()
    if pool_filter:
        df = df[df["pool_name"].str.lower().str.contains(pool_filter.lower())].copy()
    df["ts"] = pd.to_datetime(df["calldate"], utc=True, errors="coerce")  # calldate с поясом (+0100), сверено с uniqueid 12.11
    df["ts_ms"] = (df["ts"].astype("int64") // 10**6)
    return df


def load_taps(sb, table):
    hd = {"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]}
    rows, start = [], 0
    while True:
        r = requests.get(f"{sb['url']}/rest/v1/{table}", timeout=120, headers={**hd, "Range": f"{start}-{start + 999}"},
                         params={"select": "*", "order": "ts_ms.asc"})
        r.raise_for_status()
        chunk = r.json()
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="EkspertAgro", choices=list(CFG))
    ap.add_argument("--from", dest="d0", default=None)
    ap.add_argument("--to", dest="d1", default=date.today().isoformat())
    ap.add_argument("--pool-filter", default="pmax", help="подстрока в названии пула (по умолчанию pmax); пусто — все Google")
    a = ap.parse_args()
    cfg_path, table = CFG[a.client]
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    taps = load_taps(cfg["supabase"], table)
    if taps.empty:
        print(f"Таблица {table} пуста — тег не опубликован или нажатий не было.")
        return
    first = int(taps["ts_ms"].min())
    d0 = a.d0 or pd.to_datetime(first, unit="ms", utc=True).date().isoformat()
    calls = load_calls(cfg["ringostat"]["auth_key"], d0, a.d1, a.pool_filter)
    print(f"Нажатий в {table}: {len(taps)} (первое {pd.to_datetime(first, unit='ms', utc=True):%Y-%m-%d %H:%M} UTC, "
          f"с клиентским id: {(taps['rngst_client_id'] != '').sum()}, с gclid/gbraid/wbraid: {(taps['click_key'] != '').sum()})")
    if calls.empty:
        print(f"Звонков Google {a.pool_filter or 'все пулы'} за {d0}..{a.d1}: 0")
        return
    calls = calls[calls["ts_ms"] >= first - 5000].copy()
    print(f"Звонков Google (входящие, пул «{a.pool_filter or 'любой'}») после запуска тега, {d0}..{a.d1}: {len(calls)}")
    t_ms = taps["ts_ms"].astype("int64").to_numpy()
    out = []
    for _, c in calls.iterrows():
        row = dict(calldate=c["calldate"], pool=c["pool_name"], utm_campaign=c["utm_campaign"], n_alias=c["n_alias"],
                   duration=c["duration"], unique_call=c["unique_call"], client_id=c["client_id"])
        prev = taps[(taps["ts_ms"] <= c["ts_ms"] + 5000)]
        near = prev[prev["ts_ms"] >= c["ts_ms"] - 600_000]
        row["нажатий за 10 мин до звонка"] = len(near)
        if len(near):
            last = near.iloc[-1]
            row["задержка_с_до_ближайшего"] = round((c["ts_ms"] - int(last["ts_ms"])) / 1000, 1)
        else:
            row["задержка_с_до_ближайшего"] = None
        for w in WINDOWS:
            cand = prev[prev["ts_ms"] >= c["ts_ms"] - w * 1000]
            same_num = cand[cand["phone_href"].map(digits).str.endswith(digits(c["n_alias"])[-9:])] if digits(c["n_alias"]) else cand
            row[f"нажатий_{w}с"] = len(cand)
            row[f"с_тем_же_номером_{w}с"] = len(same_num)
            pick = (same_num if len(same_num) else cand)
            if len(pick):
                p = pick.iloc[-1]
                row[f"кампания_совпала_{w}с"] = (p["utm_campaign"] == c["utm_campaign"])
                row[f"gclid_{w}с"] = p["click_key"] if len(pick) == 1 else ""
        out.append(row)
    df = pd.DataFrame(out)
    path = ROOT / "Клиенты" / a.client / "Статистика" / f"tel_click_call_join_{d0}_{a.d1}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    n = len(df)
    print("\nОкно N с: звонков с хотя бы одним нажатием | однозначно (ровно 1, по номеру если есть) | неоднозначно (>1) | кампания совпала у однозначных | однозначных с gclid")
    for w in WINDOWS:
        has = df[df[f"нажатий_{w}с"] > 0]
        key = df[f"с_тем_же_номером_{w}с"]
        uniq = df[key == 1]
        amb = df[key > 1]
        camp = (uniq[f"кампания_совпала_{w}с"] == True).sum()  # noqa: E712
        gc = (uniq[f"gclid_{w}с"] != "").sum()
        print(f"  {w:>3} с: {len(has)}/{n} | {len(uniq)} | {len(amb)} | {camp} | {gc}")
    d = df["задержка_с_до_ближайшего"].dropna()
    if len(d):
        print(f"\nЗадержка нажатие → звонок (ближайшее нажатие за 10 мин, звонков {len(d)}): медиана {d.median():.0f} с, 90-й процентиль {d.quantile(.9):.0f} с, "
              f"≤60 с у {(d <= 60).mean():.0%}")
    print(f"Звонков без нажатия за 10 мин: {int((df['нажатий за 10 мин до звонка'] == 0).sum())} из {n} (десктоп, блокировщик, звонок не с сайта, нажатие не поймано)")
    print(f"\nCSV: {path}")
    print("Критерий (реестр Э-…): успех — ≥5 однозначных пар в окне ≤60 с с совпавшей кампанией за 14 дней; стоп — задержка >60 с чаще 30% или "
          "неоднозначных >30% или звонков <5 за 14 дней («данных нет»).")


if __name__ == "__main__":
    main()
