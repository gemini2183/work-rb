#!/usr/bin/env python
# coding: utf-8
"""Частотный разбор search terms по словам — data-driven, без заранее заданных тем.

В отличие от gads_search_terms_cluster.py (там темы и regex-паттерны заданы
руками заранее, поэтому всё, что не совпало, улетает в "Інше" — при большом
хвосте разнородных запросов это может быть половина расхода без единой
подсказки, что там), этот скрипт не предполагает темы заранее: разбивает
каждый search term на отдельные слова (токенизация), и считает по каждому
слову агрегат (сколько раз встречается, сумма показов/кликов/расхода/
конверсий по ВСЕМ запросам, где это слово встретилось) — темы становятся
видны по факту частотности и расхода, а не по догадке аналитика.

Слова группируются по стему (nltk SnowballStemmer('russian') — украинской
модели в nltk нет, но падежные окончания украинской и русской морфологии
достаточно близки, стеммер на практике сводит "військове/військовий/
військових/військові/військовому" к одному корню) — иначе одно и то же
слово в разных падежных формах считается как отдельные редкие слова и
искусственно размывает частотность, из-за чего заметные по расходу темы
выглядят как шум (проверено на практике 2026-09-08, Корогва — см.
Клиенты/Корогва/Решения.md). Для отображения берётся самая частая исходная
словоформа внутри стема (иначе таблица показывала бы голые обрубки типа
"військов" вместо читаемого слова).

Слово может входить в несколько search term сразу (напр. "худі чоловічі" даёт
и "худі", и "чоловічі") — значит суммы по разным словам НЕ складываются в
общий тотал без двойного счёта, это нормально для такого разреза: он отвечает
на вопрос "сколько расхода прошло через запросы, содержащие слово X", не
"сколько денег в категории X ровно".

Использование:
    python gads_search_terms_wordfreq.py --customer-id 845-234-6433 \
        --client-folder "Корогва" --campaigns "Merchant_Shopping" \
        --date-from 2026-07-01 --date-to 2026-09-07 --min-cost 20

ПРИ СВЕРКЕ С ИНТЕРФЕЙСОМ GOOGLE ADS: этот скрипт суммирует по ВСЕЙ кампании
(всем ad group внутри неё сразу). Проверено 2026-09-08 на Корогве —
Merchant_Shopping содержит минимум 2 ad group ("Всі товари" и "Акційні");
если в интерфейсе стоит фильтр по конкретной ad group (виден в шапке отчёта
"Search terms"), сумма там будет меньше, чем в выводе этого скрипта — это не
расхождение/баг, а разный охват. Сверять с интерфейсом только без фильтра по
ad group, либо явно суммировать все ad group в интерфейсе тоже.
"""
import argparse
import re
from collections import Counter, defaultdict

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from nltk.stem.snowball import SnowballStemmer

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

# Стоп-слова — служебные частицы, не несущие тематического смысла, чтобы не
# засорять топ (украинский/русский/английский минимум).
STOPWORDS = {
    "і", "й", "та", "в", "на", "з", "із", "до", "для", "від", "по", "як",
    "це", "не", "або", "у", "а", "но", "с", "на", "по", "для", "к", "и",
    "the", "a", "an", "of", "to", "in", "for", "and", "or",
}

WORD_RE = re.compile(r"[a-zа-яіїєёA-ZА-ЯІЇЄЁ0-9]+", re.UNICODE)
_stemmer = SnowballStemmer("russian")


def tokenize(term: str) -> list[str]:
    return [w for w in WORD_RE.findall(str(term).lower()) if len(w) >= 3 and w not in STOPWORDS]


def stem(word: str) -> str:
    # Латиница/цифры не гоняем через русский стеммер — он их не трогает
    # содержательно, но лишний вызов не нужен.
    if re.match(r"^[a-z0-9]+$", word):
        return word
    return _stemmer.stem(word)


def fetch_search_terms(ga_service, customer_id, date_from, date_to, campaign_names):
    query = f"""
        SELECT
            campaign.name,
            search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """
    agg = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_names and row.campaign.name not in campaign_names:
                continue
            term = row.search_term_view.search_term
            m = agg.setdefault(term, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["impressions"] += row.metrics.impressions
            m["clicks"] += row.metrics.clicks
            m["cost"] += row.metrics.cost_micros / 1_000_000
            m["conversions"] += row.metrics.conversions
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API")
    ap.add_argument("--customer-id", help="customer_id напрямую")
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaigns", required=True, help="Список кампаний через запятую")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--min-cost", type=float, default=0.0, help="Отсечь слова с суммарным расходом ниже этого порога из топа (не из CSV)")
    ap.add_argument("--top", type=int, default=60, help="Сколько строк топа печатать в консоль")
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

    terms = fetch_search_terms(ga_service, customer_id, args.date_from, args.date_to, campaign_names)
    if not terms:
        print("Нет данных search_term_view за период/кампании")
        return

    stem_stats = defaultdict(lambda: {"n_terms": 0, "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
    stem_terms = defaultdict(Counter)  # стем -> {term: cost} — для расшифровки, что за запросы дали вес
    stem_wordforms = defaultdict(Counter)  # стем -> {исходное слово: cost} — чтобы выбрать читаемый ярлык

    for term, m in terms.items():
        words = set(tokenize(term))  # set — чтобы повторное слово в одном term не удваивало вклад
        stems_in_term = {stem(w): w for w in words}  # схлопнуть словоформы термина к одному стему
        for st, original_word in stems_in_term.items():
            ss = stem_stats[st]
            ss["n_terms"] += 1
            ss["impressions"] += m["impressions"]
            ss["clicks"] += m["clicks"]
            ss["cost"] += m["cost"]
            ss["conversions"] += m["conversions"]
            stem_terms[st][term] += m["cost"]
            stem_wordforms[st][original_word] += m["cost"]

    rows = []
    for st, s in stem_stats.items():
        label = stem_wordforms[st].most_common(1)[0][0]  # самая "дорогая" исходная словоформа как ярлык
        rows.append({
            "word": label,
            "stem": st,
            "n_terms": s["n_terms"],
            "impressions": s["impressions"],
            "clicks": s["clicks"],
            "cost": round(s["cost"], 2),
            "conversions": round(s["conversions"], 3),
            "CPA": round(s["cost"] / s["conversions"], 1) if s["conversions"] > 0 else float("inf"),
            "CTR_%": round(s["clicks"] / s["impressions"] * 100, 2) if s["impressions"] else 0.0,
        })
    df = pd.DataFrame(rows).sort_values("cost", ascending=False)

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / f"search_terms_wordfreq_{args.date_from}_to_{args.date_to}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} уникальных стемов)")

    pd.set_option("display.width", 220)
    view = df[df["cost"] >= args.min_cost].head(args.top)
    print(f"\nТоп-{args.top} слов (по стему) по расходу (min_cost={args.min_cost}):")
    print(view.drop(columns=["stem"]).to_string(index=False))

    print(f"\nТоп-{args.top} слов по расходу БЕЗ ЕДИНОЙ конверсии (кандидаты в минус-слова):")
    zero_conv = df[(df["conversions"] == 0) & (df["cost"] >= args.min_cost)].head(args.top)
    print(zero_conv.drop(columns=["stem"]).to_string(index=False))

    # Расшифровка топ-10 самых дорогих "нулевых" стемов — какие конкретно search terms их составили
    print("\n=== Расшифровка топ-10 самых дорогих слов без конверсий: из каких search term состоят ===")
    for _, r in zero_conv.head(10).iterrows():
        st = r["stem"]
        top_terms = stem_terms[st].most_common(5)
        terms_str = "; ".join(f"{t} ({c:.0f}₴)" for t, c in top_terms)
        print(f"  {r['word']} (итого {r['cost']}₴): {terms_str}")


if __name__ == "__main__":
    main()
