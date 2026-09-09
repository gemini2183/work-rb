#!/usr/bin/env python
# coding: utf-8
"""Сравнение search terms (по стему) между двумя периодами — до/после гипотетической
точки разлома — с математической проверкой значимости снижения CVR по каждому слову.

Считает ВСЕ стемы сразу, без предварительного отбора "на глаз" — сортировка и
фильтрация делаются уже по посчитанным цифрам, не наоборот. Значимость — точная
биномиальная вероятность P(X <= conversions_after | n=clicks_after, p=CVR_before),
то есть: если бы конверсия слова не изменилась, какова вероятность получить
СТОЛЬКО ЖЕ ИЛИ МЕНЬШЕ конверсий, чем фактически вышло после. Малое значение —
снижение вряд ли случайность. Реализовано без scipy (сломан в этом окружении —
DLL load failed при импорте scipy.linalg, 2026-09-09) через прямую формулу
биномиального CDF, результат идентичен scipy.stats.binomtest(alternative='less').

Использование:
    python gads_search_terms_before_after.py --customer-id 845-234-6433 \
        --client-folder "Корогва" --campaigns "Merchant_Shopping" \
        --before-from 2026-07-09 --before-to 2026-08-12 \
        --after-from 2026-08-13 --after-to 2026-09-07 \
        --min-clicks 15
"""
import argparse
from math import comb

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service
from gads_search_terms_wordfreq import fetch_search_terms, tokenize, stem as stem_word


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) для X ~ Binomial(n, p). Реализация без scipy."""
    if p <= 0:
        return 1.0
    if p >= 1:
        return 1.0 if k >= n else 0.0
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def aggregate_by_stem(terms: dict) -> dict:
    stem_stats = {}
    for term, m in terms.items():
        words = set(tokenize(term))
        stems_in_term = {stem_word(w): w for w in words}
        for st, original_word in stems_in_term.items():
            ss = stem_stats.setdefault(
                st, {"word": original_word, "clicks": 0, "cost": 0.0, "conversions": 0.0}
            )
            ss["clicks"] += m["clicks"]
            ss["cost"] += m["cost"]
            ss["conversions"] += m["conversions"]
            # ярлык — самое частое исходное слово по накопленному расходу
            if m["cost"] > 0 and original_word != ss["word"]:
                pass  # оставляем первое встреченное — не критично для ярлыка
    return stem_stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API")
    ap.add_argument("--customer-id", help="customer_id напрямую")
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaigns", required=True, help="Список кампаний через запятую")
    ap.add_argument("--before-from", required=True)
    ap.add_argument("--before-to", required=True)
    ap.add_argument("--after-from", required=True)
    ap.add_argument("--after-to", required=True)
    ap.add_argument("--min-clicks", type=int, default=15, help="Минимум кликов И до, И после, чтобы слово попало в значимый список")
    ap.add_argument("--top", type=int, default=100)
    args = ap.parse_args()

    if args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    elif args.customer_id:
        customer_id = args.customer_id.replace("-", "")
    else:
        print("Нужен либо --client, либо --customer-id")
        return

    campaign_names = {c.strip() for c in args.campaigns.split(",")}
    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    terms_before = fetch_search_terms(ga_service, customer_id, args.before_from, args.before_to, campaign_names)
    terms_after = fetch_search_terms(ga_service, customer_id, args.after_from, args.after_to, campaign_names)

    stems_before = aggregate_by_stem(terms_before)
    stems_after = aggregate_by_stem(terms_after)

    all_stems = set(stems_before) | set(stems_after)
    rows = []
    for st in all_stems:
        b = stems_before.get(st, {"word": stems_after.get(st, {}).get("word", st), "clicks": 0, "cost": 0.0, "conversions": 0.0})
        a = stems_after.get(st, {"word": b["word"], "clicks": 0, "cost": 0.0, "conversions": 0.0})
        clicks_before, conv_before = b["clicks"], b["conversions"]
        clicks_after, conv_after = a["clicks"], a["conversions"]
        cvr_before = conv_before / clicks_before if clicks_before else None
        cvr_after = conv_after / clicks_after if clicks_after else None

        p_value = None
        if clicks_before >= args.min_clicks and clicks_after >= args.min_clicks and cvr_before and cvr_before > 0:
            k = int(round(conv_after))
            p_value = binom_cdf(k, clicks_after, cvr_before)

        rows.append({
            "word": b["word"] or a["word"],
            "stem": st,
            "clicks_before": clicks_before,
            "conversions_before": round(conv_before, 2),
            "CVR_before_%": round(cvr_before * 100, 2) if cvr_before is not None else None,
            "clicks_after": clicks_after,
            "conversions_after": round(conv_after, 2),
            "CVR_after_%": round(cvr_after * 100, 2) if cvr_after is not None else None,
            "cost_after": round(a["cost"], 2),
            "p_value_decline": round(p_value, 6) if p_value is not None else None,
        })

    df = pd.DataFrame(rows)

    out_dir = client_stats_dir(args.client_folder)
    fname = f"search_terms_before_after_{args.before_from}_to_{args.before_to}_vs_{args.after_from}_to_{args.after_to}.csv"
    out_path = out_dir / fname
    df.sort_values("cost_after", ascending=False).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Сохранено (ВСЕ стемы, без предварительного отбора): {out_path} ({len(df)} строк)")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", args.top)

    significant = df[df["p_value_decline"].notna()].sort_values("p_value_decline")
    print(f"\n=== Слова с рассчитанной значимостью (>= {args.min_clicks} кликов и до, и после), по возрастанию p-value ===")
    print(significant.drop(columns=["stem"]).head(args.top).to_string(index=False))

    print(f"\n=== Из них p < 0.05 (снижение статистически значимо, НЕ случайность) ===")
    print(significant[significant["p_value_decline"] < 0.05].drop(columns=["stem"]).to_string(index=False))


if __name__ == "__main__":
    main()
