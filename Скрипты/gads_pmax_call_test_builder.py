#!/usr/bin/env python
# coding: utf-8
"""Создаёт тестовую Performance Max `pmax01_call_test` (оптимизация по клику по номеру, без видео) через Google Ads API.

Берёт за образец рабочую `pmax1_test`: гео (54 региона/города), языки, расписание ПН–ПТ 08:45–17:00, логотипы и название
бизнеса (уровень кампании), поисковые темы группы `search themes`, картинки и ПОДТВЕРЖДЁННЫЕ тексты этой группы
(без «100 000+ заказов», превосходных степеней и «экспорта в 11 стран» — см. Клиенты/ProfiMet/Креативы/).
Видео не добавляется; автоматическая генерация видео и текстов выключена.

Статический номер Ringostat: имя кампании начинается с `pmax01`, шаблон отслеживания ставит utm_campaign=pmax01_call_test,
канал `google_cpc_pmax` отдаёт номер из пула `Google CPC_pmax` (проверено ringostat_channel_matrix.py 2026-10-08).

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не создаёт). Запись — только с --execute.
Кампания всегда создаётся на ПАУЗЕ. Цели конверсий кампании (только «клик по номеру») ставятся отдельным шагом
gads_set_campaign_goals.py после создания.

Использование:
    python gads_pmax_call_test_builder.py --customer-id 7552781705            # проверка
    python gads_pmax_call_test_builder.py --customer-id 7552781705 --execute  # запись
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "pmax01_call_test"
GROUPS = [("call_test_search_themes", "themes"), ("call_test_interests", "interests"), ("call_test_competitors", "competitors")]
SRC_CAMPAIGN_ID = 23775369828
SRC_ASSET_GROUP = "search themes"
BUDGET_EUR = 40
TARGET_CPA_EUR = 12
FINAL_URL = "https://mocnaszklarnia.pl/"
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + CAMPAIGN_NAME + "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}"
    "|gid_{adgroupid}|aid_{creative}|pos_{adposition}|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}"
)

# Существующие ассеты рабочей группы, подтверждённые клиентом (Креативы/КМС_ретаргет_корзина_креативы.md, сайт 2026-10-08)
KEEP_HEADLINES = ["3 Prezenty Gratis", "Szklarnie z Poliwęglanu 4-6mm", "Trwałe Szklarnie od Producenta", "100% Produkcja w Polsce",
                  "Płatność Dopiero Przy Odbiorze", "Niskie Ceny od Producenta", "Darmowa Dostawa w 3-7 Dni", "Gwarancja Fabryczna"]
KEEP_LONG = ["Szklarnie z poliwęglanu w promocji! 3 prezenty gratis. Dostawa 3-7 dni gratis."]
KEEP_DESCRIPTIONS = ["Szklarnie od producenta w niskich cenach, płatność przy odbiorze",
                     "Szklarnie z poliwęglanu w promocji! 3 prezenty gratis. Dostawa 3-7 dni gratis.",
                     "Profimet — Od 16 lat zajmujemy się produkcją ocynkowanych szklarni"]
# Новые тексты только из подтверждённых фактов (одно описание не длиннее 60 знаков, один заголовок не длиннее 15 — требования PMax)
NEW_HEADLINES = ["Od Producenta", "Producent szklarni od 16 lat"]
NEW_DESCRIPTIONS = ["Szklarnie od producenta. Płatność przy odbiorze.",
                    "Poliwęglan 4-6 mm z filtrem UV i mocne profile 40x20 mm. Polska produkcja, gwarancja."]
IMAGE_FIELDS = ("MARKETING_IMAGE", "SQUARE_MARKETING_IMAGE", "PORTRAIT_MARKETING_IMAGE")
# In-market интересы списка покупателей CRM (индексы 2.9x / 2.6x / 2.3x / 1.9x; Клиенты/ProfiMet/Аудитории/Инсайты_2026-10-08.md)
INMARKET_IDS = [80896, 80883, 80501, 80494]  # Lawn Care & Gardening Supplies, Business & Industrial Products, Outdoor Items, Landscape Design
# Конкуренты: прежние 12 адресов аудитории `Конкуренты` без своего сайта и дубля + 5 подтверждённых по Auction insights (Клиенты/ProfiMet/Конкуренты.md)
COMPETITOR_DOMAINS = ["e-szklarnia.pl", "ekotunele.pl", "ekoszklarnia.pl", "wesoly-rolnik.online", "poliszklarnia.pl", "szklarnie24.pl",
                      "szklarnie-online.pl", "www.moja-szklarnia-ogrodowa.pl", "dobraszklarnia.pl", "wm-szklarnia.pl", "nowaszklarnia.pl",
                      "www.agroszklarnia.pl", "tunelefoliowe.eu", "alistan-shop.com", "cieplarnia.pl", "wesolyrolnik.pl", "szklarnie-online.eu"]
LANGUAGES = ["languageConstants/1000", "languageConstants/1030"]
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")


def check_limits():
    for h in KEEP_HEADLINES + NEW_HEADLINES:
        assert len(h) <= 30, f"заголовок > 30: {h}"
    assert any(len(h) <= 15 for h in KEEP_HEADLINES + NEW_HEADLINES), "нужен заголовок до 15 знаков"
    for l in KEEP_LONG:
        assert len(l) <= 90
    for d in KEEP_DESCRIPTIONS + NEW_DESCRIPTIONS:
        assert len(d) <= 90, f"описание > 90: {d}"
    assert any(len(d) <= 60 for d in KEEP_DESCRIPTIONS + NEW_DESCRIPTIONS), "нужно описание до 60 знаков"


def read_source(client, ga, cid):
    """Берём из рабочей группы: ресурсы существующих ассетов, картинки, поисковые темы; из кампании: гео, расписание, лого."""
    E = client.enums
    src = {"text": {}, "images": [], "themes": [], "geo": [], "schedule": [], "campaign_assets": []}
    q = ("SELECT campaign.id, asset_group.name, asset_group_asset.field_type, asset.resource_name, asset.text_asset.text "
         f"FROM asset_group_asset WHERE campaign.id = {SRC_CAMPAIGN_ID} AND asset_group.name = '{SRC_ASSET_GROUP}' "
         "AND asset_group_asset.status != 'REMOVED'")
    for r in ga.search(customer_id=cid, query=q):
        ft = E.AssetFieldTypeEnum.AssetFieldType.Name(r.asset_group_asset.field_type)
        if ft in ("HEADLINE", "LONG_HEADLINE", "DESCRIPTION"):
            src["text"][(ft, r.asset.text_asset.text)] = r.asset.resource_name
        elif ft in IMAGE_FIELDS:
            src["images"].append((ft, r.asset.resource_name))
    q = (f"SELECT campaign.id, asset_group.name, asset_group_signal.search_theme.text FROM asset_group_signal "
         f"WHERE campaign.id = {SRC_CAMPAIGN_ID} AND asset_group.name = '{SRC_ASSET_GROUP}'")
    for r in ga.search(customer_id=cid, query=q):
        if r.asset_group_signal.search_theme.text:
            src["themes"].append(r.asset_group_signal.search_theme.text)
    q = (f"SELECT campaign.id, campaign_criterion.type, campaign_criterion.negative, campaign_criterion.location.geo_target_constant, "
         f"campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, campaign_criterion.ad_schedule.start_minute, "
         f"campaign_criterion.ad_schedule.end_hour, campaign_criterion.ad_schedule.end_minute FROM campaign_criterion "
         f"WHERE campaign.id = {SRC_CAMPAIGN_ID} AND campaign_criterion.status != 'REMOVED'")
    for r in ga.search(customer_id=cid, query=q):
        t = E.CriterionTypeEnum.CriterionType.Name(r.campaign_criterion.type_)
        if t == "LOCATION" and not r.campaign_criterion.negative:
            src["geo"].append(r.campaign_criterion.location.geo_target_constant)
        elif t == "AD_SCHEDULE":
            s = r.campaign_criterion.ad_schedule
            src["schedule"].append((s.day_of_week, s.start_hour, s.start_minute, s.end_hour, s.end_minute))
    q = (f"SELECT campaign.id, campaign_asset.field_type, asset.resource_name FROM campaign_asset "
         f"WHERE campaign.id = {SRC_CAMPAIGN_ID} AND campaign_asset.status != 'REMOVED'")
    for r in ga.search(customer_id=cid, query=q):
        ft = E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type)
        if ft in ("BUSINESS_NAME", "LOGO", "LANDSCAPE_LOGO") and not r.asset.resource_name.endswith("/75071815196"):  # лого 32x32 Google не принимает
            src["campaign_assets"].append((ft, r.asset.resource_name))
    return src


def build_operations(client, cid, src, ca_rn):
    E = client.enums
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    asset_group_rn = f"customers/{cid}/assetGroups/-3"
    ops = []
    counter = [10]

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
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    c.campaign_budget = budget_rn
    c.maximize_conversions.target_cpa_micros = TARGET_CPA_EUR * 1_000_000
    c.brand_guidelines_enabled = True
    c.tracking_url_template = TRACKING_TEMPLATE
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    for typ in ("TEXT_ASSET_AUTOMATION", "GENERATE_IMAGE_ENHANCEMENT", "GENERATE_IMAGE_EXTRACTION", "GENERATE_ENHANCED_YOUTUBE_VIDEOS",
                "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION"):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = getattr(E.AssetAutomationTypeEnum, typ)
        s.asset_automation_status = E.AssetAutomationStatusEnum.OPTED_OUT

    for geo in src["geo"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = geo
    for lang in LANGUAGES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = lang
    for day, sh, sm, eh, em in src["schedule"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = day
        cc.ad_schedule.start_hour = sh
        cc.ad_schedule.start_minute = sm
        cc.ad_schedule.end_hour = eh
        cc.ad_schedule.end_minute = em

    for ft, asset_rn in src["campaign_assets"]:
        ca = new_op().campaign_asset_operation.create
        ca.campaign = campaign_rn
        ca.asset = asset_rn
        ca.field_type = getattr(E.AssetFieldTypeEnum, ft)

    def new_text_asset(text):
        counter[0] += 1
        rn = f"customers/{cid}/assets/-{counter[0]}"
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.text_asset.text = text
        return rn

    # Общий набор ассетов: тексты и картинки одинаковые во всех группах (группы различаются только сигналами)
    shared = []  # (resource_name ассета, тип поля)
    missing = []
    for field, keep in (("HEADLINE", KEEP_HEADLINES), ("LONG_HEADLINE", KEEP_LONG), ("DESCRIPTION", KEEP_DESCRIPTIONS)):
        for t in keep:
            rn = src["text"].get((field, t))
            if rn:
                shared.append((rn, field))
            else:
                missing.append((field, t))
                shared.append((new_text_asset(t), field))  # если такого ассета нет — создадим новый с тем же текстом
    for t in NEW_HEADLINES:
        shared.append((new_text_asset(t), "HEADLINE"))
    for t in NEW_DESCRIPTIONS:
        shared.append((new_text_asset(t), "DESCRIPTION"))
    for ft, rn in src["images"]:
        shared.append((rn, ft))

    # Аудитории-сигналы (две отдельные): интересы покупателей и конкуренты (новая аудитория; старую `Конкуренты` не меняем)
    aud_interests_rn = f"customers/{cid}/audiences/-91"
    au = new_op().audience_operation.create
    au.resource_name = aud_interests_rn
    au.name = f"Сигнал call_test {ts[:8]}: интересы покупателей (in-market)"
    au.description = "In-market: Lawn Care & Gardening Supplies, Business & Industrial Products, Outdoor Items, Landscape Design"
    dim = au.dimensions.add()
    for uid in INMARKET_IDS:
        seg = dim.audience_segments.segments.add()
        seg.user_interest.user_interest_category = f"customers/{cid}/userInterests/{uid}"
    aud_comp_rn = f"customers/{cid}/audiences/-92"
    au = new_op().audience_operation.create
    au.resource_name = aud_comp_rn
    au.name = f"Сигнал call_test {ts[:8]}: конкуренты"
    au.description = "Домены конкурентов (Auction insights 2026-10-08)"
    dim = au.dimensions.add()
    seg = dim.audience_segments.segments.add()
    seg.custom_audience.custom_audience = ca_rn

    # Три группы: по одной на тип сигнала (практика агентства: разные сигналы в разных группах, алгоритм сам делит расход)
    for idx, (gname, kind) in enumerate(GROUPS):
        ag_rn = f"customers/{cid}/assetGroups/-{3 + idx}"
        ag = new_op().asset_group_operation.create
        ag.resource_name = ag_rn
        ag.name = gname
        ag.campaign = campaign_rn
        ag.final_urls.append(FINAL_URL)
        ag.status = E.AssetGroupStatusEnum.ENABLED
        for asset_rn, field in shared:
            aga = new_op().asset_group_asset_operation.create
            aga.asset_group = ag_rn
            aga.asset = asset_rn
            aga.field_type = getattr(E.AssetFieldTypeEnum, field)
        if kind == "themes":
            for theme in src["themes"]:
                sig = new_op().asset_group_signal_operation.create
                sig.asset_group = ag_rn
                sig.search_theme.text = theme
        else:
            sig = new_op().asset_group_signal_operation.create
            sig.asset_group = ag_rn
            sig.audience.audience = aud_interests_rn if kind == "interests" else aud_comp_rn
    return ops, missing


def create_custom_audience(client, cid, execute):
    """Новая аудитория конкурентов (старую `Конкуренты` не трогаем). Отдельный вызов: в пакетный Mutate её включить нельзя.
    Без --execute только проверяется (validate_only), а в основной пакет подставляется существующая аудитория как заглушка."""
    E = client.enums
    op = client.get_type("CustomAudienceOperation")
    ca = op.create
    ca.name = f"Конкуренты ProfiMet {datetime.now():%Y%m%d}"
    ca.description = "Домены конкурентов из Auction insights 2026-10-08 (без собственного сайта)"
    ca.type_ = E.CustomAudienceTypeEnum.AUTO
    for domain in COMPETITOR_DOMAINS:
        m = ca.members.add()
        m.member_type = E.CustomAudienceMemberTypeEnum.URL
        m.url = domain
    req = client.get_type("MutateCustomAudiencesRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    resp = client.get_service("CustomAudienceService").mutate_custom_audiences(request=req)
    if execute:
        return resp.results[0].resource_name
    return f"customers/{cid}/customAudiences/910784616"  # заглушка для проверки основного пакета


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально создать. Без флага — validate_only")
    args = ap.parse_args()
    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    src = read_source(client, ga, cid)
    print(f"из `{SRC_ASSET_GROUP}`: текстовых ассетов {len(src['text'])}, картинок {len(src['images'])}, поисковых тем {len(src['themes'])}, гео {len(src['geo'])}, окон расписания {len(src['schedule'])}, ассетов кампании {len(src['campaign_assets'])}")
    try:
        ca_rn = create_custom_audience(client, cid, args.execute)
    except GoogleAdsException as ex:
        print("ОШИБКА при создании аудитории конкурентов:", [e.message for e in ex.failure.errors][:3])
        raise SystemExit(1)
    print("аудитория конкурентов:", "создана " + ca_rn if args.execute else "проверка пройдена (validate_only)")
    ops, missing = build_operations(client, cid, src, ca_rn)
    if missing:
        print("НЕ найдены существующие ассеты (будут созданы заново с тем же текстом):", missing)
    print(f"операций в запросе: {len(ops)}")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not args.execute
    try:
        resp = client.get_service("GoogleAdsService").mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:10]:
            print("  -", err.message, "|", [str(p.field_name) for p in err.location.field_path_elements][:4])
        raise SystemExit(1)
    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не создано (validate_only).")
        return
    for mr in resp.mutate_operation_responses:
        if mr.campaign_result.resource_name:
            print("создана кампания:", mr.campaign_result.resource_name)
        if mr.asset_group_result.resource_name:
            print("создана группа ассетов:", mr.asset_group_result.resource_name)


if __name__ == "__main__":
    main()
