#!/usr/bin/env python
# coding: utf-8
"""Индекс in-market / affinity аудитории против населения страны (Google Ads, READ-ONLY).

Зачем: узнать, какие категории интересов (in-market, affinity и др.) у аудитории (список покупателей
или одна категория) встречаются чаще, чем у населения страны: индекс = доля в аудитории / доля в базе.
Отдельный способ выбрать категории для таргета (Demand Gen и др.). Не заменяет решение по
сигналу конверсий.

Метод API: AudienceInsightsService.GenerateAudienceCompositionInsights (1 вызов = 1 операция чтения
в журнале gads_quota_ledger). В кабинет ничего не пишет; режима записи и --execute нет.

Основа аудитории (одно из): --user-list-id | --category-id (user_interest) | --age/--gender (демо-набор).
База сравнения: вся страна (--country-geo-id, по умолчанию 2616 Польша).

Пометка «доступно для таргета в DG»: да для IN_MARKET_USER_INTEREST и AFFINITY_USER_INTEREST
(по документации, на практике по конкретному id не проверяется); для остальных измерений - нет.

Использование:
    python gads_audience_insights.py --customer-id 8826134558 --client-folder EkspertAgro \\
        --user-list-id 9475706784 --top 15
    python gads_audience_insights.py --customer-id ... --client-folder ... --category-id 80501 \\
        --dimensions IN_MARKET_USER_INTEREST --data-month 2026-10 --min-share 0.01
CSV: Клиенты/<client-folder>/Статистика/gads_audience_insights_<основа>_<дата>.csv
Дата: 2026-11-24
"""
import argparse
import sys
from datetime import date

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import record_mutate  # журнал операций API; вызов Insights пишем как 1 операцию чтения

SCRIPT = "gads_audience_insights"
ALLOWED_DIMS = ["KNOWLEDGE_GRAPH", "GEO_TARGET_COUNTRY", "SUB_COUNTRY_LOCATION", "YOUTUBE_CHANNEL",
                "YOUTUBE_LINEUP", "AFFINITY_USER_INTEREST", "IN_MARKET_USER_INTEREST",
                "LIFE_EVENT_USER_INTEREST", "PARENTAL_STATUS", "INCOME_RANGE", "AGE_RANGE", "GENDER"]
DG_OK = {"IN_MARKET_USER_INTEREST", "AFFINITY_USER_INTEREST"}


def _attr_id(md):
    """id категории из метаданных атрибута (user_interest -> id из resource name)."""
    a = md.attribute
    for fld in ("user_interest", "knowledge_graph", "age_range", "gender", "income_range",
                "parental_status", "location", "youtube_channel", "lineup"):
        try:
            if a._pb.HasField(fld):
                val = getattr(a, fld)
                if fld == "user_interest":
                    return val.user_interest_category.split("/")[-1]
                return str(val).replace("\n", " ")[:60]
        except Exception:
            continue
    return ""


def build_audience(client, args, cid, base=False):
    aud = client.get_type("InsightsAudience")
    loc = client.get_type("LocationInfo")
    loc.geo_target_constant = f"geoTargetConstants/{args.country_geo_id}"
    aud.country_locations.append(loc)
    if base:
        if args.baseline_user_list_id:
            aud.user_list.user_list = f"customers/{cid}/userLists/{args.baseline_user_list_id}"
        return aud
    if args.user_list_id:
        aud.user_list.user_list = f"customers/{cid}/userLists/{args.user_list_id}"
    if args.category_id:
        # аудитория = категория интереса: топ-уровневый атрибут в topic_audience_combinations
        grp = client.get_type("InsightsAudienceAttributeGroup")
        attr = client.get_type("AudienceInsightsAttribute")
        attr.user_interest.user_interest_category = f"customers/{cid}/userInterests/{args.category_id}"
        grp.attributes.append(attr)
        aud.topic_audience_combinations.append(grp)
    if args.age:
        for a in args.age:
            r = client.get_type("AgeRangeInfo")
            r.type_ = getattr(client.enums.AgeRangeTypeEnum, a)
            aud.age_ranges.append(r)
    if args.gender:
        aud.gender.type_ = getattr(client.enums.GenderTypeEnum, args.gender)
    return aud


def main():
    ap = argparse.ArgumentParser(description="Индекс интересов аудитории против страны (Audience insights, только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True, help="папка клиента для CSV (Клиенты/<имя>/Статистика/)")
    ap.add_argument("--user-list-id", help="id user_list как основа аудитории")
    ap.add_argument("--category-id", help="id user_interest (in-market/affinity) как основа аудитории")
    ap.add_argument("--age", nargs="*", help="демо-набор: AGE_RANGE_25_34 ...")
    ap.add_argument("--gender", help="демо-набор: MALE|FEMALE")
    ap.add_argument("--country-geo-id", default="2616", help="geoTargetConstants id страны (по умолч. 2616 Польша)")
    ap.add_argument("--baseline-user-list-id", help="список как база сравнения (по умолч. вся страна)")
    ap.add_argument("--dimensions", nargs="+", default=["IN_MARKET_USER_INTEREST", "AFFINITY_USER_INTEREST"],
                    choices=ALLOWED_DIMS)
    ap.add_argument("--data-month", help="yyyy-mm; по умолч. последние 30 дней данных")
    ap.add_argument("--top", type=int, default=15, help="топ N на измерение (по индексу)")
    ap.add_argument("--min-share", type=float, default=0.0, help="отсечь категории с долей в аудитории ниже порога (0..1)")
    ap.add_argument("--customer-insights-group", help="метка клиента (по умолч. client-folder)")
    args = ap.parse_args()

    if not (args.user_list_id or args.category_id or args.age or args.gender):
        sys.exit("Нужна основа аудитории: --user-list-id, --category-id или --age/--gender")

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc = client.get_service("AudienceInsightsService")

    req = client.get_type("GenerateAudienceCompositionInsightsRequest")
    req.customer_id = cid
    client.copy_from(req.audience, build_audience(client, args, cid))
    client.copy_from(req.baseline_audience, build_audience(client, args, cid, base=True))
    for d in args.dimensions:
        req.dimensions.append(getattr(client.enums.AudienceInsightsDimensionEnum, d))
    if args.data_month:
        req.data_month = args.data_month
    req.customer_insights_group = args.customer_insights_group or args.client_folder

    basis = (f"list{args.user_list_id}" if args.user_list_id else
             f"cat{args.category_id}" if args.category_id else "demo")
    print(f"Основа: {basis}; страна geo {args.country_geo_id}; dimensions {args.dimensions}; "
          f"data_month {args.data_month or 'последние 30 дней'}")
    print("Режим: только чтение, вызовов API: 1 (GenerateAudienceCompositionInsights)")

    record_mutate(SCRIPT, 1)
    try:
        resp = svc.generate_audience_composition_insights(request=req)
    except Exception as e:
        print("Ошибка API (дословно):")
        print(str(e))
        sys.exit(1)

    rows = []
    for sec in resp.sections:
        dim = sec.dimension.name
        for at in sec.top_attributes:
            md, m = at.attribute_metadata, at.metrics
            rows.append({
                "Dimension": dim, "Category": md.display_name, "Category_id": _attr_id(md),
                "Audience_share": round(m.audience_share, 5), "Baseline_share": round(m.baseline_audience_share, 5),
                "Index": round(m.index, 3), "Score": round(m.score, 3),
                "DG_targetable": "да" if dim in DG_OK else "нет",
            })
    df = pd.DataFrame(rows)
    print(f"Получено строк: {len(df)}; секций: {len(resp.sections)}")
    if df.empty:
        print("API вернул пустой ответ (данных по аудитории/стране нет).")
    else:
        if args.min_share > 0:
            before = len(df)
            df = df[df["Audience_share"] >= args.min_share]
            print(f"--min-share {args.min_share}: отброшено {before - len(df)} из {before} строк")
        df = df.sort_values(["Dimension", "Index"], ascending=[True, False])
        out = client_stats_dir(args.client_folder) / f"gads_audience_insights_{basis}_{date.today()}.csv"
        df.to_csv(out, index=False, encoding="utf-8")
        print(f"CSV: {out}")
        with pd.option_context("display.max_colwidth", 60, "display.width", 250):
            for dim, g in df.groupby("Dimension"):
                print(f"\n=== {dim} (топ {args.top} по индексу из {len(g)}) ===")
                print(g.head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
