#!/usr/bin/env python
# coding: utf-8
"""Создаёт Search-кампанию `search / szklarnia generic` (ProfiMet) через Google Ads API.

Назначение: общие запросы про теплицы, где материал не назван (szklarnia, szklarnia ogrodowa, cena, producent,
małe/mini, размеры без слова poliwęglan, tunel). Отсекающую роль играет текст объявления (поликарбонат в H1/D1
с закреплением). Слово «poliwęglan» в запросах оставлено в минус-словах (зона `Search | Poliweglan | Pl`).

Одной транзакцией (GoogleAdsService.mutate): бюджет, кампания (Search, Maximize clicks с потолком цены клика,
ПАУЗА, AI Max и автоассеты выключены, только поиск Google без партнёров), гео/язык/расписание как у старой
`search / szklarnia/tunel (excl. poliweglan)`, исключение CRM-покупателей, минус-слова, 6 групп с ключами
(фраза/точное, без широкого) и по одному RSA в группе.

БЕЗОПАСНОСТЬ: по умолчанию validate_only — Google проверяет запрос, ничего не создаёт. Запись только с --execute.
Кампания всегда на паузе. После записи читает объекты обратно из аккаунта.

Использование:
    python gads_search_generic_builder.py --customer-id 7552781705            # проверка
    python gads_search_generic_builder.py --customer-id 7552781705 --execute  # запись (на паузе)
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "search / szklarnia generic"
BUDGET_EUR = 25
CPC_CEILING_EUR = 0.50  # без AI Max старая кампания платила 0.42-0.62 за клик (01.08-14.09 и 07-09.10), выборка мала
POLAND_GEO = "geoTargetConstants/2616"
LANGUAGES = ["languageConstants/1030", "languageConstants/1000"]  # pl, en — как у старой
SCHEDULE = [("MONDAY", 7, 17), ("TUESDAY", 7, 17), ("WEDNESDAY", 7, 17), ("THURSDAY", 7, 17),
            ("FRIDAY", 7, 17), ("SATURDAY", 9, 16)]  # как у старой
FINAL_URL = "https://mocnaszklarnia.pl/"
CRM_EXCLUDE_LIST = 9441800617  # Profimet — уже купившие клиенты (единственное исключение аудиторий, правило 2026-10-07)
# Шаблон такой же, как у старой кампании: utm_campaign=s_{campaignid}_search подхватывает динамический пул Ringostat
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=s_{campaignid}_{ifsearch:search}{ifcontent:context}"
    "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}|gid_{adgroupid}|aid_{creative}|pos_{adposition}"
    "|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}"
)

# Минус-слова: (текст, тип). Старые 12 копируются как были (широкие).
NEG_OLD = ["2x3", "poliwęglanu", "poliwęglan", "poliweglan", "poliwęglanowe", "poliweglanu", "poliweglanowe",
           "poliweglanowa", "poliwęglanowa", "poliwęglanowy", "poliweglanowy", "poliweglowa"]
NEG_NEW = [
    # плёнка и палатки — клиент продаёт только поликарбонат (решение пользователя 2026-10-09)
    "folia", "foliowy", "foliowe", "foliowa", "foliówka", "namiot", "namioty",
    # бренд — ведёт кампания Brand
    "profimet", "mocna szklarnia", "mocnaszklarnia", "mocne szklarnie",
    # конкуренты (решение 2026-10-09: тестировать отдельно позже)
    "poligreen", "bartex", "etl group",
    # мусорные намерения
    "jak zrobić", "diy", "olx", "allegro", "używana", "używane",
]

# Группы: имя -> (фразовые, точные). Без широкого соответствия.
GROUPS = {
    "szklarnia ogrodowa": (
        ["szklarnia ogrodowa", "szklarnie ogrodowe", "szklarnia przydomowa", "szklarnia na działkę",
         "szklarnie na działkę", "szklarnia na pomidory", "szklarnie na pomidory"],
        ["szklarnia", "szklarnie"]),
    "cena kupić": (
        ["szklarnia cena", "szklarnie cena", "szklarnie ogrodowe ceny", "szklarnia ogrodowa cena",
         "ile kosztuje szklarnia", "ile kosztuje szklarnia ogrodowa", "kupić szklarnię", "gdzie kupić szklarnię",
         "szklarnia ogrodowa kupić"], []),
    "producent": (
        ["producent szklarni", "producent szklarni ogrodowych", "szklarnie od producenta", "polskie szklarnie",
         "szklarnie polskiej produkcji", "polski producent szklarni"], []),
    "małe mini": (
        ["mała szklarnia ogrodowa", "mini szklarnia ogrodowa", "małe szklarnie", "mała szklarnia", "mini szklarnia",
         "szklarnia ogrodowa mała"], []),
    "rozmiary": (
        ["szklarnia 3x6", "szklarnia 3x4", "szklarnia ogrodowa 3x6", "szklarnia ogrodowa 3x4", "szklarnie 3x6",
         "szklarnie 3x4"], []),
    "tunel": (["tunel ogrodowy", "tunele ogrodowe"], ["tunele ogrodowe"]),
}

# Тексты — только из Клиенты/ProfiMet/Креативы/Факты_сайта_2026-10-08.md и решения пользователя 2026-10-09 (акция ежемесячная).
H1 = "Szklarnie z Poliwęglanu"                 # закреплён на позиции 1 — отсекающий
H_TUNEL = "Tunel Ogrodowy z Poliwęglanu"       # для группы tunel, закреплён на позиции 1 (формулировку подтвердить)
HEADLINES = [
    "Szklarnia Poliwęglanowa MOCNA", "Producent Szklarni od 16 Lat", "Poliwęglan 4 mm i 6 mm UV",
    "Płatność przy Odbiorze", "Darmowa Dostawa", "Gwarancja 5 Lat na Poliwęglan", "3 Prezenty Gratis",
    "Konsultant Dobierze Rozmiar", "Stal Ocynkowana, Profil 40x20", "Montaż bez Spawania", "Dostawa w 3-7 Dni",
]
D1 = "Szklarnie z poliwęglanu 4 lub 6 mm z filtrem UV prosto od producenta. Zapytaj o wymiary."  # закреплено на позиции 1
DESCRIPTIONS = [
    "Płatność przy odbiorze, bez zaliczki. Darmowa dostawa w 3-7 dni.",
    "Gwarancja: 2 lata na ramę i 5 lat na poliwęglan. Doradca pomoże dobrać rozmiar.",
    "Własna produkcja od 16 lat. Stal ocynkowana, montaż bez spawania. 3 prezenty gratis.",
]

# --- Ассеты кампании (единый стандарт 2026-10-09, см. Клиенты/ProfiMet/Креативы/Ассеты_аудит_и_стандарт_2026-10-09.md).
# Без служебных параметров Roistat (не используется, решение пользователя 2026-10-09). Якоря — для анализа, на блоки не обязаны вести.
BASE = "https://mocnaszklarnia.pl/"
SITELINKS = [  # (заголовок <=25, описание1 <=35, описание2 <=35, якорь)
    ("Zobacz modele i ceny", "MOCNA od 1299 zł, 2-12 m długości", "Wybierz swoją szklarnię", "#bs9"),
    ("Szklarnia MOCNA 3 m", "Poliwęglan 4 lub 6 mm z filtrem UV", "Profil 40x20 mm, stal ocynkowana", "#profimet-mocna"),
    ("Nowość: MOCNA Went Plus", "Model z wentylacją", "Poliwęglan UV, profil 40x20 mm", "#mocna-went-plus"),
    ("Płać przy odbiorze", "Bez przedpłaty", "Zamówienie potwierdzamy telefonem", "#main"),
    ("Darmowa dostawa", "Po całej Polsce, własny transport", "Dostawa w 3-7 dni", "#dostawa"),
    ("Gwarancja do 5 lat", "2 lata na ramę", "5 lat na poliwęglan", "#gwarancja"),
    ("3 prezenty gratis", "Promocja w tym miesiącu", "Zapytaj doradcę o szczegóły", "#prezent"),
    ("Akcesoria do szklarni", "Fundamenty, otwieracze okien", "Zestawy do podwiązywania roślin", "#akcesoria"),
]
# Уточнения: уже существующие в аккаунте ассеты переиспользуем (тот же текст), остальные создаём.
CALLOUTS_EXISTING = {"Gwarancja fabryczna": 323463164380, "Płatność przy odbiorze": 323619279420,
                     "3 prezenty gratis": 323619279423, "Darmowa dostawa 3-7 dni": 323619279417}
CALLOUTS_NEW = ["Poliwęglan 4-6 mm UV", "Montaż bez spawania", "Stal ocynkowana", "Własna produkcja",
                "Doradca dobierze rozmiar", "16 lat doświadczenia", "Dostawa w 3-7 dni"]
SNIPPET = ("Modele", ["MOCNA", "MOCNA MAXI", "MOCNA SZEROKA", "MOCNA KOMPAKT", "MOCNA Went Plus", "NORDSTAR",
                      "Domek HOBBY", "STANDARD PLUS", "MINI"])
# Существующие ассеты аккаунта: реальные фото без значка ИИ (те же, что в Demand Gen), лого и название компании
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
    c.target_spend.cpc_bid_ceiling_micros = int(CPC_CEILING_EUR * 1_000_000)  # Maximize clicks с потолком
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False  # партнёры выключены (у старой 0.78 € без конверсий)
    c.network_settings.target_content_network = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = TRACKING_TEMPLATE
    c.ai_max_setting.enable_ai_max = False
    for t in (E.AssetAutomationTypeEnum.TEXT_ASSET_AUTOMATION,
              E.AssetAutomationTypeEnum.FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = t
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
    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.negative = True
    cc.user_list.user_list = f"customers/{cid}/userLists/{CRM_EXCLUDE_LIST}"

    for text in NEG_OLD + NEG_NEW:
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
        first = H_TUNEL if gname == "tunel" else H1
        pinned = [(first, True)] + [(h, False) for h in ([H1] if gname == "tunel" else [])] + \
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
        a.final_urls.append(BASE + anchor)
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
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
            "campaign.target_spend.cpc_bid_ceiling_micros, campaign.ai_max_setting.enable_ai_max, "
            "campaign.network_settings.target_search_network, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {camp_id}")):
        k = r.campaign
        print(f"{k.id} | {k.name} | {E.CampaignStatusEnum.CampaignStatus.Name(k.status)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type)} | потолок "
              f"{k.target_spend.cpc_bid_ceiling_micros / 1e6} | AI Max {k.ai_max_setting.enable_ai_max} | "
              f"партнёры {k.network_settings.target_search_network} | бюджет {r.campaign_budget.amount_micros / 1e6}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group.status FROM ad_group "
            f"WHERE campaign.id = {camp_id}")):
        print("группа:", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status))
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
    ap.add_argument("--customer-id", required=True)
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
