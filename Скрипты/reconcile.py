#!/usr/bin/env python
# coding: utf-8
"""Сверка конверсий по кампаниям: Директ vs Метрика+Callibri.

Реализация методологии из
База_знаний/Паттерны/Сверка-конверсий-Директ-Метрика-Коллтрекинг.md.
Общий скрипт для всех клиентов — сопоставление идёт по CampaignId, а UTM-метки
устроены одинаково во всех проектах: Директ отдаёт CampaignId готовым числом
в отчёте, Метрика передаёт его в UTM Campaign, Callibri — как cid_<id> внутри
utm_content. Клиент-специфичны только сами данные (goal_id, letnie/pyton-фильтры
и т.п.) — они уже применены на этапе сбора (metrika_stats_<клиент>.py,
callibri_stats_<клиент>.py), сюда попадают чистыми.

Не собирает данные сам — сначала нужно прогнать для клиента:
    direct_stats.py     (с --goals <goal_id>,<ct_goal_id>)
    metrika_stats.py     (или клиент-специфичный metrika_stats_<клиент>.py)
    callibri_stats.py    (или клиент-специфичный callibri_stats_<клиент>.py)
за тот же период, файлы должны лежать в Клиенты/<клиент>/Статистика/.

Использование:
    python reconcile.py --client-folder "ЕГЭ Merlin" --goal-id 222490461 \
        --ct-goal-id 40404508 --date-from 2026-06-01 --date-to 2026-07-17
"""
import argparse
import glob
import re

import pandas as pd

from _config import client_stats_dir


def _find_file(stats_dir, pattern):
    matches = glob.glob(str(stats_dir / pattern))
    if not matches:
        raise FileNotFoundError(
            f"Нет файла по шаблону {pattern} в {stats_dir}. "
            f"Собери сначала данные за этот период."
        )
    return matches[0]


def load_direct(stats_dir, date_from, date_to, goal_id, ct_goal_id):
    path = _find_file(stats_dir, f"direct_{date_from}_to_{date_to}*.tsv")
    df = pd.read_csv(path, sep="\t")
    df["Conv_forma"] = pd.to_numeric(df[f"Conversions_{goal_id}_AUTO"], errors="coerce").fillna(0)
    df["Conv_zvonok"] = pd.to_numeric(df[f"Conversions_{ct_goal_id}_AUTO"], errors="coerce").fillna(0)
    df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
    return df.groupby(["CampaignId", "CampaignName"]).agg(
        Cost=("Cost", "sum"), Clicks=("Clicks", "sum"),
        Direct_forma=("Conv_forma", "sum"), Direct_zvonok=("Conv_zvonok", "sum"),
    ).reset_index()


def load_metrika(stats_dir, date_from, date_to):
    path = _find_file(stats_dir, f"metrika*{date_from}_to_{date_to}*.csv")
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
    path = _find_file(stats_dir, f"callibri*{date_from}_to_{date_to}*.csv")
    df = pd.read_csv(path)

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
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "ЕГЭ Merlin"')
    ap.add_argument("--goal-id", required=True, help="ID цели формы (Метрика)")
    ap.add_argument("--ct-goal-id", required=True, help="ID цели звонка (колл-трекинг)")
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    stats_dir = client_stats_dir(args.client_folder)

    direct = load_direct(stats_dir, args.date_from, args.date_to, args.goal_id, args.ct_goal_id)
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
    print(f"Клиент: {args.client_folder} | период {args.date_from} → {args.date_to}")
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
