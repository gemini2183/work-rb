#!/usr/bin/env python
# coding: utf-8
"""Создаёт Search-кампанию `search / szklarnia 3x4-3x6` (ExpertAgro, Теплицы Польша) через Google Ads API.

План и основание — Клиенты/EkspertAgro/Кампании/Search/search_szklarnia_3x4_3x6.md (согласовано пользователем 2026-10-14).
Две группы по размеру (3x6, 3x4), посадка — каталог Tilda с фильтром ширина+длина, фразовое/точное соответствие.

Одной транзакцией (GoogleAdsService.mutate): бюджет, кампания (Search, Maximize clicks с потолком цены клика, ПАУЗА,
AI Max и автотексты выключены, только поиск Google), гео/язык/расписание, исключение списка покупателей, минус-слова,
2 группы с ключами и по одному RSA, сайтлинки и уточнения.

UTM — через `final_url_suffix`, а не `tracking_url_template`: финальные URL каталога уже содержат `?`, а у сайтлинков на
страницы без параметров его нет; суффикс Google дописывает сам с нужным `?` или `&` (шаблон `{lpurl}?…` склеил бы UTM со
значением фильтра).

БЕЗОПАСНОСТЬ: по умолчанию validate_only — Google проверяет запрос, ничего не создаёт. Запись только с --execute.
Кампания всегда на паузе. Перед записью проверяется, что кампании с таким именем ещё нет (защита от дубля).
После записи читает объекты обратно из аккаунта.

Использование:
    python gads_search_ekspertagro_size_builder.py --customer-id 8826134558            # проверка
    python gads_search_ekspertagro_size_builder.py --customer-id 8826134558 --execute  # запись (на паузе)
    python gads_search_ekspertagro_size_builder.py --customer-id 8826134558 --read-back-only
"""
import argparse
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "search / szklarnia 3x4-3x6"
BUDGET_PLN = 150          # потолок, не прогноз расхода (ожидаемо 17-45 zł/день), ≈ 1.4 × цель заявки 110 zł
CPC_CEILING_PLN = 2.50    # верх страницы по Keyword Planner 2.15-2.43 zł
POLAND_GEO = "geoTargetConstants/2616"
LANGUAGES = ["languageConstants/1030", "languageConstants/1000"]  # pl, en — как у старых кампаний
SCHEDULE = [("MONDAY", 7, 17), ("TUESDAY", 7, 17), ("WEDNESDAY", 7, 17), ("THURSDAY", 7, 17),
            ("FRIDAY", 7, 17), ("SATURDAY", 9, 18)]  # как у старых; допущение, подтверждено пользователем с планом
BUYERS_EXCLUDE_LIST = 9475706784  # «Profimet ekspertagro.pl — уже купившие клиенты» (12 000)
FINAL_URL_SUFFIX = (
    "utm_source=google&utm_medium=cpc&utm_campaign=s_{campaignid}_{ifsearch:search}{ifcontent:context}"
    "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}|gid_{adgroupid}|aid_{creative}|pos_{adposition}"
    "|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}"
)

SITE = "https://ekspertagro.pl/"
W = "tfc_charact:9246142%5B1500649011%5D"   # фильтр «Szerokość» каталога Tilda
L = "tfc_charact:9246152%5B1500649011%5D"   # фильтр «Długość»


def catalog_url(length_m):
    return f"{SITE}szklarni?{W}=3m&{L}={length_m}m&tfc_div=:::"


NEGATIVES = [
    "folia", "foliowa", "foliowy", "foliowe", "namiot", "namioty",
    "olx", "allegro", "castorama", "leroy", "obi", "używana", "używane", "diy", "jak zrobić",
    "profimet", "mocna szklarnia", "mocnaszklarnia",
    "2x3", "3x5", "4x6", "3x8",
]


def group_spec(length, other_price, width=3, profile="40x20"):
    s = f"{width}x{length}"
    phrase = [f"szklarnia z poliwęglanu {s}", f"szklarnie z poliwęglanu {s}", f"szklarnia {s}",
              f"szklarnia poliwęglan {s}", f"szklarnia ogrodowa {s}", f"tunel ogrodowy {s}",
              f"tunel z poliwęglanu {s}", f"tunel poliwęglan {s}"]
    exact = [f"szklarnia z poliwęglanu {s}", f"szklarnia {s}", f"tunel ogrodowy {s}",
             f"tunel z poliwęglanu {s}", f"szklarnie z poliwęglanu {s}"]
    h1 = f"Szklarnia {s} z Poliwęglanu"
    headlines = [
        f"Szklarnie {s} od Producenta", f"Szklarnia {s} od {other_price} zł", f"Tunel {s} z Poliwęglanu",
        "Płatność przy Odbiorze", "Darmowa Dostawa po Polsce", "Producent Szklarni od 2008 r.",
        "Poliwęglan 4 lub 6 mm", f"Profil Ocynkowany {profile} mm", "Żywotność ponad 15 lat",
        "Wybierz Model i Cenę", "Faktura VAT", "Rabat od 100 zł przy 2 szt.",
    ]
    d1 = f"Szklarnie {s} m z poliwęglanu 4 i 6 mm od producenta. Zobacz modele i ceny w katalogu."
    d3 = f"Własna produkcja od 2008 roku. Stal ocynkowana {profile} mm, żywotność ponad 15 lat."
    url = f"{SITE}szklarni?{W}={width}m&{L}={length}m&tfc_div=:::"
    return {"name": s, "url": url, "phrase": phrase, "exact": exact, "h1": h1,
            "headlines": headlines, "d1": d1, "d3": d3, "path2": s}


# Цена «от» — минимальная в каталоге 14.10 для размера (3x6: 1 949 zł; 3x4: 1 599 zł; 2x4: 1 499 zł; 4x6: 2 799 zł).
GROUPS = [group_spec(6, 1949), group_spec(4, 1599)]
EXTRA = {  # добавляются отдельным вызовом --add-sizes (согласовано пользователем 2026-10-14)
    "2x4": group_spec(4, 1499, width=2, profile="20x20"),   # Mini Ekspert Tunel 20×20
    "4x6": group_spec(6, 2799, width=4, profile="40x20"),   # Tytan Ekspert Tunel 40x20
}
D2 = "Płatność przy odbiorze i darmowa dostawa po Polsce. Montaż według instrukcji w zestawie."
DESCRIPTIONS = [
    "Własna produkcja od 2008 roku. Stal ocynkowana 40x20 mm, żywotność ponad 15 lat.",
    "Rabat od 100 zł przy zamówieniu dwóch szklarni na jeden adres. Wystawiamy fakturę VAT.",
]
SITELINKS = [  # (заголовок <=25, описание1 <=35, описание2 <=35, URL)
    ("Szklarnie 3x4 – katalog", "Poliwęglan 4 i 6 mm, profil 40x20", "Zobacz modele i ceny", catalog_url(4)),
    ("Szklarnie 3x6 – katalog", "Poliwęglan 4 i 6 mm, profil 40x20", "Zobacz modele i ceny", catalog_url(6)),
    ("Wysyłka i płatność", "Darmowa wysyłka po Polsce", "Płatność przy odbiorze", SITE + "wysylka-i-platnosc"),
    ("Wszystkie szklarnie", "12 modeli od producenta", "Wybierz rozmiar i poliwęglan", SITE + "szklarni"),
    ("Fundament do szklarni", "Dopasowany do wymiarów", "Zobacz ofertę", SITE + "fundament-do-szklarni"),
    ("Akcesoria do szklarni", "Dodatki do szklarni", "Zobacz ofertę", SITE + "akcesoria-do-szklarni"),
]
CALLOUTS = ["Płatność przy odbiorze", "Darmowa dostawa", "Producent od 2008 roku", "Faktura VAT",
            "Poliwęglan 4 i 6 mm", "12 modeli szklarni"]


def check_limits():
    for g in GROUPS + list(EXTRA.values()):
        assert len(g["h1"]) <= 30, g["h1"]
        assert all(len(h) <= 30 for h in g["headlines"]), g["headlines"]
        assert len(g["headlines"]) + 1 <= 15
        assert len(g["d1"]) <= 90 and len(g.get("d3", "")) <= 90
        assert all(len(k) <= 80 for k in g["phrase"] + g["exact"])
    assert all(len(d) <= 90 for d in [D2] + DESCRIPTIONS)
    for a, b, c_, _ in SITELINKS:
        assert len(a) <= 25 and len(b) <= 35 and len(c_) <= 35, (a, b, c_)
    assert all(len(x) <= 25 for x in CALLOUTS)


def campaign_exists(client, cid):
    ga = client.get_service("GoogleAdsService")
    q = f"SELECT campaign.id FROM campaign WHERE campaign.name = '{CAMPAIGN_NAME}' AND campaign.status != 'REMOVED'"
    return [r.campaign.id for r in ga.search(customer_id=cid, query=q)]


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
    b.amount_micros = int(BUDGET_PLN * 1_000_000)
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.SEARCH
    c.campaign_budget = budget_rn
    c.target_spend.cpc_bid_ceiling_micros = int(CPC_CEILING_PLN * 1_000_000)  # Maximize clicks с потолком
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False
    c.network_settings.target_content_network = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.final_url_suffix = FINAL_URL_SUFFIX
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
    cc.user_list.user_list = f"customers/{cid}/userLists/{BUYERS_EXCLUDE_LIST}"

    for text in NEGATIVES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = E.KeywordMatchTypeEnum.PHRASE if " " in text else E.KeywordMatchTypeEnum.BROAD

    for i, g in enumerate(GROUPS, start=1):
        ag_rn = f"customers/{cid}/adGroups/-{10 + i}"
        ag = new_op().ad_group_operation.create
        ag.resource_name = ag_rn
        ag.name = g["name"]
        ag.campaign = campaign_rn
        ag.status = E.AdGroupStatusEnum.ENABLED
        ag.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
        for kw, mt in [(k, E.KeywordMatchTypeEnum.PHRASE) for k in g["phrase"]] + \
                      [(k, E.KeywordMatchTypeEnum.EXACT) for k in g["exact"]]:
            agc = new_op().ad_group_criterion_operation.create
            agc.ad_group = ag_rn
            agc.status = E.AdGroupCriterionStatusEnum.ENABLED
            agc.keyword.text = kw
            agc.keyword.match_type = mt

        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.final_urls.append(g["url"])
        rsa = aga.ad.responsive_search_ad
        rsa.path1 = "szklarnie"
        rsa.path2 = g["path2"]
        for text, pin in [(g["h1"], True)] + [(h, False) for h in g["headlines"]]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin:
                a.pinned_field = E.ServedAssetFieldTypeEnum.HEADLINE_1
            rsa.headlines.append(a)
        for text, pin in [(g["d1"], E.ServedAssetFieldTypeEnum.DESCRIPTION_1),
                          (D2, E.ServedAssetFieldTypeEnum.DESCRIPTION_2)] +                          [(g.get("d3", DESCRIPTIONS[0]), None), (DESCRIPTIONS[1], None)]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin is not None:
                a.pinned_field = pin
            rsa.descriptions.append(a)

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

    for link_text, d1, d2, url in SITELINKS:
        rn = new_asset_rn()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.final_urls.append(url)
        a.sitelink_asset.link_text = link_text
        a.sitelink_asset.description1 = d1
        a.sitelink_asset.description2 = d2
        link(rn, E_.SITELINK)
    for text in CALLOUTS:
        rn = new_asset_rn()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.callout_asset.callout_text = text
        link(rn, E_.CALLOUT)
    return ops


def build_add_group_operations(client, cid, campaign_id, groups, ga):
    """Добавляет группы в УЖЕ существующую кампанию; снимает минус-слово размера, если он блокирует новые ключи."""
    E = client.enums
    campaign_rn = f"customers/{cid}/campaigns/{campaign_id}"
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    # конфликт «минус-слово ↔ новые ключи»: широкий/фразовый минус, все слова которого есть в ключе
    new_tokens = [set(k.lower().split()) for g in groups for k in g["phrase"] + g["exact"]]
    q = ("SELECT campaign.id, campaign_criterion.resource_name, campaign_criterion.keyword.text, "
         "campaign_criterion.keyword.match_type FROM campaign_criterion "
         f"WHERE campaign.id = {campaign_id} AND campaign_criterion.negative = TRUE AND campaign_criterion.type = KEYWORD")
    removed = []
    for r in ga.search(customer_id=cid, query=q):
        txt = r.campaign_criterion.keyword.text
        toks = set(txt.lower().split())
        if any(toks and toks <= t for t in new_tokens):
            op = new_op().campaign_criterion_operation
            op.remove = r.campaign_criterion.resource_name
            removed.append(txt)
    print("снимается минус-слово, блокирующее новые ключи:", removed or "нет")

    for i, g in enumerate(groups, start=1):
        ag_rn = f"customers/{cid}/adGroups/-{50 + i}"
        ag = new_op().ad_group_operation.create
        ag.resource_name = ag_rn
        ag.name = g["name"]
        ag.campaign = campaign_rn
        ag.status = E.AdGroupStatusEnum.ENABLED
        ag.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
        for kw, mt in [(k, E.KeywordMatchTypeEnum.PHRASE) for k in g["phrase"]] +                       [(k, E.KeywordMatchTypeEnum.EXACT) for k in g["exact"]]:
            agc = new_op().ad_group_criterion_operation.create
            agc.ad_group = ag_rn
            agc.status = E.AdGroupCriterionStatusEnum.ENABLED
            agc.keyword.text = kw
            agc.keyword.match_type = mt
        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.final_urls.append(g["url"])
        rsa = aga.ad.responsive_search_ad
        rsa.path1 = "szklarnie"
        rsa.path2 = g["path2"]
        for text, pin in [(g["h1"], True)] + [(h, False) for h in g["headlines"]]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin:
                a.pinned_field = E.ServedAssetFieldTypeEnum.HEADLINE_1
            rsa.headlines.append(a)
        for text, pin in [(g["d1"], E.ServedAssetFieldTypeEnum.DESCRIPTION_1),
                          (D2, E.ServedAssetFieldTypeEnum.DESCRIPTION_2),
                          (g.get("d3", DESCRIPTIONS[0]), None), (DESCRIPTIONS[1], None)]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin is not None:
                a.pinned_field = pin
            rsa.descriptions.append(a)
    return ops


def read_back(client, cid, campaign_id):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
            "campaign.target_spend.cpc_bid_ceiling_micros, campaign.ai_max_setting.enable_ai_max, "
            "campaign.network_settings.target_search_network, campaign.network_settings.target_content_network, "
            "campaign.final_url_suffix, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {campaign_id}")):
        k = r.campaign
        print(f"{k.id} | {k.name} | {E.CampaignStatusEnum.CampaignStatus.Name(k.status)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type)} | потолок клика "
              f"{k.target_spend.cpc_bid_ceiling_micros / 1e6} | AI Max {k.ai_max_setting.enable_ai_max} | "
              f"партнёры {k.network_settings.target_search_network} | КМС {k.network_settings.target_content_network} | "
              f"бюджет {r.campaign_budget.amount_micros / 1e6}")
        print("  суффикс:", k.final_url_suffix)
    for r in ga.search(customer_id=cid, query=f"SELECT campaign.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.id = {campaign_id}"):
        print("группа:", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status))
    counts = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, ad_group.name, ad_group_criterion.keyword.match_type FROM ad_group_criterion "
            f"WHERE campaign.id = {campaign_id} AND ad_group_criterion.type = KEYWORD")):
        key = (r.ad_group.name, E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.ad_group_criterion.keyword.match_type))
        counts[key] = counts.get(key, 0) + 1
    print("ключей:", counts)
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, ad_group.name, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, "
            "ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad "
            f"WHERE campaign.id = {campaign_id}")):
        rsa = r.ad_group_ad.ad.responsive_search_ad
        print(f"объявление {r.ad_group.name}: URL {list(r.ad_group_ad.ad.final_urls)}")
        for i, h in enumerate(rsa.headlines, 1):
            pin = E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(h.pinned_field) if h.pinned_field else ""
            print(f"   H{i:02d} [{len(h.text):2d}] {h.text} {('<' + pin + '>') if pin and pin != 'UNSPECIFIED' else ''}")
        for i, d in enumerate(rsa.descriptions, 1):
            pin = E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(d.pinned_field) if d.pinned_field else ""
            print(f"   D{i} [{len(d.text):2d}] {d.text} {('<' + pin + '>') if pin and pin != 'UNSPECIFIED' else ''}")
    crit = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_criterion.type, campaign_criterion.negative FROM campaign_criterion "
            f"WHERE campaign.id = {campaign_id}")):
        key = (E.CriterionTypeEnum.CriterionType.Name(r.campaign_criterion.type_), r.campaign_criterion.negative)
        crit[key] = crit.get(key, 0) + 1
    print("критерии кампании (тип, минус?):", crit)
    assets = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_asset.field_type, campaign_asset.status FROM campaign_asset "
            f"WHERE campaign.id = {campaign_id}")):
        key = (E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type),
               E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status))
        assets[key] = assets.get(key, 0) + 1
    print("ассеты кампании (тип, статус):", assets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага — только validate_only")
    ap.add_argument("--read-back-only", action="store_true", help="Ничего не создавать, прочитать кампанию по имени")
    ap.add_argument("--add-sizes", default="", help="Добавить группы в существующую кампанию, например 2x4,4x6")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    if args.read_back_only:
        for camp_id in campaign_exists(client, cid):
            read_back(client, cid, camp_id)
        return

    check_limits()
    existing = campaign_exists(client, cid)
    if args.add_sizes:
        sizes = [x.strip() for x in args.add_sizes.split(",") if x.strip()]
        assert all(x in EXTRA for x in sizes), f"неизвестный размер, доступны {list(EXTRA)}"
        assert len(existing) == 1, f"нужна ровно одна кампания «{CAMPAIGN_NAME}», найдено {existing}"
        camp_id = existing[0]
        ga = client.get_service("GoogleAdsService")
        have = {r.ad_group.name for r in ga.search(customer_id=cid, query=(
            f"SELECT campaign.id, ad_group.name FROM ad_group WHERE campaign.id = {camp_id} AND ad_group.status != 'REMOVED'"))}
        todo = [EXTRA[x] for x in sizes if x not in have]
        print("уже есть:", sorted(have), "| добавляю:", [g["name"] for g in todo])
        if not todo:
            return
        try:
            ops = build_add_group_operations(client, cid, camp_id, todo, ga)
            request = client.get_type("MutateGoogleAdsRequest")
            request.customer_id = cid
            request.mutate_operations.extend(ops)
            request.validate_only = not args.execute
            ga.mutate(request=request)
        except GoogleAdsException as ex:
            print("ОШИБКА от Google Ads:")
            for err in ex.failure.errors:
                loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
                print(f"  - {err.message} [{loc}]")
            raise SystemExit(1)
        print(f"{'Записано' if args.execute else 'Проверка пройдена, НИЧЕГО не создано'} ({len(ops)} операций).")
        if args.execute:
            read_back(client, cid, camp_id)
        return
    if existing and args.execute:
        print(f"СТОП: кампания «{CAMPAIGN_NAME}» уже есть (id {existing}). Повторная запись создала бы дубль.")
        raise SystemExit(1)
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
    campaign_id = None
    print("Создано (кампания на паузе):")
    for r in response.mutate_operation_responses:
        kind = r.WhichOneof("response")
        rn = getattr(r, kind).resource_name
        if kind == "campaign_result":
            campaign_id = rn.split("/")[-1]
        print(" ", kind, rn)
    if campaign_id:
        read_back(client, cid, campaign_id)


if __name__ == "__main__":
    main()
