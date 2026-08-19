#!/usr/bin/env python
# coding: utf-8
"""Полный технический дамп настроек кампании(й) Google Ads — не метрики, а конфиг.

Отдельная задача от остальных gads_*.py: gads_campaigns_list.py даёт только
статус/бюджет/тип (быстрый обзор всего аккаунта), gads_campaigns_breakdown.py —
только исторические метрики. Этот скрипт — для кампаний, заведённых вручную в
кабинете (не через наши скрипты, поэтому в Решения.md/логах про них ничего
нет) и требующих полного "рентгена" настроек перед стратегическим решением:
гео-таргетинг (включая positive/negative и proximity/location group), сеть
показа (search/search partners вкл/выкл), устройства, расписание показов,
стратегия и уровень ставок, дата старта.

Использование (одна кампания или несколько через запятую):
    python gads_campaign_settings.py --customer-id 213-621-6123 \
        --client-folder "Andverpersonalinjury" \
        --campaigns "search / all injuries / geo - la specific,search / all injuries / kw -  la specific"

Без --campaigns — дамп по ВСЕМ ENABLED-кампаниям аккаунта.
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def fetch_campaign_core(ga_service, customer_id, campaign_names=None):
    """Базовые настройки кампании -> DataFrame (одна строка на кампанию)."""
    query = """
        SELECT
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign.bidding_strategy_type,
            campaign.target_spend.target_spend_micros,
            campaign.target_cpa.target_cpa_micros,
            campaign.maximize_conversions.target_cpa_micros,
            campaign.network_settings.target_google_search,
            campaign.network_settings.target_search_network,
            campaign.network_settings.target_content_network,
            campaign.network_settings.target_partner_search_network,
            campaign.geo_target_type_setting.positive_geo_target_type,
            campaign.geo_target_type_setting.negative_geo_target_type,
            campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.status = 'ENABLED'
    """

    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_names and row.campaign.name not in campaign_names:
                continue
            c = row.campaign
            rows.append({
                "Campaign": c.name,
                "Status": _enum_name("CampaignStatusEnum", "CampaignStatus", c.status),
                "Channel_type": _enum_name(
                    "AdvertisingChannelTypeEnum", "AdvertisingChannelType", c.advertising_channel_type
                ),
                "Bidding_strategy": _enum_name(
                    "BiddingStrategyTypeEnum", "BiddingStrategyType", c.bidding_strategy_type
                ),
                "Target_spend_micros": c.target_spend.target_spend_micros or None,
                "Target_cpa_micros": c.target_cpa.target_cpa_micros or c.maximize_conversions.target_cpa_micros or None,
                "Daily_budget": round(row.campaign_budget.amount_micros / 1_000_000, 2),
                "Network_google_search": c.network_settings.target_google_search,
                "Network_search_partners": c.network_settings.target_search_network,
                "Network_display": c.network_settings.target_content_network,
                "Network_partner_search": c.network_settings.target_partner_search_network,
                "Geo_positive_type": _enum_name(
                    "PositiveGeoTargetTypeEnum", "PositiveGeoTargetType",
                    c.geo_target_type_setting.positive_geo_target_type,
                ) if c.geo_target_type_setting.positive_geo_target_type else "(default: PRESENCE_OR_INTEREST)",
                "Geo_negative_type": _enum_name(
                    "NegativeGeoTargetTypeEnum", "NegativeGeoTargetType",
                    c.geo_target_type_setting.negative_geo_target_type,
                ) if c.geo_target_type_setting.negative_geo_target_type else "(default: PRESENCE)",
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def resolve_geo_target_names(ga_service_client, customer_id, resource_names):
    """geoTargetConstants/<id> -> "Beverly Hills, CA, USA" и т.п.

    geo_target_constant НЕ доступен как FROM в обычном search/search_stream
    GAQL (Google Ads API это отдельный сервис) — но ЕСТЬ обходной путь:
    ресурс geo_target_constant МОЖНО SELECT'ить из GAQL, если фильтровать по
    его resource_name через IN — так и делаем здесь, батчами по 500 (лимит
    GAQL на количество значений в IN).
    """
    names = {}
    resource_names = list(resource_names)
    for i in range(0, len(resource_names), 500):
        batch_rn = resource_names[i : i + 500]
        rn_list = ", ".join(f"'{rn}'" for rn in batch_rn)
        query = f"""
            SELECT
                geo_target_constant.resource_name,
                geo_target_constant.name,
                geo_target_constant.canonical_name,
                geo_target_constant.target_type
            FROM geo_target_constant
            WHERE geo_target_constant.resource_name IN ({rn_list})
        """
        for batch in ga_service_client.search_stream(customer_id=customer_id, query=query):
            for row in batch.results:
                g = row.geo_target_constant
                names[g.resource_name] = {
                    "name": g.name,
                    "canonical_name": g.canonical_name,
                    "target_type": g.target_type,
                }
    return names


def fetch_geo_criteria(ga_service, customer_id, campaign_names=None):
    """Гео-таргетинг (positive/negative location criteria) -> DataFrame.

    Расшифровывает geoTargetConstants/<id> в читаемое название через
    resolve_geo_target_names (ZIP-код / город / округ и т.п. — target_type
    показывает, что именно это за единица таргетинга).
    """
    query = """
        SELECT
            campaign.name,
            campaign_criterion.type,
            campaign_criterion.negative,
            campaign_criterion.location.geo_target_constant,
            campaign_criterion.proximity.radius,
            campaign_criterion.proximity.radius_units
        FROM campaign_criterion
        WHERE campaign_criterion.type IN ('LOCATION', 'PROXIMITY')
            AND campaign.status = 'ENABLED'
    """

    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_names and row.campaign.name not in campaign_names:
                continue
            cc = row.campaign_criterion
            ctype = _enum_name("CriterionTypeEnum", "CriterionType", cc.type_)
            rows.append({
                "Campaign": row.campaign.name,
                "Type": ctype,
                "Negative": cc.negative,
                "Geo_target_constant": cc.location.geo_target_constant or "",
                "Proximity_radius": cc.proximity.radius or None,
                "Proximity_radius_units": (
                    _enum_name("ProximityRadiusUnitsEnum", "ProximityRadiusUnits", cc.proximity.radius_units)
                    if cc.proximity.radius_units else ""
                ),
            })

    if not rows:
        return pd.DataFrame()

    geo_rns = {r["Geo_target_constant"] for r in rows if r["Geo_target_constant"]}
    if geo_rns:
        resolved = resolve_geo_target_names(ga_service, customer_id, geo_rns)
        for r in rows:
            info = resolved.get(r["Geo_target_constant"])
            r["Geo_name"] = info["canonical_name"] if info else "(не удалось разрешить)"
            r["Geo_target_type"] = info["target_type"] if info else ""

    return pd.DataFrame(rows)


def fetch_ad_schedule(ga_service, customer_id, campaign_names=None):
    """Расписание показов (ad_schedule_view / campaign_criterion AD_SCHEDULE) -> DataFrame."""
    query = """
        SELECT
            campaign.name,
            campaign_criterion.ad_schedule.day_of_week,
            campaign_criterion.ad_schedule.start_hour,
            campaign_criterion.ad_schedule.start_minute,
            campaign_criterion.ad_schedule.end_hour,
            campaign_criterion.ad_schedule.end_minute
        FROM campaign_criterion
        WHERE campaign_criterion.type = 'AD_SCHEDULE'
            AND campaign.status = 'ENABLED'
    """

    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_names and row.campaign.name not in campaign_names:
                continue
            sch = row.campaign_criterion.ad_schedule
            rows.append({
                "Campaign": row.campaign.name,
                "Day": _enum_name("DayOfWeekEnum", "DayOfWeek", sch.day_of_week),
                "Start": f"{sch.start_hour:02d}:{sch.start_minute * 15:02d}",
                "End": f"{sch.end_hour:02d}:{sch.end_minute * 15:02d}",
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Andverpersonalinjury"')
    ap.add_argument("--campaigns", help="Список названий кампаний через запятую (без — все ENABLED)")
    args = ap.parse_args()

    if args.customer_id:
        customer_id = args.customer_id.replace("-", "").strip()
    elif args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
        if not customer_id:
            print(f"У клиента '{args.client}' на вкладке 'Google_Ads_API' пустой client_id")
            return
    else:
        print("Нужен либо --client, либо --customer-id")
        return

    campaign_names = None
    if args.campaigns:
        campaign_names = {c.strip() for c in args.campaigns.split(",")}

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    out_dir = client_stats_dir(args.client_folder)

    df_core = fetch_campaign_core(ga_service, customer_id, campaign_names)
    core_path = out_dir / "gads_campaign_settings_core.csv"
    df_core.to_csv(core_path, index=False, encoding="utf-8")
    print(f"Сохранено: {core_path} ({len(df_core)} кампаний)")
    if not df_core.empty:
        print(df_core.to_string(index=False))

    df_geo = fetch_geo_criteria(ga_service, customer_id, campaign_names)
    geo_path = out_dir / "gads_campaign_settings_geo.csv"
    df_geo.to_csv(geo_path, index=False, encoding="utf-8")
    print(f"\nСохранено: {geo_path} ({len(df_geo)} гео-критериев)")
    if not df_geo.empty:
        print(df_geo.to_string(index=False))
        print(
            "\nПРИМЕЧАНИЕ: Geo_target_constant — сырой resource name (числовой ID),"
            " не название города. Расшифровка требует отдельного шага (см. docstring"
            " fetch_geo_criteria) — не реализовано в этой версии."
        )

    df_schedule = fetch_ad_schedule(ga_service, customer_id, campaign_names)
    schedule_path = out_dir / "gads_campaign_settings_schedule.csv"
    df_schedule.to_csv(schedule_path, index=False, encoding="utf-8")
    print(f"\nСохранено: {schedule_path} ({len(df_schedule)} строк расписания)")
    if not df_schedule.empty:
        print(df_schedule.to_string(index=False))
    else:
        print("Расписание не задано (показ круглосуточно) для выбранных кампаний.")


if __name__ == "__main__":
    main()
