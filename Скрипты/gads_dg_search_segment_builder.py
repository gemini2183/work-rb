#!/usr/bin/env python
# coding: utf-8
"""Создаёт Demand Gen `dg_search_segment` (Landver) через Google Ads API: аудитория «искали эти запросы», без канала Display.

Эксперимент Клиенты/Andverpersonalinjury/Эксперименты.md (Э-10). Шаги:
  1) пользовательский сегмент типа SEARCH («искали на Google») по ключам из действующей Search;
  2) загрузка 4 картинок (без людей, из Медиа/Кандидаты_2026-10-13);
  3) одной транзакцией: бюджет, кампания (Demand Gen, «Максимум кликов» с потолком, ПАУЗА), гео и язык —
     копия критериев действующей Search, группа (YouTube + Discover + Gmail, Display ВЫКЛ, оптимизированный
     таргетинг ВЫКЛ), аудитория группы, два мультиассет-объявления.

Цели кампании не меняются: наследуются от аккаунта (форма, звонки); оптимизация — по кликам. Включение — отдельным согласованием.

БЕЗОПАСНОСТЬ: по умолчанию validate_only — Google проверяет запрос, ничего не создаёт (аудитория и картинки подменяются
существующими объектами аккаунта для проверки структуры). Запись только с --execute. Кампания всегда на паузе, после записи
всё читается обратно из аккаунта.

Использование:
    python gads_dg_search_segment_builder.py --customer-id 213-621-6123            # проверка
    python gads_dg_search_segment_builder.py --customer-id 213-621-6123 --execute  # запись (на паузе)
    python gads_dg_search_segment_builder.py --customer-id 213-621-6123 --read-back-only
Для другого клиента копировать и менять константы вверху.
"""
import argparse
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "dg_search_segment"
AD_GROUP_NAME = "dg_search_segment car accident queries"
BUDGET_USD = 50  # в день; решение пользователя 2026-10-26 («поставим пятьдесят долларов для начала»)
CPC_CEILING_USD = 5  # допущение: данных по цене клика в Demand Gen у Landver нет, ставим, чтобы откручивалось; корректировать по показам
SOURCE_CAMPAIGN_ID = 24331208797  # действующая Search: из неё копируем гео и язык
FINAL_URL = "https://landverpersonalinjury.tilda.ws/california-car-accident-lawyer"
BUSINESS_NAME = "Landver Law"
CALL_TO_ACTION = "Contact us"
TRACKING_TEMPLATE = ("{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + CAMPAIGN_NAME +
                     "&utm_content=rb_cid_{campaignid}|gid_{adgroupid}|aid_{creative}|plc_{placement}|dev_{device}|gclid_{gclid}")
AUDIENCE_NAME = "dg_search_segment: car accident lawyer queries"
# Ключи — из действующей Search (30 дней, показы/клики), только запросы про найм юриста; без «settlement/calculator/claim»
SEARCH_KEYWORDS = ["car accident lawyer", "car accident attorney", "car accident law firm", "car accident personal injury lawyer",
                   "car crash attorney", "car crash lawyer", "car injury attorney", "car injury lawyer",
                   "traffic accident lawyer", "auto injury attorney", "auto injury lawyer", "attorney for car accident"]
MEDIA = Path(__file__).resolve().parent.parent / "Клиенты" / "Andverpersonalinjury" / "Медиа" / "Кандидаты_2026-10-13"
# Тексты: факты только из присланного клиентом (матрица 2026-08-28, объявления OpenAI 07.10, действующая Search): бесплатный разбор,
# «no fee unless we win», расходы по делу авансирует фирма. Без сумм, сроков и результатов. Лимит заголовка 30, описания 90.
ADS = [
    {"name": "A free review",
     "headlines": ["Injured in a Car Accident?", "Free Injury Case Review", "CA Car Crash Injury Lawyers",
                   "Free Review Before You Sign", "Talk to a CA Injury Attorney"],
     "descriptions": ["Free review of your California car accident injury claim. Landver Law, Beverly Hills.",
                      "Hurt in a crash? Talk to a California injury attorney before you give a statement."],
     "images": {"landscape": "V1_case_value_landscape_1200x628.jpg", "square": "V1_case_value_square_1200x1200.jpg"}},
    {"name": "B no fee",
     "headlines": ["Hurt in a Crash? No Fee", "No Fee Unless We Win", "Litigation Costs Advanced",
                   "Car Accident Injury Attorney", "Free California Case Review"],
     "descriptions": ["Crash injury cases on contingency, litigation costs advanced. Free review first.",
                      "Landver Law, Beverly Hills. Free California case review. No fee unless we win."],
     "images": {"landscape": "V2_free_review_landscape_1200x628.jpg", "square": "V2_free_review_square_1200x1200.jpg"}},
]
# Для validate_only: существующие объекты аккаунта вместо ещё не созданных
PLACEHOLDER_LANDSCAPE = 372548929299  # 1800x942
PLACEHOLDER_SQUARE = 372479354179     # 1200x1200
PLACEHOLDER_USER_LIST = 9383981659    # All Users of Landverpersonalinjury.com (вместо сегмента SEARCH)
LOGO_SQUARE = 369666444411            # Suggested logo #1_1, 1330x1330


def check_limits():
    for ad in ADS:
        assert all(len(h) <= 30 for h in ad["headlines"]), ("заголовок > 30", ad["name"])
        assert all(len(d) <= 90 for d in ad["descriptions"]), ("описание > 90", ad["name"])
        assert all("injur" in h.lower() or "hurt" in h.lower() or "crash" in h.lower() for h in ad["headlines"][:1])
        for f in ad["images"].values():
            assert (MEDIA / f).exists(), f"нет файла {f}"
    assert len(BUSINESS_NAME) <= 25 and 10 <= len(SEARCH_KEYWORDS) <= 15


def create_custom_audience(client, cid, execute):
    op = client.get_type("CustomAudienceOperation")
    ca = op.create
    ca.name = AUDIENCE_NAME + " " + datetime.now().strftime("%Y%m%d")
    ca.description = "Люди, искавшие эти запросы в Google (тип SEARCH). Demand Gen dg_search_segment, Э-10."
    ca.type_ = client.enums.CustomAudienceTypeEnum.SEARCH
    for kw in SEARCH_KEYWORDS:
        m = ca.members.add()
        m.member_type = client.enums.CustomAudienceMemberTypeEnum.KEYWORD
        m.keyword = kw
    req = client.get_type("MutateCustomAudiencesRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    resp = client.get_service("CustomAudienceService").mutate_custom_audiences(request=req)
    if execute:
        rn = resp.results[0].resource_name
        print("Создан пользовательский сегмент:", rn)
        return rn
    print("Проверка сегмента SEARCH пройдена (validate_only).")
    return None


def upload_images(client, cid, execute):
    """-> {ad_name: {'landscape': rn, 'square': rn}}"""
    if not execute:
        print("Проверка: картинки подменены существующими ассетами аккаунта (загрузка — только с --execute).")
        return {ad["name"]: {"landscape": f"customers/{cid}/assets/{PLACEHOLDER_LANDSCAPE}",
                             "square": f"customers/{cid}/assets/{PLACEHOLDER_SQUARE}"} for ad in ADS}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ops, keys = [], []
    for ad in ADS:
        for kind, fname in ad["images"].items():
            op = client.get_type("AssetOperation")
            op.create.name = f"{CAMPAIGN_NAME}_{Path(fname).stem}_{ts}"
            op.create.image_asset.data = (MEDIA / fname).read_bytes()
            ops.append(op)
            keys.append((ad["name"], kind))
    req = client.get_type("MutateAssetsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    resp = client.get_service("AssetService").mutate_assets(request=req)
    out = {}
    for (name, kind), r in zip(keys, resp.results):
        out.setdefault(name, {})[kind] = r.resource_name
    print("Загружены картинки:", sum(len(v) for v in out.values()))
    return out


def source_criteria(client, cid):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    rows = []
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.location.geo_target_constant, "
            "campaign_criterion.language.language_constant FROM campaign_criterion "
            f"WHERE campaign.id = {SOURCE_CAMPAIGN_ID} AND campaign_criterion.type IN ('LOCATION','LANGUAGE')")):
        x = r.campaign_criterion
        rows.append((E.CriterionTypeEnum.CriterionType.Name(x.type_), x.negative,
                     x.location.geo_target_constant, x.language.language_constant))
    return rows


def build_operations(client, cid, audience_rn, img_rns):
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
    b.amount_micros = BUDGET_USD * 1_000_000
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = CAMPAIGN_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.DEMAND_GEN
    c.campaign_budget = budget_rn
    c.target_spend.SetInParent()  # «Максимум кликов»; потолок на создании API не принимает (проверено validate_only), ставится отдельным шагом
    c.demand_gen_campaign_settings.upgraded_targeting = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = TRACKING_TEMPLATE

    for kind, negative, geo, lang in source_criteria(client, cid):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        if kind == "LOCATION":
            cc.negative = negative
            cc.location.geo_target_constant = geo
        else:
            cc.language.language_constant = lang

    ag = new_op().ad_group_operation.create
    ag.resource_name = ad_group_rn
    ag.name = AD_GROUP_NAME
    ag.campaign = campaign_rn
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.optimized_targeting_enabled = False  # без расширения за пределы сегмента
    ch = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
    ch.discover = True
    ch.gmail = True
    ch.youtube_in_stream = True
    ch.youtube_in_feed = True
    ch.youtube_shorts = True
    ch.display = False  # решение пользователя 2026-10-26: без Display

    audience_res = f"customers/{cid}/audiences/-4"
    au = new_op().audience_operation.create
    au.resource_name = audience_res
    au.name = f"{CAMPAIGN_NAME} искали запросы {ts}"
    au.description = "Э-10: люди, искавшие запросы про юриста по ДТП (сегмент SEARCH)"
    dim = au.dimensions.add()
    if audience_rn:
        dim.audience_segments.segments.add().custom_audience.custom_audience = audience_rn
    else:  # проверка: сегмента ещё нет
        dim.audience_segments.segments.add().user_list.user_list = f"customers/{cid}/userLists/{PLACEHOLDER_USER_LIST}"
    agc = new_op().ad_group_criterion_operation.create
    agc.ad_group = ad_group_rn
    agc.audience.audience = audience_res

    logo_rn = f"customers/{cid}/assets/{LOGO_SQUARE}"
    for ad in ADS:
        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ad_group_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.name = f"{CAMPAIGN_NAME} {ad['name']}"
        aga.ad.final_urls.append(FINAL_URL)
        m = aga.ad.demand_gen_multi_asset_ad
        m.business_name = BUSINESS_NAME
        m.call_to_action_text = CALL_TO_ACTION
        for t in ad["headlines"]:
            m.headlines.add().text = t
        for t in ad["descriptions"]:
            m.descriptions.add().text = t
        m.marketing_images.add().asset = img_rns[ad["name"]]["landscape"]
        m.square_marketing_images.add().asset = img_rns[ad["name"]]["square"]
        m.logo_images.add().asset = logo_rn
    return ops


def read_back(client, cid, campaign_rn):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    camp_id = campaign_rn.split("/")[-1]
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
            "campaign.target_spend.cpc_bid_ceiling_micros, campaign.tracking_url_template, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {camp_id}")):
        k = r.campaign
        print(f"{k.id} | {k.name} | {E.CampaignStatusEnum.CampaignStatus.Name(k.status)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type)} | "
              f"потолок клика {k.target_spend.cpc_bid_ceiling_micros / 1e6} | бюджет в день {r.campaign_budget.amount_micros / 1e6}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.optimized_targeting_enabled, "
            "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.discover, "
            "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.gmail, "
            "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.display, "
            "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_in_feed "
            f"FROM ad_group WHERE campaign.id = {camp_id}")):
        s = r.ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels
        print(f"группа: {r.ad_group.name} | {E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status)} | "
              f"оптимиз. таргетинг {r.ad_group.optimized_targeting_enabled} | discover {s.discover} gmail {s.gmail} "
              f"youtube_in_feed {s.youtube_in_feed} display {s.display}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group_ad.ad.name, ad_group_ad.status, ad_group_ad.policy_summary.approval_status "
            f"FROM ad_group_ad WHERE campaign.id = {camp_id}")):
        print("  объявление:", r.ad_group_ad.ad.name, "|", E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status), "|",
              E.PolicyApprovalStatusEnum.PolicyApprovalStatus.Name(r.ad_group_ad.policy_summary.approval_status))
    n = {}
    for r in ga.search(customer_id=cid, query=(
            f"SELECT campaign_criterion.type FROM campaign_criterion WHERE campaign.id = {camp_id}")):
        t = E.CriterionTypeEnum.CriterionType.Name(r.campaign_criterion.type_)
        n[t] = n.get(t, 0) + 1
    print("критерии кампании:", n)
    for r in ga.search(customer_id=cid, query=(
            "SELECT custom_audience.name, custom_audience.type, custom_audience.status FROM custom_audience "
            f"WHERE custom_audience.name LIKE '{AUDIENCE_NAME}%'")):
        print("сегмент:", r.custom_audience.name, E.CustomAudienceTypeEnum.CustomAudienceType.Name(r.custom_audience.type_),
              E.CustomAudienceStatusEnum.CustomAudienceStatus.Name(r.custom_audience.status))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага — только validate_only")
    ap.add_argument("--read-back-only", action="store_true")
    args = ap.parse_args()
    check_limits()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    if args.read_back_only:
        for r in ga.search(customer_id=cid, query=f"SELECT campaign.id FROM campaign WHERE campaign.name = '{CAMPAIGN_NAME}'"):
            read_back(client, cid, f"customers/{cid}/campaigns/{r.campaign.id}")
        return
    try:
        audience_rn = create_custom_audience(client, cid, args.execute)
        img_rns = upload_images(client, cid, args.execute)
        ops = build_operations(client, cid, audience_rn, img_rns)
        request = client.get_type("MutateGoogleAdsRequest")
        request.customer_id = cid
        request.mutate_operations.extend(ops)
        request.validate_only = not args.execute
        response = ga.mutate(request=request)
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
        if r.WhichOneof("response") == "campaign_result":
            campaign_rn = r.campaign_result.resource_name
    print("Создано (кампания на паузе):", campaign_rn)
    if campaign_rn:
        read_back(client, cid, campaign_rn)


if __name__ == "__main__":
    main()
