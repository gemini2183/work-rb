#!/usr/bin/env python
# coding: utf-8
"""Объём спроса (Keyword Planner) по seed-словам для одного клиента/аккаунта.

В отличие от gads_semantics.py (который читает keyword_view/search_term_view —
факт по уже запущенным кампаниям), этот скрипт использует
KeywordPlanIdeaService.GenerateKeywordIdeas — прогноз спроса по любым словам,
включая ещё не запущенные, с помесячной историей и диапазоном ставок.
Используется, когда нужно сравнить объём спроса по направлениям ДО их запуска
в кампании (не путать с fetch_keywords/fetch_search_terms в gads_semantics.py).

Принимает customer_id напрямую (--customer-id), а не только через вкладку
Google_Ads_API общей таблицы (--client) — нужно для клиентов, ещё не заведённых
в таблицу (см. Клиенты/<клиент>/Задачи.md).

Гео берётся из geo_target_constant.resource_name (numeric id), не из свободного
текста — GenerateKeywordIdeas принимает только geo target constant resource
names. Если гео неизвестно, сначала запустить --list-campaign-geo, чтобы
вытянуть текущий гео-таргетинг из уже настроенных кампаний аккаунта.

Использование:
    python gads_keyword_ideas.py --customer-id 143-548-8870 --list-campaign-geo
    python gads_keyword_ideas.py --customer-id 143-548-8870 --client-folder "Юристы США" \
        --geo-id 21176 --keywords "car accident lawyer,truck accident lawyer,motorcycle accident lawyer"
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

import pandas as pd

# Enum-поля (campaign.status, competition) приходят из search_stream как int,
# не как объект с .name — резолвятся через дескриптор enum-сообщения (см.
# аналогичный _enum_name в gads_semantics.py).
_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def get_client(login_customer_id=None):
    ads_client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    if login_customer_id:
        ads_client.login_customer_id = login_customer_id
    return ads_client


def list_campaign_geo(ads_client, customer_id):
    """Гео-таргетинг (campaign_criterion.location) текущих активных кампаний.

    Возвращает список (campaign.name, geo_target_constant resource_name).
    geo_target_constant сам по себе не содержит человекочитаемое название в
    campaign_criterion — для расшифровки нужен отдельный запрос к
    GeoTargetConstantService.
    """
    ga_service = ads_client.get_service("GoogleAdsService")
    query = """
        SELECT
            campaign.name,
            campaign.status,
            campaign_criterion.location.geo_target_constant,
            campaign_criterion.negative
        FROM campaign_criterion
        WHERE campaign_criterion.type = 'LOCATION'
            AND campaign.status != 'REMOVED'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            rows.append({
                "Campaign": row.campaign.name,
                "Status": _enum_name("CampaignStatusEnum", "CampaignStatus", row.campaign.status),
                "Negative": row.campaign_criterion.negative,
                "GeoTargetConstant": row.campaign_criterion.location.geo_target_constant,
            })
    return rows


def resolve_geo_names(ads_client, customer_id, geo_resource_names):
    """Резолвит geo_target_constant resource names -> {"resource_name": "canonical_name"}."""
    if not geo_resource_names:
        return {}
    ga_service = ads_client.get_service("GoogleAdsService")
    names_list = ", ".join(f"'{n}'" for n in sorted(set(geo_resource_names)))
    query = f"""
        SELECT
            geo_target_constant.resource_name,
            geo_target_constant.id,
            geo_target_constant.name,
            geo_target_constant.canonical_name,
            geo_target_constant.country_code,
            geo_target_constant.target_type
        FROM geo_target_constant
        WHERE geo_target_constant.resource_name IN ({names_list})
    """
    result = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            gtc = row.geo_target_constant
            result[gtc.resource_name] = {
                "id": gtc.id,
                "name": gtc.name,
                "canonical_name": gtc.canonical_name,
                "country_code": gtc.country_code,
                "target_type": gtc.target_type,
            }
    return result


def generate_keyword_ideas(ads_client, customer_id, keywords, geo_target_ids, language_id="1000"):
    """KeywordPlanIdeaService.GenerateKeywordIdeas -> список dict с метриками объёма.

    language_id по умолчанию "1000" = English. geo_target_ids — список numeric
    id (не resource names) вида ["21176"] (пример: California, US).
    """
    idea_service = ads_client.get_service("KeywordPlanIdeaService")
    keyword_plan_network = (
        ads_client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    )

    geo_target_service = ads_client.get_service("GeoTargetConstantService")
    location_rns = [
        geo_target_service.geo_target_constant_path(gid) for gid in geo_target_ids
    ]
    language_rn = ads_client.get_service("GoogleAdsService").language_constant_path(language_id)

    request = ads_client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = language_rn
    request.geo_target_constants.extend(location_rns)
    request.keyword_plan_network = keyword_plan_network
    request.keyword_seed.keywords.extend(keywords)

    rows = []
    try:
        response = idea_service.generate_keyword_ideas(request=request)
    except GoogleAdsException as ex:
        for error in ex.failure.errors:
            print(f"GoogleAdsException: {error.message}")
        raise

    for idea in response:
        metrics = idea.keyword_idea_metrics
        monthly = [
            {"month": f"{m.month.name}-{m.year}", "searches": m.monthly_searches}
            for m in metrics.monthly_search_volumes
        ]
        rows.append({
            "Keyword": idea.text,
            "Avg_monthly_searches": metrics.avg_monthly_searches,
            "Competition": metrics.competition.name if metrics.competition else "",
            "Competition_index": metrics.competition_index,
            "Low_top_of_page_bid_micros": metrics.low_top_of_page_bid_micros,
            "High_top_of_page_bid_micros": metrics.high_top_of_page_bid_micros,
            "Monthly_breakdown": monthly,
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True, help="customer_id аккаунта, формат XXX-XXX-XXXX или без дефисов")
    ap.add_argument("--client-folder", help='Папка клиента в Клиенты/, напр. "Юристы США" — нужна для сохранения результата')
    ap.add_argument("--list-campaign-geo", action="store_true", help="Только вывести гео-таргетинг текущих кампаний и выйти")
    ap.add_argument("--geo-id", action="append", help="Numeric geo_target_constant id, можно указать несколько раз")
    ap.add_argument("--keywords", help="Seed-ключи через запятую")
    ap.add_argument("--language-id", default="1000", help="language_constant id, по умолчанию 1000=English")
    args = ap.parse_args()

    customer_id = args.customer_id.replace("-", "").strip()
    ads_client = get_client(login_customer_id=None)

    if args.list_campaign_geo:
        rows = list_campaign_geo(ads_client, customer_id)
        if not rows:
            print("Гео-таргетинг на уровне campaign_criterion не найден (возможно, кампании без явного LOCATION-критерия).")
            return
        geo_names = resolve_geo_names(ads_client, customer_id, [r["GeoTargetConstant"] for r in rows])
        for r in rows:
            info = geo_names.get(r["GeoTargetConstant"], {})
            print(f"{r['Campaign']} ({r['Status']}) | negative={r['Negative']} | "
                  f"{r['GeoTargetConstant']} -> {info.get('canonical_name', '?')} (id={info.get('id', '?')})")
        return

    if not args.keywords:
        print("Укажите --keywords 'car accident lawyer,truck accident lawyer,...' (или используйте --list-campaign-geo сначала)")
        return
    if not args.geo_id:
        print("Укажите --geo-id (numeric id, см. --list-campaign-geo для определения гео из текущих кампаний)")
        return

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    rows = generate_keyword_ideas(ads_client, customer_id, keywords, args.geo_id, args.language_id)

    df = pd.DataFrame([
        {
            "Keyword": r["Keyword"],
            "Avg_monthly_searches": r["Avg_monthly_searches"],
            "Competition": r["Competition"],
            "Competition_index": r["Competition_index"],
            "Low_top_of_page_bid": round(r["Low_top_of_page_bid_micros"] / 1_000_000, 2),
            "High_top_of_page_bid": round(r["High_top_of_page_bid_micros"] / 1_000_000, 2),
        }
        for r in rows
    ]).sort_values("Avg_monthly_searches", ascending=False).reset_index(drop=True)

    print(df.to_string(index=False))

    if args.client_folder:
        out_dir = client_stats_dir(args.client_folder)
        path = out_dir / "gads_keyword_ideas.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"\nСохранено: {path}")


if __name__ == "__main__":
    main()
