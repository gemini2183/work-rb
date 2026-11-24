#!/usr/bin/env python
# coding: utf-8
"""Общий сборщик Search-кампании Google Ads на ПАУЗЕ: всё из конфига (YAML/JSON) и аргументов.

Зачем: образцы `gads_search_ekspertagro_size_builder.py` и `gads_search_generic_builder.py` зашивают клиента, ID, группы,
ключи и тексты в константы. Здесь привязок к клиенту и кампании в коде нет: клиент, аккаунт, имя, бюджет, стратегия,
расписание, гео, языки, группы, ключи (тип совпадения), минус-слова, исключаемые аудитории, посадочная, UTM-суффикс,
сайтлинки/уточнения берутся из конфига; тексты RSA (с номерами и pin) - из отдельного файла (`rsa_texts_file`).
Функции сборки взяты из образцов (бюджет, кампания, критерии, группы, RSA, ассеты, чтение обратно).

Что создаёт одной транзакцией (GoogleAdsService.mutate): бюджет, кампанию (Search, ПАУЗА, AI Max и автоассеты текста
выключены, только поиск Google, партнёры и КМС выключены), гео/языки/расписание, исключения аудиторий, минус-слова,
группы с ключами и по одному RSA на группу, сайтлинки и уточнения (если заданы).

Стратегии (`strategy`): maximize_clicks (+ cpc_ceiling), manual_cpc (+ enhanced_cpc, у групп нужна ставка
`group_cpc_bid`), maximize_conversions (+ target_cpa, необязательно), target_cpa (обязателен target_cpa).
UTM - через `final_url_suffix` (как в образце: у URL каталога уже может быть `?`); `tracking_url_template` - по желанию.

Режимы:
  без флагов          validate_only: печатает план «было -> станет», Google проверяет запрос, ничего не создаётся
  --execute           запись (кампания всё равно на паузе); потом читает обратно из аккаунта
  --read-back-only    ничего не пишет, читает кампанию(и) с этим именем и печатает состояние
Перед записью проверяется, что кампании с таким именем (не REMOVED) нет: защита от дубля. Если чтение обратно
упало после записи, --execute повторно не запускать. Включение кампании - отдельный шаг, не здесь.

Формат конфига и файла текстов - см. пример: Клиенты/EkspertAgro/Работы/2026-11-23_бренд_search/brand_config.yaml.

Использование (из папки Скрипты):
    python gads_search_campaign_builder.py --config <brand_config.yaml>                 # проверка
    python gads_search_campaign_builder.py --config <brand_config.yaml> --execute       # запись, на паузе
    python gads_search_campaign_builder.py --config <brand_config.yaml> --read-back-only
    переопределения: --customer-id --campaign-name --budget --strategy --cpc-ceiling --texts
Дата: 2026-11-23.
"""
import argparse
import json
import os
import sys
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

LANG_CODES = {"pl": 1030, "en": 1000, "de": 1001, "ru": 1031, "uk": 1036, "cs": 1021, "sk": 1033, "lt": 1019}
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
DAY_ALIASES = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
STRATEGIES = ("maximize_clicks", "manual_cpc", "maximize_conversions", "target_cpa")
MATCHES = ("EXACT", "PHRASE", "BROAD")


# ------------------------------------------------------------------ конфиг
def load_file(path):
    with open(path, encoding="utf-8") as f:
        if path.lower().endswith(".json"):
            return json.load(f)
        import yaml
        return yaml.safe_load(f)


def expand_days(spec):
    """'MON-FRI' | 'SAT' | ['MON','TUE'] | 'MONDAY' -> список имён дней."""
    if isinstance(spec, (list, tuple)):
        out = []
        for s in spec:
            out += expand_days(s)
        return out
    s = str(spec).upper().strip()
    if "-" in s:
        a, b = [x.strip()[:3] for x in s.split("-")]
        return [DAYS[i] for i in range(DAY_ALIASES[a], DAY_ALIASES[b] + 1)]
    return [DAYS[DAY_ALIASES[s[:3]]]]


def norm_schedule(raw):
    """[{days: 'MON-FRI', start: 8, end: 18}, ...] -> [(DAY, start, end)]; пусто/None = без расписания."""
    out = []
    for r in raw or []:
        for d in expand_days(r["days"]):
            out.append((d, int(r["start"]), int(r["end"])))
    return out


def norm_languages(raw):
    out = []
    for x in raw or []:
        out.append(int(LANG_CODES[x.lower()]) if isinstance(x, str) and not x.isdigit() else int(x))
    return out


def norm_negatives(raw):
    """строка (фраза, если есть пробел, иначе broad) или {text, match}."""
    out = []
    for x in raw or []:
        if isinstance(x, dict):
            out.append((x["text"], str(x.get("match", "BROAD")).upper()))
        else:
            out.append((x, "PHRASE" if " " in x else "BROAD"))
    return out


def norm_group_keywords(g, default_matches):
    """keywords: [строки] + match_types (по умолчанию из кампании) ИЛИ keywords: {exact: [...], phrase: [...]}."""
    kws = g["keywords"]
    out = []
    if isinstance(kws, dict):
        for mt, lst in kws.items():
            for k in lst or []:
                out.append((k, mt.upper()))
    else:
        for mt in [m.upper() for m in g.get("match_types", default_matches)]:
            for k in kws:
                out.append((k, mt))
    return out


def load_texts(path):
    t = load_file(path)
    assert isinstance(t, dict) and ("default" in t or "groups" in t), "в файле текстов нужен раздел default или groups"
    return t


def norm_items(items):
    """['текст', {n: 1, text: '...', pin: 1}] -> [(text, pin|None)], порядок по n (если задан), иначе как в файле."""
    rows = []
    for i, it in enumerate(items or []):
        if isinstance(it, str):
            rows.append((10_000 + i, it, None))
        else:
            rows.append((int(it.get("n", 10_000 + i)), it["text"], it.get("pin")))
    rows.sort(key=lambda r: r[0])
    return [(t, p) for _, t, p in rows]


def group_texts(texts, gname):
    d = dict(texts.get("default", {}))
    d.update((texts.get("groups") or {}).get(gname, {}))
    return {"path1": d.get("path1", ""), "path2": d.get("path2", ""),
            "headlines": norm_items(d.get("headlines")), "descriptions": norm_items(d.get("descriptions"))}


def build_cfg(args):
    here = os.path.dirname(os.path.abspath(args.config))
    cfg = load_file(args.config)
    if args.customer_id:
        cfg["customer_id"] = args.customer_id
    if args.campaign_name:
        cfg["campaign_name"] = args.campaign_name
    if args.budget is not None:
        cfg["budget"] = args.budget
    if args.strategy:
        cfg["strategy"] = args.strategy
    if args.cpc_ceiling is not None:
        cfg["cpc_ceiling"] = args.cpc_ceiling
    tpath = args.texts or cfg.get("rsa_texts_file")
    if tpath and not os.path.isabs(tpath):
        tpath = os.path.join(here, tpath)
    cfg["_texts_path"] = tpath
    cfg["customer_id"] = str(cfg["customer_id"]).replace("-", "").strip()
    return cfg


# ------------------------------------------------------------------ проверки
def check_cfg(cfg, texts):
    assert cfg.get("campaign_name"), "campaign_name обязателен"
    assert cfg.get("strategy") in STRATEGIES, f"strategy: одно из {STRATEGIES}"
    assert float(cfg.get("budget", 0)) > 0, "budget (в день, валюта аккаунта) обязателен"
    st = cfg["strategy"]
    if st == "target_cpa":
        assert cfg.get("target_cpa"), "для target_cpa нужен target_cpa"
    if st == "manual_cpc":
        assert cfg.get("group_cpc_bid"), "для manual_cpc нужен group_cpc_bid (ставка группы)"
    assert cfg.get("landing_url"), "landing_url обязателен"
    assert cfg.get("groups"), "нужна хотя бы одна группа"
    blob = json.dumps(cfg, ensure_ascii=False, default=str).lower()
    assert "claude" not in blob, "слово claude в метках/названиях не допускается"
    assert texts, "нужен файл текстов RSA (rsa_texts_file или --texts)"
    for g in cfg["groups"]:
        assert g.get("name"), "у группы нет name"
        kws = norm_group_keywords(g, cfg.get("match_types", ["EXACT", "PHRASE"]))
        assert kws, f"группа {g['name']}: нет ключей"
        for k, mt in kws:
            assert len(k) <= 80 and mt in MATCHES, (k, mt)
        t = group_texts(texts, g["name"])
        assert 3 <= len(t["headlines"]) <= 15, f"{g['name']}: заголовков {len(t['headlines'])}, нужно 3-15"
        assert 2 <= len(t["descriptions"]) <= 4, f"{g['name']}: описаний {len(t['descriptions'])}, нужно 2-4"
        assert all(len(h) <= 30 for h, _ in t["headlines"]), f"{g['name']}: заголовок > 30"
        assert all(len(d) <= 90 for d, _ in t["descriptions"]), f"{g['name']}: описание > 90"
        assert len(t["path1"]) <= 15 and len(t["path2"]) <= 15
        assert all(p in (None, 1, 2, 3) for _, p in t["headlines"]), "pin заголовка: 1-3"
        assert all(p in (None, 1, 2) for _, p in t["descriptions"]), "pin описания: 1-2"
    for s in cfg.get("sitelinks") or []:
        assert len(s["text"]) <= 25 and len(s.get("d1", "")) <= 35 and len(s.get("d2", "")) <= 35, s
    assert all(len(x) <= 25 for x in cfg.get("callouts") or [])


def sched_str(sched):
    return "; ".join(f"{d[:3]} {a}-{b}" for d, a, b in sched) or "без расписания (круглосуточно)"


def print_plan(cfg, texts, existing):
    sched = norm_schedule(cfg.get("schedule"))
    print("=== План (было -> станет) ===")
    print(f"аккаунт: {cfg['customer_id']}")
    print(f"кампания «{cfg['campaign_name']}»: было {'ЕСТЬ id ' + str(existing) if existing else 'нет'} -> "
          f"{'повторно не создаётся (дубль)' if existing else 'новая, ПАУЗА'}")
    print(f"бюджет/день: {cfg['budget']} | стратегия: {cfg['strategy']}"
          f"{' | потолок клика ' + str(cfg['cpc_ceiling']) if cfg.get('cpc_ceiling') else ''}"
          f"{' | целевая цена ' + str(cfg['target_cpa']) if cfg.get('target_cpa') else ''}")
    print(f"гео: {cfg.get('geo', [2616])} | языки: {norm_languages(cfg.get('languages'))} | расписание: {sched_str(sched)}")
    print(f"исключаемые аудитории: {cfg.get('exclude_user_lists') or 'нет'} | минус-слов: {len(norm_negatives(cfg.get('negatives')))}")
    print(f"посадочная: {cfg['landing_url']} | суффикс UTM: {'задан' if cfg.get('final_url_suffix') else 'нет'}")
    for g in cfg["groups"]:
        kws = norm_group_keywords(g, cfg.get("match_types", ["EXACT", "PHRASE"]))
        t = group_texts(texts, g["name"])
        print(f"группа «{g['name']}»: ключей {len(kws)} ({', '.join(f'{k} [{m[0]}]' for k, m in kws)}) | "
              f"заголовков {len(t['headlines'])}, описаний {len(t['descriptions'])} | URL {g.get('url', cfg['landing_url'])}")
    print(f"сайтлинков {len(cfg.get('sitelinks') or [])}, уточнений {len(cfg.get('callouts') or [])}")
    print("партнёры/КМС: выкл | AI Max и автотексты: выкл | статус: PAUSED")


# ------------------------------------------------------------------ сборка
def campaign_ids(client, cid, name):
    ga = client.get_service("GoogleAdsService")
    safe = name.replace("'", "\\'")
    q = f"SELECT campaign.id FROM campaign WHERE campaign.name = '{safe}' AND campaign.status != 'REMOVED'"
    return [r.campaign.id for r in ga.search(customer_id=cid, query=q)]


def build_operations(client, cid, cfg, texts):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    E = client.enums
    name = cfg["campaign_name"]
    st = cfg["strategy"]
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{name} budget {ts}"
    b.amount_micros = int(float(cfg["budget"]) * 1_000_000)
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = name
    c.status = E.CampaignStatusEnum.PAUSED                       # всегда пауза
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.SEARCH
    c.campaign_budget = budget_rn
    if st == "maximize_clicks":
        if cfg.get("cpc_ceiling"):
            c.target_spend.cpc_bid_ceiling_micros = int(float(cfg["cpc_ceiling"]) * 1_000_000)
        else:
            c.target_spend.cpc_bid_ceiling_micros = 0
            c.target_spend.SetInParent()
    elif st == "manual_cpc":
        c.manual_cpc.enhanced_cpc_enabled = bool(cfg.get("enhanced_cpc", False))
    elif st == "maximize_conversions":
        if cfg.get("target_cpa"):
            c.maximize_conversions.target_cpa_micros = int(float(cfg["target_cpa"]) * 1_000_000)
        else:
            c.maximize_conversions.SetInParent()
    elif st == "target_cpa":
        c.target_cpa.target_cpa_micros = int(float(cfg["target_cpa"]) * 1_000_000)
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False             # партнёры выключены
    c.network_settings.target_content_network = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    if cfg.get("final_url_suffix"):
        c.final_url_suffix = cfg["final_url_suffix"]
    if cfg.get("tracking_url_template"):
        c.tracking_url_template = cfg["tracking_url_template"]
    c.ai_max_setting.enable_ai_max = False                       # AI Max выключен
    for t in (E.AssetAutomationTypeEnum.TEXT_ASSET_AUTOMATION,
              E.AssetAutomationTypeEnum.FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = t
        s.asset_automation_status = E.AssetAutomationStatusEnum.OPTED_OUT

    for geo in cfg.get("geo", [2616]):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = f"geoTargetConstants/{geo}"
    for lang in norm_languages(cfg.get("languages")):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = f"languageConstants/{lang}"
    for day, h1, h2 in norm_schedule(cfg.get("schedule")):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = getattr(E.DayOfWeekEnum, day)
        cc.ad_schedule.start_hour = h1
        cc.ad_schedule.start_minute = E.MinuteOfHourEnum.ZERO
        cc.ad_schedule.end_hour = h2
        cc.ad_schedule.end_minute = E.MinuteOfHourEnum.ZERO
    for ul in cfg.get("exclude_user_lists") or []:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.user_list.user_list = f"customers/{cid}/userLists/{ul}"
    for text, mt in norm_negatives(cfg.get("negatives")):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = getattr(E.KeywordMatchTypeEnum, mt)

    for i, g in enumerate(cfg["groups"], start=1):
        ag_rn = f"customers/{cid}/adGroups/-{10 + i}"
        ag = new_op().ad_group_operation.create
        ag.resource_name = ag_rn
        ag.name = g["name"]
        ag.campaign = campaign_rn
        ag.status = E.AdGroupStatusEnum.ENABLED
        ag.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
        if st == "manual_cpc":
            ag.cpc_bid_micros = int(float(g.get("cpc_bid", cfg["group_cpc_bid"])) * 1_000_000)
        for kw, mt in norm_group_keywords(g, cfg.get("match_types", ["EXACT", "PHRASE"])):
            agc = new_op().ad_group_criterion_operation.create
            agc.ad_group = ag_rn
            agc.status = E.AdGroupCriterionStatusEnum.ENABLED
            agc.keyword.text = kw
            agc.keyword.match_type = getattr(E.KeywordMatchTypeEnum, mt)

        t = group_texts(texts, g["name"])
        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.final_urls.append(g.get("url", cfg["landing_url"]))
        rsa = aga.ad.responsive_search_ad
        if t["path1"]:
            rsa.path1 = t["path1"]
        if t["path2"]:
            rsa.path2 = t["path2"]
        for text, pin in t["headlines"]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin:
                a.pinned_field = getattr(E.ServedAssetFieldTypeEnum, f"HEADLINE_{pin}")
            rsa.headlines.append(a)
        for text, pin in t["descriptions"]:
            a = client.get_type("AdTextAsset")
            a.text = text
            if pin:
                a.pinned_field = getattr(E.ServedAssetFieldTypeEnum, f"DESCRIPTION_{pin}")
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

    for s in cfg.get("sitelinks") or []:
        rn = new_asset_rn()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.final_urls.append(s["url"])
        a.sitelink_asset.link_text = s["text"]
        a.sitelink_asset.description1 = s.get("d1", "")
        a.sitelink_asset.description2 = s.get("d2", "")
        link(rn, E_.SITELINK)
    for text in cfg.get("callouts") or []:
        rn = new_asset_rn()
        a = new_op().asset_operation.create
        a.resource_name = rn
        a.callout_asset.callout_text = text
        link(rn, E_.CALLOUT)
    return ops


# ------------------------------------------------------------------ чтение обратно
def read_back(client, cid, campaign_id):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
            "campaign.target_spend.cpc_bid_ceiling_micros, campaign.manual_cpc.enhanced_cpc_enabled, "
            "campaign.ai_max_setting.enable_ai_max, "
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
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group.status, ad_group.cpc_bid_micros FROM ad_group "
            f"WHERE campaign.id = {campaign_id} AND ad_group.status != 'REMOVED'")):
        print("группа:", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status),
              f"ставка {r.ad_group.cpc_bid_micros / 1e6}")
    kws = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
            f"FROM ad_group_criterion WHERE campaign.id = {campaign_id} AND ad_group_criterion.type = KEYWORD "
            "AND ad_group_criterion.status != 'REMOVED'")):
        mt = E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.ad_group_criterion.keyword.match_type)
        kws.setdefault((r.ad_group.name, mt), []).append(r.ad_group_criterion.keyword.text)
    for (g, mt), lst in sorted(kws.items()):
        print(f"ключи {g} [{mt}] ({len(lst)}): {', '.join(lst)}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.name, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, "
            "ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad "
            f"WHERE campaign.id = {campaign_id} AND ad_group_ad.status != 'REMOVED'")):
        rsa = r.ad_group_ad.ad.responsive_search_ad
        print(f"объявление {r.ad_group.name}: URL {list(r.ad_group_ad.ad.final_urls)}")
        for lab, items in (("H", rsa.headlines), ("D", rsa.descriptions)):
            for i, h in enumerate(items, 1):
                pin = E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(h.pinned_field) if h.pinned_field else ""
                pin = "" if pin in ("", "UNSPECIFIED", "UNKNOWN") else f" <{pin}>"
                print(f"   {lab}{i:02d} [{len(h.text):2d}] {h.text}{pin}")
    sched, geo, lang, lists, negs = [], [], [], [], []
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.ad_schedule.day_of_week, "
            "campaign_criterion.ad_schedule.start_hour, campaign_criterion.ad_schedule.end_hour, "
            "campaign_criterion.location.geo_target_constant, campaign_criterion.language.language_constant, "
            "campaign_criterion.user_list.user_list, campaign_criterion.keyword.text, "
            "campaign_criterion.keyword.match_type FROM campaign_criterion "
            f"WHERE campaign.id = {campaign_id}")):
        cc = r.campaign_criterion
        t = E.CriterionTypeEnum.CriterionType.Name(cc.type_)
        if t == "AD_SCHEDULE":
            sched.append(f"{E.DayOfWeekEnum.DayOfWeek.Name(cc.ad_schedule.day_of_week)[:3]} "
                         f"{cc.ad_schedule.start_hour}-{cc.ad_schedule.end_hour}")
        elif t == "LOCATION":
            geo.append(cc.location.geo_target_constant)
        elif t == "LANGUAGE":
            lang.append(cc.language.language_constant)
        elif t == "USER_LIST":
            lists.append(("минус " if cc.negative else "плюс ") + cc.user_list.user_list)
        elif t == "KEYWORD" and cc.negative:
            negs.append(f"{cc.keyword.text} [{E.KeywordMatchTypeEnum.KeywordMatchType.Name(cc.keyword.match_type)[0]}]")
    print("расписание:", "; ".join(sched) or "нет")
    print("гео:", geo, "| языки:", lang)
    print("аудитории:", lists or "нет")
    print(f"минус-слова ({len(negs)}):", ", ".join(negs))
    assets = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign_asset.field_type, campaign_asset.status FROM campaign_asset "
            f"WHERE campaign.id = {campaign_id}")):
        key = (E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type),
               E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status))
        assets[key] = assets.get(key, 0) + 1
    print("ассеты кампании (тип, статус):", assets)


def main():
    ap = argparse.ArgumentParser(description="Общий сборщик Search-кампании на паузе (конфиг YAML/JSON). "
                                             "По умолчанию validate_only; запись только с --execute.")
    ap.add_argument("--config", required=True, help="YAML/JSON конфиг кампании")
    ap.add_argument("--texts", help="файл текстов RSA (иначе rsa_texts_file из конфига)")
    ap.add_argument("--customer-id", help="переопределяет customer_id конфига")
    ap.add_argument("--campaign-name", help="переопределяет campaign_name")
    ap.add_argument("--budget", type=float, help="дневной бюджет, валюта аккаунта")
    ap.add_argument("--strategy", choices=STRATEGIES)
    ap.add_argument("--cpc-ceiling", type=float, help="потолок цены клика для maximize_clicks")
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты (на паузе). Без флага - validate_only")
    ap.add_argument("--read-back-only", action="store_true", help="Ничего не создавать, прочитать кампанию по имени")
    args = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    cfg = build_cfg(args)
    cid = cfg["customer_id"]
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    existing = campaign_ids(client, cid, cfg["campaign_name"])
    if args.read_back_only:
        print(f"кампаний «{cfg['campaign_name']}» в аккаунте {cid}: {existing or 'нет'}")
        for camp_id in existing:
            read_back(client, cid, camp_id)
        return

    texts = load_texts(cfg["_texts_path"]) if cfg.get("_texts_path") else None
    check_cfg(cfg, texts)
    print_plan(cfg, texts, existing)
    if existing and args.execute:
        print(f"СТОП: кампания «{cfg['campaign_name']}» уже есть (id {existing}). Повторная запись создала бы дубль.")
        raise SystemExit(1)
    try:
        service = client.get_service("GoogleAdsService")
        ops = build_operations(client, cid, cfg, texts)
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
