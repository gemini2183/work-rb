#!/usr/bin/env python
# coding: utf-8
"""Общий сборщик кампании Demand Gen «только YouTube, холодный тест» для любого клиента (Google Ads API).

Зачем: одна и та же кампания (Demand Gen, YouTube in-stream / in-feed / Shorts, оптимизированный таргетинг выключен,
Maximize conversions без цели по CPA, ПАУЗА) нужна разным клиентам. Логика взята из gads_demand_gen_yt_cold_builder.py
(ProfiMet; тот файл не менять), но всё клиентское вынесено в YAML-конфиг.

Что делает (одной транзакцией MutateGoogleAdsService.mutate): бюджет, кампания (ПАУЗА), гео и языки, расписание (если задано),
группа объявлений (каналы только YouTube; Discover, Gmail, Display выключены), аудитория (включения трёх видов:
списки пользователей / look-alike, пользовательские сегменты custom_audience, in-market и интересы user_interest;
исключения - списки пользователей), кнопка (call_to_action-ассет), по видеообъявлению на каждый видео-ассет
(у каждого своя метка utm_content - для отдельного номера Ringostat), логотип (готовый ассет или файл).
Как подключать custom_audience и списки в группу - как в gads_dg_search_segment_builder.py: Audience -> dimensions.audience_segments.

Цели кампании (форма, звонок из объявления, звонок с сайта) ставятся ОТДЕЛЬНЫМ шагом: gads_set_campaign_goals.py.
Сегмент SEARCH создаётся отдельным шагом (create_custom_audience в gads_dg_search_segment_builder.py), look-alike -
gads_lookalike_create.py. Здесь только ссылки на уже существующие id.

Режимы:
  без флагов  - validate_only: Google проверяет запрос, ничего не создаёт (нужны настоящие ассеты, не заглушки);
                если в конфиге остались заглушки TODO (видео, тексты, логотип) - только печать плана, к API записи не обращаемся;
  --execute   - реальная запись (кампания всё равно на ПАУЗЕ); запрещён при заглушках и при существующей кампании с тем же именем.
Состояние: перед записью читается, есть ли кампания с таким именем; после записи кампания читается обратно (было -> станет).

Конфиг (YAML) - пример: Клиенты/EkspertAgro/Работы/2026-11-23_холодный_тест_DG_YT/dg_yt_config.yaml.
Ключи API берутся из gads_stats.GOOGLE_ADS_YAML (как у всех скриптов), в вывод не печатаются.

Использование (из папки Скрипты):
    python gads_dg_yt_builder.py --customer-id 8826134558 --config <путь>\\dg_yt_config.yaml            # проверка / план
    python gads_dg_yt_builder.py --customer-id 8826134558 --config <путь>\\dg_yt_config.yaml --execute  # запись (на паузе)

Дата создания: 2026-11-23.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

TRACK_TAIL = ("|gid_{adgroupid}|aid_{creative}|pos_{adposition}|dev_{device}|plc_{placement}"
              "|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}")
DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
DAY_ALIASES = {"MON": "MONDAY", "TUE": "TUESDAY", "WED": "WEDNESDAY", "THU": "THURSDAY",
               "FRI": "FRIDAY", "SAT": "SATURDAY", "SUN": "SUNDAY"}
MINUTES = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}


def is_todo(v):
    return v is None or (isinstance(v, str) and v.strip().upper().startswith("TODO")) or v == ""


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_todos(cfg):
    """Список мест конфига, где остались заглушки."""
    todos = []
    for i, v in enumerate(cfg.get("videos") or []):
        if is_todo(v.get("asset_id")):
            todos.append(f"videos[{i}].asset_id")
    t = cfg.get("texts") or {}
    for key in ("headlines", "long_headlines", "descriptions"):
        vals = t.get(key) or []
        if not vals or any(is_todo(x) for x in vals):
            todos.append(f"texts.{key}")
    if is_todo(cfg.get("logo_asset_id")) and is_todo(cfg.get("logo_file")):
        todos.append("logo_asset_id / logo_file")
    if is_todo(cfg.get("business_name")):
        todos.append("business_name")
    return todos


def parse_hm(s):
    h, m = str(s).split(":")
    h, m = int(h), int(m)
    if m not in MINUTES:
        raise ValueError(f"минуты {m} не поддерживаются (0/15/30/45): {s}")
    return h, MINUTES[m]


def schedule_rows(cfg):
    """schedule: null / [] -> без расписания; иначе список {days: [MON..], start: '9:30', end: '17:00'}."""
    rows = []
    for item in cfg.get("schedule") or []:
        sh, sm = parse_hm(item["start"])
        eh, em = parse_hm(item["end"])
        for d in item["days"]:
            d = str(d).upper()
            d = DAY_ALIASES.get(d, d)
            if d not in DAYS:
                raise ValueError(f"неизвестный день {d}")
            rows.append((d, sh, sm, eh, em))
    return rows


def validate_config(cfg):
    for key in ("campaign_name", "ad_group_name", "budget_per_day", "final_url", "business_name",
                "geo", "languages", "videos", "texts"):
        if key not in cfg:
            raise SystemExit(f"в конфиге нет обязательного ключа: {key}")
    inc = cfg.get("include") or {}
    if not any(inc.get(k) for k in ("user_lists", "custom_audiences", "user_interests")):
        raise SystemExit("в конфиге include пуст: нужен хотя бы один сегмент (user_lists / custom_audiences / user_interests)")
    t = cfg["texts"]
    if not find_todos({"texts": t, "logo_asset_id": "x", "business_name": "x", "videos": []}):
        assert all(len(h) <= 30 for h in t["headlines"]), "заголовок > 30"
        assert all(len(h) <= 90 for h in t["long_headlines"]), "длинный заголовок > 90"
        assert all(len(d) <= 90 for d in t["descriptions"]), "описание > 90"
        assert 1 <= len(t["headlines"]) <= 5, "заголовков должно быть 1-5"
        assert 1 <= len(t["long_headlines"]) <= 5, "длинных заголовков должно быть 1-5"
        assert 1 <= len(t["descriptions"]) <= 5, "описаний должно быть 1-5"
    if not is_todo(cfg["business_name"]):
        assert len(cfg["business_name"]) <= 25, "имя бизнеса > 25"
    schedule_rows(cfg)  # проверка формата


def resolve_logo_file(cfg, config_path):
    p = Path(str(cfg["logo_file"]))
    if p.is_absolute():
        return p
    for base in (config_path.parent, ROOT):
        if (base / p).exists():
            return base / p
    return config_path.parent / p


def tracking_template(cfg, label):
    # utm_content начинается с метки ролика (на ней фильтр канала Ringostat), дальше как в остальных кампаниях (rb_cid)
    utm_campaign = cfg.get("utm_campaign") or cfg["campaign_name"]
    return ("{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=" + utm_campaign +
            "&utm_content=" + label + "_rb_cid_{campaignid}" + TRACK_TAIL)


def print_plan(cfg, cid, todos):
    inc, exc = cfg.get("include") or {}, cfg.get("exclude") or {}
    print(f"=== План (аккаунт {cid}), было: кампании не создано -> станет: ===")
    print(f"кампания: {cfg['campaign_name']} (Demand Gen, ПАУЗА, Maximize conversions без цели CPA), группа: {cfg['ad_group_name']}")
    print(f"бюджет в день: {cfg['budget_per_day']} (валюта аккаунта); посадочная: {cfg['final_url']}; бизнес: {cfg['business_name']}")
    print(f"гео: {cfg['geo']}; языки: {cfg['languages']}")
    rows = schedule_rows(cfg)
    print("расписание:", "без расписания" if not rows else "; ".join(f"{d} {sh}:{sm}-{eh}:{em}" for d, sh, sm, eh, em in rows))
    print("каналы: YouTube in-stream, in-feed, Shorts; Discover/Gmail/Display выключены; оптимизированный таргетинг выключен")
    print(f"включить: списки {inc.get('user_lists') or []}; custom_audience {inc.get('custom_audiences') or []}; "
          f"user_interest {inc.get('user_interests') or []}")
    print(f"исключить списки: {exc.get('user_lists') or []}")
    for v in cfg["videos"]:
        print(f"  видео: ассет {v.get('asset_id')} | метка {v.get('label')} | объявление {v.get('ad_name')}")
    t = cfg["texts"]
    print(f"тексты: заголовков {len(t.get('headlines') or [])}, длинных {len(t.get('long_headlines') or [])}, "
          f"описаний {len(t.get('descriptions') or [])}; кнопка {cfg.get('call_to_action', 'LEARN_MORE')}")
    if todos:
        print("ЗАГЛУШКИ TODO в конфиге:", ", ".join(todos))


def find_campaign(client, cid, name):
    ga = client.get_service("GoogleAdsService")
    esc = name.replace("\\", "\\\\").replace("'", "\\'")
    return [(r.campaign.id, r.campaign.name, client.enums.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status))
            for r in ga.search(customer_id=cid, query=(
                "SELECT campaign.id, campaign.name, campaign.status FROM campaign "
                f"WHERE campaign.name = '{esc}' AND campaign.status != 'REMOVED'"))]


def upload_logo(client, cid, execute, cfg, config_path):
    """Логотип: готовый ассет (logo_asset_id) или загрузка файла. Без execute файл проверяется validate_only,
    а в объявление подставляется placeholder_logo_asset_id (существующий квадратный ассет аккаунта)."""
    if not is_todo(cfg.get("logo_asset_id")):
        return f"customers/{cid}/assets/{cfg['logo_asset_id']}"
    path = resolve_logo_file(cfg, config_path)
    assert path.exists(), f"нет файла логотипа {path}"
    svc = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    op.create.name = f"{cfg['campaign_name']}_logo_square_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    op.create.image_asset.data = path.read_bytes()
    req = client.get_type("MutateAssetsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    resp = svc.mutate_assets(request=req)
    if execute:
        return resp.results[0].resource_name
    print("Проверка загрузки логотипа пройдена (validate_only).")
    ph = cfg.get("placeholder_logo_asset_id")
    if is_todo(ph):
        raise SystemExit("для validate_only с logo_file нужен placeholder_logo_asset_id (существующий квадратный ассет аккаунта)")
    return f"customers/{cid}/assets/{ph}"


def build_operations(client, cid, cfg, logo_rn):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    E = client.enums
    name = cfg["campaign_name"]
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ad_group_rn = f"customers/{cid}/adGroups/-3"
    audience_rn = f"customers/{cid}/audiences/-4"
    cta_rn = f"customers/{cid}/assets/-5"
    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

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
    c.maximize_conversions.SetInParent()  # без цели по CPA
    c.demand_gen_campaign_settings.upgraded_targeting = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING

    for geo in cfg["geo"]:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
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

    ag = new_op().ad_group_operation.create
    ag.resource_name = ad_group_rn
    ag.name = cfg["ad_group_name"]
    ag.campaign = campaign_rn
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.optimized_targeting_enabled = False
    ch = ag.demand_gen_ad_group_settings.channel_controls.selected_channels
    ch.discover = False
    ch.gmail = False
    ch.display = False
    ch.youtube_in_stream = True
    ch.youtube_in_feed = True
    ch.youtube_shorts = True

    # Аудитория: все включения в одном измерении (объединение), исключения - списки пользователей
    inc, exc = cfg.get("include") or {}, cfg.get("exclude") or {}
    au = new_op().audience_operation.create
    au.resource_name = audience_rn
    au.name = f"{name} аудитория {ts}"
    au.description = cfg.get("audience_description") or f"{name}: включения и исключения из конфига"
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
    agc.ad_group = ad_group_rn
    agc.audience.audience = audience_rn

    a = new_op().asset_operation.create
    a.resource_name = cta_rn
    a.name = f"{name}_cta_{ts}"
    a.call_to_action_asset.call_to_action = getattr(E.CallToActionTypeEnum, cfg.get("call_to_action", "LEARN_MORE"))

    t = cfg["texts"]
    for v in cfg["videos"]:
        aga = new_op().ad_group_ad_operation.create
        aga.ad_group = ad_group_rn
        aga.status = E.AdGroupAdStatusEnum.ENABLED
        aga.ad.name = v["ad_name"]
        aga.ad.final_urls.append(cfg["final_url"])
        aga.ad.tracking_url_template = tracking_template(cfg, v["label"])
        va = aga.ad.demand_gen_video_responsive_ad
        va.videos.add().asset = f"customers/{cid}/assets/{v['asset_id']}"
        for x in t["headlines"]:
            va.headlines.add().text = x
        for x in t["long_headlines"]:
            va.long_headlines.add().text = x
        for x in t["descriptions"]:
            va.descriptions.add().text = x
        va.business_name.text = cfg["business_name"]
        va.logo_images.add().asset = logo_rn
        va.call_to_actions.add().asset = cta_rn
    return ops


def read_back(client, cid, campaign_id):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    print("\n=== Чтение обратно из аккаунта ===")
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
            "campaign_budget.amount_micros FROM campaign "
            f"WHERE campaign.id = {campaign_id}")):
        print(f"кампания {r.campaign.id} | {r.campaign.name} | "
              f"{E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status)} | "
              f"{E.AdvertisingChannelTypeEnum.AdvertisingChannelType.Name(r.campaign.advertising_channel_type)} | "
              f"бюджет в день {r.campaign_budget.amount_micros / 1e6:g}")
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.optimized_targeting_enabled FROM ad_group "
            f"WHERE campaign.id = {campaign_id}")):
        print(f"группа {r.ad_group.id} | {r.ad_group.name} | "
              f"{E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status)} | опт.таргетинг {r.ad_group.optimized_targeting_enabled}")
    n = 0
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status FROM ad_group_ad "
            f"WHERE campaign.id = {campaign_id}")):
        n += 1
        print(f"объявление {r.ad_group_ad.ad.id} | {r.ad_group_ad.ad.name} | "
              f"{E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status)}")
    print("объявлений:", n)


def main():
    ap = argparse.ArgumentParser(description="Общий сборщик Demand Gen «только YouTube, холодный тест» (кампания на паузе)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--config", required=True, help="YAML-конфиг клиента (см. шапку скрипта)")
    ap.add_argument("--execute", action="store_true", help="Реально создать объекты. Без флага - validate_only / план")
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    validate_config(cfg)
    cid = args.customer_id.replace("-", "").strip()
    todos = find_todos(cfg)
    print_plan(cfg, cid, todos)

    if todos:
        if args.execute:
            raise SystemExit("--execute запрещён: в конфиге заглушки TODO (" + ", ".join(todos) + ").")
        print("\nСухой прогон: заглушки не позволяют проверить запрос в Google, API не вызывался. Конфиг и план корректны по формату.")
        return

    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    from gads_stats import GOOGLE_ADS_YAML

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    try:
        exist = find_campaign(client, cid, cfg["campaign_name"])
        if exist:
            print("Было: кампания с таким именем уже есть:", exist)
            if args.execute:
                raise SystemExit("--execute остановлен: дубль кампании не создаю.")
        else:
            print(f"Было: кампании «{cfg['campaign_name']}» нет -> станет: создана на ПАУЗЕ (после --execute).")
        service = client.get_service("GoogleAdsService")
        logo_rn = upload_logo(client, cid, args.execute, cfg, config_path)
        ops = build_operations(client, cid, cfg, logo_rn)
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
