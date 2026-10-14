#!/usr/bin/env python
# coding: utf-8
"""Регулярный разбор поисковых запросов Search-кампании: кандидаты в минус-слова (ТОЛЬКО ЧТЕНИЕ).

Не пишет в аккаунт. Читает search_term_view кампании за период, делит запросы на классы и печатает
кандидатов в EXACT-минусы + готовую команду для `gads_add_campaign_negatives.py` (по умолчанию validate_only).
Решение «добавлять» принимает пользователь по таблице; скрипт — только подготовка.

Классы (эвристика по словарю, не истина — смотреть глазами):
  ИМЯ        нет слов про аварию/травму/юриста-ДТП: имена людей, фирм, сайтов
  ИНФО       информационные («how much», «should i», «settlement»…)
  ИСПАНСКИЙ  abogado/abogados (испаноязычной страницы нет)
  ДРУГОЙ     явно не ДТП на машине (slip and fall, premises, workers comp…)
  СПОРНЫЙ    может быть ДТП или не ДТП (pedestrian, bicycle, motorcycle, wrongful death, rideshare) — НЕ минусовать автоматически
  ОБЩИЙ      «accident lawyer» без car/truck — решает человек
  ЦЕЛЕВОЙ    остальное (содержит car/auto/truck/crash…)

В кандидаты попадают ИМЯ, ИНФО, ИСПАНСКИЙ, ДРУГОЙ с показами >= --min-impr (по умолчанию 2) или с кликами,
если такого минуса ещё нет и это не наш собственный ключ.

    python gads_search_terms_triage.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" --date-from 2026-10-14 --date-to 2026-10-17
"""
import argparse
import re
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

CORE = re.compile(r"(car|auto|automobile|truck|trucking|crash|collision|wreck|vehicle|wheeler|semi|big rig|"
                  r"accident|injur|hurt|rear.?end|hit and run|t-bone|uber|lyft)")
PRO = re.compile(r"(lawyer|attorney|law firm|lawyers|attorneys|claim|compensation|settlement|case)")
INFO = re.compile(r"\b(how much|how to|how long|should i|what|when|why|can i|do i|does|is it|settlement|"
                  r"statute|average|cost|fee|fees|percent|worth|free)\b")
SPAN = re.compile(r"abogad")
OTHER = re.compile(r"(slip and fall|slip & fall|trip and fall|premises|workers|work comp|work injur|medical malpractice|"
                   r"malpractice|nursing home|dog bite|product liability|construction|boat|plane|train|bus accident|"
                   r"wrongful termination|employment|divorce|dui|criminal)")
DISPUTED = re.compile(r"(pedestrian|bicycl|bike|motorcycle|scooter|wrongful death|rideshare|ride share|passenger)")


def classify(term: str) -> str:
    t = term.lower()
    if SPAN.search(t):
        return "ИСПАНСКИЙ"
    if OTHER.search(t):
        return "ДРУГОЙ"
    if DISPUTED.search(t):
        return "СПОРНЫЙ"
    if INFO.search(t):
        return "ИНФО"
    if not CORE.search(t):
        return "ИМЯ"
    if re.search(r"accident|injur", t) and not re.search(r"car|auto|truck|vehicle|wheeler|semi|rig|crash|collision|wreck|motor", t):
        return "ОБЩИЙ"
    return "ЦЕЛЕВОЙ"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--min-impr", type=int, default=2)
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    q = ("SELECT search_term_view.search_term, metrics.impressions, metrics.clicks, metrics.cost_micros, "
         "metrics.conversions FROM search_term_view "
         f"WHERE campaign.name = '{args.campaign}' AND segments.date BETWEEN '{args.date_from}' AND '{args.date_to}'")
    rows = [{"term": r.search_term_view.search_term.lower(), "impr": r.metrics.impressions,
             "clicks": r.metrics.clicks, "cost": r.metrics.cost_micros / 1e6, "conv": r.metrics.conversions}
            for r in ga.search(customer_id=cid, query=q)]
    if not rows:
        print("Нет запросов за период.")
        return
    df = pd.DataFrame(rows).groupby("term", as_index=False).sum()
    df["class"] = df.term.map(classify)

    neg_q = ("SELECT campaign_criterion.keyword.text FROM campaign_criterion "
             f"WHERE campaign.name = '{args.campaign}' AND campaign_criterion.negative = TRUE "
             "AND campaign_criterion.type = 'KEYWORD'")
    negs = {r.campaign_criterion.keyword.text.lower() for r in ga.search(customer_id=cid, query=neg_q)}
    own_q = ("SELECT ad_group_criterion.keyword.text FROM ad_group_criterion "
             f"WHERE campaign.name = '{args.campaign}' AND ad_group_criterion.negative = FALSE "
             "AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.status != 'REMOVED'")
    own = {r.ad_group_criterion.keyword.text.lower() for r in ga.search(customer_id=cid, query=own_q)}

    out = client_stats_dir(args.client_folder) / f"search_terms_triage_{args.date_from}_to_{args.date_to}.csv"
    df.sort_values(["class", "impr"], ascending=[True, False]).to_csv(out, index=False)
    print(f"Период {args.date_from} → {args.date_to}; запросов {len(df)}; файл: {out}")
    print(f"Охват: показов {int(df.impr.sum())}, кликов {int(df.clicks.sum())}, расход ${df.cost.sum():.2f} "
          f"(только то, что отдаёт search_term_view; остальное скрыто порогом приватности)\n")
    g = df.groupby("class")[["impr", "clicks", "cost", "conv"]].sum()
    g["запросов"] = df.groupby("class").size()
    print(g.to_string(), "\n")

    cand_mask = df["class"].isin(["ИМЯ", "ИНФО", "ИСПАНСКИЙ", "ДРУГОЙ"]) & \
        ((df.impr >= args.min_impr) | (df.clicks > 0)) & ~df.term.isin(negs) & ~df.term.isin(own)
    cand = df[cand_mask].sort_values(["class", "impr"], ascending=[True, False])
    print(f"Кандидаты в EXACT-минусы ({len(cand)}), ещё не в минусах и не наши ключи:")
    print(cand[["class", "term", "impr", "clicks", "cost"]].to_string(index=False))
    for cls in ("СПОРНЫЙ", "ОБЩИЙ"):
        part = df[df["class"] == cls].sort_values("impr", ascending=False)
        if len(part):
            print(f"\n{cls} — решает человек ({len(part)}):")
            print(part[["term", "impr", "clicks", "cost"]].head(25).to_string(index=False))
    if len(cand):
        texts = ";".join(cand.term)
        print("\nКоманда (проверка без записи; запись — после «да», добавить --execute):")
        print(f'python gads_add_campaign_negatives.py --customer-id {args.customer_id} --campaign "{args.campaign}" '
              f'--match EXACT --texts "{texts}"')


if __name__ == "__main__":
    main()
