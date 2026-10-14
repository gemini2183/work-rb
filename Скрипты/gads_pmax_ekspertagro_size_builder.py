#!/usr/bin/env python
# coding: utf-8
"""Создаёт Performance Max `general_pmax_rozmiary` (ExpertAgro, Теплицы Польша) через Google Ads API.

План — Клиенты/EkspertAgro/Кампании/РСЯ_КМС/План_PMax_и_DG_lookalike_2026-10-14.md (согласован пользователем 2026-10-14).
Четыре группы ассетов по размеру (3x6, 3x4, 2x4, 4x6); финальный URL — каталог Tilda с фильтром ширина+длина и
`utm_content=ag_<размер>` (метка группы попадает в Supabase); сигналы — поисковые темы размера + одна аудитория
(CRM-список покупателей + in-market 80896 Lawn Care & Gardening и 80501 Outdoor Items — гипотеза из ProfiMet).

Одной транзакцией (GoogleAdsService.mutate): бюджет 110 zł, кампания (PMax, Maximize conversions БЕЗ цели CPA, ПАУЗА,
автогенерация видео/текстов/картинок и расширение URL выключены), гео/язык/расписание, логотип, название бизнеса и звонковый
ассет (существующие), аудитория-сигнал, 4 группы с текстами, картинками (существующие реальные фото сайта) и сигналами.
Цели ставок (форма + звонок из объявления, без «клика по номеру») — ОТДЕЛЬНЫМ шагом gads_set_campaign_goals.py.

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись только с --execute. Кампания всегда на паузе. Перед записью проверяется,
что кампании с таким именем нет (защита от дубля). После записи читает объекты обратно. Если чтение упало — НЕ запускать
--execute повторно, а использовать --read-back-only.

Использование:
    python gads_pmax_ekspertagro_size_builder.py --customer-id 8826134558             # проверка
    python gads_pmax_ekspertagro_size_builder.py --customer-id 8826134558 --execute   # запись (на паузе)
    python gads_pmax_ekspertagro_size_builder.py --customer-id 8826134558 --read-back-only
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_search_ekspertagro_size_builder import DESCRIPTIONS, D2, EXTRA, GROUPS, SITE, W, L
from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "general_pmax_rozmiary"   # = utm_campaign: содержит `general_pmax` (канал Ringostat General - pmax, проверено 14.10)
BUDGET_PLN = 110
POLAND_GEO = "geoTargetConstants/2616"
LANGUAGES = ["languageConstants/1030", "languageConstants/1000"]
SCHEDULE = [("MONDAY", 7, 17), ("TUESDAY", 7, 17), ("WEDNESDAY", 7, 17), ("THURSDAY", 7, 17),
            ("FRIDAY", 7, 17), ("SATURDAY", 9, 18)]
FINAL_URL_SUFFIX = f"utm_source=google&utm_medium=cpc&utm_campaign={CAMPAIGN_NAME}"
CRM_LIST_ID = 9475706784
INMARKET_IDS = [80896, 80501]  # Lawn Care & Gardening Supplies, Home & Garden > Outdoor Items (индексы ProfiMet; для ExpertAgro не проверены)
# Существующие ассеты аккаунта (реальные фото сайта без значка ИИ, логотип, название, звонковый ассет с номером PMax-пула)
IMAGES = [(334849195421, "SQUARE_MARKETING_IMAGE"), (334938661390, "SQUARE_MARKETING_IMAGE"),
          (334849207652, "MARKETING_IMAGE"), (334938102400, "MARKETING_IMAGE"),
          (334849355174, "PORTRAIT_MARKETING_IMAGE"), (334938554638, "PORTRAIT_MARKETING_IMAGE")]
CAMPAIGN_ASSETS = [(315822292116, "LOGO"), (314556660604, "BUSINESS_NAME"), (426265129071, "CALL")]
SHORT_DESCRIPTION = "Płatność przy odbiorze. Darmowa dostawa po Polsce."   # <= 60 знаков (требование PMax)


def sizes():
    """[(имя группы, spec)] — те же тексты и ключи, что у Search."""
    return [(g["name"], g) for g in GROUPS] + [(k, v) for k, v in EXTRA.items()]


def group_url(g):
    return f"{g['url']}&utm_content=ag_{g['name']}"


def long_headlines(g):
    s = g["name"]
    return [f"Szklarnie {s} m z poliwęglanu 4 i 6 mm prosto od producenta. Zobacz modele i ceny.",
            f"Szklarnia {s} z poliwęglanu. Płatność przy odbiorze i darmowa dostawa po Polsce."]


def descriptions(g):
    return [g["d1"], D2, g.get("d3", DESCRIPTIONS[0]), DESCRIPTIONS[1], SHORT_DESCRIPTION]


def headlines(g):
    return [g["h1"]] + g["headlines"]            # 12 заголовков (лимит PMax — 15)


def check_limits():
    for _, g in sizes():
        assert all(len(h) <= 30 for h in headlines(g)), headlines(g)
        assert any(len(h) <= 15 for h in headlines(g)), "нужен заголовок до 15 знаков"
        assert all(len(t) <= 90 for t in long_headlines(g) + descriptions(g))
        assert any(len(d) <= 60 for d in descriptions(g)), "нужно описание до 60 знаков"
        assert 3 <= len(headlines(g)) <= 15 and 1 <= len(long_headlines(g)) <= 5 and 2 <= len(descriptions(g)) <= 5


def campaign_exists(ga, cid):
    q = f"SELECT campaign.id FROM campaign WHERE campaign.name = '{CAMPAIGN_NAME}' AND campaign.status != 'REMOVED'"
    return [r.campaign.id for r in ga.search(customer_id=cid, query=q)]


def build_operations(client, cid):
    E = client.enums
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ops = []
    counter = [1000]

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{CAMPAIGN_NAME} budget {ts}"
    b.amount_micros = BUDGET_PLN * 1_000_000
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    c.campaign_budget = budget_rn
    client.copy_from(c.maximize_conversions, client.get_type("MaximizeConversions"))   # без цели CPA
    c.brand_guidelines_enabled = True
    c.final_url_suffix = FINAL_URL_SUFFIX
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    for typ in ("TEXT_ASSET_AUTOMATION", "GENERATE_IMAGE_ENHANCEMENT", "GENERATE_IMAGE_EXTRACTION",
                "GENERATE_ENHANCED_YOUTUBE_VIDEOS", "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION"):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = getattr(E.AssetAutomationTypeEnum, typ)
        s.asset_automation_status = E.AssetAutomationStatusEnum.OPTED_OUT

    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.location.geo_target_constant = POLAND_GEO
    for lang in LANGUAGES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = lang
    for day, h1, h2 in SCHEDULE:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = getattr(E.DayOfWeekEnum, day)
        cc.ad_schedule.start_hour = h1
        cc.ad_schedule.start_minute = E.MinuteOfHourEnum.ZERO
        cc.ad_schedule.end_hour = h2
        cc.ad_schedule.end_minute = E.MinuteOfHourEnum.ZERO

    for aid, ft in CAMPAIGN_ASSETS:
        ca = new_op().campaign_asset_operation.create
        ca.campaign = campaign_rn
        ca.asset = f"customers/{cid}/assets/{aid}"
        ca.field_type = getattr(E.AssetFieldTypeEnum, ft)

    # аудитория-сигнал: CRM-покупатели + in-market (один Audience на все группы)
    aud_rn = f"customers/{cid}/audiences/-91"
    au = new_op().audience_operation.create
    au.resource_name = aud_rn
    au.name = f"ExpertAgro сигнал {ts[:8]}: CRM-покупатели + in-market"
    au.description = "Список 9475706784 (CRM, 540 дн.) + in-market Lawn Care & Gardening, Outdoor Items (гипотеза ProfiMet)"
    dim = au.dimensions.add()
    seg = dim.audience_segments.segments.add()
    seg.user_list.user_list = f"customers/{cid}/userLists/{CRM_LIST_ID}"
    for uid in INMARKET_IDS:
        seg = dim.audience_segments.segments.add()
        seg.user_interest.user_interest_category = f"customers/{cid}/userInterests/{uid}"

    text_assets = {}   # (поле, текст) -> временный ресурс: одинаковые тексты не дублируем

    def text_asset(text):
        if text not in text_assets:
            counter[0] += 1
            rn = f"customers/{cid}/assets/-{counter[0]}"
            a = new_op().asset_operation.create
            a.resource_name = rn
            a.text_asset.text = text
            text_assets[text] = rn
        return text_assets[text]

    for i, (name, g) in enumerate(sizes(), start=1):
        ag_rn = f"customers/{cid}/assetGroups/-{50 + i}"
        ag = new_op().asset_group_operation.create
        ag.resource_name = ag_rn
        ag.name = name
        ag.campaign = campaign_rn
        ag.final_urls.append(group_url(g))
        ag.path1 = "szklarnie"
        ag.path2 = name
        ag.status = E.AssetGroupStatusEnum.ENABLED

        def link(asset_rn, field):
            aga = new_op().asset_group_asset_operation.create
            aga.asset_group = ag_rn
            aga.asset = asset_rn
            aga.field_type = getattr(E.AssetFieldTypeEnum, field)

        for t in headlines(g):
            link(text_asset(t), "HEADLINE")
        for t in long_headlines(g):
            link(text_asset(t), "LONG_HEADLINE")
        for t in descriptions(g):
            link(text_asset(t), "DESCRIPTION")
        for aid, ft in IMAGES:
            link(f"customers/{cid}/assets/{aid}", ft)
        for theme in g["phrase"]:
            sig = new_op().asset_group_signal_operation.create
            sig.asset_group = ag_rn
            sig.search_theme.text = theme
        sig = new_op().asset_group_signal_operation.create
        sig.asset_group = ag_rn
        sig.audience.audience = aud_rn
    return ops


def read_back(client, cid, campaign_id):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, campaign.bidding_strategy_type, "
            "campaign.maximize_conversions.target_cpa_micros, campaign.final_url_suffix, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {campaign_id}")):
        k = r.campaign
        print(f"{k.id} | {k.name} | {E.CampaignStatusEnum.CampaignStatus.Name(k.status)} | "
              f"{E.AdvertisingChannelTypeEnum.AdvertisingChannelType.Name(k.advertising_channel_type)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type)} | цель CPA "
              f"{k.maximize_conversions.target_cpa_micros / 1e6} | бюджет {r.campaign_budget.amount_micros / 1e6}")
        print("  суффикс:", k.final_url_suffix)
    groups = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, asset_group.id, asset_group.name, asset_group.status, asset_group.final_urls "
            f"FROM asset_group WHERE campaign.id = {campaign_id} AND asset_group.status != 'REMOVED'")):
        groups[r.asset_group.id] = (r.asset_group.name, E.AssetGroupStatusEnum.AssetGroupStatus.Name(r.asset_group.status),
                                    list(r.asset_group.final_urls)[0])
    cnt = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, asset_group.id, asset_group_asset.field_type FROM asset_group_asset "
            f"WHERE campaign.id = {campaign_id} AND asset_group_asset.status != 'REMOVED'")):
        k = (r.asset_group.id, E.AssetFieldTypeEnum.AssetFieldType.Name(r.asset_group_asset.field_type))
        cnt[k] = cnt.get(k, 0) + 1
    sig = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, asset_group.id, asset_group_signal.search_theme.text, asset_group_signal.audience.audience "
            f"FROM asset_group_signal WHERE campaign.id = {campaign_id}")):
        k = (r.asset_group.id, "тема" if r.asset_group_signal.search_theme.text else "аудитория")
        sig[k] = sig.get(k, 0) + 1
    for gid, (name, st, url) in sorted(groups.items(), key=lambda x: x[1][0]):
        by = {ft: n for (g, ft), n in cnt.items() if g == gid}
        print(f"группа {name} [{st}] URL {url}")
        print("   ассеты:", by, "| сигналы:", {t: n for (g, t), n in sig.items() if g == gid})
    assets = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_asset.field_type, campaign_asset.status FROM campaign_asset "
            f"WHERE campaign.id = {campaign_id}")):
        k = (E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type),
             E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status))
        assets[k] = assets.get(k, 0) + 1
    print("ассеты кампании:", assets)
    crit = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_criterion.type, campaign_criterion.negative FROM campaign_criterion "
            f"WHERE campaign.id = {campaign_id}")):
        k = (E.CriterionTypeEnum.CriterionType.Name(r.campaign_criterion.type_), r.campaign_criterion.negative)
        crit[k] = crit.get(k, 0) + 1
    print("критерии кампании:", crit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--read-back-only", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    if a.read_back_only:
        for camp_id in campaign_exists(ga, cid):
            read_back(client, cid, camp_id)
        return
    check_limits()
    existing = campaign_exists(ga, cid)
    if existing and a.execute:
        print(f"СТОП: кампания «{CAMPAIGN_NAME}» уже есть (id {existing}); повторная запись создала бы дубль.")
        raise SystemExit(1)
    try:
        ops = build_operations(client, cid)
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.mutate_operations.extend(ops)
        req.validate_only = not a.execute
        resp = ga.mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)
    if not a.execute:
        print(f"Проверка пройдена ({len(ops)} операций). НИЧЕГО не создано (validate_only).")
        return
    campaign_id = None
    for r in resp.mutate_operation_responses:
        if r.WhichOneof("response") == "campaign_result":
            campaign_id = r.campaign_result.resource_name.split("/")[-1]
    print(f"Создано (кампания на паузе): id {campaign_id}, операций {len(ops)}")
    if campaign_id:
        read_back(client, cid, campaign_id)


if __name__ == "__main__":
    main()
