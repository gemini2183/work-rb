#!/usr/bin/env python
# coding: utf-8
"""Создаёт кампанию Demand Gen `yt_warm` (ProfiMet YouTube, тёплая аудитория) через Google Ads API.

Одной транзакцией (MutateGoogleAdsService.mutate): бюджет, кампания (Demand Gen, Maximize conversions без цели по CPA,
ПАУЗА), гео и языки, расписание ПН-ПТ, группа объявлений (каналы только YouTube: in-stream, in-feed, Shorts;
Discover, Gmail, Display выключены; оптимизированный таргетинг выключен) с аудиторией «тёплые списки сайта»
и исключениями (CRM-покупатели, лиды), два видеообъявления (по одному ролику: 16:9 и 9:16, у каждого своя метка
utm_content для отдельного номера Ringostat), тексты, логотип, кнопка.

Цели кампании (форма, звонок из объявления, звонок с сайта) ставятся ОТДЕЛЬНЫМ шагом: gads_set_campaign_goals.py.
Решения и обоснование: Клиенты/ProfiMet_YouTube/Решения.md, План_фазы_1.md.

БЕЗОПАСНОСТЬ: по умолчанию validate_only — Google проверяет запрос, ничего не создаёт. Запись только с --execute.
Кампания всегда на паузе. Видео уже загружены в аккаунт (Ю-001), здесь только ссылки на готовые ассеты.

Использование:
    python gads_demand_gen_youtube_builder.py --customer-id 7552781705            # проверка
    python gads_demand_gen_youtube_builder.py --customer-id 7552781705 --execute  # запись (кампания на паузе)
"""
import argparse
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "yt_warm"
AD_GROUP_NAME = "yt_warm_g1"
BUDGET_EUR = 20  # потолок тёплой (решение 2026-11-03)
POLAND_GEO = "geoTargetConstants/2616"
LANGUAGES = ["languageConstants/1030", "languageConstants/1000"]  # pl, en
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")
FINAL_URL = "https://mocnaszklarnia.pl/"
BUSINESS_NAME = "ProfiMet"

# Тёплые списки (включить) и исключения; id и размеры для YouTube — Клиенты/ProfiMet_YouTube/План_фазы_1.md (03.11)
USER_LISTS_INCLUDE = [8699804100, 8575354546, 8576048211, 8365998003]  # 60sec (30), engage_mid, engage_hi, корзина 60 дн.
USER_LISTS_EXCLUDE = [9441800617, 8365697315]                           # CRM «уже купившие», GA4 - Лиды (540дн.)

# Видео-ассеты (загружены 2026-11-03, Ю-001): (метка utm_content, id видео-ассета, имя объявления)
VIDEOS = [
    ("yt_16x9", 435959602419, "yt_warm ad A 16x9"),
    ("yt_9x16", 435774123941, "yt_warm ad B 9x16"),
]

# Тексты — только по сайту mocnaszklarnia.pl, прочитан 2026-11-03 (См. План_фазы_1.md, таблица текстов)
HEADLINES = ["Płatność przy odbiorze", "Bez przedpłaty", "Szklarnie od producenta",
             "Ocynkowana rama szklarni", "2 lata gwarancji na ramę"]
LONG_HEADLINES = ["Szklarnie z poliwęglanu od producenta. Płatność przy odbiorze, bez przedpłaty.",
                  "Czy szklarnia wytrzyma śnieg i wiatr? Sprawdź, na co zwrócić uwagę przed zakupem."]
DESCRIPTIONS = [
    "Producent szklarni od 16 lat. Ocynkowana stal, montaż na skręcanie, bez spawania.",
    "Płacisz dopiero przy odbiorze. Zamówienie potwierdzamy telefonicznie.",
    "2 lata gwarancji na ramę i 5 lat na poliwęglan. Sprawdź modele na mocnaszklarnia.pl.",
    "Poliwęglan 4 lub 6 mm z ochroną UV. Wybierz model na mocnaszklarnia.pl.",
    "Cały komplet sprawdzamy trzykrotnie: przy pakowaniu, załadunku i rozładunku.",
]
CALL_TO_ACTION = "LEARN_MORE"  # допустимое значение проверяет validate_only

LOGO_FILE = Path(__file__).resolve().parent.parent / "Клиенты" / "ProfiMet_YouTube" / "Картинки" / "logo_square_1200_transparent.png"
PLACEHOLDER_LOGO_ASSET = 286986548910  # существующий квадратный логотип аккаунта (2048×2048) — только для проверки структуры

TRACK_TAIL = ("|gid_{adgroupid}|aid_{creative}|pos_{adposition}|dev_{device}|plc_{placement}"
              "|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}")


def tracking_template(label):
    # utm_content начинается с метки ячейки (на ней стоит фильтр канала Ringostat), дальше как в остальных кампаниях (rb_cid)
    return ("{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + CAMPAIGN_NAME +
            "&utm_content=" + label + "_rb_cid_{campaignid}" + TRACK_TAIL)


def check_limits():
    assert all(len(h) <= 30 for h in HEADLINES), "заголовок > 30"
    assert all(len(h) <= 90 for h in LONG_HEADLINES), "длинный заголовок > 90"
    assert all(len(d) <= 90 for d in DESCRIPTIONS), "описание > 90"
    assert len(BUSINESS_NAME) <= 25
    assert LOGO_FILE.exists(), f"нет файла {LOGO_FILE}"


def upload_logo(client, cid, execute):
    """Загружает логотип как image-ассет. Без execute — validate_only и подстановка существующего ассета для проверки структуры."""
    svc = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    op.create.name = f"{CAMPAIGN_NAME}_logo_square_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    op.create.image_asset.data = LOGO_FILE.read_bytes()
    req = client.get_type("MutateAssetsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    resp = svc.mutate_assets(request=req)
    if execute:
        return resp.results[0].resource_name
    print("Проверка загрузки логотипа пройдена (validate_only).")
    return f"customers/{cid}/assets/{PLACEHOLDER_LOGO_ASSET}"


def build_operations(client, cid, logo_rn):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    E = client.enums
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ad_group_rn = f"customers/{cid}/adGroups/-3"
    audience_rn = f"customers/{cid}/audiences/-4"
    cta_rn = f"customers/{cid}/assets/-5"
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
    c.maximize_conversions.SetInParent()  # без цели по CPA (как dg_*, решение 2026-10-08)
    c.demand_gen_campaign_settings.upgraded_targeting = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING

    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.location.geo_target_constant = POLAND_GEO
    for lang in LANGUAGES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = lang
    for day in WEEKDAYS:  # будни, весь день (допущение: часы работы клиента 9–17 пока не ограничиваем)
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = getattr(E.DayOfWeekEnum, day)
        cc.ad_schedule.start_hour = 0
        cc.ad_schedule.start_minute = E.MinuteOfHourEnum.ZERO
        cc.ad_schedule.end_hour = 24
        cc.ad_schedule.end_minute = E.MinuteOfHourEnum.ZERO

    ag = new_op().ad_group_operation.create
    ag.resource_name = ad_group_rn
    ag.name = AD_GROUP_NAME
    ag.campaign = campaign_rn
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.optimized_targeting_enabled = False
    ch = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
    ch.discover = False
    ch.gmail = False
    ch.display = False
    ch.youtube_in_stream = True
    ch.youtube_in_feed = True
    ch.youtube_shorts = True

    # Аудитория: тёплые списки (включить) минус CRM-покупатели и лиды
    au = new_op().audience_operation.create
    au.resource_name = audience_rn
    au.name = f"{CAMPAIGN_NAME} тёплые списки без покупателей и лидов {ts}"
    au.description = "60sec (30) + engage_mid + engage_hi + корзина 60 дн.; исключены CRM-покупатели и GA4-лиды (540 дн.)"
    dim = au.dimensions.add()
    for ul in USER_LISTS_INCLUDE:
        dim.audience_segments.segments.add().user_list.user_list = f"customers/{cid}/userLists/{ul}"
    for ul in USER_LISTS_EXCLUDE:
        au.exclusion_dimension.exclusions.add().user_list.user_list = f"customers/{cid}/userLists/{ul}"
    agc = new_op().ad_group_criterion_operation.create
    agc.ad_group = ad_group_rn
    agc.audience.audience = audience_rn

    # Кнопка: отдельный ассет call_to_action
    a = new_op().asset_operation.create
    a.resource_name = cta_rn
    a.name = f"{CAMPAIGN_NAME}_cta_{ts}"
    a.call_to_action_asset.call_to_action = getattr(E.CallToActionTypeEnum, CALL_TO_ACTION)

    for label, video_asset, ad_name in VIDEOS:
        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ad_group_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.name = ad_name
        aga.ad.final_urls.append(FINAL_URL)
        aga.ad.tracking_url_template = tracking_template(label)
        v = aga.ad.demand_gen_video_responsive_ad
        v.videos.add().asset = f"customers/{cid}/assets/{video_asset}"
        for t in HEADLINES:
            v.headlines.add().text = t
        for t in LONG_HEADLINES:
            v.long_headlines.add().text = t
        for t in DESCRIPTIONS:
            v.descriptions.add().text = t
        v.business_name.text = BUSINESS_NAME
        v.logo_images.add().asset = logo_rn
        v.call_to_actions.add().asset = cta_rn
    return ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага — только validate_only")
    args = ap.parse_args()

    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    try:
        service = client.get_service("GoogleAdsService")
        logo_rn = upload_logo(client, cid, args.execute)
        ops = build_operations(client, cid, logo_rn)
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
