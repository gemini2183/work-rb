#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: сопоставление звонков Ringostat с визитами из Supabase (profimet_visits) по client_id. ТОЛЬКО ЧТЕНИЕ (2026-11-05).

Зачем: проверить, что `client_id` звонка (API Ringostat, uuid) равен `rngst.clientId` посетителя, записанному тегом GTM «Визит - rngst и клик
в Supabase», и тем самым вернуть gclid звонкам статических пулов (в них gclid нет). Динамический пул (Google CPC_dyn) — КОНТРОЛЬ: gclid лежит в
`utm_content` звонка (`...|gclid_<значение>`), поэтому для него видно, совпал ли gclid визита с gclid звонка. Если у динамических пары есть, а у статических
нет — проблема статических пулов; если нет ни у тех, ни у других — `client_id` звонка не равен `rngst.clientId`.

Что считается парой: визит с тем же client_id, записанный не позже, чем через 5 минут после времени звонка (визит раньше звонка), берём самый поздний.
Окно по давности клика: 90 дней (дальше Google офлайн-конверсию не принимает). «Calls from ads» пары иметь не должен (визита нет).

    PYTHONUTF8=1 python visit_call_join.py [--from 2026-11-06] [--to ВЧЕРА] [--client ProfiMet]
Пишет Клиенты/<клиент>/Статистика/visit_call_join_<с>_<по>.csv (по звонку: пул, client_id, есть ли визит, gclid визита, gclid звонка, совпадение).
"""
import argparse
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import yaml

from ringostat_stats_profimet import AUTH_KEY

ROOT = Path(__file__).resolve().parent.parent
MON_CFG = "E:/PythonProjects/RedBird/monitoring scripts/monitoring/config/profimet.yaml"
FIELDS = "calldate,caller,call_type,disposition,pool_name,client_id,utm_source,utm_campaign,utm_content,unique_call"


def load_calls(d0, d1):
    r = requests.get("https://api.ringostat.net/calls/list", timeout=600,
                     params={"export_type": "json", "from": f"{d0} 00:00:00", "to": f"{d1} 23:59:59", "fields": FIELDS},
                     headers={"Auth-key": AUTH_KEY, "Content-Type": "application/json; charset=utf-8"})
    r.raise_for_status()
    df = pd.DataFrame(r.json()).fillna("")
    df = df[(df["call_type"] == "in") & (df["utm_source"].str.lower() == "google")].copy()
    df["ts"] = pd.to_datetime(df["calldate"], utc=True, errors="coerce")
    df["gclid_call"] = df["utm_content"].map(lambda x: (re.search(r"gclid_([^|\s]+)", x) or [None, ""])[1])
    return df


def load_visits(sb):
    hd = {"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]}
    rows, start = [], 0
    while True:
        r = requests.get(f"{sb['url']}/rest/v1/profimet_visits", timeout=120, headers={**hd, "Range": f"{start}-{start + 999}"},
                         params={"select": "*", "order": "created_at.asc"})
        r.raise_for_status()
        chunk = r.json()
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000
    v = pd.DataFrame(rows)
    if v.empty:
        return v
    v["ts"] = pd.to_datetime(v["created_at"], utc=True, errors="coerce")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default=(date.today() - timedelta(days=14)).isoformat())
    ap.add_argument("--to", dest="d1", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--client", default="ProfiMet")
    a = ap.parse_args()
    sb = yaml.safe_load(open(MON_CFG, encoding="utf-8"))["supabase"]
    calls, vis = load_calls(a.d0, a.d1), load_visits(sb)
    print(f"Звонков Google (входящие) {a.d0}..{a.d1}: {len(calls)}; визитов в profimet_visits всего: {len(vis)}")
    if vis.empty:
        print("Таблица визитов пуста — тег ещё не опубликован или визитов с кликом не было.")
        return
    print(f"Первый визит в таблице: {vis['ts'].min()}; последний: {vis['ts'].max()}")
    out = []
    for _, c in calls.iterrows():
        cand = vis[(vis["rngst_client_id"] == c["client_id"]) & (vis["ts"] <= c["ts"] + pd.Timedelta(minutes=5))
                   & (vis["ts"] >= c["ts"] - pd.Timedelta(days=90))] if c["client_id"] else vis.iloc[0:0]
        v = cand.sort_values("ts").iloc[-1] if len(cand) else None
        # звонки до запуска тега пары иметь не могут: не считаем их «потерей»
        before_tag = c["ts"] < vis["ts"].min()
        out.append(dict(calldate=c["calldate"], pool=c["pool_name"], utm_campaign=c["utm_campaign"], client_id=c["client_id"],
                        unique_call=c["unique_call"], до_запуска_тега=before_tag, есть_визит=v is not None,
                        gclid_визита=(v["gclid"] if v is not None else ""), consent_визита=(v["consent"] if v is not None else ""),
                        кампания_визита=(v["utm_campaign"] if v is not None else ""),
                        кампания_совпала=((v["utm_campaign"] == c["utm_campaign"]) if v is not None and c["utm_campaign"] else None),
                        gclid_звонка=c["gclid_call"],
                        gclid_совпал=(bool(c["gclid_call"]) and v is not None and v["gclid"] == c["gclid_call"])
                        if c["gclid_call"] else None))
    df = pd.DataFrame(out)
    path = ROOT / "Клиенты" / a.client / "Статистика" / f"visit_call_join_{a.d0}_{a.d1}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    live = df[~df["до_запуска_тега"]]
    print(f"\nПосле запуска тега ({vis['ts'].min():%Y-%m-%d %H:%M} UTC и позже): звонков {len(live)}")
    g = live.groupby("pool").agg(звонков=("client_id", "size"), с_client_id=("client_id", lambda x: (x != "").sum()),
                                 с_визитом=("есть_визит", "sum"),
                                 gclid_у_звонка=("gclid_звонка", lambda x: (x != "").sum()),
                                 gclid_совпал=("gclid_совпал", lambda x: (x == True).sum()),  # noqa: E712
                                 кампания_совпала=("кампания_совпала", lambda x: (x == True).sum()))  # noqa: E712
    print(g.to_string())
    print(f"\nCSV: {path}")
    print("Статические пулы (pmax, demand_gen, yt_*, dspl_*): «с_визитом» — звонки, которым вернули клик; «кампания_совпала» — у найденного визита "
          "та же utm_campaign, что у звонка (проверка прямо на статике). Контроль метода: у Google CPC_dyn «gclid_совпал» близко к «с_визитом».")


if __name__ == "__main__":
    main()
