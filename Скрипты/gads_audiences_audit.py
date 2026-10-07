#!/usr/bin/env python
# coding: utf-8
"""Инвентаризация аудиторий Google Ads (READ-ONLY): списки, где применены, статистика.

Отвечает на вопросы аудита: какие списки аудиторий есть в аккаунте (тип, размер на
Display/Search, срок жизни, статус сбора), где каждый реально подключён (кампания/группа,
targeting или observation, исключение), что по ним показывалось и кликалось за период,
какие списки нигде не используются (кандидаты на удаление). Плюс справочник
конверсионных действий и объём клик/конверсия по кампаниям, чтобы сопоставить трафик с
тем, сколько людей реально попадает в списки "корзина"/"лид".

Только считает и сохраняет CSV в Статистика/ клиента — в аккаунте ничего не меняет.

Использование:
    python gads_audiences_audit.py --customer-id 7552781705 --client-folder "ProfiMet" --days 90
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


_CLIENT = None


def _name(v, enum="", ):
    """Числовое значение enum -> имя. enum — имя типа, напр. 'UserListTypeEnum'."""
    global _CLIENT
    if hasattr(v, "name"):
        return v.name
    if not enum:
        return str(v)
    if _CLIENT is None:
        _CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    d = getattr(_CLIENT.enums, enum).DESCRIPTOR.enum_types_by_name[enum[:-4]]
    return d.values_by_number[int(v)].name


def _id(resource_name):
    return resource_name.split("/")[-1] if resource_name else ""


def run(ga, cid, query):
    out = []
    for batch in ga.search_stream(customer_id=cid, query=query):
        out.extend(batch.results)
    return out


def fetch_user_lists(ga, cid):
    q = """
        SELECT user_list.id, user_list.name, user_list.type, user_list.membership_status,
               user_list.membership_life_span, user_list.size_for_display,
               user_list.size_for_search, user_list.eligible_for_display,
               user_list.eligible_for_search, user_list.read_only, user_list.description
        FROM user_list
    """
    rows = []
    for r in run(ga, cid, q):
        u = r.user_list
        rows.append({
            "List_id": u.id, "Name": u.name, "Type": _name(u.type_, "UserListTypeEnum"),
            "Membership": _name(u.membership_status, "UserListMembershipStatusEnum"), "Life_span_days": u.membership_life_span,
            "Size_display": u.size_for_display, "Size_search": u.size_for_search,
            "Eligible_display": u.eligible_for_display, "Eligible_search": u.eligible_for_search,
            "Read_only": u.read_only, "Description": u.description,
        })
    return pd.DataFrame(rows)


def fetch_audiences_resource(ga, cid):
    """Новый ресурс Audience (комбинированные/сегменты в новой модели)."""
    q = "SELECT audience.id, audience.name, audience.status, audience.description FROM audience"
    try:
        return pd.DataFrame([{
            "Audience_id": r.audience.id, "Name": r.audience.name,
            "Status": _name(r.audience.status, "AudienceStatusEnum"), "Description": r.audience.description,
        } for r in run(ga, cid, q)])
    except Exception as e:  # ресурс может быть недоступен — не критично
        print(f"[audience] пропущено: {str(e)[:150]}")
        return pd.DataFrame()


def fetch_usage_ad_group(ga, cid):
    q = """
        SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
               ad_group.id, ad_group.name, ad_group.status,
               ad_group_criterion.criterion_id, ad_group_criterion.type,
               ad_group_criterion.negative, ad_group_criterion.status,
               ad_group_criterion.user_list.user_list, ad_group_criterion.bid_modifier
        FROM ad_group_criterion
        WHERE ad_group_criterion.type = USER_LIST
    """
    rows = []
    for r in run(ga, cid, q):
        c = r.ad_group_criterion
        rows.append({
            "Level": "ad_group", "Campaign": r.campaign.name, "Campaign_status": _name(r.campaign.status, "CampaignStatusEnum"),
            "Channel": _name(r.campaign.advertising_channel_type, "AdvertisingChannelTypeEnum"), "Ad_group": r.ad_group.name,
            "Ad_group_status": _name(r.ad_group.status, "AdGroupStatusEnum"), "List_id": _id(c.user_list.user_list),
            "Negative": c.negative, "Criterion_status": _name(c.status, "AdGroupCriterionStatusEnum"), "Bid_modifier": c.bid_modifier,
        })
    return pd.DataFrame(rows)


def fetch_usage_campaign(ga, cid):
    q = """
        SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
               campaign_criterion.negative, campaign_criterion.status,
               campaign_criterion.user_list.user_list
        FROM campaign_criterion
        WHERE campaign_criterion.type = USER_LIST
    """
    rows = []
    for r in run(ga, cid, q):
        c = r.campaign_criterion
        rows.append({
            "Level": "campaign", "Campaign": r.campaign.name, "Campaign_status": _name(r.campaign.status, "CampaignStatusEnum"),
            "Channel": _name(r.campaign.advertising_channel_type, "AdvertisingChannelTypeEnum"), "Ad_group": "",
            "Ad_group_status": "", "List_id": _id(c.user_list.user_list), "Negative": c.negative,
            "Criterion_status": _name(c.status, "CampaignCriterionStatusEnum"), "Bid_modifier": None,
        })
    return pd.DataFrame(rows)


def fetch_targeting_mode(ga, cid):
    """Targeting vs Observation по группам (ad_group.targeting_setting)."""
    q = """
        SELECT ad_group.id, ad_group.name, campaign.name,
               ad_group.targeting_setting.target_restrictions
        FROM ad_group
        WHERE ad_group.status != REMOVED
    """
    rows = []
    for r in run(ga, cid, q):
        for tr in r.ad_group.targeting_setting.target_restrictions:
            if _name(tr.targeting_dimension, "TargetingDimensionEnum") == "AUDIENCE":
                rows.append({"Campaign": r.campaign.name, "Ad_group": r.ad_group.name,
                             "Audience_mode": "OBSERVATION" if tr.bid_only else "TARGETING"})
    return pd.DataFrame(rows)


def fetch_perf(ga, cid, d1, d2):
    q = f"""
        SELECT campaign.name, ad_group.name, ad_group_criterion.user_list.user_list,
               ad_group_criterion.negative,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.conversions, metrics.all_conversions
        FROM ad_group_audience_view
        WHERE segments.date BETWEEN '{d1}' AND '{d2}'
    """
    rows = []
    for r in run(ga, cid, q):
        m = r.metrics
        rows.append({
            "Campaign": r.campaign.name, "Ad_group": r.ad_group.name,
            "List_id": _id(r.ad_group_criterion.user_list.user_list),
            "Impr": m.impressions, "Clicks": m.clicks, "Cost": round(m.cost_micros / 1e6, 2),
            "Conv": round(m.conversions, 2), "All_conv": round(m.all_conversions, 2),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.groupby(["Campaign", "Ad_group", "List_id"], as_index=False).sum(numeric_only=True)


def fetch_conv_actions(ga, cid):
    q = """
        SELECT conversion_action.id, conversion_action.name, conversion_action.type,
               conversion_action.status, conversion_action.category,
               conversion_action.primary_for_goal, conversion_action.counting_type
        FROM conversion_action
        WHERE conversion_action.status != REMOVED
    """
    return pd.DataFrame([{
        "Id": r.conversion_action.id, "Name": r.conversion_action.name,
        "Type": _name(r.conversion_action.type_, "ConversionActionTypeEnum"), "Status": _name(r.conversion_action.status, "ConversionActionStatusEnum"),
        "Category": _name(r.conversion_action.category, "ConversionActionCategoryEnum"),
        "Primary": r.conversion_action.primary_for_goal, "Counting": _name(r.conversion_action.counting_type, "ConversionActionCountingTypeEnum"),
    } for r in run(ga, cid, q)])


def fetch_campaign_conv(ga, cid, d1, d2):
    """Клики/расход по кампаниям и all_conversions по конверсионным действиям."""
    q = f"""
        SELECT campaign.name, campaign.status, campaign.advertising_channel_type,
               segments.conversion_action_name,
               metrics.all_conversions, metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{d1}' AND '{d2}' AND metrics.all_conversions > 0
    """
    rows = [{
        "Campaign": r.campaign.name, "Status": _name(r.campaign.status, "CampaignStatusEnum"),
        "Channel": _name(r.campaign.advertising_channel_type, "AdvertisingChannelTypeEnum"),
        "Action": r.segments.conversion_action_name,
        "All_conv": round(r.metrics.all_conversions, 2), "Conv": round(r.metrics.conversions, 2),
    } for r in run(ga, cid, q)]
    df = pd.DataFrame(rows)
    return df.groupby(["Campaign", "Status", "Channel", "Action"], as_index=False).sum(numeric_only=True) if rows else df


def fetch_campaign_traffic(ga, cid, d1, d2):
    q = f"""
        SELECT campaign.name, campaign.status, campaign.advertising_channel_type,
               metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{d1}' AND '{d2}'
    """
    rows = [{
        "Campaign": r.campaign.name, "Status": _name(r.campaign.status, "CampaignStatusEnum"),
        "Channel": _name(r.campaign.advertising_channel_type, "AdvertisingChannelTypeEnum"), "Impr": r.metrics.impressions,
        "Clicks": r.metrics.clicks, "Cost": round(r.metrics.cost_micros / 1e6, 2),
    } for r in run(ga, cid, q)]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).groupby(["Campaign", "Status", "Channel"], as_index=False).sum(numeric_only=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    login = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga = get_ads_service(login)

    d2 = date.today() - timedelta(days=1)
    d1 = d2 - timedelta(days=args.days - 1)
    out = client_stats_dir(args.client_folder)
    tag = f"{d1}_to_{d2}"

    jobs = [
        ("user_lists", lambda: fetch_user_lists(ga, cid), "gads_audiences_user_lists.csv"),
        ("audience_resource", lambda: fetch_audiences_resource(ga, cid), "gads_audiences_audience_resource.csv"),
        ("usage_ad_group", lambda: fetch_usage_ad_group(ga, cid), "gads_audiences_usage_ad_group.csv"),
        ("usage_campaign", lambda: fetch_usage_campaign(ga, cid), "gads_audiences_usage_campaign.csv"),
        ("targeting_mode", lambda: fetch_targeting_mode(ga, cid), "gads_audiences_targeting_mode.csv"),
        ("perf", lambda: fetch_perf(ga, cid, d1, d2), f"gads_audiences_perf_{tag}.csv"),
        ("conv_actions", lambda: fetch_conv_actions(ga, cid), "gads_conversion_actions.csv"),
        ("campaign_conv", lambda: fetch_campaign_conv(ga, cid, d1, d2), f"gads_campaign_conv_by_action_{tag}.csv"),
        ("campaign_traffic", lambda: fetch_campaign_traffic(ga, cid, d1, d2), f"gads_campaign_traffic_{tag}.csv"),
    ]
    for label, fn, fname in jobs:
        try:
            df = fn()
        except Exception as e:
            print(f"[{label}] ОШИБКА: {str(e)[:300]}")
            continue
        df.to_csv(out / fname, index=False, encoding="utf-8")
        print(f"[{label}] {len(df)} строк -> {fname}")


if __name__ == "__main__":
    main()
