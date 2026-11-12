#!/usr/bin/env python
# coding: utf-8
"""Создаёт Search-кампанию `search / montaz` (ProfiMet) — тест семантики «szklarnia z montażem» на странице /montaz-szklarni.

Одной транзакцией (GoogleAdsService.mutate): бюджет, кампания (Search, Maximize clicks с потолком цены клика, ПАУЗА, AI Max и автоассеты
выключены, только поиск Google без партнёров), гео 4 воеводства (только присутствие), язык pl, расписание, исключение
CRM-покупателей, 5 общих списков минусов, кампанийные минуса, 4 группы с ключами (фраза/точное, без широкого), RSA
с закреплением H1/D1, ассеты.

ПОРЯДОК: сначала `gads_montaz_block_list.py --execute` (выносит широкие `montaż`/`montaz`/`z montażem` из списков
«Общий» и «Из запросов»), потом этот скрипт. С --execute проверяет, что этих терминов в списках уже нет, иначе стоп.
Список `montaz` (16 точных минусов) к кампании НЕ подключается, `montaz-block` — тоже.

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись только с --execute. Кампания всегда на паузе. После записи — чтение обратно.
Тексты и факты — Клиенты/ProfiMet/Работы/2026-11-12_монтаж_тест/25_тексты.md (источник — страница /montaz-szklarni 12.11.2026).

    python gads_search_montaz_builder.py                # проверка
    python gads_search_montaz_builder.py --execute      # запись, на паузе
    python gads_search_montaz_builder.py --read-back-only
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_quota_ledger import record_mutate
from gads_stats import GOOGLE_ADS_YAML

CID_DEFAULT = "7552781705"
CAMPAIGN_NAME = "search / montaz"   # новый стиль имён: маленькие буквы, через « / », без «pl» (гео — 4 воеводства, не вся страна)
BUDGET_EUR = 30           # решение пользователя 12.11; спрос по Planner мал — потолок, скорее всего, не будет достигнут
CPC_CEILING_EUR = 1.00    # Maximize clicks с потолком: верх страницы по Planner 0.55-1.10 €, Poliweglan при ставках 0.4-0.5 теряет 57% по рейтингу
GEO_IDS = [20853, 20852, 20859, 20847]   # mazowieckie, małopolskie, śląskie, dolnośląskie — зона монтажа по FAQ страницы
LANGUAGES = ["languageConstants/1030"]    # pl
SCHEDULE = [("MONDAY", 7, 21), ("TUESDAY", 7, 21), ("WEDNESDAY", 7, 21), ("THURSDAY", 7, 21),
            ("FRIDAY", 7, 21), ("SATURDAY", 9, 16)]   # как у Poliweglan (07:45-21:00, сб 09-16), округлено до часа
FINAL_URL = "https://mocnaszklarnia.pl/montaz-szklarni"
CRM_EXCLUDE_LIST = 9441800617  # Profimet — уже купившие клиенты
# Тот же шаблон, что у остальных Search: utm_campaign=s_{campaignid}_search подхватывает динамический пул Ringostat Google CPC_dyn
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=s_{campaignid}_{ifsearch:search}{ifcontent:context}"
    "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}|gid_{adgroupid}|aid_{creative}|pos_{adposition}"
    "|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}"
)
# Общие списки минусов (id из чтения 12.11): без montaz и montaz-block. «Общий» и «Из запросов» — только после gads_montaz_block_list.py
SHARED_LISTS = {"Инфо": 8156157822, "Общий": 8159975327, "Конкуренты": 8159977358,
                "Из запросов": 10192906393, "Не релев размеры": 11767304962}
BLOCKED_TERMS = {"montaż", "montaz", "z montażem"}   # не должно остаться в «Общий»/«Из запросов» к моменту --execute

# Кампанийные минуса: бренд (ведёт Brand), «сделай сам»/инструкции, мусор. Широкий для одного слова, фразовый для нескольких.
NEG = [
    "profimet", "mocna szklarnia", "mocnaszklarnia", "mocne szklarnie",
    "instrukcja", "instrukcją", "pdf", "film", "youtube", "krok po kroku", "diy", "samodzielnie",
    "olx", "allegro", "używana", "używane",
]

# Группы: имя -> (фразовые, точные); ставок нет — Maximize clicks. Без широкого. 2x3 не берём: блокирует список «Не релев размеры».
GROUPS = {
    "szklarnia z montażem": ([
        "szklarnia z montażem", "szklarnie z montażem", "szklarnia ogrodowa z montażem", "szklarnie ogrodowe z montażem",
        "szklarnia z montazem", "szklarnie ogrodowe z montazem"],
        ["szklarnia z montażem", "szklarnie z montażem", "szklarnia z montazem"]),
    "poliwęglan z montażem": ([
        "szklarnia z poliwęglanu z montażem", "szklarnie z poliwęglanu z montażem", "szklarnia poliwęglan z montażem",
        "szklarnia poliwęglanowa z montażem", "szklarnie poliwęglanowe z montażem"],
        ["szklarnia z poliwęglanu z montażem", "szklarnie z poliwęglanu z montażem"]),
    "wymiary z montażem": ([
        "szklarnia z poliwęglanu 3x6 z montażem", "szklarnia z poliwęglanu 3x4 z montażem",
        "szklarnia z poliwęglanu 3x6m z montażem"],
        ["szklarnia z poliwęglanu 3x6 z montażem", "szklarnia z poliwęglanu 3x4 z montażem"]),
    "tunel z montażem": (["tunel z poliwęglanu z montażem"], ["tunel z poliwęglanu z montażem"]),
}

# Тексты — только со страницы /montaz-szklarni (12.11.2026) и фактов сайта 13.10 (гарантия, оплата, срок доставки).
H1 = "Szklarnie z Montażem"                  # закреплён на позиции 1
H_TUNEL = "Tunel z Poliwęglanu z Montażem"   # для группы tunel, закреплён на позиции 1
HEADLINES = [
    "Montaż Szklarni pod Klucz", "Montaż Przez Naszych Monterów", "Omówimy Montaż i Termin", "Producent Szklarni od 16 Lat",
    "Poliwęglan 4 mm i 6 mm UV", "Zamów Montaż Szklarni", "Montujemy w 4 Województwach", "Płatność przy Odbiorze",
    "Gwarancja 5 Lat na Poliwęglan", "Dostawa w 3-7 Dni", "Szklarnie Ocynkowane",
]
D1 = "Szklarnia od producenta z montażem pod klucz. Zostaw numer, omówimy termin i szczegóły."  # закреплено на позиции 1
DESCRIPTIONS = [
    "Złożymy konstrukcję, zakotwimy w gruncie, zamontujemy poliwęglan i wyregulujemy okna.",
    "Montaż w woj. mazowieckim, małopolskim, śląskim i dolnośląskim. Termin ustalamy z Tobą.",
    "Płatność przy odbiorze, bez zaliczki. Gwarancja: 2 lata na ramę i 5 lat na poliwęglan.",
]

# --- Ассеты кампании
BASE = "https://mocnaszklarnia.pl/"
MZ = BASE + "montaz-szklarni"
SITELINKS = [  # (заголовок <=25, описание1 <=35, описание2 <=35, URL). Цен нет (решение 12.11): монтаж считается индивидуально
    ("Montaż szklarni", "Złożymy i zamontujemy", "Szklarnia od producenta", MZ),
    ("Zamów montaż", "Zostaw numer, oddzwonimy", "Omówimy montaż Twojej szklarni", MZ + "#pm-kalkulator"),
    ("Szklarnie w sklepie", "Modele od producenta", "Poliwęglan 4 lub 6 mm z UV", BASE + "produkty"),
    ("O firmie PROFIMET", "Produkcja szklarni od 16 lat", "Własne warsztaty i magazyny", BASE + "ofirmie"),
]
CALLOUTS_EXISTING = {"Płatność przy odbiorze": 323619279420, "Gwarancja fabryczna": 323463164380}
CALLOUTS_NEW = ["Montaż pod klucz", "Montaż przez producenta", "Montaż w 4 województwach", "Poliwęglan 4-6 mm UV",
                "Własna produkcja", "16 lat doświadczenia"]
SNIPPET = ("Modele", ["MOCNA", "MOCNA Went Plus", "MOCNA SZEROKA", "MOCNA MAXI", "MOCNA KOMPAKT", "STANDARD PLUS",
                      "MINI", "NORDSTAR", "Domek HOBBY"])
IMAGE_ASSETS = [297786040282, 322937504523, 322886122180, 322937504517, 322937874606, 322937937225]
BUSINESS_NAME_ASSET = 323482647671
BUSINESS_LOGO_ASSET = 286986548910


def check_limits():
    assert all(len(h) <= 30 for h in HEADLINES + [H1, H_TUNEL]), "заголовок > 30"
    assert all(len(d) <= 90 for d in DESCRIPTIONS + [D1]), "описание > 90"
    assert len(HEADLINES) + 2 <= 15
    for a, b, c_, _ in SITELINKS:
        assert len(a) <= 25 and len(b) <= 35 and len(c_) <= 35, (a, b, c_)
    assert all(len(x) <= 25 for x in list(CALLOUTS_EXISTING) + CALLOUTS_NEW)
    assert all(len(v) <= 25 for v in SNIPPET[1])
    for g, (ph, ex) in GROUPS.items():
        for k in ph + ex:
            assert len(k) <= 80, k


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
    b.amount_micros = int(BUDGET_EUR * 1_000_000)
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.SEARCH
    c.campaign_budget = budget_rn
    c.target_spend.cpc_bid_ceiling_micros = int(CPC_CEILING_EUR * 1_000_000)  # Maximize clicks с потолком цены клика
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False  # партнёры выключены
    c.network_settings.target_content_network = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE   # монтаж только для тех, кто в зоне
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = TRACKING_TEMPLATE
    c.ai_max_setting.enable_ai_max = False
    for t in (E.AssetAutomationTypeEnum.TEXT_ASSET_AUTOMATION,
              E.AssetAutomationTypeEnum.FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = t
        s.asset_automation_status = E.AssetAutomationStatusEnum.OPTED_OUT

    for gid in GEO_IDS:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = f"geoTargetConstants/{gid}"
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
    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.negative = True
    cc.user_list.user_list = f"customers/{cid}/userLists/{CRM_EXCLUDE_LIST}"

    for list_name, set_id in SHARED_LISTS.items():
        css = new_op().campaign_shared_set_operation.create
        css.campaign = campaign_rn
        css.shared_set = f"customers/{cid}/sharedSets/{set_id}"
    for text in NEG:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = E.KeywordMatchTypeEnum.PHRASE if " " in text else E.KeywordMatchTypeEnum.BROAD

    for i, (gname, (phrase, exact)) in enumerate(GROUPS.items(), start=1):
        ag_rn = f"customers/{cid}/adGroups/-{10 + i}"
        ag = new_op().ad_group_operation.create
        ag.resource_name = ag_rn
        ag.name = gname
        ag.campaign = campaign_rn
        ag.status = E.AdGroupStatusEnum.ENABLED
        ag.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
        for kw, mt in [(k, E.KeywordMatchTypeEnum.PHRASE) for k in phrase] + \
                      [(k, E.KeywordMatchTypeEnum.EXACT) for k in exact]:
            agc = new_op().ad_group_criterion_operation.create
            agc.ad_group = ag_rn
            agc.status = E.AdGroupCriterionStatusEnum.ENABLED
            agc.keyword.text = kw
            agc.keyword.match_type = mt

        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.final_urls.append(FINAL_URL)
        rsa = aga.ad.responsive_search_ad
        first = H_TUNEL if gname == "tunel z montażem" else H1
        pinned = [(first, True)] + [(h, False) for h in ([H1] if gname == "tunel z montażem" else [])] + \
                 [(h, False) for h in HEADLINES]
        for text, pin in pinned:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin:
                a.pinned_field = E.ServedAssetFieldTypeEnum.HEADLINE_1
            rsa.headlines.append(a)
        for text, pin in [(D1, True)] + [(d, False) for d in DESCRIPTIONS]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin:
                a.pinned_field = E.ServedAssetFieldTypeEnum.DESCRIPTION_1
            rsa.descriptions.append(a)
    # --- ассеты кампании
    E_ = E.AssetFieldTypeEnum
    counter = [100]

    def new_asset_rn():
        counter[0] += 1
        return f"customers/{cid}/assets/-{counter[0]}"

    def link(asset_rn, field_type):
        ca = new_op().campaign_asset_operation.create
        ca.campaign = campaign_rn
        ca.asset = asset_rn
        ca.field_type = field_type

    for link_text, d1, d2, anchor in SITELINKS:
        rn = new_asset_rn()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.final_urls.append(anchor)   # в SITELINKS уже полные URL
        a.sitelink_asset.link_text = link_text
        a.sitelink_asset.description1 = d1
        a.sitelink_asset.description2 = d2
        link(rn, E_.SITELINK)
    for text in CALLOUTS_NEW:
        rn = new_asset_rn()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.callout_asset.callout_text = text
        link(rn, E_.CALLOUT)
    for text, aid in CALLOUTS_EXISTING.items():
        link(f"customers/{cid}/assets/{aid}", E_.CALLOUT)
    rn = new_asset_rn()
    a = new_op().asset_operation.create
    a.resource_name = rn
    a.structured_snippet_asset.header = SNIPPET[0]
    a.structured_snippet_asset.values.extend(SNIPPET[1])
    link(rn, E_.STRUCTURED_SNIPPET)
    for aid in IMAGE_ASSETS:
        link(f"customers/{cid}/assets/{aid}", E_.AD_IMAGE)
    link(f"customers/{cid}/assets/{BUSINESS_NAME_ASSET}", E_.BUSINESS_NAME)
    link(f"customers/{cid}/assets/{BUSINESS_LOGO_ASSET}", E_.BUSINESS_LOGO)
    return ops


def read_back(client, cid, campaign_rn):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    camp_id = campaign_rn.split("/")[-1]
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, campaign.target_spend.cpc_bid_ceiling_micros, "
            "campaign.ai_max_setting.enable_ai_max, campaign.geo_target_type_setting.positive_geo_target_type, "
            "campaign.network_settings.target_search_network, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {camp_id}")):
        k = r.campaign
        print(f"{k.id} | {k.name} | {E.CampaignStatusEnum.CampaignStatus.Name(k.status)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type)} потолок {k.target_spend.cpc_bid_ceiling_micros / 1e6} | гео "
              f"{E.PositiveGeoTargetTypeEnum.PositiveGeoTargetType.Name(k.geo_target_type_setting.positive_geo_target_type)} | AI Max {k.ai_max_setting.enable_ai_max} | "
              f"партнёры {k.network_settings.target_search_network} | бюджет {r.campaign_budget.amount_micros / 1e6}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group.status FROM ad_group "
            f"WHERE campaign.id = {camp_id}")):
        print("группа:", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status))
    print("общие списки минусов:", sorted(r.shared_set.name for r in ga.search(customer_id=cid, query=(
        "SELECT shared_set.name FROM campaign_shared_set "
        f"WHERE campaign.id = {camp_id} AND shared_set.type = 'NEGATIVE_KEYWORDS'"))))
    print("гео:", sorted(r.campaign_criterion.location.geo_target_constant for r in ga.search(customer_id=cid, query=(
        "SELECT campaign_criterion.location.geo_target_constant FROM campaign_criterion "
        f"WHERE campaign.id = {camp_id} AND campaign_criterion.type = LOCATION"))))
    counts = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group_criterion.keyword.match_type FROM ad_group_criterion "
            f"WHERE campaign.id = {camp_id} AND ad_group_criterion.type = KEYWORD")):
        key = (r.ad_group.name, E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.ad_group_criterion.keyword.match_type))
        counts[key] = counts.get(key, 0) + 1
    print("ключей:", counts)
    n_ads = sum(1 for _ in ga.search(customer_id=cid, query=f"SELECT ad_group_ad.ad.id FROM ad_group_ad WHERE campaign.id = {camp_id}"))
    print("объявлений:", n_ads)
    crit = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign_criterion.type, campaign_criterion.negative FROM campaign_criterion "
            f"WHERE campaign.id = {camp_id}")):
        key = (E.CriterionTypeEnum.CriterionType.Name(r.campaign_criterion.type_), r.campaign_criterion.negative)
        crit[key] = crit.get(key, 0) + 1
    print("критерии кампании (тип, минус?):", crit)
    assets = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_asset.field_type, campaign_asset.status FROM campaign_asset "
            f"WHERE campaign.id = {camp_id}")):
        key = (E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type),
               E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status))
        assets[key] = assets.get(key, 0) + 1
    print("ассеты кампании (тип, статус):", assets)
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, asset.sitelink_asset.link_text, asset.final_urls FROM campaign_asset "
            f"WHERE campaign.id = {camp_id} AND campaign_asset.field_type = SITELINK")):
        print("  сайтлинк:", r.asset.sitelink_asset.link_text, list(r.asset.final_urls))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", default=CID_DEFAULT)
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага — только validate_only")
    ap.add_argument("--read-back-only", action="store_true", help="Ничего не создавать, только прочитать кампанию по имени")
    args = ap.parse_args()
    if args.read_back_only:
        cid_ = args.customer_id.replace("-", "").strip()
        cl = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
        for r in cl.get_service("GoogleAdsService").search(customer_id=cid_, query=(
                f"SELECT campaign.id FROM campaign WHERE campaign.name = '{CAMPAIGN_NAME}'")):
            read_back(cl, cid_, f"customers/{cid_}/campaigns/{r.campaign.id}")
        return

    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    if args.execute:
        ga_ = client.get_service("GoogleAdsService")
        if any(True for _ in ga_.search(customer_id=cid, query=(
                f"SELECT campaign.id FROM campaign WHERE campaign.name = '{CAMPAIGN_NAME}' AND campaign.status != 'REMOVED'"))):
            raise SystemExit(f"Кампания «{CAMPAIGN_NAME}» уже есть — повторно не создаю. Проверка: --read-back-only")
        left = [(r.shared_set.name, r.shared_criterion.keyword.text) for r in ga_.search(customer_id=cid, query=(
            "SELECT shared_set.name, shared_criterion.keyword.text FROM shared_criterion "
            "WHERE shared_set.name IN ('Общий', 'Из запросов') AND shared_criterion.keyword.text LIKE '%mont%'"))
            if r.shared_criterion.keyword.text in BLOCKED_TERMS]
        if left:
            raise SystemExit(f"СТОП: в больших списках ещё стоят {left}. Сначала gads_montaz_block_list.py --execute")
    try:
        service = client.get_service("GoogleAdsService")
        ops = build_operations(client, cid)
        request = client.get_type("MutateGoogleAdsRequest")
        request.customer_id = cid
        request.mutate_operations.extend(ops)
        request.validate_only = not args.execute
        record_mutate("gads_search_montaz_builder", len(ops), validate_only=not args.execute)
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
    print("Создано (кампания на паузе):")
    for r in response.mutate_operation_responses:
        kind = r.WhichOneof("response")
        rn = getattr(r, kind).resource_name
        if kind == "campaign_result":
            campaign_rn = rn
        print(" ", kind, rn)
    if campaign_rn:
        read_back(client, cid, campaign_rn)


if __name__ == "__main__":
    main()
