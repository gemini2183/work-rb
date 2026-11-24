#!/usr/bin/env python
# coding: utf-8
"""Общий сборщик многогруппового Demand Gen с мультиассет-картинками (Google Ads API), любой клиент.

Зачем: gads_demand_gen_builder.py зашит под dg_lookalike_test (имя, Польша, одна группа, карусель, группа ENABLED).
Здесь всё клиентское вынесено в файл плана (YAML или JSON): имя кампании, бюджет, стратегия, гео (список id) и режим гео,
языки, расписание, шаблон отслеживания, бизнес, логотип, картинки по форматам, и список групп (имя, статус, каналы,
оптимизированный таргетинг, включаемые и исключаемые аудитории, тексты, кнопка, свои картинки). Привязок к клиенту в коде нет.

Что делает ОДНОЙ транзакцией (GoogleAdsService.mutate): бюджет, кампания (ВСЕГДА PAUSED; Maximize conversions или сразу
TARGET_CPA - решает файл плана), критерии гео/языка/расписания, и для каждой группы: группа (по умолчанию PAUSED; каналы
через channel_controls; опт.таргетинг), Audience (включения: списки/look-alike, custom audience, интересы; исключения: списки),
привязка Audience, мультиассет-объявление (картинки 1.91:1 / 1:1 / 4:5, логотип, 1-5 заголовков, 1-5 описаний, кнопка).
Карусель не создаётся. Картинки-файлы грузятся ВНУТРИ той же транзакции (временные id): в validate_only Google их не сохраняет.

Что делает ОТДЕЛЬНЫМИ шагами (скрипт только печатает готовые команды): цели кампании (gads_set_campaign_goals.py) и, если
target_cpa_at_create: false, TARGET_CPA (gads_set_campaign_bidding.py --target-cpa, П-038: maximize_conversions.target_cpa_micros
Google отклоняет, пишется campaign.target_cpa). Сторож, Ringostat, GTM здесь не трогаются. Включение кампании - отдельно.

Maps: канал Maps в DemandGenSelectedChannels (google-ads v23) НЕТ, через API не задаётся. Если в группе channels.maps: true,
скрипт его пропускает и печатает «Maps вручную»; наличие поля `maps` в установленной версии библиотеки проверяется на лету.

Режимы:
  без флагов          - validate_only: Google проверяет запрос, ничего не создаёт. Картинки-файлы НЕ отправляются: вместо
                        них подставляются существующие ассеты аккаунта из placeholder_assets (как в прежних сборщиках);
                        печатается «было -> станет», контроль числа IMAGE-ассетов до/после (должно совпасть);
  --validate-images   - то же, но настоящие картинки и логотип-файл уходят в validate_only-запрос (проверка размеров и
                        форматов Google). Ассеты при validate_only не создаются; флаг отделён, чтобы это было явным решением;
  --execute           - запись (кампания на ПАУЗЕ, группы по плану); запрещён при заглушках TODO и при кампании с тем же
                        именем; после записи состояние читается обратно;
  --read-back-only    - только чтение созданного (кампания, критерии, группы, каналы, Audience, объявления, policy_summary):
                        по --campaign-id или по имени из плана. Для кампаний на паузе (закрывает часть П-031).
Ключи API берутся из gads_stats.GOOGLE_ADS_YAML, в вывод не печатаются. Операции пишутся в журнал gads_quota_ledger.

Файл плана (ключи): campaign_name, budget_per_day, bidding {strategy: MAXIMIZE_CONVERSIONS|TARGET_CPA, target_cpa, target_cpa_at_create},
geo_ids [..], geo_exclude_ids [..], geo_mode PRESENCE|PRESENCE_OR_INTEREST, languages [..], schedule ([{days:[MON..], start:"9:00", end:"17:00"}] или null),
final_url, utm_campaign (по умолч. campaign_name), tracking_template (необяз.), business_name, logo_asset_id | logo_file,
images {landscape|square|portrait: [путь к файлу или id существующего ассета]}, placeholder_assets {landscape|square|portrait: [id], logo: id},
groups [{name, status, channels {discover, gmail, display, youtube_in_stream, youtube_in_feed, youtube_shorts, maps},
optimized_targeting, include {user_lists, custom_audiences, user_interests}, exclude {user_lists}, headlines, descriptions,
cta, ad_name, final_url, images}], goals {on: [КАТЕГОРИЯ:ИСТОЧНИК..], off: [..]}, snapshot_dir.
Пример: Клиенты/ProfiMet/Работы/2026-11-24_dg_montaz/файлы/dg_montaz_config.yaml

Использование (из папки Скрипты):
    python gads_dg_image_builder.py --customer-id <ID> --config <план.yaml>                    # проверка (validate_only)
    python gads_dg_image_builder.py --customer-id <ID> --config <план.yaml> --validate-images  # проверка с настоящими картинками
    python gads_dg_image_builder.py --customer-id <ID> --config <план.yaml> --execute          # запись (на паузе)
    python gads_dg_image_builder.py --customer-id <ID> --config <план.yaml> --read-back-only [--campaign-id <id>]

Дата создания: 2026-11-24.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Общие функции из gads_dg_yt_builder.py (не менять тот файл): конфиг, расписание, заглушки, поиск кампании
from gads_dg_yt_builder import (TRACK_TAIL, find_campaign, is_todo, load_config,
                                schedule_rows)

SCRIPT = "gads_dg_image_builder"
ORIENT = {  # формат -> (поле объявления, ширина:высота, допуск)
    "landscape": ("marketing_images", 1.91, 0.06),
    "square": ("square_marketing_images", 1.0, 0.02),
    "portrait": ("portrait_marketing_images", 0.8, 0.02),
}
CHANNEL_KEYS = ("discover", "gmail", "display", "youtube_in_stream", "youtube_in_feed", "youtube_shorts")
LIM_HEAD, LIM_DESC, LIM_BIZ = 30, 90, 25
MIN_NUM = {"ZERO": 0, "FIFTEEN": 15, "THIRTY": 30, "FORTY_FIVE": 45}


def resolve_path(base, p):
    p = Path(str(p))
    if p.is_absolute():
        return p
    for b in (base, Path(__file__).resolve().parent.parent):
        if (b / p).exists():
            return b / p
    return base / p


def is_asset_id(x):
    return isinstance(x, int) or (isinstance(x, str) and x.strip().isdigit())


def group_images(cfg, grp):
    return grp.get("images") or cfg.get("images") or {}


def find_todos(cfg):
    todos = []
    if is_todo(cfg.get("business_name")):
        todos.append("business_name")
    if is_todo(cfg.get("logo_asset_id")) and is_todo(cfg.get("logo_file")):
        todos.append("logo_asset_id / logo_file")
    for i, g in enumerate(cfg.get("groups") or []):
        for key in ("headlines", "descriptions"):
            vals = g.get(key) or []
            if not vals or any(is_todo(x) for x in vals):
                todos.append(f"groups[{i}].{key}")
        if is_todo(g.get("cta")):
            todos.append(f"groups[{i}].cta")
        inc = g.get("include") or {}
        if not any(inc.get(k) for k in ("user_lists", "custom_audiences", "user_interests")):
            todos.append(f"groups[{i}].include")
    return todos


def validate_config(cfg, base):
    for key in ("campaign_name", "budget_per_day", "final_url", "business_name", "geo_ids", "languages", "groups"):
        if key not in cfg:
            raise SystemExit(f"в плане нет обязательного ключа: {key}")
    if not cfg["groups"]:
        raise SystemExit("в плане нет групп")
    if cfg.get("geo_mode", "PRESENCE") not in ("PRESENCE", "PRESENCE_OR_INTEREST"):
        raise SystemExit("geo_mode: PRESENCE или PRESENCE_OR_INTEREST")
    bid = cfg.get("bidding") or {"strategy": "MAXIMIZE_CONVERSIONS"}
    if bid.get("strategy") not in ("MAXIMIZE_CONVERSIONS", "TARGET_CPA"):
        raise SystemExit("bidding.strategy: MAXIMIZE_CONVERSIONS или TARGET_CPA")
    if bid.get("strategy") == "TARGET_CPA" and not bid.get("target_cpa"):
        raise SystemExit("bidding.strategy TARGET_CPA требует target_cpa")
    if not is_todo(cfg["business_name"]):
        assert len(cfg["business_name"]) <= LIM_BIZ, f"имя бизнеса > {LIM_BIZ}"
    names = [g.get("name") for g in cfg["groups"]]
    assert all(names) and len(set(names)) == len(names), "у групп должны быть уникальные имена"
    for g in cfg["groups"]:
        assert all(len(h) <= LIM_HEAD for h in g.get("headlines") or [] if not is_todo(h)), f"{g['name']}: заголовок > {LIM_HEAD}"
        assert all(len(d) <= LIM_DESC for d in g.get("descriptions") or [] if not is_todo(d)), f"{g['name']}: описание > {LIM_DESC}"
        assert len(g.get("headlines") or []) <= 5 and len(g.get("descriptions") or []) <= 5, f"{g['name']}: макс. 5 заголовков и 5 описаний"
        if g.get("status", "PAUSED") not in ("PAUSED", "ENABLED"):
            raise SystemExit(f"{g['name']}: status PAUSED или ENABLED")
        ch = g.get("channels") or {}
        if not any(ch.get(k) for k in CHANNEL_KEYS):
            raise SystemExit(f"{g['name']}: не включён ни один канал (кроме Maps, его API не умеет)")
        imgs = group_images(cfg, g)
        if not (imgs.get("landscape") or imgs.get("square")):
            raise SystemExit(f"{g['name']}: нужна хотя бы одна картинка landscape или square")
    schedule_rows(cfg)
    # размеры и форматы файлов (до обращения к API)
    seen = set()
    for g in cfg["groups"]:
        for kind, items in group_images(cfg, g).items():
            if kind not in ORIENT:
                raise SystemExit(f"images: неизвестный формат {kind} (landscape/square/portrait)")
            for it in items or []:
                if is_asset_id(it) or str(it) in seen:
                    continue
                seen.add(str(it))
                check_image_file(resolve_path(base, it), kind)
    if not is_todo(cfg.get("logo_file")) and is_todo(cfg.get("logo_asset_id")):
        check_image_file(resolve_path(base, cfg["logo_file"]), "square", logo=True)


def check_image_file(path, kind, logo=False):
    assert path.exists(), f"нет файла {path}"
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(path) as im:
        w, h = im.size
    _, ratio, tol = ORIENT[kind]
    assert abs(w / h - ratio) <= tol, f"{path.name}: {w}x{h} не {kind} (нужно ~{ratio}:1)"
    if logo and w < 128:
        print(f"ПРЕДУПРЕЖДЕНИЕ: логотип {path.name} {w}x{h}: меньше 128 px, Google может отклонить")
    elif logo and w < 1200:
        print(f"предупреждение: логотип {path.name} {w}x{h} ниже рекомендуемых 1200x1200")


def maps_supported(client):
    """Есть ли поле maps у DemandGenSelectedChannels в установленной версии библиотеки (проверка на лету)."""
    ag = client.get_type("AdGroup")
    sc = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
    return "maps" in sc.DESCRIPTOR.fields_by_name


def tracking_template(cfg):
    if not is_todo(cfg.get("tracking_template")):
        return cfg["tracking_template"]
    utm = cfg.get("utm_campaign") or cfg["campaign_name"]
    return ("{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + utm +
            "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}" + TRACK_TAIL + "&utm_term={keyword}")


def count_images(ga, cid):
    return sum(1 for _ in ga.search(customer_id=cid, query="SELECT asset.id FROM asset WHERE asset.type = IMAGE"))


def pick_placeholders(cfg, kind, n):
    ph = (cfg.get("placeholder_assets") or {}).get(kind) or []
    if not ph:
        raise SystemExit(f"для validate_only без --validate-images нужен placeholder_assets.{kind} (существующие ассеты аккаунта)")
    return ph[:n]


def print_plan(cfg, cid, base, todos, client=None):
    bid = cfg.get("bidding") or {"strategy": "MAXIMIZE_CONVERSIONS"}
    rows = schedule_rows(cfg)
    print(f"=== План (аккаунт {cid}): было - кампании нет -> станет ===")
    print(f"кампания: {cfg['campaign_name']} | Demand Gen | ПАУЗА | бюджет в день {cfg['budget_per_day']} (валюта аккаунта)")
    tc = bid.get("target_cpa")
    if bid["strategy"] == "TARGET_CPA" and bid.get("target_cpa_at_create", True):
        print(f"стратегия: TARGET_CPA {tc} сразу при создании (принимает ли API - покажет validate_only)")
    elif bid["strategy"] == "TARGET_CPA":
        print(f"стратегия: при создании Maximize conversions без цели, затем отдельным шагом TARGET_CPA {tc} (П-038)")
    else:
        print("стратегия: Maximize conversions без цели CPA")
    print(f"гео: {cfg['geo_ids']} (режим {cfg.get('geo_mode', 'PRESENCE')}); исключить гео: {cfg.get('geo_exclude_ids') or []}; языки: {cfg['languages']}")
    print("расписание:", "без расписания" if not rows else "; ".join(f"{d} {sh}:{MIN_NUM[sm]:02d}-{eh}:{MIN_NUM[em]:02d}" for d, sh, sm, eh, em in rows))
    print(f"посадочная: {cfg['final_url']} | бизнес: {cfg['business_name']} | utm_campaign: {cfg.get('utm_campaign') or cfg['campaign_name']}")
    logo = cfg.get("logo_asset_id") if not is_todo(cfg.get("logo_asset_id")) else f"файл {cfg.get('logo_file')}"
    print(f"логотип: {logo}")
    maps_req = False
    for g in cfg["groups"]:
        ch = g.get("channels") or {}
        on = [k for k in CHANNEL_KEYS if ch.get(k)]
        inc, exc = g.get("include") or {}, g.get("exclude") or {}
        print(f"группа «{g['name']}» ({g.get('status', 'PAUSED')}): каналы {on}; опт.таргетинг {'ВКЛ' if g.get('optimized_targeting') else 'выкл'}; кнопка {g.get('cta')}")
        print(f"   включить: списки {inc.get('user_lists') or []}, custom_audience {inc.get('custom_audiences') or []}, интересы {inc.get('user_interests') or []}")
        print(f"   исключить списки: {exc.get('user_lists') or []}")
        print(f"   тексты: заголовков {len(g.get('headlines') or [])}, описаний {len(g.get('descriptions') or [])}")
        imgs = group_images(cfg, g)
        print("   картинки: " + ", ".join(f"{k} {len(imgs.get(k) or [])}" for k in ORIENT))
        maps_req = maps_req or bool(ch.get("maps"))
    if client is not None:
        has_maps = maps_supported(client)
        if maps_req or not has_maps:
            print(("Maps вручную: " if not has_maps else "") +
                  ("в установленной google-ads у DemandGenSelectedChannels нет поля maps - канал Maps через API не задаётся; "
                   "включить в интерфейсе после создания (в API-чтении не виден)." if not has_maps else
                   "поле maps в библиотеке есть, но скрипт его не задаёт - проверить и добавить."))
    elif maps_req:
        print("Maps вручную: канал Maps через API не задаётся (v23).")
    if todos:
        print("ЗАГЛУШКИ TODO в плане:", ", ".join(todos))


def build_operations(client, cid, cfg, base, upload_images):
    """upload_images=True: файлы-картинки и логотип создаются в этой же транзакции (временные id).
    False: подставляются placeholder_assets (существующие ассеты аккаунта)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    E = client.enums
    name = cfg["campaign_name"]
    bid = cfg.get("bidding") or {"strategy": "MAXIMIZE_CONVERSIONS"}
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ops = []
    counter = [10]

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    def tmp(kind):
        counter[0] += 1
        return f"customers/{cid}/{kind}/-{counter[0]}"

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{name} budget {ts}"
    b.amount_micros = int(round(float(cfg["budget_per_day"]) * 1_000_000))
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = name
    c.status = E.CampaignStatusEnum.PAUSED  # всегда пауза; включение - отдельное согласование
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.DEMAND_GEN
    c.campaign_budget = budget_rn
    if bid["strategy"] == "TARGET_CPA" and bid.get("target_cpa_at_create", True):
        c.target_cpa.target_cpa_micros = int(round(float(bid["target_cpa"]) * 1_000_000))
    else:
        c.maximize_conversions.SetInParent()
    c.demand_gen_campaign_settings.upgraded_targeting = bool(cfg.get("upgraded_targeting", False))
    c.geo_target_type_setting.positive_geo_target_type = getattr(E.PositiveGeoTargetTypeEnum, cfg.get("geo_mode", "PRESENCE"))
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = tracking_template(cfg)

    for geo in cfg["geo_ids"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = f"geoTargetConstants/{geo}"
    for geo in cfg.get("geo_exclude_ids") or []:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.location.geo_target_constant = f"geoTargetConstants/{geo}"
    for lang in cfg["languages"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = f"languageConstants/{lang}"
    for d, sh, sm, eh, em in schedule_rows(cfg):
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = getattr(E.DayOfWeekEnum, d)
        cc.ad_schedule.start_hour = sh
        cc.ad_schedule.start_minute = getattr(E.MinuteOfHourEnum, sm)
        cc.ad_schedule.end_hour = eh
        cc.ad_schedule.end_minute = getattr(E.MinuteOfHourEnum, em)

    # --- ассеты-картинки: один файл = один ассет на весь план
    file_rn = {}

    def image_rn(kind, item, idx):
        if is_asset_id(item):
            return f"customers/{cid}/assets/{int(item)}"
        key = str(item)
        if key not in file_rn:
            rn = tmp("assets")
            a = new_op().asset_operation.create
            a.resource_name = rn
            a.name = f"{name}_{Path(key).stem}_{ts}"
            a.image_asset.data = resolve_path(base, key).read_bytes()
            file_rn[key] = rn
        return file_rn[key]

    if not is_todo(cfg.get("logo_asset_id")):
        logo_rn = f"customers/{cid}/assets/{int(cfg['logo_asset_id'])}"
    elif upload_images:
        logo_rn = tmp("assets")
        a = new_op().asset_operation.create
        a.resource_name = logo_rn
        a.name = f"{name}_logo_{ts}"
        a.image_asset.data = resolve_path(base, cfg["logo_file"]).read_bytes()
    else:
        ph = (cfg.get("placeholder_assets") or {}).get("logo")
        if is_todo(ph):
            raise SystemExit("для проверки с logo_file без --validate-images нужен placeholder_assets.logo")
        logo_rn = f"customers/{cid}/assets/{int(ph)}"

    if upload_images:  # ассеты создаются раньше объявлений: порядок операций в транзакции важен
        for g in cfg["groups"]:
            for kind, items in group_images(cfg, g).items():
                for i, it in enumerate(items or []):
                    image_rn(kind, it, i)

    for gi, g in enumerate(cfg["groups"]):
        ag_rn = tmp("adGroups")
        aud_rn = tmp("audiences")
        ag = new_op().ad_group_operation.create
        ag.resource_name = ag_rn
        ag.name = g["name"]
        ag.campaign = campaign_rn
        ag.status = getattr(E.AdGroupStatusEnum, g.get("status", "PAUSED"))
        ag.optimized_targeting_enabled = bool(g.get("optimized_targeting", False))
        ch = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
        gch = g.get("channels") or {}
        for k in CHANNEL_KEYS:
            setattr(ch, k, bool(gch.get(k, False)))

        inc, exc = g.get("include") or {}, g.get("exclude") or {}
        au = new_op().audience_operation.create
        au.resource_name = aud_rn
        au.name = f"{name} {g['name']} {ts}"
        au.description = g.get("audience_description") or f"{name} / {g['name']}: включения и исключения из плана"
        dim = au.dimensions.add()
        for ul in inc.get("user_lists") or []:
            dim.audience_segments.segments.add().user_list.user_list = f"customers/{cid}/userLists/{ul}"
        for ca in inc.get("custom_audiences") or []:
            dim.audience_segments.segments.add().custom_audience.custom_audience = f"customers/{cid}/customAudiences/{ca}"
        for ui in inc.get("user_interests") or []:
            dim.audience_segments.segments.add().user_interest.user_interest_category = f"customers/{cid}/userInterests/{ui}"
        for ul in exc.get("user_lists") or []:
            au.exclusion_dimension.exclusions.add().user_list.user_list = f"customers/{cid}/userLists/{ul}"
        agc = new_op().ad_group_criterion_operation.create
        agc.ad_group = ag_rn
        agc.audience.audience = aud_rn

        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ag_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.name = g.get("ad_name") or f"{name} {g['name']} multi asset"
        aga.ad.final_urls.append(g.get("final_url") or cfg["final_url"])
        m = aga.ad.demand_gen_multi_asset_ad
        m.business_name = cfg["business_name"]
        m.call_to_action_text = g["cta"]
        for t in g["headlines"]:
            m.headlines.add().text = t
        for t in g["descriptions"]:
            m.descriptions.add().text = t
        imgs = group_images(cfg, g)
        for kind, (field, _, _) in ORIENT.items():
            items = imgs.get(kind) or []
            if not upload_images:  # проверка без загрузки: существующие ассеты аккаунта вместо файлов
                files = [x for x in items if not is_asset_id(x)]
                ids = [x for x in items if is_asset_id(x)]
                items = ids + pick_placeholders(cfg, kind, len(files)) if files else ids
            seen_rn = set()
            for i, it in enumerate(items):
                rn = image_rn(kind, it, i)
                if rn in seen_rn:
                    continue
                seen_rn.add(rn)
                getattr(m, field).add().asset = rn
        m.logo_images.add().asset = logo_rn
    return ops


def next_steps(cfg, cid):
    bid = cfg.get("bidding") or {}
    goals = cfg.get("goals") or {}
    print("\n=== Дальше отдельными шагами (скрипт их не выполняет; после создания подставить id кампании) ===")
    if goals.get("on") or goals.get("off"):
        snap = f' --snapshot-dir "{cfg["snapshot_dir"]}"' if cfg.get("snapshot_dir") else ""
        print(f"цели:      python gads_set_campaign_goals.py --customer-id {cid} --campaign-id <ID> "
              f"--on {' '.join(goals.get('on') or [])} --off {' '.join(goals.get('off') or [])}{snap}")
    if bid.get("strategy") == "TARGET_CPA" and not bid.get("target_cpa_at_create", True):
        cf = f" --client-folder {cfg['client_folder']}" if cfg.get("client_folder") else ""
        print(f"стратегия: python gads_set_campaign_bidding.py --customer-id {cid}{cf} --campaign-id <ID> "
              f"--strategy MAXIMIZE_CONVERSIONS --target-cpa {bid['target_cpa']}")
    print("Maps:      включить вручную в интерфейсе, если нужен (API не умеет).")
    print("включение: отдельным согласованием (gads_set_campaign_status.py и включение групп); сторож и Ringostat - вне скрипта.")


def read_back(client, cid, campaign_id):
    from gads_quota_ledger import wrap_ga
    ga = wrap_ga(client.get_service("GoogleAdsService"), SCRIPT)
    E = client.enums
    print("\n=== Чтение из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, campaign.bidding_strategy_type, "
            "campaign.target_cpa.target_cpa_micros, campaign.geo_target_type_setting.positive_geo_target_type, "
            "campaign.tracking_url_template, campaign_budget.amount_micros FROM campaign "
            f"WHERE campaign.id = {campaign_id}")):
        c = r.campaign
        print(f"кампания {c.id} | {c.name} | {E.CampaignStatusEnum.CampaignStatus.Name(c.status)} | "
              f"{E.AdvertisingChannelTypeEnum.AdvertisingChannelType.Name(c.advertising_channel_type)} | "
              f"{E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(c.bidding_strategy_type)} "
              f"tCPA {c.target_cpa.target_cpa_micros / 1e6:g} | бюджет в день {r.campaign_budget.amount_micros / 1e6:g} | "
              f"гео-режим {E.PositiveGeoTargetTypeEnum.PositiveGeoTargetType.Name(c.geo_target_type_setting.positive_geo_target_type)}")
        print(f"шаблон отслеживания: {c.tracking_url_template[:140]}")
    loc, lang, sched = [], [], 0
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.location.geo_target_constant, "
            "campaign_criterion.language.language_constant FROM campaign_criterion "
            f"WHERE campaign.id = {campaign_id}")):
        cr = r.campaign_criterion
        t = E.CriterionTypeEnum.CriterionType.Name(cr.type_)
        if t == "LOCATION":
            loc.append(("-" if cr.negative else "") + cr.location.geo_target_constant.split("/")[-1])
        elif t == "LANGUAGE":
            lang.append(cr.language.language_constant.split("/")[-1])
        elif t == "AD_SCHEDULE":
            sched += 1
    print(f"гео: {loc} | языки: {lang} | строк расписания: {sched}")
    groups = []
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.optimized_targeting_enabled FROM ad_group "
            f"WHERE campaign.id = {campaign_id}")):
        groups.append(r.ad_group.id)
        print(f"группа {r.ad_group.id} | {r.ad_group.name} | {E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status)} | "
              f"опт.таргетинг {r.ad_group.optimized_targeting_enabled}")
    try:  # каналы: поля вложенные; если GAQL их не отдаёт - сказать прямо
        q = ("SELECT ad_group.id, ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.discover, "
             "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.gmail, "
             "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.display, "
             "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_in_stream, "
             "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_in_feed, "
             "ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels.youtube_shorts FROM ad_group "
             f"WHERE campaign.id = {campaign_id}")
        for r in ga.search(customer_id=cid, query=q):
            s = r.ad_group.demand_gen_ad_group_settings.channel_controls.selected_channels
            print(f"   каналы группы {r.ad_group.id}: discover {s.discover}, gmail {s.gmail}, display {s.display}, "
                  f"yt_in_stream {s.youtube_in_stream}, yt_in_feed {s.youtube_in_feed}, yt_shorts {s.youtube_shorts} (Maps через API не читается)")
    except Exception as ex:  # noqa: BLE001
        print(f"   каналы группы GAQL не отдал: {str(ex)[:160]}")
    try:
        for r in ga.search(customer_id=cid, query=(
                "SELECT ad_group.id, ad_group_criterion.audience.audience FROM ad_group_criterion "
                f"WHERE campaign.id = {campaign_id} AND ad_group_criterion.type = AUDIENCE")):
            aud = r.ad_group_criterion.audience.audience
            for a in ga.search(customer_id=cid, query=(
                    "SELECT audience.id, audience.name, audience.dimensions, audience.exclusion_dimension FROM audience "
                    f"WHERE audience.resource_name = '{aud}'")):
                inc = [s.user_list.user_list.split("/")[-1] for d in a.audience.dimensions
                       for s in d.audience_segments.segments if s.user_list.user_list]
                inc_o = [("custom", s.custom_audience.custom_audience.split("/")[-1]) for d in a.audience.dimensions
                         for s in d.audience_segments.segments if s.custom_audience.custom_audience]
                exc = [e.user_list.user_list.split("/")[-1] for e in a.audience.exclusion_dimension.exclusions if e.user_list.user_list]
                print(f"   Audience {a.audience.id} группы {r.ad_group.id}: {a.audience.name} | включено списков {inc} {inc_o} | исключено {exc}")
    except Exception as ex:  # noqa: BLE001
        print(f"   состав Audience не прочитан: {str(ex)[:160]}")
    n = 0
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.id, ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status, "
            "ad_group_ad.policy_summary.approval_status, ad_group_ad.policy_summary.review_status, "
            "ad_group_ad.ad.demand_gen_multi_asset_ad.call_to_action_text FROM ad_group_ad "
            f"WHERE campaign.id = {campaign_id}")):
        n += 1
        a = r.ad_group_ad
        print(f"объявление {a.ad.id} (группа {r.ad_group.id}) | {a.ad.name} | {E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(a.status)} | "
              f"{E.PolicyApprovalStatusEnum.PolicyApprovalStatus.Name(a.policy_summary.approval_status)} / "
              f"{E.PolicyReviewStatusEnum.PolicyReviewStatus.Name(a.policy_summary.review_status)} | "
              f"кнопка «{a.ad.demand_gen_multi_asset_ad.call_to_action_text}»")
    print("объявлений:", n)


def main():
    ap = argparse.ArgumentParser(description="Общий сборщик многогруппового Demand Gen на картинках (кампания на паузе); запись только с --execute")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--config", required=True, help="файл плана YAML/JSON (ключи в шапке скрипта)")
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага - validate_only")
    ap.add_argument("--validate-images", action="store_true",
                    help="в validate_only отправить настоящие картинки/логотип (Google их не сохраняет; по умолчанию подставляются существующие ассеты)")
    ap.add_argument("--read-back-only", action="store_true", help="только прочитать созданное (по --campaign-id или имени из плана)")
    ap.add_argument("--campaign-id", help="для --read-back-only: id кампании (иначе по имени из плана)")
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    base = config_path.parent
    cfg = load_config(config_path)
    cid = args.customer_id.replace("-", "").strip()

    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    from gads_stats import GOOGLE_ADS_YAML
    from gads_quota_ledger import record_mutate, wrap_ga

    if args.read_back_only:
        client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
        camp = args.campaign_id
        if not camp:
            ex = find_campaign(client, cid, cfg["campaign_name"])
            if not ex:
                raise SystemExit(f"кампании «{cfg['campaign_name']}» в аккаунте нет")
            camp = ex[0][0]
        read_back(client, cid, camp)
        return

    validate_config(cfg, base)
    todos = find_todos(cfg)
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    print_plan(cfg, cid, base, todos, client)
    next_steps(cfg, cid)

    if todos:
        if args.execute:
            raise SystemExit("--execute запрещён: в плане заглушки TODO (" + ", ".join(todos) + ").")
        print("\nЗаглушки не позволяют проверить запрос в Google, API записи не вызывался. План корректен по формату.")
        return

    upload = args.execute or args.validate_images
    before = None
    ga = None
    try:
        ga = wrap_ga(client.get_service("GoogleAdsService"), SCRIPT)
        exist = find_campaign(client, cid, cfg["campaign_name"])
        if exist:
            print("\nБыло: кампания с таким именем уже есть:", exist)
            raise SystemExit("остановлено: имя занято (дубль не создаю; для чтения - --read-back-only).")
        print(f"\nБыло: кампании «{cfg['campaign_name']}» нет -> станет: создана на ПАУЗЕ (после --execute).")
        before = count_images(ga, cid)
        print(f"контроль: IMAGE-ассетов в аккаунте до запроса: {before}")
        if args.validate_images and not args.execute:
            print("ВНИМАНИЕ: --validate-images: картинки отправляются в validate_only-запрос; Google их не сохраняет, число ассетов проверю после.")
        elif not args.execute:
            print("Картинки-файлы в запрос НЕ отправляются (подставлены существующие ассеты аккаунта из placeholder_assets).")
        ops = build_operations(client, cid, cfg, base, upload)
        request = client.get_type("MutateGoogleAdsRequest")
        request.customer_id = cid
        request.mutate_operations.extend(ops)
        request.validate_only = not args.execute
        record_mutate(SCRIPT, len(ops), validate_only=not args.execute)
        response = client.get_service("GoogleAdsService").mutate(request=request)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads (validate_only: ничего не создано)" if not args.execute else "ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        if not args.execute and before is not None:
            after = count_images(ga, cid)
            print(f"контроль: IMAGE-ассетов после запроса: {after} ({'совпало' if after == before else 'ИЗМЕНИЛОСЬ - сообщить'})")
        raise SystemExit(1)

    if not args.execute:
        after = count_images(ga, cid)
        print(f"Проверка пройдена ({len(ops)} операций). НИЧЕГО не создано (validate_only).")
        print(f"контроль: IMAGE-ассетов после запроса: {after} ({'совпало' if after == before else 'ИЗМЕНИЛОСЬ - СООБЩИТЬ'})")
        return
    print("Создано (кампания на паузе):")
    camp_id = None
    for r in response.mutate_operation_responses:
        kind = r.WhichOneof("response")
        rn = getattr(r, kind).resource_name
        print(" ", kind, rn)
        if kind == "campaign_result":
            camp_id = rn.split("/")[-1]
    if camp_id:
        read_back(client, cid, camp_id)


if __name__ == "__main__":
    main()
