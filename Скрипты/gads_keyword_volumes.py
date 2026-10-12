#!/usr/bin/env python
# coding: utf-8
"""Объёмы Keyword Planner по ЗАДАННОМУ списку фраз (не идеи по seed, а точный список).

Только чтение. В отличие от gads_keyword_ideas.py (GenerateKeywordIdeas — подбор идей по
seed-словам), здесь `generate_keyword_historical_metrics`: по каждой фразе из списка возвращает
средний месячный объём и диапазон ставок «верх страницы». Нужен, чтобы проверить объём у фраз,
которые мы собрали сами (паттерн «услуга × город», кандидаты из истории запросов).

Важно: Planner объединяет близкие варианты — одинаковые объёмы у разных формулировок —
это кластер, не точное число (см. Паттерны/Google-Ads-Search-юристы-только-пострадавшие...).
Гео: по умолчанию California (21137), потому что гео кампании — набор городов и округ; объём
по штату — оценка сверху, не прогноз показов кампании.

Использование:
    python gads_keyword_volumes.py --customer-id 213-621-6123 --client-folder "Andverpersonalinjury" \
        --keywords-csv candidates.csv [--geo-id 21137]      # колонка keyword
"""
import argparse
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--keywords-csv", required=True, help="CSV с колонкой keyword")
    ap.add_argument("--geo-id", default="21137", help="geo_target_constant id (21137 = California)")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc = client.get_service("KeywordPlanIdeaService")

    kws = pd.read_csv(args.keywords_csv)["keyword"].astype(str).str.strip().drop_duplicates().tolist()
    rows = []
    for i in range(0, len(kws), 500):
        req = client.get_type("GenerateKeywordHistoricalMetricsRequest")
        req.customer_id = cid
        req.keywords.extend(kws[i:i + 500])
        req.geo_target_constants.append(f"geoTargetConstants/{args.geo_id}")
        req.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
        req.language = "languageConstants/1000"
        resp = svc.generate_keyword_historical_metrics(request=req)
        for r in resp.results:
            m = r.keyword_metrics
            rows.append({
                "keyword": r.text,
                "avg_monthly_searches": m.avg_monthly_searches,
                "low_top_of_page_bid": round(m.low_top_of_page_bid_micros / 1e6, 2),
                "high_top_of_page_bid": round(m.high_top_of_page_bid_micros / 1e6, 2),
            })
    df = pd.DataFrame(rows).sort_values("avg_monthly_searches", ascending=False)
    path = client_stats_dir(args.client_folder) / f"gads_keyword_volumes_{datetime.now():%Y%m%d_%H%M}.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"Фраз: {len(df)}; файл: {path}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
