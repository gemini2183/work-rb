#!/usr/bin/env python
# coding: utf-8
"""Создаёт КМС-кампанию ретаргетинга (адаптивное медийное объявление) через Google Ads API.

Зачем API, а не CSV для Editor: Editor не кладёт картинки в CSV (картинки идут
отдельным архивом), поэтому bulksheet-подход из gads_campaign_builder.py для
адаптивных медийных объявлений с картинками не работает. Картинки при этом уже
лежат в аккаунте как ассеты (скачаны из ассет-группы pmax1_test, см.
Клиенты/ProfiMet/Креативы/), поэтому здесь они переиспользуются по ID и заново
не заливаются.

Создаёт одной транзакцией (MutateGoogleAdsService.mutate): бюджет, кампанию
(Display, Maximize clicks, пауза), язык/гео/расписание, группу объявлений с
аудиторией (targeting, не observation) и исключением лидов, адаптивное
объявление.

БЕЗОПАСНОСТЬ: по умолчанию запускается в режиме validate_only — Google проверяет
запрос на своей стороне, но НИЧЕГО не создаёт. Реальная запись — только с флагом
--execute. Кампания всегда создаётся на паузе.

Использование:
    python gads_display_rtg_builder.py --customer-id 7552781705            # проверка
    python gads_display_rtg_builder.py --customer-id 7552781705 --execute  # запись
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "dspl_rtg_basket"
AD_GROUP_NAME = "rtg_cart_60d"
BUDGET_PLN = 40
POLAND_GEO = "geoTargetConstants/2616"
LANGUAGES = ["languageConstants/1030", "languageConstants/1000"]  # pl, en — как в черновике Editor
AD_GROUP_CPC_PLN = 0.50  # ставка группы из черновика Editor (при Maximize clicks не используется)
CALL_TO_ACTION = "Otwórz stronę"
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=cid|{campaignid}|"
    "{ifsearch:search}{ifcontent:context}&utm_content=rb|cid|{campaignid}|"
    "{ifsearch:search}{ifcontent:context}|gid|{adgroupid}|aid|{creative}|"
    "position|{adposition}|placement|{placement}|device|{device}|placement|{placement}|"
    "region_id|{loc_physical_ms}|targetid|{targetid}|gclid|{gclid}&utm_term={keyword}"
)

# Аудитория: 60 дней, потому что 30-дневный список на Display = 16 человек (2026-10-06)
USER_LIST_INCLUDE = 8365998003  # GA4 - Добавили товар в корзину (60 дн.)
USER_LIST_EXCLUDE = 8366436798  # GA4 - Лиды (60 дн.)

# Тексты и ассеты — Клиенты/ProfiMet/Креативы/КМС_ретаргет_корзина_креативы.md
HEADLINES = [
    "Twoja szklarnia wciąż czeka",
    "Płatność dopiero przy odbiorze",
    "3 prezenty do końca miesiąca",
    "Darmowa dostawa w 3-7 dni",
    "Szklarnia prosto od producenta",
]
LONG_HEADLINE = "Wróć po swoją szklarnię: 3 prezenty gratis do końca miesiąca i płatność przy odbiorze"
DESCRIPTIONS = [
    "Wybrana szklarnia nadal czeka. 3 prezenty gratis do końca miesiąca i darmowa dostawa.",
    "Płacisz dopiero przy odbiorze. Bez przedpłaty. Szklarnia prosto od polskiego producenta.",
    "Poliwęglan 4-6 mm z filtrem UV i mocne profile 40x20 mm. Polska produkcja, gwarancja.",
    "Masz pytania o wymiary? Zadzwoń, doradca pomoże dobrać szklarnię. Darmowa dostawa.",
    "3 prezenty: dodatkowe okno, zestaw do podwiązywania roślin, taśma paroprzepuszczalna.",
]
BUSINESS_NAME = "Profimet"
ASSETS_LANDSCAPE = [297786040282, 322937504523]                    # 1,91:1
ASSETS_SQUARE = [322886122180, 322937504517, 322937874606, 322937937225]  # 1:1
ASSETS_LOGO_LANDSCAPE = [17107180913]                              # 4:1
ASSETS_LOGO_SQUARE = [286986548910]                                # 1:1


def check_limits():
    assert all(len(h) <= 30 for h in HEADLINES), "заголовок > 30"
    assert len(LONG_HEADLINE) <= 90, "длинный заголовок > 90"
    assert all(len(d) <= 90 for d in DESCRIPTIONS), "описание > 90"
    assert len(BUSINESS_NAME) <= 25


def build_operations(client, cid, final_url, hour_from, hour_to):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ad_group_rn = f"customers/{cid}/adGroups/-3"
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{CAMPAIGN_NAME} budget {ts}"
    b.amount_micros = BUDGET_PLN * 1_000_000
    b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = client.enums.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.DISPLAY
    c.campaign_budget = budget_rn
    c.target_spend.SetInParent()  # Maximize clicks
    c.network_settings.target_content_network = True
    c.geo_target_type_setting.positive_geo_target_type = (
        client.enums.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST)
    c.geo_target_type_setting.negative_geo_target_type = (
        client.enums.NegativeGeoTargetTypeEnum.PRESENCE)
    c.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
    c.tracking_url_template = TRACKING_TEMPLATE

    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.location.geo_target_constant = POLAND_GEO
    for lang in LANGUAGES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = lang
    for day in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, day)
        cc.ad_schedule.start_hour = hour_from
        cc.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        cc.ad_schedule.end_hour = hour_to
        cc.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO

    ag = new_op().ad_group_operation.create
    ag.resource_name = ad_group_rn
    ag.name = AD_GROUP_NAME
    ag.campaign = campaign_rn
    ag.type_ = client.enums.AdGroupTypeEnum.DISPLAY_STANDARD
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    ag.optimized_targeting_enabled = False
    ag.cpc_bid_micros = int(AD_GROUP_CPC_PLN * 1_000_000)
    tr = ag.targeting_setting.target_restrictions.add()
    tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
    tr.bid_only = False  # "Targeting" (ограничивать показ аудиторией), не "Observation"

    for list_id, negative in ((USER_LIST_INCLUDE, False), (USER_LIST_EXCLUDE, True)):
        agc = new_op().ad_group_criterion_operation.create
        agc.ad_group = ad_group_rn
        agc.negative = negative
        agc.user_list.user_list = f"customers/{cid}/userLists/{list_id}"

    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ad_group_rn
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(final_url)
    rda = aga.ad.responsive_display_ad
    for text in HEADLINES:
        rda.headlines.add().text = text
    rda.long_headline.text = LONG_HEADLINE
    for text in DESCRIPTIONS:
        rda.descriptions.add().text = text
    rda.business_name = BUSINESS_NAME
    rda.call_to_action_text = CALL_TO_ACTION
    rda.control_spec.enable_asset_enhancements = True  # как в черновике Editor
    rda.control_spec.enable_autogen_video = True      # как в черновике Editor
    for asset_id in ASSETS_LANDSCAPE:
        rda.marketing_images.add().asset = f"customers/{cid}/assets/{asset_id}"
    for asset_id in ASSETS_SQUARE:
        rda.square_marketing_images.add().asset = f"customers/{cid}/assets/{asset_id}"
    for asset_id in ASSETS_LOGO_LANDSCAPE:
        rda.logo_images.add().asset = f"customers/{cid}/assets/{asset_id}"
    for asset_id in ASSETS_LOGO_SQUARE:
        rda.square_logo_images.add().asset = f"customers/{cid}/assets/{asset_id}"
    return ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--final-url", default="https://mocnaszklarnia.pl/")
    ap.add_argument("--hour-from", type=int, default=7)
    ap.add_argument("--hour-to", type=int, default=20)
    ap.add_argument("--execute", action="store_true",
                    help="Реально создать объекты. Без флага — только validate_only")
    args = ap.parse_args()

    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    service = client.get_service("GoogleAdsService")
    ops = build_operations(client, cid, args.final_url, args.hour_from, args.hour_to)

    request = client.get_type("MutateGoogleAdsRequest")
    request.customer_id = cid
    request.mutate_operations.extend(ops)
    request.validate_only = not args.execute
    try:
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
    print("Создано (кампания на паузе):")
    for r in response.mutate_operation_responses:
        kind = r.WhichOneof("response")
        print(" ", kind, getattr(r, kind).resource_name)


if __name__ == "__main__":
    main()
