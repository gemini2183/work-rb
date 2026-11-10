#!/usr/bin/env python
# coding: utf-8
"""Полное состояние Search-кампании Google Ads В ЛЮБОМ статусе (в том числе на паузе): ТОЛЬКО ЧТЕНИЕ.

Зачем (Landver, 2026-11-10): gads_campaign_settings.py и gads_ad_extensions.py видят только ENABLED-кампании, а перед
перестройкой групп нужен «рентген» кампании, стоящей на паузе: настройки, группы со ставками, и ВСЕ активы с их уровнем
(кампания / группа): быстрые ссылки, звонок, callout, сниппеты, картинки, промо, название бизнеса. Выводов не делает.

    python gads_campaign_state_dump.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda"
Пишет Статистика/gads_state_dump_<кампания>_<дата>.txt и печатает то же.
"""
import argparse
import datetime as dt
import re
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_CL = None


def enum_name(enum_type, field, value):
    global _CL
    if _CL is None:
        _CL = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    return getattr(_CL.enums, enum_type).DESCRIPTOR.enum_types_by_name[field].values_by_number[value].name


def q(svc, cid, query):
    out = []
    for b in svc.search_stream(customer_id=cid, query=query):
        out.extend(b.results)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    lines = []

    def P(s=""):
        print(s)
        lines.append(s)

    login = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    svc = get_ads_service(login)
    cname = a.campaign.replace("'", "\\'")

    P(f"=== Состояние кампании «{a.campaign}» на {dt.datetime.now():%Y-%m-%d %H:%M} (чтение) ===")
    rows = q(svc, cid, f"""SELECT campaign.id, campaign.status, campaign.serving_status, campaign.bidding_strategy_type,
        campaign.manual_cpc.enhanced_cpc_enabled, campaign.network_settings.target_google_search,
        campaign.network_settings.target_search_network, campaign.network_settings.target_content_network,
        campaign.tracking_url_template, campaign.final_url_suffix, campaign_budget.amount_micros,
        campaign.geo_target_type_setting.positive_geo_target_type
        FROM campaign WHERE campaign.name = '{cname}'""")
    if not rows:
        P("кампания не найдена")
        return
    r = rows[0]
    c = r.campaign
    cid_camp = c.id
    P(f"[1] id {cid_camp}; статус {enum_name('CampaignStatusEnum','CampaignStatus',c.status)}; "
      f"стратегия {enum_name('BiddingStrategyTypeEnum','BiddingStrategyType',c.bidding_strategy_type)}; "
      f"бюджет/день {r.campaign_budget.amount_micros/1e6:.2f}")
    P(f"    сеть: Google Search={c.network_settings.target_google_search}, партнёры={c.network_settings.target_search_network}, "
      f"контекст={c.network_settings.target_content_network}")
    P(f"    шаблон отслеживания: {c.tracking_url_template or '—'}; суффикс: {c.final_url_suffix or '—'}")

    P("\n[2] Гео и расписание (критерии кампании):")
    incl, excl = [], []
    for x in q(svc, cid, f"""SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.location.geo_target_constant,
        campaign_criterion.proximity.radius, campaign_criterion.proximity.radius_units,
        campaign_criterion.proximity.geo_point.latitude_in_micro_degrees, campaign_criterion.proximity.geo_point.longitude_in_micro_degrees,
        campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, campaign_criterion.ad_schedule.end_hour,
        campaign_criterion.bid_modifier, campaign_criterion.device.type
        FROM campaign_criterion WHERE campaign.id = {cid_camp}
        AND campaign_criterion.type IN ('LOCATION','PROXIMITY','AD_SCHEDULE','DEVICE','LANGUAGE')"""):
        cc = x.campaign_criterion
        t = enum_name("CriterionTypeEnum", "CriterionType", cc.type_)
        if t == "LOCATION":
            (excl if cc.negative else incl).append(cc.location.geo_target_constant.split("/")[-1])
        elif t == "PROXIMITY":
            P(f"    PROXIMITY радиус {cc.proximity.radius} {enum_name('ProximityRadiusUnitsEnum','ProximityRadiusUnits',cc.proximity.radius_units)} "
              f"центр {cc.proximity.geo_point.latitude_in_micro_degrees/1e6:.4f},{cc.proximity.geo_point.longitude_in_micro_degrees/1e6:.4f}")
        elif t == "AD_SCHEDULE":
            P(f"    РАСПИСАНИЕ {enum_name('DayOfWeekEnum','DayOfWeek',cc.ad_schedule.day_of_week)} {cc.ad_schedule.start_hour}-{cc.ad_schedule.end_hour} модификатор {cc.bid_modifier}")
        elif t == "DEVICE":
            P(f"    УСТРОЙСТВО {enum_name('DeviceEnum','Device',cc.device.type_)} модификатор {cc.bid_modifier}")
        else:
            P(f"    {t} {cc.negative}")

    P("\n[3] Группы объявлений (статус, ставка):")
    groups = {}
    for x in q(svc, cid, f"""SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros
        FROM ad_group WHERE campaign.id = {cid_camp} AND ad_group.status != 'REMOVED' ORDER BY ad_group.name"""):
        g = x.ad_group
        groups[g.id] = g.name
        P(f"    {g.name:34s} {enum_name('AdGroupStatusEnum','AdGroupStatus',g.status):8s} ставка ${g.cpc_bid_micros/1e6:.2f}  (id {g.id})")

    P("\n[4] Активы уровня КАМПАНИИ:")
    for x in q(svc, cid, f"""SELECT campaign.id, campaign_asset.field_type, campaign_asset.status, asset.id, asset.type, asset.name,
        asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2,
        asset.final_urls, asset.callout_asset.callout_text, asset.call_asset.phone_number, asset.call_asset.country_code,
        asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.promotion_asset.promotion_target,
        asset.text_asset.text
        FROM campaign_asset WHERE campaign.id = {cid_camp} AND campaign_asset.status != 'REMOVED'"""):
        P("    " + fmt_asset(x, "campaign_asset"))

    P("\n[5] Активы уровня ГРУППЫ (по группам):")
    for x in q(svc, cid, f"""SELECT campaign.id, ad_group.name, ad_group_asset.field_type, ad_group_asset.status, asset.id, asset.type, asset.name,
        asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2,
        asset.final_urls, asset.callout_asset.callout_text, asset.call_asset.phone_number, asset.call_asset.country_code,
        asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.promotion_asset.promotion_target
        FROM ad_group_asset WHERE campaign.id = {cid_camp} AND ad_group_asset.status != 'REMOVED' ORDER BY ad_group.name"""):
        P(f"    [{x.ad_group.name}] " + fmt_asset(x, "ad_group_asset"))

    P("\n[6] Активы уровня АККАУНТА (customer_asset):")
    for x in q(svc, cid, """SELECT customer_asset.field_type, customer_asset.status, asset.id, asset.type, asset.name,
        asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.final_urls, asset.callout_asset.callout_text,
        asset.call_asset.phone_number, asset.call_asset.country_code, asset.structured_snippet_asset.header,
        asset.structured_snippet_asset.values, asset.text_asset.text
        FROM customer_asset WHERE customer_asset.status != 'REMOVED'"""):
        P("    " + fmt_asset(x, "customer_asset"))

    P("\n[7] Кампанийные минус-слова: число = " + str(len(q(svc, cid, f"""SELECT campaign.id, campaign_criterion.keyword.text
        FROM campaign_criterion WHERE campaign.id = {cid_camp} AND campaign_criterion.type = 'KEYWORD'
        AND campaign_criterion.negative = TRUE"""))))

    out = client_stats_dir(a.client_folder) / f"gads_state_dump_{re.sub(r'[^a-zA-Z0-9]+','_',a.campaign)}_{dt.date.today()}.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nСохранено: {out}")


def fmt_asset(x, link_attr):
    a = x.asset
    link = getattr(x, link_attr)
    ft = enum_name("AssetFieldTypeEnum", "AssetFieldType", link.field_type)
    st = enum_name("AssetLinkStatusEnum", "AssetLinkStatus", link.status)
    ty = enum_name("AssetTypeEnum", "AssetType", a.type_)
    d = ""
    if ty == "SITELINK":
        s = a.sitelink_asset
        d = f"«{s.link_text}» | {s.description1} | {s.description2} -> {list(a.final_urls)}"
    elif ty == "CALLOUT":
        d = a.callout_asset.callout_text
    elif ty == "CALL":
        d = f"{a.call_asset.country_code} {a.call_asset.phone_number}"
    elif ty == "STRUCTURED_SNIPPET":
        d = f"{a.structured_snippet_asset.header}: {list(a.structured_snippet_asset.values)}"
    elif ty == "PROMOTION":
        d = a.promotion_asset.promotion_target
    elif ty == "BUSINESS_NAME":
        d = a.text_asset.text
    else:
        d = a.name
    return f"{ty:18s} {ft:22s} {st:8s} asset {a.id}: {d}"


if __name__ == "__main__":
    main()
