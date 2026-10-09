#!/usr/bin/env python
# coding: utf-8
"""Создаёт Demand Gen `dg_interest_nodiscover` (ProfiMet) через Google Ads API: Gmail + Display, без Discover и YouTube.

Эксперимент Э-11 (Клиенты/ProfiMet/Эксперименты.md). Одной транзакцией: бюджет, кампания (Demand Gen, Maximize conversions
без цели по CPA, ПАУЗА), гео/язык/расписание, две группы объявлений — `inmarket` (4 in-market категории по индексам
покупателей CRM) и `intent_queries` (пользовательская аудитория «Целевые запросы 5»), исключение CRM-покупателей,
по два объявления в группе (карусель на готовых карточках `dg_lookalike_test` и мультиассет).

Цели кампании ставятся ОТДЕЛЬНЫМ шагом: gads_set_campaign_goals.py (как у dg_lookalike_test). Включение — отдельным согласованием.

БЕЗОПАСНОСТЬ: по умолчанию validate_only — Google проверяет запрос, ничего не создаёт. Запись только с --execute.
Кампания всегда на паузе. После записи читает объекты обратно.

Использование:
    python gads_demand_gen_interest_builder.py --customer-id 7552781705            # проверка
    python gads_demand_gen_interest_builder.py --customer-id 7552781705 --execute  # запись (на паузе)
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML
from gads_demand_gen_builder import (ASSET_LOGO_SQUARE, ASSETS_LANDSCAPE, ASSETS_PORTRAIT, ASSETS_SQUARE, BUSINESS_NAME,
                                     CALL_TO_ACTION, CAROUSEL_HEADLINE, CRM_EXCLUDE_LIST, FINAL_URL, HEADLINES,
                                     HOUR_FROM, HOUR_TO, LANGUAGES, MIN_FROM, MIN_TO, POLAND_GEO, WEEKDAYS)

CAMPAIGN_NAME = "dg_interest_nodiscover"
BUDGET_EUR = 25
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + CAMPAIGN_NAME + "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}"
    "|gid_{adgroupid}|aid_{creative}|pos_{adposition}|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}"
)
# Готовые карточки карусели из dg_lookalike_test (цены на 2026-10-08; перед включением сверить с главной)
CARD_ASSET_IDS = [428580621979, 428668905720, 428580622699, 428580621982, 428668905723]  # 1..5 (cardasset1,2,3,4,5)
# Описания: как у dg_lookalike_test, но акция без явной даты (акция ежемесячная, решение пользователя 2026-10-09)
DESCRIPTIONS = [
    "Producent szklarni od 16 lat. Własne warsztaty, ocynkowana stal, montaż bez spawania.",
    "Płatność przy odbiorze, bez przedpłaty. Zamówienie potwierdzamy telefonicznie.",
    "Dostawa w całej Polsce w 3-7 dni. Kurier rozładowuje u klienta.",
    "Gwarancja: 2 lata na ramę i 5 lat na poliwęglan. Doradca pomoże dobrać rozmiar.",
    "Przy zamówieniu w tym miesiącu 3 prezenty gratis. Zapytaj o szczegóły.",
]
CAROUSEL_DESCRIPTION = DESCRIPTIONS[1]
# In-market категории по индексам покупателей CRM (Аудитории/Инсайты_2026-10-08): id из user_interest
INMARKET = {"Lawn Care & Gardening Supplies": 80896, "Outdoor Items": 80501, "Landscape Design": 80494,
            "Business & Industrial Products": 80883}
CUSTOM_INTENT_AUDIENCE = 518459501  # «Целевые запросы 5» (запросы про szklarnia ogrodowa / poliwęglan)
GROUPS = ["inmarket", "intent_queries"]


def check_limits():
    assert all(len(h) <= 30 for h in HEADLINES), "заголовок > 30"
    assert all(len(d) <= 90 for d in DESCRIPTIONS), "описание > 90"
    assert len(set(CARD_ASSET_IDS)) == 5


def build_operations(client, cid):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    E = client.enums
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{CAMPAIGN_NAME} budget {ts}"
    b.amount_micros = BUDGET_EUR * 1_000_000
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.DEMAND_GEN
    c.campaign_budget = budget_rn
    c.maximize_conversions.SetInParent()  # без цели по CPA
    c.demand_gen_campaign_settings.upgraded_targeting = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = TRACKING_TEMPLATE

    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.location.geo_target_constant = POLAND_GEO
    for lang in LANGUAGES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = lang
    for day in WEEKDAYS:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = getattr(E.DayOfWeekEnum, day)
        cc.ad_schedule.start_hour = HOUR_FROM
        cc.ad_schedule.start_minute = getattr(E.MinuteOfHourEnum, MIN_FROM)
        cc.ad_schedule.end_hour = HOUR_TO
        cc.ad_schedule.end_minute = getattr(E.MinuteOfHourEnum, MIN_TO)

    logo_rn = f"customers/{cid}/assets/{ASSET_LOGO_SQUARE}"
    card_rns = [f"customers/{cid}/assets/{i}" for i in CARD_ASSET_IDS]

    for i, gname in enumerate(GROUPS, start=1):
        ag_rn = f"customers/{cid}/adGroups/-{2 + i}"
        ag = new_op().ad_group_operation.create
        ag.resource_name = ag_rn
        ag.name = gname
        ag.campaign = campaign_rn
        ag.status = E.AdGroupStatusEnum.ENABLED
        ag.optimized_targeting_enabled = False
        ch = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
        ch.discover = False  # главное отличие теста
        ch.gmail = True
        ch.display = True
        ch.youtube_in_stream = False
        ch.youtube_in_feed = False
        ch.youtube_shorts = False

        audience_rn = f"customers/{cid}/audiences/-{10 + i}"
        au = new_op().audience_operation.create
        au.resource_name = audience_rn
        au.name = f"{CAMPAIGN_NAME} {gname} {ts}"
        au.description = "Э-11: " + ("in-market интересы покупателей" if gname == "inmarket" else "пользовательская аудитория по запросам")
        dim = au.dimensions.add()
        if gname == "inmarket":
            for uid in INMARKET.values():
                dim.audience_segments.segments.add().user_interest.user_interest_category = f"customers/{cid}/userInterests/{uid}"
        else:
            dim.audience_segments.segments.add().custom_audience.custom_audience = f"customers/{cid}/customAudiences/{CUSTOM_INTENT_AUDIENCE}"
        au.exclusion_dimension.exclusions.add().user_list.user_list = f"customers/{cid}/userLists/{CRM_EXCLUDE_LIST}"
        agc = new_op().ad_group_criterion_operation.create
        agc.ad_group = ag_rn
        agc.audience.audience = audience_rn

        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.name = f"{CAMPAIGN_NAME} {gname} carousel"
        aga.ad.final_urls.append(FINAL_URL)
        car = aga.ad.demand_gen_carousel_ad
        car.business_name = BUSINESS_NAME
        car.logo_image.asset = logo_rn
        car.headline.text = CAROUSEL_HEADLINE
        car.description.text = CAROUSEL_DESCRIPTION
        car.call_to_action_text = CALL_TO_ACTION
        for rn in card_rns:
            car.carousel_cards.add().asset = rn

        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.name = f"{CAMPAIGN_NAME} {gname} multi asset"
        aga.ad.final_urls.append(FINAL_URL)
        m = aga.ad.demand_gen_multi_asset_ad
        m.business_name = BUSINESS_NAME
        m.call_to_action_text = CALL_TO_ACTION
        for t in HEADLINES:
            m.headlines.add().text = t
        for t in DESCRIPTIONS:
            m.descriptions.add().text = t
        for aid in ASSETS_LANDSCAPE:
            m.marketing_images.add().asset = f"customers/{cid}/assets/{aid}"
        for aid in ASSETS_SQUARE:
            m.square_marketing_images.add().asset = f"customers/{cid}/assets/{aid}"
        for aid in ASSETS_PORTRAIT:
            m.portrait_marketing_images.add().asset = f"customers/{cid}/assets/{aid}"
        m.logo_images.add().asset = logo_rn
    return ops


def read_back(client, cid, campaign_rn):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    camp_id = campaign_rn.split("/")[-1]
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {camp_id}")):
        k = r.campaign
        print(f"{k.id} | {k.name} | {E.CampaignStatusEnum.CampaignStatus.Name(k.status)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type)} | бюджет {r.campaign_budget.amount_micros / 1e6}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group "
            f"WHERE campaign.id = {camp_id}")):
        print("группа:", r.ad_group.id, r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status))
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group_ad.ad.name, ad_group_ad.status, ad_group_ad.policy_summary.approval_status "
            f"FROM ad_group_ad WHERE campaign.id = {camp_id}")):
        print("  объявление:", r.ad_group.name, "|", r.ad_group_ad.ad.name,
              E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status),
              E.PolicyApprovalStatusEnum.PolicyApprovalStatus.Name(r.ad_group_ad.policy_summary.approval_status))
    n = sum(1 for _ in ga.search(customer_id=cid, query=(
        f"SELECT campaign_criterion.type FROM campaign_criterion WHERE campaign.id = {camp_id}")))
    print("критериев кампании (гео, язык, расписание):", n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага — только validate_only")
    ap.add_argument("--read-back-only", action="store_true")
    args = ap.parse_args()
    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    if args.read_back_only:
        for r in client.get_service("GoogleAdsService").search(customer_id=cid, query=(
                f"SELECT campaign.id FROM campaign WHERE campaign.name = '{CAMPAIGN_NAME}'")):
            read_back(client, cid, f"customers/{cid}/campaigns/{r.campaign.id}")
        return
    try:
        service = client.get_service("GoogleAdsService")
        ops = build_operations(client, cid)
        request = client.get_type("MutateGoogleAdsRequest")
        request.customer_id = cid
        request.mutate_operations.extend(ops)
        request.validate_only = not args.execute
        response = service.mutate(request=request)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)
    if not args.execute:
        print(f"Проверка пройдена ({len(ops)} операций). НИЧЕГО не создано (validate_only).")
        return
    campaign_rn = None
    for r in response.mutate_operation_responses:
        kind = r.WhichOneof("response")
        if kind == "campaign_result":
            campaign_rn = getattr(r, kind).resource_name
    print("Создано (кампания на паузе):", campaign_rn)
    if campaign_rn:
        read_back(client, cid, campaign_rn)


if __name__ == "__main__":
    main()
