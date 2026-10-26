#!/usr/bin/env python
# coding: utf-8
"""Какая часть трафика группы объявлений сейчас закрыта минус-словами кампании. ТОЛЬКО ЧТЕНИЕ.

Зачем (Landver, 2026-10-26): перед подключением новой страницы к группе «Car Accident - Settlement» выяснилось, что 29 из 42 минусов,
добавленных в тот же день для всей кампании, — запросы того же семейства («settlement calculator», «car settlement», «…amounts»).
Тест страницы на группе, у которой 54% показов и 6 из 8 видимых кликов закрыты минусами, невозможен: трафика не будет.

Что печатает: ключи группы (статус); сколько минусов у кампании по типам соответствия; поисковые запросы группы за период с пометкой
«закрыт минусом» (EXACT — совпадение запроса целиком; PHRASE/BROAD — по словам) и итог: показы / клики / расход всего и под минусами.
Ограничение: отчёт запросов Google показывает не все клики (редкие запросы скрыты), доля — по видимой части.

    python gads_group_negatives_overlap.py --customer-id 213-621-6123 --campaign-id 24331208797 --group-id 202050998078 \
        --date-from 2026-10-15 --date-to 2026-10-26
"""
import argparse
import io
import sys

from google.ads.googleads.client import GoogleAdsClient

from gads_campaign_summary import enum_name
from gads_stats import GOOGLE_ADS_YAML


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--group-id", required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc = c.get_service("GoogleAdsService")

    def q(s):
        return list(svc.search(customer_id=cid, query=s))

    print("Ключи группы:")
    for r in q(f"SELECT ad_group_criterion.keyword.text,ad_group_criterion.keyword.match_type,ad_group_criterion.status FROM ad_group_criterion "
               f"WHERE ad_group.id={a.group_id} AND ad_group_criterion.type=KEYWORD AND ad_group_criterion.negative=FALSE AND ad_group_criterion.status!='REMOVED'"):
        k = r.ad_group_criterion
        print(f"  {k.keyword.text} [{enum_name(c, 'KeywordMatchTypeEnum', k.keyword.match_type)}] {enum_name(c, 'AdGroupCriterionStatusEnum', k.status)}")

    neg = []
    for r in q(f"SELECT campaign_criterion.keyword.text,campaign_criterion.keyword.match_type FROM campaign_criterion "
               f"WHERE campaign.id={a.campaign_id} AND campaign_criterion.negative=TRUE AND campaign_criterion.type=KEYWORD"):
        neg.append((r.campaign_criterion.keyword.text.lower(), enum_name(c, "KeywordMatchTypeEnum", r.campaign_criterion.keyword.match_type)))
    for r in q(f"SELECT ad_group_criterion.keyword.text,ad_group_criterion.keyword.match_type FROM ad_group_criterion "
               f"WHERE ad_group.id={a.group_id} AND ad_group_criterion.negative=TRUE AND ad_group_criterion.type=KEYWORD"):
        neg.append((r.ad_group_criterion.keyword.text.lower(), enum_name(c, "KeywordMatchTypeEnum", r.ad_group_criterion.keyword.match_type)))
    by = {}
    for _, m in neg:
        by[m] = by.get(m, 0) + 1
    print(f"\nМинус-слов (кампания + группа): {len(neg)} {by}")

    def blocked(term):
        words = term.split()
        for t, m in neg:
            if m == "EXACT" and t == term:
                return f"EXACT «{t}»"
            if m == "PHRASE" and f" {t} " in f" {term} ":
                return f"PHRASE «{t}»"
            if m == "BROAD" and set(t.split()) <= set(words):
                return f"BROAD «{t}»"
        return ""

    tot, blk = [0, 0, 0.0], [0, 0, 0.0]
    rows = []
    for r in q(f"SELECT search_term_view.search_term,metrics.impressions,metrics.clicks,metrics.cost_micros FROM search_term_view "
               f"WHERE ad_group.id={a.group_id} AND segments.date BETWEEN '{a.date_from}' AND '{a.date_to}'"):
        t = r.search_term_view.search_term.lower()
        m = r.metrics
        why = blocked(t)
        for arr in ([tot, blk] if why else [tot]):
            arr[0] += m.impressions
            arr[1] += m.clicks
            arr[2] += m.cost_micros / 1e6
        rows.append((bool(why), m.impressions, m.clicks, m.cost_micros / 1e6, t, why))
    print(f"\nЗапросы группы {a.date_from}…{a.date_to} (видимые в отчёте запросов):")
    for b, i, k, cost, t, why in sorted(rows, key=lambda x: (-x[0], -x[1])):
        print(f"  {'ЗАКРЫТ' if b else 'открыт'} | {i:4d} показов {k:2d} кликов ${cost:6.2f} | {t}{(' ← ' + why) if why else ''}")
    pct = lambda x, y: f"{round(100 * x / y)}%" if y else "—"
    print(f"\nИтого видимых: {tot[0]} показов / {tot[1]} кликов / ${tot[2]:.2f}")
    print(f"Из них под минусами сейчас: {blk[0]} показов ({pct(blk[0], tot[0])}) / {blk[1]} кликов ({pct(blk[1], tot[1])}) / ${blk[2]:.2f} ({pct(blk[2], tot[2])})")
    print("Это чтение: если группа должна получать этот трафик (тест страницы), снимать минусы нужно отдельным согласованием (gads_remove_campaign_negatives.py).")


if __name__ == "__main__":
    main()
