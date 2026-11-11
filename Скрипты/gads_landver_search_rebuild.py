#!/usr/bin/env python
# coding: utf-8
"""Landver: перестройка Search (план 10.11.2026): новая кампания LA+BH (только Car, на паузе) и правки основной. ЗАПИСЬ только с --execute.

Что делает (все параметры — константы ниже, план согласован пользователем 10.11, см. Решения.md и Хронику_2026-11):
  --part new   Создаёт кампанию LA+BH на паузе: бюджет, гео Los Angeles + Beverly Hills (присутствие), язык English, ручная ставка,
               только поиск Google, шаблон отслеживания как у основной, минусы основной (кроме точных «near me»-семейства) +
               5 перекрёстных, три общих списка минусов, группа с 3 точными ключами и ставкой, RSA, 6 быстрых ссылок и 10 картинок
               (те же активы, что у группы Car LA/BH), звонковый ассет и логотип.
  --part main  Основная кампания: ставка Motorcycle, новое объявление Motorcycle (старое на паузу), все остальные группы на паузу,
               бюджет, звонковые ассеты (3 отклонённых отвязать, одобренный привязать), callout «$38.5M» отвязать от аккаунта.
  --part both  (по умолчанию) оба шага; сначала новая кампания.
Без --execute — validate_only (Google проверяет, ничего не создаёт). Снимок «до» основной — Статистика/snapshot_before_labh_rebuild_*.json.
Откат: --rollback-main <снимок.json> --execute (возвращает основную), --remove-new --execute (удаляет новую кампанию).
Цели конверсий новой кампании выравниваются отдельно: gads_set_campaign_goals.py (команду печатает --read-back-only).

    python gads_landver_search_rebuild.py --customer-id 213-621-6123 [--part new|main|both] [--execute]
    python gads_landver_search_rebuild.py --customer-id 213-621-6123 --read-back-only
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.api_core.exceptions import ResourceExhausted
from google.protobuf import field_mask_pb2

from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import wrap_ga, record_mutate

MAIN_CAMPAIGN_ID = 24331208797
MAIN_CAMPAIGN_NAME = "search / car+truck injuries / s / lp - tilda"
MAIN_BUDGET_ID = 15921268502
NEW_NAME = "search / car accident / la+bh / lp - tilda"
NEW_BUDGET_USD = 110
MAIN_BUDGET_USD = 200
CAR_BID_USD = 100          # решение 10.11 ночью: возвращаем исходное предложение ($60 отменено)
MOTO_BID_USD = 150
GEO_LA = "geoTargetConstants/1013962"   # Los Angeles
GEO_BH = "geoTargetConstants/1013587"   # Beverly Hills
LANG_EN = "languageConstants/1000"
GROUP_NAME = "Car Accident - LA/BH Exact"
CAR_URL = "https://landverpersonalinjury.tilda.ws/california-car-accident-lawyer"
MOTO_URL = "https://landverpersonalinjury.tilda.ws/motorcycle-accident-lawyer-california"
KEYWORDS = ["car accident lawyer", "car accident attorney", "car accident lawyer los angeles"]  # все EXACT
# Google помечает ключи про травмы политикой HEALTH_IN_PERSONALIZED_ADS (ограничение персонализации, показ по ключу не блокирует; исключаемая).
# Те же ограничения уже стоят на действующих ключах и ссылках («APPROVED_LIMITED»). validate_only 10.11 флагнул эти два ключа.
KEYWORD_POLICY_EXEMPT = ["car accident lawyer", "car accident lawyer los angeles"]
CROSS_NEGATIVES = ["motorcycle", "pedestrian", "bike", "bicycle", "truck"]
NEAR_ME = ("near me", "nearby", "close to me", "near by")
SHARED_SETS = [12099348931, 12186238091, 12186251357]            # gen / init, names, rivals
SITELINKS_CAR = [433557208780, 433557212995, 433557229471, 433639342692, 433639355625, 433639357008]
IMAGES_CAR = [433442950841, 433630815477, 434394631925, 434394641063, 434394643274,
              434394643289, 434394643301, 434394652385, 434394652397, 434580645711]
CALL_ASSET_OK = 411032321136
LOGO_ASSET = 367221514317
OLD_CALL_LINKS = [428162733238, 433454980319, 434315972748]
CALLOUT_REMOVE = 360482809557   # «$38.5M Injury Verdict»
OLD_MOTO_AD_ID = 829858102713
MOTO_GROUP_NAME = "Motorcycle - Exact"
KEEP_ENABLED_GROUPS = {MOTO_GROUP_NAME}

# (текст, закрепление: None / "H1" / "H2" / "D1")
LABH_HEADLINES = [
    ("Los Angeles Car Crash Lawyer", "H1"), ("LA Car Accident Injury Lawyer", "H1"), ("Beverly Hills Car Crash Lawyer", "H1"),
    ("{KeyWord:LA Car Accident Lawyer}", None), ("Office on Wilshire Blvd", None), ("Beverly Hills Office", None),
    ("Injured in a Crash in LA?", None), ("Call Landver Law 24/7", None), ("Free Case Review", None),
    ("No Fee Unless We Win", None), ("20+ Years in California", None), ("4.8-Star Client Rating", None),
    ("Trial-Focused Representation", None), ("We Help People Hurt in Crashes", "H2"), ("Know What Your Case Is Worth", None),
]
LABH_DESCRIPTIONS = [
    ("Free case review after an LA car crash. We help injured people pursue compensation.", "D1"),
    ("Visit our Beverly Hills office at 8730 Wilshire Blvd or call for a free case review.", None),
    ("Free case review. Contingency fee, litigation costs advanced. Call Landver Law today.", None),
    ("We investigate the crash, document your injuries and build the case for trial.", None),
]
LABH_PATHS = ("car-accident", "los-angeles")
MOTO_HEADLINES = [
    ("Motorcycle Accident Lawyer", "H1"), ("Motorcycle Crash Attorneys", "H1"), ("California Motorcycle Lawyer", "H1"),
    ("Free Case Review", None), ("No Fee Unless We Win", None), ("Talk to an Attorney 24/7", None),
    ("Call Landver Law 24/7", None), ("Hurt in a Motorcycle Crash?", None), ("20+ Years in California", None),
    ("4.8-Star Client Rating", None), ("Trial-Focused Representation", None),
    ("Blamed for Lane Splitting?", None), ("Practicing Since 2004", None), ("Beverly Hills Law Firm", None),
    ("Defense-Side Experience", None),
]
MOTO_DESCRIPTIONS = [
    ("Free case review after a motorcycle crash. We help injured riders pursue compensation.", "D1"),
    ("Tell us what happened. An attorney reviews your case for free. No obligation.", None),
    ("Free case review. No fee unless we win. Call Landver Law 24/7 or leave your number.", None),
    ("20+ years in California courts. Trial-focused, with insight from the defense side.", None),
]
MOTO_PATHS = ("motorcycle", "california")


def check_limits():
    for lst in (LABH_HEADLINES, MOTO_HEADLINES):
        assert len(lst) <= 15
        for t, _ in lst:
            n = len(t.replace("{KeyWord:", "").rstrip("}")) if t.startswith("{KeyWord:") else len(t)
            assert n <= 30, (t, n)
    for lst in (LABH_DESCRIPTIONS, MOTO_DESCRIPTIONS):
        assert len(lst) <= 4 and all(len(t) <= 90 for t, _ in lst)
    assert all(len(p) <= 15 for p in LABH_PATHS + MOTO_PATHS)


def mm(micros_usd):
    return int(micros_usd * 1_000_000)


def fill_rsa(client, ad, headlines, descriptions, paths, url):
    E = client.enums
    pin = {"H1": E.ServedAssetFieldTypeEnum.HEADLINE_1, "H2": E.ServedAssetFieldTypeEnum.HEADLINE_2,
           "D1": E.ServedAssetFieldTypeEnum.DESCRIPTION_1}
    ad.final_urls.append(url)
    rsa = ad.responsive_search_ad
    for text, p in headlines:
        a = client.get_type("AdTextAsset")
        a.text = text
        if p:
            a.pinned_field = pin[p]
        rsa.headlines.append(a)
    for text, p in descriptions:
        a = client.get_type("AdTextAsset")
        a.text = text
        if p:
            a.pinned_field = pin[p]
        rsa.descriptions.append(a)
    rsa.path1, rsa.path2 = paths


def q(ga, cid, query):
    return list(ga.search(customer_id=cid, query=query))


def read_main_negatives(ga, cid, E):
    out = []
    for r in q(ga, cid, "SELECT campaign.id, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type "
                         f"FROM campaign_criterion WHERE campaign.id = {MAIN_CAMPAIGN_ID} "
                         "AND campaign_criterion.type = KEYWORD AND campaign_criterion.negative = TRUE"):
        k = r.campaign_criterion.keyword
        out.append((k.text, k.match_type))
    return out


def build_new_ops(client, cid, ga):
    E = client.enums
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    main = q(ga, cid, "SELECT campaign.id, campaign.tracking_url_template FROM campaign "
                      f"WHERE campaign.id = {MAIN_CAMPAIGN_ID}")[0].campaign
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ag_rn = f"customers/{cid}/adGroups/-3"
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{NEW_NAME} budget {ts}"
    b.amount_micros = mm(NEW_BUDGET_USD)
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = NEW_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.SEARCH
    c.campaign_budget = budget_rn
    c.manual_cpc.enhanced_cpc_enabled = False
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False
    c.network_settings.target_content_network = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = main.tracking_url_template
    c.ai_max_setting.enable_ai_max = False
    for t in (E.AssetAutomationTypeEnum.TEXT_ASSET_AUTOMATION,
              E.AssetAutomationTypeEnum.FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = t
        s.asset_automation_status = E.AssetAutomationStatusEnum.OPTED_OUT

    for geo in (GEO_LA, GEO_BH):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = geo
    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.language.language_constant = LANG_EN

    # Минусы основной (1 699 штук) копируются отдельным шагом --part negatives (суточный лимит операций basic access, 10.11 упёрлись в него).
    for text in CROSS_NEGATIVES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = E.KeywordMatchTypeEnum.PHRASE
    for sid in SHARED_SETS:
        css = new_op().campaign_shared_set_operation.create
        css.campaign = campaign_rn
        css.shared_set = f"customers/{cid}/sharedSets/{sid}"

    ag = new_op().ad_group_operation.create
    ag.resource_name = ag_rn
    ag.name = GROUP_NAME
    ag.campaign = campaign_rn
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
    ag.cpc_bid_micros = mm(CAR_BID_USD)
    for kw in KEYWORDS:
        kop = new_op().ad_group_criterion_operation
        agc = kop.create
        agc.ad_group = ag_rn
        agc.status = E.AdGroupCriterionStatusEnum.ENABLED
        agc.keyword.text = kw
        agc.keyword.match_type = E.KeywordMatchTypeEnum.EXACT
        if kw in KEYWORD_POLICY_EXEMPT:
            k = kop.exempt_policy_violation_keys.add()
            k.policy_name = "HEALTH_IN_PERSONALIZED_ADS"
            k.violating_text = kw
    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ag_rn
    aga.status = E.AdGroupAdStatusEnum.ENABLED
    fill_rsa(client, aga.ad, LABH_HEADLINES, LABH_DESCRIPTIONS, LABH_PATHS, CAR_URL)
    for aid in SITELINKS_CAR:
        x = new_op().ad_group_asset_operation.create
        x.ad_group = ag_rn
        x.asset = f"customers/{cid}/assets/{aid}"
        x.field_type = E.AssetFieldTypeEnum.SITELINK
    for aid in IMAGES_CAR:
        x = new_op().ad_group_asset_operation.create
        x.ad_group = ag_rn
        x.asset = f"customers/{cid}/assets/{aid}"
        x.field_type = E.AssetFieldTypeEnum.AD_IMAGE
    for aid, ft in ((CALL_ASSET_OK, E.AssetFieldTypeEnum.CALL), (LOGO_ASSET, E.AssetFieldTypeEnum.BUSINESS_LOGO)):
        x = new_op().campaign_asset_operation.create
        x.campaign = campaign_rn
        x.asset = f"customers/{cid}/assets/{aid}"
        x.field_type = ft
    print(f"[new] операций: {len(ops)} (без копии минусов основной; перекрёстных {len(CROSS_NEGATIVES)})")
    return ops


def build_neg_ops(client, cid, ga, new_id, limit):
    """Недостающие кампанийные минусы новой кампании (копия основной без точных «near me»-семейства). Идемпотентно."""
    E = client.enums
    have = set()
    for r in q(ga, cid, "SELECT campaign.id, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type "
                         f"FROM campaign_criterion WHERE campaign.id = {new_id} AND campaign_criterion.type = KEYWORD AND campaign_criterion.negative = TRUE"):
        have.add((r.campaign_criterion.keyword.text, r.campaign_criterion.keyword.match_type))
    want, skipped = [], 0
    for text, mt in read_main_negatives(ga, cid, E):
        if mt == E.KeywordMatchTypeEnum.EXACT and any(w in text for w in NEAR_ME):
            skipped += 1
            continue
        want.append((text, mt))
    assert skipped == 34, f"ожидали 34 «near me» минуса, нашли {skipped}"
    missing = [x for x in want if x not in have]
    print(f"[negatives] нужно {len(want)}, уже есть {len(want) - len(missing)}, добавить {len(missing)} (за шаг не больше {limit})")
    ops = []
    for text, mt in missing[:limit]:
        op = client.get_type("MutateOperation")
        cc = op.campaign_criterion_operation.create
        cc.campaign = f"customers/{cid}/campaigns/{new_id}"
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = mt
        ops.append(op)
    return ops, len(missing)


def snapshot_main(client, cid, ga):
    E = client.enums
    snap = {"taken": datetime.now().isoformat(timespec="seconds"), "groups": [], "calls": [], "callout": None}
    for r in q(ga, cid, "SELECT campaign.id, ad_group.resource_name, ad_group.name, ad_group.status, ad_group.cpc_bid_micros "
                         f"FROM ad_group WHERE campaign.id = {MAIN_CAMPAIGN_ID}"):
        snap["groups"].append({"rn": r.ad_group.resource_name, "name": r.ad_group.name,
                               "status": E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status),
                               "cpc_micros": r.ad_group.cpc_bid_micros})
    r = q(ga, cid, f"SELECT campaign.id, campaign_budget.resource_name, campaign_budget.amount_micros FROM campaign WHERE campaign.id = {MAIN_CAMPAIGN_ID}")[0]
    snap["budget"] = {"rn": r.campaign_budget.resource_name, "micros": r.campaign_budget.amount_micros}
    r = q(ga, cid, f"SELECT ad_group_ad.resource_name, ad_group_ad.status FROM ad_group_ad WHERE ad_group_ad.ad.id = {OLD_MOTO_AD_ID}")[0]
    snap["old_moto_ad"] = {"rn": r.ad_group_ad.resource_name,
                           "status": E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status)}
    for r in q(ga, cid, "SELECT campaign.id, campaign_asset.resource_name, campaign_asset.asset, campaign_asset.status "
                         f"FROM campaign_asset WHERE campaign.id = {MAIN_CAMPAIGN_ID} AND campaign_asset.field_type = CALL"):
        snap["calls"].append({"rn": r.campaign_asset.resource_name, "asset": r.campaign_asset.asset,
                              "status": E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status)})
    for r in q(ga, cid, "SELECT customer_asset.resource_name, customer_asset.asset, customer_asset.status FROM customer_asset "
                         f"WHERE customer_asset.field_type = CALLOUT AND customer_asset.asset = 'customers/{cid}/assets/{CALLOUT_REMOVE}'"):
        snap["callout"] = {"rn": r.customer_asset.resource_name, "asset": r.customer_asset.asset,
                           "status": E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.customer_asset.status)}
    return snap


def build_main_ops(client, cid, ga, snap):
    E = client.enums
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    moto_rn = None
    for g in snap["groups"]:
        if g["name"] == MOTO_GROUP_NAME:
            moto_rn = g["rn"]
    assert moto_rn, "нет группы Motorcycle"
    op = new_op().ad_group_operation
    op.update.resource_name = moto_rn
    op.update.cpc_bid_micros = mm(MOTO_BID_USD)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))

    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = moto_rn
    aga.status = E.AdGroupAdStatusEnum.ENABLED
    fill_rsa(client, aga.ad, MOTO_HEADLINES, MOTO_DESCRIPTIONS, MOTO_PATHS, MOTO_URL)
    op = new_op().ad_group_ad_operation
    op.update.resource_name = snap["old_moto_ad"]["rn"]
    op.update.status = E.AdGroupAdStatusEnum.PAUSED
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))

    paused = []
    for g in snap["groups"]:
        if g["name"] in KEEP_ENABLED_GROUPS or g["status"] == "PAUSED":
            continue
        op = new_op().ad_group_operation
        op.update.resource_name = g["rn"]
        op.update.status = E.AdGroupStatusEnum.PAUSED
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
        paused.append(g["name"])

    op = new_op().campaign_budget_operation
    op.update.resource_name = snap["budget"]["rn"]
    op.update.amount_micros = mm(MAIN_BUDGET_USD)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))

    for link in snap["calls"]:
        new_op().campaign_asset_operation.remove = link["rn"]
    x = new_op().campaign_asset_operation.create
    x.campaign = f"customers/{cid}/campaigns/{MAIN_CAMPAIGN_ID}"
    x.asset = f"customers/{cid}/assets/{CALL_ASSET_OK}"
    x.field_type = E.AssetFieldTypeEnum.CALL
    if snap["callout"]:
        new_op().customer_asset_operation.remove = snap["callout"]["rn"]
    print(f"[main] операций: {len(ops)}; группы на паузу: {paused}")
    return ops


def build_rollback_ops(client, cid, ga, snap):
    E = client.enums
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    for g in snap["groups"]:
        op = new_op().ad_group_operation
        op.update.resource_name = g["rn"]
        op.update.status = getattr(E.AdGroupStatusEnum, g["status"])
        op.update.cpc_bid_micros = g["cpc_micros"]
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status", "cpc_bid_micros"]))
    op = new_op().campaign_budget_operation
    op.update.resource_name = snap["budget"]["rn"]
    op.update.amount_micros = snap["budget"]["micros"]
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))
    op = new_op().ad_group_ad_operation
    op.update.resource_name = snap["old_moto_ad"]["rn"]
    op.update.status = getattr(E.AdGroupAdStatusEnum, snap["old_moto_ad"]["status"])
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    moto = [g for g in snap["groups"] if g["name"] == MOTO_GROUP_NAME][0]["rn"].split("/")[-1]
    for r in q(ga, cid, f"SELECT ad_group_ad.resource_name, ad_group_ad.ad.id FROM ad_group_ad WHERE ad_group.id = {moto} "
                         f"AND ad_group_ad.ad.id != {OLD_MOTO_AD_ID} AND ad_group_ad.status != REMOVED"):
        op = new_op().ad_group_ad_operation
        op.update.resource_name = r.ad_group_ad.resource_name
        op.update.status = E.AdGroupAdStatusEnum.PAUSED
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    new_op().campaign_asset_operation.remove = f"customers/{cid}/campaignAssets/{MAIN_CAMPAIGN_ID}~{CALL_ASSET_OK}~CALL"
    for link in snap["calls"]:
        x = new_op().campaign_asset_operation.create
        x.campaign = f"customers/{cid}/campaigns/{MAIN_CAMPAIGN_ID}"
        x.asset = link["asset"]
        x.field_type = E.AssetFieldTypeEnum.CALL
        x.status = getattr(E.AssetLinkStatusEnum, link["status"])
    if snap["callout"]:
        x = new_op().customer_asset_operation.create
        x.asset = snap["callout"]["asset"]
        x.field_type = E.AssetFieldTypeEnum.CALLOUT
        x.status = getattr(E.AssetLinkStatusEnum, snap["callout"]["status"])
    return ops


def run(client, cid, ops, execute, label):
    svc = client.get_service("GoogleAdsService")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not execute
    record_mutate("gads_landver_search_rebuild", len(ops), validate_only=not execute)   # журнал операций API (П-001)
    try:
        resp = svc.mutate(request=req)
    except ResourceExhausted as ex:
        print(f"ЛИМИТ ОПЕРАЦИЙ Google Ads ({label}): {str(ex)[:300]}")
        raise SystemExit(2)
    except GoogleAdsException as ex:
        print(f"ОШИБКА от Google Ads ({label}):")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
            d = err.details.policy_violation_details
            if d.key.policy_name:
                print(f"      политика: {d.key.policy_name}; текст: {d.key.violating_text}; исключаемо: {d.is_exemptible}; {d.external_policy_name}; {d.external_policy_description}")
        raise SystemExit(1)
    if not execute:
        print(f"[{label}] проверка пройдена ({len(ops)} операций), ничего не записано (validate_only).")
        return None
    print(f"[{label}] записано, ответов: {len(resp.mutate_operation_responses)}")
    return resp


def find_new_campaign(ga, cid):
    rows = q(ga, cid, f"SELECT campaign.id FROM campaign WHERE campaign.name = '{NEW_NAME}' AND campaign.status != REMOVED")
    return rows[0].campaign.id if rows else None


def read_back(client, cid, ga):
    E = client.enums
    new_id = find_new_campaign(ga, cid)
    print("\n=== Чтение обратно ===")
    if new_id:
        print(f"-- новая кампания {new_id}")
        for r in q(ga, cid, "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, campaign.tracking_url_template, "
                            "campaign.network_settings.target_google_search, campaign.network_settings.target_search_network, "
                            "campaign.network_settings.target_content_network, campaign.geo_target_type_setting.positive_geo_target_type, "
                            f"campaign_budget.amount_micros FROM campaign WHERE campaign.id = {new_id}"):
            k = r.campaign
            print(k.name, E.CampaignStatusEnum.CampaignStatus.Name(k.status), E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(k.bidding_strategy_type),
                  "бюджет", r.campaign_budget.amount_micros / 1e6, "| поиск", k.network_settings.target_google_search,
                  "партнёры", k.network_settings.target_search_network, "контекст", k.network_settings.target_content_network,
                  "| гео-режим", E.PositiveGeoTargetTypeEnum.PositiveGeoTargetType.Name(k.geo_target_type_setting.positive_geo_target_type))
            print("шаблон:", k.tracking_url_template[:90], "...")
        crit = {}
        for r in q(ga, cid, f"SELECT campaign.id, campaign_criterion.type, campaign_criterion.negative, campaign_criterion.keyword.match_type, "
                            f"campaign_criterion.location.geo_target_constant FROM campaign_criterion WHERE campaign.id = {new_id}"):
            c = r.campaign_criterion
            key = (E.CriterionTypeEnum.CriterionType.Name(c.type_), c.negative,
                   E.KeywordMatchTypeEnum.KeywordMatchType.Name(c.keyword.match_type) if c.negative else "")
            crit[key] = crit.get(key, 0) + 1
            if c.location.geo_target_constant:
                print("  гео:", c.location.geo_target_constant)
        print("критерии (тип, минус?, соответствие): ", crit)
        for r in q(ga, cid, f"SELECT campaign.id, shared_set.name FROM campaign_shared_set WHERE campaign.id = {new_id}"):
            print("  общий список:", r.shared_set.name)
        for r in q(ga, cid, f"SELECT campaign.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros FROM ad_group WHERE campaign.id = {new_id}"):
            print("  группа:", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status), "ставка", r.ad_group.cpc_bid_micros / 1e6)
        for r in q(ga, cid, f"SELECT campaign.id, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status "
                            f"FROM ad_group_criterion WHERE campaign.id = {new_id} AND ad_group_criterion.type = KEYWORD"):
            c = r.ad_group_criterion
            print("  ключ:", c.keyword.text, E.KeywordMatchTypeEnum.KeywordMatchType.Name(c.keyword.match_type), c.status)
        for r in q(ga, cid, f"SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.policy_summary.approval_status, ad_group_ad.ad.final_urls, "
                            f"ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions, "
                            f"ad_group_ad.ad.responsive_search_ad.path1, ad_group_ad.ad.responsive_search_ad.path2 FROM ad_group_ad WHERE campaign.id = {new_id}"):
            a = r.ad_group_ad
            print_ad(E, a)
        for r in q(ga, cid, f"SELECT campaign.id, campaign_asset.field_type, campaign_asset.asset, campaign_asset.status, campaign_asset.primary_status, "
                            f"campaign_asset.primary_status_reasons FROM campaign_asset WHERE campaign.id = {new_id}"):
            ca = r.campaign_asset
            print("  кампанийный ассет:", E.AssetFieldTypeEnum.AssetFieldType.Name(ca.field_type), ca.asset, "статус", ca.status,
                  "primary", ca.primary_status, list(ca.primary_status_reasons))
        cnt = {}
        for r in q(ga, cid, f"SELECT campaign.id, ad_group_asset.field_type, ad_group_asset.status FROM ad_group_asset WHERE campaign.id = {new_id}"):
            key = (E.AssetFieldTypeEnum.AssetFieldType.Name(r.ad_group_asset.field_type), r.ad_group_asset.status)
            cnt[key] = cnt.get(key, 0) + 1
        print("  ассеты группы (тип, статус):", cnt)
    else:
        print("новой кампании ещё нет")
    print(f"\n-- основная {MAIN_CAMPAIGN_ID}")
    for r in q(ga, cid, f"SELECT campaign.id, campaign.status, campaign_budget.amount_micros FROM campaign WHERE campaign.id = {MAIN_CAMPAIGN_ID}"):
        print("статус", E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status), "бюджет", r.campaign_budget.amount_micros / 1e6)
    for r in q(ga, cid, f"SELECT campaign.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros FROM ad_group WHERE campaign.id = {MAIN_CAMPAIGN_ID} ORDER BY ad_group.name"):
        print("  ", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status), r.ad_group.cpc_bid_micros / 1e6)
    for r in q(ga, cid, f"SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.policy_summary.approval_status, ad_group_ad.ad.final_urls, "
                        f"ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions, "
                        f"ad_group_ad.ad.responsive_search_ad.path1, ad_group_ad.ad.responsive_search_ad.path2 FROM ad_group_ad "
                        f"WHERE ad_group.name = '{MOTO_GROUP_NAME}' AND campaign.id = {MAIN_CAMPAIGN_ID} AND ad_group_ad.status != REMOVED"):
        print_ad(E, r.ad_group_ad)
    for r in q(ga, cid, f"SELECT campaign.id, campaign_asset.asset, campaign_asset.status, campaign_asset.primary_status, campaign_asset.primary_status_reasons "
                        f"FROM campaign_asset WHERE campaign.id = {MAIN_CAMPAIGN_ID} AND campaign_asset.field_type = CALL"):
        ca = r.campaign_asset
        print("  звонок:", ca.asset, "статус", ca.status, "primary", ca.primary_status, list(ca.primary_status_reasons))
    left = [r.customer_asset.asset for r in q(ga, cid, f"SELECT customer_asset.asset FROM customer_asset WHERE customer_asset.field_type = CALLOUT")]
    print("  callouts аккаунта:", len(left), "| «$38.5M» привязан:", f"customers/{cid}/assets/{CALLOUT_REMOVE}" in left)


def print_ad(E, a):
    print(f"  объявление {a.ad.id} {a.status} approval={a.policy_summary.approval_status} url={list(a.ad.final_urls)} path={a.ad.responsive_search_ad.path1}/{a.ad.responsive_search_ad.path2}")
    for i, h in enumerate(a.ad.responsive_search_ad.headlines, 1):
        pin = E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(h.pinned_field) if h.pinned_field else "-"
        print(f"     H{i} [{len(h.text)}] {pin}: {h.text}")
    for i, d in enumerate(a.ad.responsive_search_ad.descriptions, 1):
        pin = E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(d.pinned_field) if d.pinned_field else "-"
        print(f"     D{i} [{len(d.text)}] {pin}: {d.text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--part", choices=["new", "main", "both", "negatives"], default="both")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    ap.add_argument("--chunk", type=int, default=400, help="минусов за один запрос в --part negatives")
    ap.add_argument("--read-back-only", action="store_true")
    ap.add_argument("--rollback-main", help="снимок .json — вернуть основную кампанию")
    ap.add_argument("--remove-new", action="store_true", help="удалить новую кампанию LA+BH")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = wrap_ga(client.get_service("GoogleAdsService"), "gads_landver_search_rebuild")   # журнал операций API (П-001)
    check_limits()
    if a.read_back_only:
        read_back(client, cid, ga)
        return
    if a.rollback_main:
        snap = json.load(open(a.rollback_main, encoding="utf-8"))
        run(client, cid, build_rollback_ops(client, cid, ga, snap), a.execute, "rollback-main")
        return
    if a.remove_new:
        nid = find_new_campaign(ga, cid)
        assert nid, "новой кампании нет"
        op = client.get_type("MutateOperation")
        op.campaign_operation.remove = f"customers/{cid}/campaigns/{nid}"
        run(client, cid, [op], a.execute, "remove-new")
        return
    if a.part == "negatives":
        nid = find_new_campaign(ga, cid)
        assert nid, "новой кампании нет"
        total = 0
        while True:
            ops, left = build_neg_ops(client, cid, ga, nid, a.chunk)
            if not ops:
                break
            run(client, cid, ops, a.execute, "negatives")
            if not a.execute:
                break
        read_back(client, cid, ga) if a.execute else None
        return
    if a.part in ("new", "both"):
        if find_new_campaign(ga, cid):
            raise SystemExit("Новая кампания уже существует — повторное создание остановлено.")
        run(client, cid, build_new_ops(client, cid, ga), a.execute, "new")
    if a.part in ("main", "both"):
        snap = snapshot_main(client, cid, ga)
        if a.execute:
            p = Path(__file__).resolve().parent.parent / "Клиенты" / "Andverpersonalinjury" / "Статистика" / \
                f"snapshot_before_labh_rebuild_{datetime.now():%Y%m%d_%H%M}.json"
            p.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
            print("Снимок «до»:", p)
        run(client, cid, build_main_ops(client, cid, ga, snap), a.execute, "main")
    if a.execute:
        read_back(client, cid, ga)


if __name__ == "__main__":
    main()
