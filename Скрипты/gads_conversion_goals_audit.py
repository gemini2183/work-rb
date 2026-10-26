#!/usr/bin/env python
# coding: utf-8
"""Какие действия считаются конверсией у кампании Google Ads и откуда они приходят. ТОЛЬКО ЧТЕНИЕ.

Зачем (Landver, 2026-10-24 и 26): перед подключением новой страницы нужно знать, какие цели основные, считаются ли они в колонке
«Конверсии», нет ли двойного счёта формы (тег на сайте + импорт события из GA4) и что реально засчитано за месяц.
Раньше это делалось разовыми запросами (Хроника 24.10).

Печатает: конверсионные действия (тип, основное ли, входит ли в колонку «Конверсии», счёт, для GA4 — имя события, для WEBPAGE — send_to
из сниппета), цели аккаунта и кампании (какие можно использовать для ставок), уровень настройки целей (аккаунт / кампания),
конверсии кампании по действиям за период. Теги сайта сверять отдельно: `gtm_read_container.py --find "<имя>"` (есть ли в контейнере
тег с этим send_to; без него WEBPAGE-цель на Tilda не срабатывает).

    python gads_conversion_goals_audit.py --customer-id 213-621-6123 --campaign-id 24331208797 --date-from 2026-10-01 --date-to 2026-10-26
"""
import argparse
import io
import re
import sys

from google.ads.googleads.client import GoogleAdsClient

from gads_campaign_summary import enum_name
from gads_stats import GOOGLE_ADS_YAML


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc = c.get_service("GoogleAdsService")

    def q(s):
        return list(svc.search(customer_id=cid, query=s))

    print("== Конверсионные действия (не удалённые, не скрытые)")
    for r in q("SELECT conversion_action.id,conversion_action.name,conversion_action.type,conversion_action.status,conversion_action.primary_for_goal,"
               "conversion_action.category,conversion_action.counting_type,conversion_action.include_in_conversions_metric,"
               "conversion_action.google_analytics_4_settings.event_name,conversion_action.tag_snippets "
               "FROM conversion_action WHERE conversion_action.status = 'ENABLED'"):
        x = r.conversion_action
        extra = ""
        if x.google_analytics_4_settings.event_name:
            extra = f" | событие GA4 «{x.google_analytics_4_settings.event_name}»"
        sends = {m for s in x.tag_snippets for m in re.findall(r"AW-\d+/[\w-]+", s.event_snippet)}
        if sends:
            extra += " | send_to " + ", ".join(sorted(sends))
        print(f"  {x.id} {x.name} | {enum_name(c, 'ConversionActionTypeEnum', x.type_)} | {enum_name(c, 'ConversionActionCategoryEnum', x.category)} | "
              f"{'основное' if x.primary_for_goal else 'второстепенное'} | в колонке «Конверсии»: {'да' if x.include_in_conversions_metric else 'НЕТ'} | "
              f"счёт {enum_name(c, 'ConversionActionCountingTypeEnum', x.counting_type)}{extra}")

    print("\n== Цели аккаунта (category / origin / используется для ставок)")
    for r in q("SELECT customer_conversion_goal.category,customer_conversion_goal.origin,customer_conversion_goal.biddable FROM customer_conversion_goal"):
        g = r.customer_conversion_goal
        print(f"  {enum_name(c, 'ConversionActionCategoryEnum', g.category)} / {enum_name(c, 'ConversionOriginEnum', g.origin)} / {g.biddable}")

    print("\n== Настройка целей кампании")
    for r in q(f"SELECT campaign.name,campaign.bidding_strategy_type,conversion_goal_campaign_config.goal_config_level FROM conversion_goal_campaign_config WHERE campaign.id={a.campaign_id}"):
        print(f"  {r.campaign.name}: стратегия {enum_name(c, 'BiddingStrategyTypeEnum', r.campaign.bidding_strategy_type)}, "
              f"уровень целей {enum_name(c, 'GoalConfigLevelEnum', r.conversion_goal_campaign_config.goal_config_level)}")
    for r in q(f"SELECT campaign_conversion_goal.category,campaign_conversion_goal.origin,campaign_conversion_goal.biddable FROM campaign_conversion_goal WHERE campaign.id={a.campaign_id}"):
        g = r.campaign_conversion_goal
        print(f"  {enum_name(c, 'ConversionActionCategoryEnum', g.category)} / {enum_name(c, 'ConversionOriginEnum', g.origin)} / для ставок: {g.biddable}")

    print(f"\n== Конверсии кампании по действиям {a.date_from}…{a.date_to} (conversions / all_conversions)")
    rows = q(f"SELECT segments.conversion_action_name,metrics.conversions,metrics.all_conversions FROM campaign "
             f"WHERE campaign.id={a.campaign_id} AND segments.date BETWEEN '{a.date_from}' AND '{a.date_to}'")
    agg = {}
    for r in rows:
        k = r.segments.conversion_action_name or "(без действия)"
        v = agg.setdefault(k, [0.0, 0.0])
        v[0] += r.metrics.conversions
        v[1] += r.metrics.all_conversions
    for k, v in sorted(agg.items()):
        print(f"  {k}: {v[0]} / {v[1]}")
    if not any(v[0] or v[1] for v in agg.values()):
        print("  нет конверсий ни по одному действию")


if __name__ == "__main__":
    main()
