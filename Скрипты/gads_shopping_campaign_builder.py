#!/usr/bin/env python
# coding: utf-8
"""Создаёт тестовую Shopping-кампанию «весь фид (теплицы), хвост запросов» по образцу рабочей `shop_search` — ЗАПИСЬ.

Тест EkspertAgro, вариант C+ (решения пользователя 2026-10-27, `Клиенты/EkspertAgro/Мерчант/Решения.md`): новая кампания без списков
«Shop - запросы без размера 1/2» и «размеры - есть в фиде, нет отдельных групп»; хвост запросов открыт, голова, мусор, не про товар,
листы и бренды закрыты новым списком (точные запросы), 7 дорогих размеров закрыты фразами. Берёт у `shop_search`: Merchant Center,
приоритет, сети, гео и тип гео, расписание, исключённую аудиторию, минусы кампании (все), шаблон отслеживания (метка кампании
меняется на имя новой). Подключает те же общие списки «Общий», «Из запросов», «folia», «размеры - есть в запросах, нет в фиде».

Создаётся ОДНИМ атомарным запросом (всё или ничего): бюджет, кампания (ПАУЗА), критерии, два новых общих списка с содержимым, подключение
списков, группа, товарное объявление, дерево товарных групп (тип `szklarnie` — ставка; всё остальное исключено).
БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не создаёт). Запись — только с --execute. Включение кампании — НЕ
здесь (отдельное согласование). Чтение результата — `--read-back-only`.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python gads_shopping_campaign_builder.py                    # проверка (validate_only)
    python gads_shopping_campaign_builder.py --execute          # запись, на паузе
    python gads_shopping_campaign_builder.py --read-back-only   # прочитать созданное из кабинета
Ограничения: скрипт под одну кампанию-образец; CSV классификации запросов берутся из `Статистика/` клиента (файлы
`gads_shopping_nosize_split.py` за --stamp); бюджет, потолок клика и размеры задаются параметрами.
"""
import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "Клиенты" / "EkspertAgro" / "Мерчант" / "Статистика"
CUSTOMER_ID = "8826134558"
SRC_CAMPAIGN_ID = "24210390946"  # shop_search
NEW_NAME = "shop_tail"
ATTACH_EXISTING = ["Общий", "Из запросов", "folia", "размеры - есть в запросах, нет в фиде"]
SIZES_SRC_LIST = "размеры - есть в в фиде, нет отдельных групп"  # в кабинете имя с опечаткой «в в»
NEW_LIST_JUNK = "Shop - тест: голова, мусор, бренды"
NEW_LIST_SIZES = "Shop - тест: дорогие размеры"
EXPENSIVE_SIZES = ["2x2", "3x2", "3,5x4", "3x10", "2,5x8", "3x8", "4x4"]
PRODUCT_TYPE = "szklarnie"
MAX_CHARS, MAX_WORDS = 80, 10
INVALID_CHARS = set(",!@%^()={};~`<>?\\|")
SIZE_RX = re.compile(r"(?<!\d)(\d+)(?:[.,\s](\d))?\s*[x×х]\s*(\d+)(?:[.,](\d))?(?!\d)")


def norm_size(text):
    m = SIZE_RX.search(text.lower())
    if not m:
        return None
    a, b, c, d = m.groups()
    return f"{a},{b}" if b else a, f"{c},{d}" if d else c


def size_key(text):
    s = norm_size(text)
    return f"{s[0]}x{s[1]}" if s else None


def valid_text(t):
    return bool(t) and len(t) <= MAX_CHARS and len(t.split()) <= MAX_WORDS and not (INVALID_CHARS & set(t))


def q(ga, query):
    return [r for b in ga.search_stream(customer_id=CUSTOMER_ID, query=query) for r in b.results]


def read_source(client, ga):
    E = client.enums
    r = q(ga, f"""SELECT campaign.name, campaign.shopping_setting.merchant_id, campaign.shopping_setting.campaign_priority,
        campaign.shopping_setting.enable_local, campaign.tracking_url_template,
        campaign.geo_target_type_setting.positive_geo_target_type, campaign.geo_target_type_setting.negative_geo_target_type
        FROM campaign WHERE campaign.id = {SRC_CAMPAIGN_ID}""")[0].campaign
    src = {"merchant_id": r.shopping_setting.merchant_id, "priority": r.shopping_setting.campaign_priority,
           "enable_local": r.shopping_setting.enable_local, "tracking": r.tracking_url_template,
           "geo_pos": r.geo_target_type_setting.positive_geo_target_type, "geo_neg": r.geo_target_type_setting.negative_geo_target_type,
           "geo": [], "schedule": [], "user_lists": [], "neg_kw": []}
    for x in q(ga, f"""SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.location.geo_target_constant,
        campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, campaign_criterion.ad_schedule.start_minute,
        campaign_criterion.ad_schedule.end_hour, campaign_criterion.ad_schedule.end_minute, campaign_criterion.user_list.user_list,
        campaign_criterion.keyword.text, campaign_criterion.keyword.match_type
        FROM campaign_criterion WHERE campaign.id = {SRC_CAMPAIGN_ID} AND campaign_criterion.status != 'REMOVED'"""):
        k = x.campaign_criterion
        t = E.CriterionTypeEnum.CriterionType.Name(k.type_)
        if t == "LOCATION" and not k.negative:
            src["geo"].append(k.location.geo_target_constant)
        elif t == "AD_SCHEDULE":
            s = k.ad_schedule
            src["schedule"].append((s.day_of_week, s.start_hour, s.start_minute, s.end_hour, s.end_minute))
        elif t == "USER_LIST":
            src["user_lists"].append((k.user_list.user_list, k.negative))
        elif t == "KEYWORD" and k.negative:
            src["neg_kw"].append((k.keyword.text, k.keyword.match_type))
    return src


def shared_sets(ga):
    return {r.shared_set.name: r.shared_set.id for r in
            q(ga, "SELECT shared_set.id, shared_set.name FROM shared_set WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND shared_set.status = 'ENABLED'")}


def read_list(ga, set_id):
    return [r.shared_criterion.keyword.text for r in
            q(ga, f"SELECT shared_criterion.keyword.text FROM shared_criterion WHERE shared_set.id = {set_id}")]


def build_lists(ga, sets, stamp):
    """Содержимое двух новых списков. Возвращает (junk_exact, sizes_phrase, сводка)."""
    parts = {}
    for b in ("keep_junk", "keep_no_product", "keep_sheet"):
        parts[b] = [str(t).strip().lower() for t in pd.read_csv(STATS / f"nosize_{b}_{stamp}.csv", encoding="utf-8-sig")["term"].dropna()]
    parts["head"] = [str(t).strip().lower() for t in pd.read_csv(STATS / f"nosize_head_{stamp}.csv", encoding="utf-8-sig")["term"].dropna()]
    junk, rejected = [], []
    for name, terms in parts.items():
        for t in terms:
            (junk if valid_text(t) else rejected).append(t)
    junk = list(dict.fromkeys(junk))
    sizes_all = read_list(ga, sets[SIZES_SRC_LIST])
    target = set(EXPENSIVE_SIZES)
    sizes = list(dict.fromkeys(t.lower() for t in sizes_all if size_key(t) in target and valid_text(t.lower())))
    summary = {**{k: len(v) for k, v in parts.items()}, "в список мусора (после проверки)": len(junk), "отклонено Google-правилами": len(rejected),
               "фраз по дорогим размерам": len(sizes), "из списка размеров прочитано": len(sizes_all)}
    return junk, sizes, summary


def build_operations(client, src, sets, junk, sizes, args):
    E = client.enums
    cid = CUSTOMER_ID
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ag_id, root_id = -3, -4
    ops = []
    tmp = [100]

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{NEW_NAME} budget {ts}"
    b.amount_micros = int(args.budget * 1_000_000)
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = NEW_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.SHOPPING
    c.campaign_budget = budget_rn
    c.shopping_setting.merchant_id = src["merchant_id"]
    c.shopping_setting.campaign_priority = src["priority"]
    c.shopping_setting.enable_local = src["enable_local"]
    c.target_spend.cpc_bid_ceiling_micros = int(args.cpc_ceiling * 1_000_000)
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False
    c.network_settings.target_content_network = False
    c.network_settings.target_partner_search_network = False
    c.geo_target_type_setting.positive_geo_target_type = src["geo_pos"]
    c.geo_target_type_setting.negative_geo_target_type = src["geo_neg"]
    c.tracking_url_template = src["tracking"].replace("utm_campaign=shop_search_", f"utm_campaign={NEW_NAME}_")
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING

    for geo in src["geo"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = geo
    for day, sh, sm, eh, em in src["schedule"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = day
        cc.ad_schedule.start_hour = sh
        cc.ad_schedule.start_minute = sm
        cc.ad_schedule.end_hour = eh
        cc.ad_schedule.end_minute = em
    for ul, neg in src["user_lists"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.user_list.user_list = ul
        cc.negative = neg
    for text, mt in src["neg_kw"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = mt

    for name in ATTACH_EXISTING:
        cs = new_op().campaign_shared_set_operation.create
        cs.campaign = campaign_rn
        cs.shared_set = f"customers/{cid}/sharedSets/{sets[name]}"
    for name, items, mt in ((NEW_LIST_JUNK, junk, E.KeywordMatchTypeEnum.EXACT), (NEW_LIST_SIZES, sizes, E.KeywordMatchTypeEnum.PHRASE)):
        tmp[0] += 1
        set_rn = f"customers/{cid}/sharedSets/-{tmp[0]}"
        s = new_op().shared_set_operation.create
        s.resource_name = set_rn
        s.name = name
        s.type_ = E.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        for t in items:
            sc = new_op().shared_criterion_operation.create
            sc.shared_set = set_rn
            sc.keyword.text = t
            sc.keyword.match_type = mt
        cs = new_op().campaign_shared_set_operation.create
        cs.campaign = campaign_rn
        cs.shared_set = set_rn

    ag = new_op().ad_group_operation.create
    ag_rn = f"customers/{cid}/adGroups/{ag_id}"
    ag.resource_name = ag_rn
    ag.name = "greenhouses"
    ag.campaign = campaign_rn
    ag.type_ = E.AdGroupTypeEnum.SHOPPING_PRODUCT_ADS
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.cpc_bid_micros = int(args.cpc_ceiling * 1_000_000)

    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ag_rn
    aga.status = E.AdGroupAdStatusEnum.ENABLED
    client.copy_from(aga.ad.shopping_product_ad, client.get_type("ShoppingProductAdInfo"))

    root_rn = f"customers/{cid}/adGroupCriteria/{ag_id}~{root_id}"
    root = new_op().ad_group_criterion_operation.create
    root.resource_name = root_rn
    root.ad_group = ag_rn
    root.status = E.AdGroupCriterionStatusEnum.ENABLED
    root.listing_group.type_ = E.ListingGroupTypeEnum.SUBDIVISION

    unit = new_op().ad_group_criterion_operation.create
    unit.resource_name = f"customers/{cid}/adGroupCriteria/{ag_id}~-5"
    unit.ad_group = ag_rn
    unit.status = E.AdGroupCriterionStatusEnum.ENABLED
    unit.cpc_bid_micros = int(args.cpc_ceiling * 1_000_000)
    unit.listing_group.type_ = E.ListingGroupTypeEnum.UNIT
    unit.listing_group.parent_ad_group_criterion = root_rn
    unit.listing_group.case_value.product_type.level = E.ProductTypeLevelEnum.LEVEL1
    unit.listing_group.case_value.product_type.value = PRODUCT_TYPE

    rest = new_op().ad_group_criterion_operation.create
    rest.resource_name = f"customers/{cid}/adGroupCriteria/{ag_id}~-6"
    rest.ad_group = ag_rn
    rest.status = E.AdGroupCriterionStatusEnum.ENABLED
    rest.negative = True
    rest.listing_group.type_ = E.ListingGroupTypeEnum.UNIT
    rest.listing_group.parent_ad_group_criterion = root_rn
    rest.listing_group.case_value.product_type.level = E.ProductTypeLevelEnum.LEVEL1
    return ops


def read_back(client, ga):
    E = client.enums
    rows = q(ga, f"""SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, campaign.bidding_strategy_type,
        campaign.target_spend.cpc_bid_ceiling_micros, campaign.shopping_setting.merchant_id, campaign.shopping_setting.campaign_priority,
        campaign.shopping_setting.enable_local, campaign.network_settings.target_google_search, campaign.network_settings.target_search_network,
        campaign.network_settings.target_content_network, campaign.network_settings.target_partner_search_network,
        campaign.tracking_url_template, campaign_budget.amount_micros, campaign_budget.explicitly_shared
        FROM campaign WHERE campaign.name = '{NEW_NAME}' AND campaign.status != 'REMOVED'""")
    if not rows:
        print(f"Кампания «{NEW_NAME}» не найдена")
        return
    r = rows[0]
    c = r.campaign
    cid = c.id
    n = c.network_settings
    print(f"кампания {c.name} (id {cid}): статус {E.CampaignStatusEnum.CampaignStatus.Name(c.status)}, тип {E.AdvertisingChannelTypeEnum.AdvertisingChannelType.Name(c.advertising_channel_type)}, "
          f"ставки {E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(c.bidding_strategy_type)}, потолок клика {c.target_spend.cpc_bid_ceiling_micros / 1e6:g}")
    print(f"бюджет {r.campaign_budget.amount_micros / 1e6:g} (общий: {r.campaign_budget.explicitly_shared}); Merchant {c.shopping_setting.merchant_id}, "
          f"приоритет {c.shopping_setting.campaign_priority}, local {c.shopping_setting.enable_local}; сети: Google Search {n.target_google_search}, "
          f"партнёры {n.target_search_network}, контент {n.target_content_network}, партнёры-поиск {n.target_partner_search_network}")
    print("шаблон:", c.tracking_url_template[:110], "...")
    crit = {}
    for x in q(ga, f"SELECT campaign_criterion.type, campaign_criterion.negative FROM campaign_criterion WHERE campaign.id = {cid} AND campaign_criterion.status != 'REMOVED'"):
        k = (E.CriterionTypeEnum.CriterionType.Name(x.campaign_criterion.type_), "минус" if x.campaign_criterion.negative else "")
        crit[k] = crit.get(k, 0) + 1
    print("критерии кампании:", {f"{a} {b}".strip(): v for (a, b), v in crit.items()})
    for x in q(ga, f"SELECT shared_set.name, shared_set.member_count FROM campaign_shared_set WHERE campaign.id = {cid} AND campaign_shared_set.status = 'ENABLED'"):
        print(f"  общий список: {x.shared_set.name} — {x.shared_set.member_count}")
    for x in q(ga, f"SELECT ad_group.name, ad_group.status, ad_group.cpc_bid_micros FROM ad_group WHERE campaign.id = {cid}"):
        print(f"группа {x.ad_group.name}: статус {E.AdGroupStatusEnum.AdGroupStatus.Name(x.ad_group.status)}, ставка {x.ad_group.cpc_bid_micros / 1e6:g}")
    for x in q(ga, f"SELECT ad_group_ad.status, ad_group_ad.ad.type FROM ad_group_ad WHERE campaign.id = {cid}"):
        print("объявление:", E.AdTypeEnum.AdType.Name(x.ad_group_ad.ad.type_), E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(x.ad_group_ad.status))
    for x in q(ga, f"""SELECT ad_group_criterion.negative, ad_group_criterion.listing_group.type, ad_group_criterion.listing_group.case_value.product_type.value,
        ad_group_criterion.listing_group.case_value.product_type.level, ad_group_criterion.cpc_bid_micros FROM ad_group_criterion
        WHERE campaign.id = {cid} AND ad_group_criterion.type = LISTING_GROUP AND ad_group_criterion.status != 'REMOVED'"""):
        k = x.ad_group_criterion
        print("товарная группа:", E.ListingGroupTypeEnum.ListingGroupType.Name(k.listing_group.type_), "| тип товара:",
              repr(k.listing_group.case_value.product_type.value), "| исключена" if k.negative else "| включена", "| ставка", k.cpc_bid_micros / 1e6)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="Реально создать. Без флага — validate_only")
    ap.add_argument("--read-back-only", action="store_true")
    ap.add_argument("--budget", type=float, default=70.0, help="Дневной бюджет, zł")
    ap.add_argument("--cpc-ceiling", type=float, default=1.22, help="Потолок цены клика (Maximize clicks), zł")
    ap.add_argument("--stamp", default="2026-10-27", help="Дата файлов nosize_*.csv")
    args = ap.parse_args()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    if args.read_back_only:
        read_back(client, ga)
        return
    if q(ga, f"SELECT campaign.id FROM campaign WHERE campaign.name = '{NEW_NAME}' AND campaign.status != 'REMOVED'"):
        raise SystemExit(f"Кампания «{NEW_NAME}» уже существует — создание остановлено")
    sets = shared_sets(ga)
    missing = [n for n in ATTACH_EXISTING + [SIZES_SRC_LIST] if n not in sets]
    if missing:
        raise SystemExit(f"Не найдены общие списки: {missing}")
    for n in (NEW_LIST_JUNK, NEW_LIST_SIZES):
        if n in sets:
            raise SystemExit(f"Общий список «{n}» уже существует — создание остановлено")
    src = read_source(client, ga)
    junk, sizes, summary = build_lists(ga, sets, args.stamp)
    print("образец shop_search: Merchant", src["merchant_id"], "приоритет", src["priority"], "| гео", src["geo"], "| окон расписания", len(src["schedule"]),
          "| исключённых аудиторий", len(src["user_lists"]), "| минусов кампании", len(src["neg_kw"]))
    print("новые списки:", summary)
    ops = build_operations(client, src, sets, junk, sizes, args)
    print(f"операций в запросе: {len(ops)}; бюджет {args.budget:g} zł, потолок клика {args.cpc_ceiling:g} zł")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = CUSTOMER_ID
    req.mutate_operations.extend(ops)
    req.validate_only = not args.execute
    try:
        resp = client.get_service("GoogleAdsService").mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:12]:
            print("  -", err.message, "|", [str(p.field_name) + (f"[{p.index}]" if p.index else "") for p in err.location.field_path_elements][:5])
        raise SystemExit(1)
    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не создано (validate_only).")
        return
    for mr in resp.mutate_operation_responses:
        if mr.campaign_result.resource_name:
            print("создана кампания:", mr.campaign_result.resource_name)
    print("Создано на ПАУЗЕ. Дальше: --read-back-only.")


if __name__ == "__main__":
    main()
