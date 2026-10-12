#!/usr/bin/env python
# coding: utf-8
"""Проверка: какие минус-слова блокируют заданные фразы (кандидаты в ключи или свои ключи кампании).

Только чтение. Читает минус-слова кампании на всех уровнях, которые работают на ключ,
заведённый в группу кампании:
  1. кампанийные минусы (`campaign_criterion`, negative = TRUE);
  2. общие списки минусов, подключённые к кампании (`campaign_shared_set` + `shared_criterion`).
Минусы уровня группы здесь НЕ учитываются: новая группа их не наследует (они только
печатаются числом, чтобы было видно, что они есть).

Правила совпадения (справка Google, «Negative keywords», не проверено на кабинете):
  - широкий минус блокирует, если ВСЕ его слова есть в запросе, в любом порядке;
  - фразовый — слова подряд и в том же порядке;
  - точный — запрос целиком совпадает.
Минусы не знают про близкие варианты (множественное число, синонимы не блокируются) —
стемминга здесь нет намеренно. Знаки препинания считаются пробелом.

Использование:
    python gads_negatives_conflicts.py --customer-id 213-621-6123 --client-folder "Andverpersonalinjury" \
        --campaign "search / car+truck injuries / s / lp - tilda" --candidates candidates.csv   # колонка keyword
    python gads_negatives_conflicts.py ... --own-keywords      # проверить и собственные позитивные ключи кампании
"""
import argparse
import re
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

TOKEN_RE = re.compile(r"[a-z0-9а-яё]+")


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(str(text).lower())


def blocks(neg_tokens: list[str], match: str, query_tokens: list[str]) -> bool:
    if not neg_tokens:
        return False
    if match == "EXACT":
        return neg_tokens == query_tokens
    if match == "PHRASE":
        n = len(neg_tokens)
        return any(query_tokens[i:i + n] == neg_tokens for i in range(len(query_tokens) - n + 1))
    return all(t in query_tokens for t in neg_tokens)  # BROAD


def fetch_negatives(client, ga, cid, campaign):
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType
    rows = []
    q = f"""
        SELECT campaign_criterion.keyword.text, campaign_criterion.keyword.match_type
        FROM campaign_criterion
        WHERE campaign.name = '{campaign}' AND campaign_criterion.type = 'KEYWORD'
            AND campaign_criterion.negative = TRUE
    """
    for r in ga.search(customer_id=cid, query=q):
        rows.append(("кампания", r.campaign_criterion.keyword.text, mt.Name(r.campaign_criterion.keyword.match_type)))

    q = f"""
        SELECT shared_set.id, shared_set.name
        FROM campaign_shared_set
        WHERE campaign.name = '{campaign}' AND shared_set.type = 'NEGATIVE_KEYWORDS'
            AND campaign_shared_set.status = 'ENABLED'
    """
    sets = [(r.shared_set.id, r.shared_set.name) for r in ga.search(customer_id=cid, query=q)]
    for sid, sname in sets:
        q = f"""
            SELECT shared_criterion.keyword.text, shared_criterion.keyword.match_type
            FROM shared_criterion WHERE shared_set.id = {sid}
        """
        for r in ga.search(customer_id=cid, query=q):
            rows.append((f"список «{sname}»", r.shared_criterion.keyword.text, mt.Name(r.shared_criterion.keyword.match_type)))

    q = f"""
        SELECT ad_group_criterion.keyword.text
        FROM ad_group_criterion
        WHERE campaign.name = '{campaign}' AND ad_group_criterion.type = 'KEYWORD'
            AND ad_group_criterion.negative = TRUE
    """
    group_neg = sum(1 for _ in ga.search(customer_id=cid, query=q))
    return rows, sets, group_neg


def fetch_own_keywords(client, ga, cid, campaign):
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType
    q = f"""
        SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type
        FROM ad_group_criterion
        WHERE campaign.name = '{campaign}' AND ad_group_criterion.type = 'KEYWORD'
            AND ad_group_criterion.negative = FALSE AND ad_group_criterion.status = 'ENABLED'
    """
    return [(r.ad_group.name, r.ad_group_criterion.keyword.text, mt.Name(r.ad_group_criterion.keyword.match_type))
            for r in ga.search(customer_id=cid, query=q)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True, help="точное имя кампании")
    ap.add_argument("--candidates", help="CSV с колонкой keyword")
    ap.add_argument("--own-keywords", action="store_true", help="проверить и позитивные ключи самой кампании")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    negs, sets, group_neg = fetch_negatives(client, ga, cid, args.campaign)
    by_level = pd.Series([n[0] for n in negs]).value_counts()
    print(f"Минусы кампании: всего {len(negs)} (уровень группы — {group_neg}, здесь не учитываются)")
    print(by_level.to_string())
    prepared = [(lvl, txt, m, tokens(txt)) for lvl, txt, m in negs]

    items = []  # (источник, группа, фраза)
    if args.candidates:
        cdf = pd.read_csv(args.candidates)
        for _, r in cdf.iterrows():
            items.append(("кандидат", r.get("group", ""), r["keyword"]))
    if args.own_keywords:
        for g, t, m in fetch_own_keywords(client, ga, cid, args.campaign):
            items.append((f"свой ключ ({m})", g, t))
    if not items:
        print("Нечего проверять: нужен --candidates и/или --own-keywords")
        return

    out = []
    for src, grp, phrase in items:
        qt = tokens(phrase)
        hit = [f"{lvl}: «{txt}» [{m}]" for lvl, txt, m, nt in prepared if blocks(nt, m, qt)]
        out.append({"source": src, "group": grp, "keyword": phrase, "blocked": bool(hit), "blockers": " | ".join(hit)})
    res = pd.DataFrame(out)
    path = client_stats_dir(args.client_folder) / f"negatives_conflicts_{datetime.now():%Y%m%d_%H%M}.csv"
    res.to_csv(path, index=False, encoding="utf-8")
    print(f"\nПроверено фраз: {len(res)}; заблокировано: {int(res.blocked.sum())}. Файл: {path}")
    if res.blocked.any():
        pd.set_option("display.width", 220)
        pd.set_option("display.max_colwidth", 110)
        print(res[res.blocked][["source", "keyword", "blockers"]].to_string(index=False))


if __name__ == "__main__":
    main()
