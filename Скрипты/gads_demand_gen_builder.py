#!/usr/bin/env python
# coding: utf-8
"""Создаёт кампанию Demand Gen `dg_lookalike_test` (ProfiMet) через Google Ads API.

Одной транзакцией (MutateGoogleAdsService.mutate): бюджет, кампания (Demand Gen, Maximize conversions
без цели по CPA, ПАУЗА), гео/язык/расписание, группа объявлений с look-alike (targeting, оптимизированный
таргетинг ВЫКЛ, каналы вручную: Discover + Gmail + Display, YouTube выключен) и исключением CRM-покупателей,
пять картинок для карточек карусели (загружаются), пять карточек, карусельное объявление
и мультиассет-объявление (на существующих картинках аккаунта).

Цели кампании (основные: форма, звонок из объявления, звонок с сайта; клик по номеру вторичный) ставятся
ОТДЕЛЬНЫМ шагом после создания: gads_set_campaign_goals.py (см. Клиенты/ProfiMet/Журнал_изменений.md).
Сам look-alike (2.5%, Narrow) создаётся отдельно: --create-lookalike (тоже validate_only без --execute).

БЕЗОПАСНОСТЬ: по умолчанию validate_only — Google проверяет запрос, ничего не создаёт. Запись только с --execute.
Кампания всегда на паузе.

Использование:
    python gads_demand_gen_builder.py --customer-id 7552781705 --lookalike-list-id 9475488813            # проверка
    python gads_demand_gen_builder.py --customer-id 7552781705 --create-lookalike                         # проверка look-alike
    python gads_demand_gen_builder.py --customer-id 7552781705 --lookalike-list-id <id> --execute       # запись
"""
import argparse
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "dg_lookalike_test"
AD_GROUP_NAME = "dg_lookalike_crm_2_5"
BUDGET_EUR = 20  # старт 20 (решение пользователя 2026-10-08 после перерасхода pmax01); после 2-3 нормальных дней поднять до 30
POLAND_GEO = "geoTargetConstants/2616"
LANGUAGES = ["languageConstants/1030", "languageConstants/1000"]  # pl, en
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")
HOUR_FROM, MIN_FROM, HOUR_TO, MIN_TO = 8, "FORTY_FIVE", 17, "ZERO"
FINAL_URL = "https://mocnaszklarnia.pl/"
CRM_EXCLUDE_LIST = 9441800617  # Profimet — уже купившие клиенты (Customer Match)
SEED_CRM_LIST = 9441800617
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + CAMPAIGN_NAME + "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}"
    "|gid_{adgroupid}|aid_{creative}|pos_{adposition}|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}"
)
BUSINESS_NAME = "Profimet"
CALL_TO_ACTION = "Learn more"  # допустимые значения проверяет validate_only

# Тексты — только из Клиенты/ProfiMet/Креативы/Факты_сайта_2026-10-08.md. Лимит заголовка 30 (API v23: max display width 30).
HEADLINES = ["Szklarnie prosto od producenta", "Poliwęglan 4-6 mm z filtrem UV", "Płatność przy odbiorze",
             "Darmowa dostawa od 1200 zł", "Szklarnie od 1199 zł"]
DESCRIPTIONS = [
    "Producent szklarni od 16 lat. Własne warsztaty, ocynkowana stal, montaż bez spawania.",
    "Płatność przy odbiorze, bez przedpłaty. Zamówienie potwierdzamy telefonicznie.",
    "Dostawa w całej Polsce w 3-7 dni, darmowa od 1200 zł. Kurier rozładowuje u klienta.",
    "Gwarancja: 2 lata na ramę i 5 lat na poliwęglan. Doradca pomoże dobrać rozmiar.",
    "Przy zamówieniu do 31 października 3 prezenty gratis. Zapytaj o szczegóły.",
]
# Карточки карусели: (заголовок, файл картинки 1:1). Цены — с главной страницы 2026-10-08 (для 2 м длины, 4 мм).
CARDS = [
    ("MOCNA 3 m od 1299 zł", "card1_1200x1200.jpg"),
    ("NORDSTAR 2,5 m od 1949 zł", "card2_1200x1200.jpg"),
    ("HOBBY 2,1 m od 1599 zł", "card3_1200x1200.jpg"),
    ("MOCNA MAXI 4 m od 2249 zł", "card4_1200x1200.jpg"),
    ("MINI 2 m od 1199 zł", "card5_1200x1200.jpg"),
]
CARDS_DIR = Path(__file__).resolve().parent.parent / "Клиенты" / "ProfiMet" / "Креативы" / "DG_карусель_карточки"
CAROUSEL_HEADLINE = "Szklarnie prosto od producenta"
CAROUSEL_DESCRIPTION = DESCRIPTIONS[1]
# Существующие картинки аккаунта (реальные фото, без ИИ-значка) для мультиассет-объявления
ASSETS_LANDSCAPE = [297786040282, 322937504523]                          # 1.91:1
ASSETS_SQUARE = [322886122180, 322937504517, 322937874606, 322937937225]  # 1:1
ASSETS_PORTRAIT = [322886732212, 322886750212, 322937426502]              # 4:5
ASSET_LOGO_SQUARE = 286986548910                                         # 1:1, 2048x2048


def check_limits():
    assert all(len(h) <= 30 for h in HEADLINES), "заголовок > 30"
    assert all(len(d) <= 90 for d in DESCRIPTIONS), "описание > 90"
    assert all(len(h) <= 30 for h, _ in CARDS), "заголовок карточки > 30 (мой запас)"
    assert len(BUSINESS_NAME) <= 25
    for _, f in CARDS:
        assert (CARDS_DIR / f).exists(), f"нет файла {f}"


def create_lookalike(client, cid, execute):
    svc = client.get_service("UserListService")
    op = client.get_type("UserListOperation")
    ul = op.create
    ul.name = "look-a-like / crm customers / 2.5% narrow " + datetime.now().strftime("%Y%m%d")
    ul.description = "Look-alike Narrow (2.5%) от CRM-покупателей (Customer Match), для Demand Gen dg_lookalike_test"
    ul.membership_life_span = 540
    ul.lookalike_user_list.seed_user_list_ids.append(SEED_CRM_LIST)
    ul.lookalike_user_list.expansion_level = client.enums.LookalikeExpansionLevelEnum.NARROW
    ul.lookalike_user_list.country_codes.append("PL")
    req = client.get_type("MutateUserListsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    resp = svc.mutate_user_lists(request=req)
    if execute:
        print("Создан look-alike:", resp.results[0].resource_name)
    else:
        print("Проверка look-alike пройдена. НИЧЕГО не создано (validate_only).")


def upload_card_images(client, cid, execute):
    """Загружает 5 картинок карточек как ассеты. Без execute — только validate_only и подставляет
    существующие квадратные ассеты аккаунта как заглушки, чтобы проверить остальную структуру."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    svc = client.get_service("AssetService")
    ops = []
    for i, (_, fname) in enumerate(CARDS, 1):
        op = client.get_type("AssetOperation")
        op.create.name = f"{CAMPAIGN_NAME}_card{i}_{ts}"
        op.create.image_asset.data = (CARDS_DIR / fname).read_bytes()
        ops.append(op)
    req = client.get_type("MutateAssetsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not execute
    resp = svc.mutate_assets(request=req)
    if execute:
        return [r.resource_name for r in resp.results]
    print("Проверка загрузки картинок пройдена (validate_only).")
    placeholders = ASSETS_SQUARE + [ASSET_LOGO_SQUARE]  # 5 разных квадратных ассетов (в карточках картинки не должны повторяться)
    return [f"customers/{cid}/assets/{placeholders[i]}" for i in range(len(CARDS))]


def build_operations(client, cid, lookalike_list_id, img_rns):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    E = client.enums
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
    b.amount_micros = BUDGET_EUR * 1_000_000
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.DEMAND_GEN
    c.campaign_budget = budget_rn
    c.maximize_conversions.SetInParent()  # без цели по CPA (решение пользователя 2026-10-08)
    c.demand_gen_campaign_settings.upgraded_targeting = False  # как у demand_gen: гео и язык на уровне кампании
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

    ag = new_op().ad_group_operation.create
    ag.resource_name = ad_group_rn
    ag.name = AD_GROUP_NAME
    ag.campaign = campaign_rn
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.optimized_targeting_enabled = False
    ch = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
    ch.discover = True
    ch.gmail = True
    ch.display = True
    ch.youtube_in_stream = False
    ch.youtube_in_feed = False
    ch.youtube_shorts = False

    # В Demand Gen аудитории подключаются через объединённый объект Audience (прямое подключение списка запрещено)
    audience_rn = f"customers/{cid}/audiences/-4"
    au = new_op().audience_operation.create
    au.resource_name = audience_rn
    au.name = f"{CAMPAIGN_NAME} look-alike без CRM-покупателей {ts}"
    au.description = "Look-alike от CRM-покупателей; исключены сами CRM-покупатели"
    dim = au.dimensions.add()
    dim.audience_segments.segments.add().user_list.user_list = f"customers/{cid}/userLists/{lookalike_list_id}"
    au.exclusion_dimension.exclusions.add().user_list.user_list = f"customers/{cid}/userLists/{CRM_EXCLUDE_LIST}"
    agc = new_op().ad_group_criterion_operation.create
    agc.ad_group = ad_group_rn
    agc.audience.audience = audience_rn

    # --- карточки (картинки загружены отдельным шагом upload_card_images)
    card_rns = []
    for i, (headline, fname) in enumerate(CARDS, 1):
        rn = f"customers/{cid}/assets/-{20 + i}"
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.name = f"{CAMPAIGN_NAME}_cardasset{i}_{ts}"
        a.final_urls.append(FINAL_URL)  # у карточки свой URL: пока главная для всех (решение пользователя)
        a.demand_gen_carousel_card_asset.square_marketing_image_asset = img_rns[i - 1]
        a.demand_gen_carousel_card_asset.headline = headline
        a.demand_gen_carousel_card_asset.call_to_action_text = CALL_TO_ACTION
        card_rns.append(rn)

    logo_rn = f"customers/{cid}/assets/{ASSET_LOGO_SQUARE}"

    # --- карусель
    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ad_group_rn
    aga.status = E.AdGroupAdStatusEnum.ENABLED
    aga.ad.name = f"{CAMPAIGN_NAME} carousel models"
    aga.ad.final_urls.append(FINAL_URL)
    car = aga.ad.demand_gen_carousel_ad
    car.business_name = BUSINESS_NAME
    car.logo_image.asset = logo_rn
    car.headline.text = CAROUSEL_HEADLINE
    car.description.text = CAROUSEL_DESCRIPTION
    car.call_to_action_text = CALL_TO_ACTION
    for rn in card_rns:
        car.carousel_cards.add().asset = rn

    # --- мультиассет (картинки, тексты)
    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ad_group_rn
    aga.status = E.AdGroupAdStatusEnum.ENABLED
    aga.ad.name = f"{CAMPAIGN_NAME} multi asset"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--lookalike-list-id", type=int, help="id look-alike списка для группы (для проверки можно взять существующий)")
    ap.add_argument("--create-lookalike", action="store_true", help="создать (или проверить создание) look-alike 2.5% от CRM")
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага — только validate_only")
    args = ap.parse_args()

    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    try:
        if args.create_lookalike:
            create_lookalike(client, cid, args.execute)
            return
        if not args.lookalike_list_id:
            raise SystemExit("нужен --lookalike-list-id")
        service = client.get_service("GoogleAdsService")
        img_rns = upload_card_images(client, cid, args.execute)
        ops = build_operations(client, cid, args.lookalike_list_id, img_rns)
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
    print("Создано (кампания на паузе):")
    for r in response.mutate_operation_responses:
        kind = r.WhichOneof("response")
        print(" ", kind, getattr(r, kind).resource_name)


if __name__ == "__main__":
    main()
