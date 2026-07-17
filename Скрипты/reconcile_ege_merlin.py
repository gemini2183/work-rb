#!/usr/bin/env python
# coding: utf-8
"""Сверка конверсий по кампаниям для ЕГЭ Merlin: Директ vs Метрика+Callibri.

Реализация методологии из
База_знаний/Паттерны/Сверка-конверсий-Директ-Метрика-Коллтрекинг.md,
клиент-специфичный шаг (letnie-фильтр, Source-классификация звонков,
парсинг CampaignId из UTM) — 1:1 с прод-job'ами
callibri2_merlin_ege / ym2_merlin_ege.

Не пересобирает данные — читает уже готовые файлы из Статистика/, которые
должны быть собраны заранее:
    python direct_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" \
        --date-from ... --date-to ... --goals 222490461,40404508
    python metrika_stats_ege_merlin.py --date-from ... --date-to ...
    python callibri_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" \
        --date-from ... --date-to ...

Использование:
    python reconcile_ege_merlin.py --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
import re

import pandas as pd

from _config import client_stats_dir

CLIENT_FOLDER = "ЕГЭ Merlin"
GOAL_ID = "222490461"
CT_GOAL_ID = "40404508"


def load_direct(stats_dir, date_from, date_to):
    path = stats_dir / f"direct_{date_from}_to_{date_to}_goals-{GOAL_ID}-{CT_GOAL_ID}.tsv"
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла {path}. Собери сначала: "
            f"python direct_stats.py --client \"ЕГЭ Merlin\" --client-folder \"ЕГЭ Merlin\" "
            f"--date-from {date_from} --date-to {date_to} --goals {GOAL_ID},{CT_GOAL_ID}"
        )
    df = pd.read_csv(path, sep="\t")
    df["Conv_forma"] = pd.to_numeric(df[f"Conversions_{GOAL_ID}_AUTO"], errors="coerce").fillna(0)
    df["Conv_zvonok"] = pd.to_numeric(df[f"Conversions_{CT_GOAL_ID}_AUTO"], errors="coerce").fillna(0)
    df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
    return df.groupby(["CampaignId", "CampaignName"]).agg(
        Cost=("Cost", "sum"), Clicks=("Clicks", "sum"),
        Direct_forma=("Conv_forma", "sum"), Direct_zvonok=("Conv_zvonok", "sum"),
    ).reset_index()


def load_metrika(stats_dir, date_from, date_to):
    path = stats_dir / f"metrika_yadirect-core_{date_from}_to_{date_to}_goals-{GOAL_ID}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла {path}. Собери сначала: "
            f"python metrika_stats_ege_merlin.py --date-from {date_from} --date-to {date_to}"
        )
    df = pd.read_csv(path)

    def extract_cid(x):
        if not isinstance(x, str):
            return None
        m = re.search(r"\d{6,}", x)
        return m.group(0) if m else None

    df["CampaignId"] = df["UTM Campaign"].apply(extract_cid)
    by_camp = df.groupby("CampaignId")["Goal_visits"].sum().reset_index()
    by_camp = by_camp.rename(columns={"Goal_visits": "Metrika_forma"})
    by_camp["CampaignId"] = by_camp["CampaignId"].astype("Int64")
    return by_camp


def load_callibri(stats_dir, date_from, date_to):
    path = stats_dir / f"callibri_{date_from}_to_{date_to}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла {path}. Собери сначала: "
            f"python callibri_stats.py --client \"ЕГЭ Merlin\" --client-folder \"ЕГЭ Merlin\" "
            f"--date-from {date_from} --date-to {date_to}"
        )
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")

    df["is_letnie"] = df["utm_content"].apply(lambda x: isinstance(x, str) and "letnie" in x)

    def classify(row):
        tt = row["traffic_type"]
        tt_empty = pd.isna(tt) or tt == ""
        if tt_empty and row["conversations_number"] == 1:
            return "Контекст"
        if not tt_empty and isinstance(row["utm_source"], str) and "yandex" in row["utm_source"]:
            return "YaDirect"
        return None

    df["Source"] = df.apply(classify, axis=1)
    df = df[df["Source"].isin(["Контекст", "YaDirect"])]
    df = df[~df["is_letnie"]]
    df["dup"] = df[["phone", "month"]].duplicated()
    df = df[~df["dup"]].copy()

    def extract_cid(x):
        if not isinstance(x, str):
            return None
        m = re.search(r"cid_(\d+)", x)
        return m.group(1) if m else None

    df["CampaignId"] = df["utm_content"].apply(extract_cid)
    no_cid = int(df["CampaignId"].isna().sum())
    by_camp = df[df["CampaignId"].notna()].groupby("CampaignId").size().reset_index(name="Callibri_zvonok")
    by_camp["CampaignId"] = by_camp["CampaignId"].astype("Int64")
    return by_camp, no_cid, len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    stats_dir = client_stats_dir(CLIENT_FOLDER)

    direct = load_direct(stats_dir, args.date_from, args.date_to)
    metrika = load_metrika(stats_dir, args.date_from, args.date_to)
    callibri, no_cid, callibri_total = load_callibri(stats_dir, args.date_from, args.date_to)

    merged = direct.merge(metrika, on="CampaignId", how="left")
    merged = merged.merge(callibri, on="CampaignId", how="left")
    merged = merged.fillna(0)
    merged["Direct_total"] = merged["Direct_forma"] + merged["Direct_zvonok"]
    merged["MK_total"] = merged["Metrika_forma"] + merged["Callibri_zvonok"]
    merged["diff_total"] = merged["MK_total"] - merged["Direct_total"]
    merged = merged.sort_values("Cost", ascending=False)

    pd.set_option("display.width", 200)
    print(f"Период: {args.date_from} → {args.date_to}")
    print()
    print(merged[[
        "CampaignId", "CampaignName", "Cost", "Clicks",
        "Direct_forma", "Metrika_forma", "Direct_zvonok", "Callibri_zvonok",
        "Direct_total", "MK_total", "diff_total",
    ]].to_string(index=False))
    print()
    print(f"Звонков без UTM/cid (не привязать ни к одной кампании): {no_cid} из {callibri_total}")
    print("Эти звонки — только в общий знаменатель заявок клиента, не в разбивку по кампаниям.")

    out_path = stats_dir / f"reconcile_{args.date_from}_to_{args.date_to}.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\nСохранено: {out_path}")


if __name__ == "__main__":
    main()
