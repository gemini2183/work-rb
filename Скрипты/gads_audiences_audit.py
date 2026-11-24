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

Разрез «сигналы групп ассетов PMax» (добавлен 2026-11-23): asset_group_signal по всем PMax
(ENABLED/PAUSED, группы не REMOVED): аудитория (id, имя, состав из audience.dimensions) и поисковые
темы; по группе — есть ли аудиторный сигнал; --check-audience-id — подключён ли Audience к группам.
CSV: gads_audiences_asset_group_signals.csv. Только чтение.

Использование:
    python gads_audiences_audit.py --customer-id 7552781705 --client-folder "ProfiMet" --days 90
    python gads_audiences_audit.py --customer-id 8826134558 --client-folder EkspertAgro \\
        --only-asset-group-signals --check-audience-id 362371630 [--campaign-id <id>]
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


def _describe_dimension(d):
    """Одно измерение Audience -> короткая строка (только заполненное)."""
    parts = []
    for fld in ("age", "gender", "parental_status", "household_income"):
        sub = getattr(d, fld)
        if getattr(sub, '_pb', sub).ListFields():
            parts.append(f"{fld}:" + " ".join(str(sub).split())[:100])
    for seg in d.audience_segments.segments:
        if seg.user_list.user_list:
            parts.append("user_list:" + _id(seg.user_list.user_list))
        if seg.user_interest.user_interest_category:
            parts.append("in_market/affinity:" + seg.user_interest.user_interest_category)
        if seg.life_event.life_event:
            parts.append("life_event:" + seg.life_event.life_event)
        if seg.detailed_demographic.detailed_demographic:
            parts.append("detailed_demographic:" + seg.detailed_demographic.detailed_demographic)
        if seg.custom_audience.custom_audience:
            parts.append("custom_audience:" + seg.custom_audience.custom_audience)
    return "; ".join(parts)


def fetch_asset_group_signals(ga, cid, campaign_id=None):
    """Сигналы групп ассетов PMax: аудитории (с составом) и поисковые темы.
    Включает все PMax-кампании (ENABLED/PAUSED), группы не REMOVED; группы без сигналов — строкой NONE."""
    cf = f" AND campaign.id = {int(campaign_id)}" if campaign_id else ""
    base = ("campaign.advertising_channel_type = PERFORMANCE_MAX AND campaign.status IN (ENABLED, PAUSED) "
            "AND asset_group.status != REMOVED" + cf)
    aud = {}
    try:
        for r in run(ga, cid, "SELECT audience.resource_name, audience.id, audience.name, audience.dimensions, "
                              "audience.exclusion_dimension FROM audience"):
            a = r.audience
            comp = " | ".join(x for x in (_describe_dimension(d) for d in a.dimensions) if x)
            if a.exclusion_dimension.exclusions:
                comp += " | EXCLUDE:" + str(len(a.exclusion_dimension.exclusions))
            aud[a.resource_name] = (a.id, a.name, comp)
    except Exception as e:
        print(f"[asset_group_signals] audience состав не прочитан: {str(e)[:300]}")
    groups = {}
    for r in run(ga, cid, f"SELECT campaign.id, campaign.name, campaign.status, asset_group.id, asset_group.name, "
                          f"asset_group.status FROM asset_group WHERE {base}"):
        groups[r.asset_group.id] = (r.campaign.id, r.campaign.name, _name(r.campaign.status, "CampaignStatusEnum"),
                                    r.asset_group.name, _name(r.asset_group.status, "AssetGroupStatusEnum"))
    rows, seen = [], set()
    q = (f"SELECT campaign.id, asset_group.id, asset_group_signal.audience.audience, "
         f"asset_group_signal.search_theme.text FROM asset_group_signal WHERE {base}")
    for r in run(ga, cid, q):
        s = r.asset_group_signal
        g = groups.get(r.asset_group.id)
        if not g:
            continue
        seen.add(r.asset_group.id)
        if s.audience.audience:
            aid, aname, comp = aud.get(s.audience.audience, (_id(s.audience.audience), "?", ""))
            rows.append(_sig_row(r.asset_group.id, g, "AUDIENCE", aid, aname, comp))
        elif s.search_theme.text:
            rows.append(_sig_row(r.asset_group.id, g, "SEARCH_THEME", "", s.search_theme.text, ""))
    for gid, g in groups.items():
        if gid not in seen:
            rows.append(_sig_row(gid, g, "NONE", "", "", ""))
    return pd.DataFrame(rows)


def _sig_row(gid, g, typ, aid, value, comp):
    return {"Campaign_id": g[0], "Campaign": g[1], "Campaign_status": g[2], "Asset_group_id": gid,
            "Asset_group": g[3], "Asset_group_status": g[4], "Signal_type": typ,
            "Audience_id": aid, "Value": value, "Composition": comp}


def report_asset_group_signals(df, check_ids):
    """Консольная таблица + по группе «есть ли аудиторный сигнал» + проверка id Audience."""
    if df.empty:
        print("[asset_group_signals] PMax-групп не найдено")
        return
    print("\n=== Сигналы групп ассетов PMax ===")
    cols = ["Campaign", "Campaign_status", "Asset_group", "Asset_group_status", "Signal_type", "Value", "Composition"]
    with pd.option_context("display.max_colwidth", 90, "display.width", 250, "display.max_rows", 500):
        print(df[cols].to_string(index=False))
    print("\n=== По группам: есть ли аудиторный сигнал ===")
    for (cn, gn), sub in df.groupby(["Campaign", "Asset_group"], sort=False):
        n = int((sub["Signal_type"] == "AUDIENCE").sum())
        t = int((sub["Signal_type"] == "SEARCH_THEME").sum())
        print(f"{cn} | {gn} | аудиторных сигналов: {n} ({'ЕСТЬ' if n else 'НЕТ'}) | поисковых тем: {t}")
    for cid_ in check_ids:
        hit = df[(df["Signal_type"] == "AUDIENCE") & (df["Audience_id"].astype(str) == str(cid_))]
        if hit.empty:
            print(f"\nAudience {cid_}: не подключён ни к одной группе ассетов PMax")
        else:
            print(f"\nAudience {cid_}: подключён к {len(hit)} групп(е/ам):")
            for _, x in hit.iterrows():
                print(f"  {x['Campaign']} | {x['Campaign_status']} | {x['Asset_group']} | {x['Asset_group_status']}")


def _in(ids):
    return ", ".join(str(int(i)) for i in ids)


def _lookup_names(ga, cid, ul_ids, ui_ids, ca_ids):
    """Названия по id: user_list (+размер), user_interest (+taxonomy), custom_audience (+type, members)."""
    ul, ui, ca, errs = {}, {}, {}, []
    if ul_ids:
        try:
            for r in run(ga, cid, "SELECT user_list.id, user_list.name, user_list.type, user_list.size_for_display, "
                                  f"user_list.size_for_search FROM user_list WHERE user_list.id IN ({_in(ul_ids)})"):
                u = r.user_list
                ul[str(u.id)] = f"{u.name} [{_name(u.type_, 'UserListTypeEnum')}; display={u.size_for_display}, search={u.size_for_search}]"
        except Exception as e:
            errs.append(f"user_list: {e}")
    if ui_ids:
        try:
            for r in run(ga, cid, "SELECT user_interest.user_interest_id, user_interest.name, user_interest.taxonomy_type "
                                  f"FROM user_interest WHERE user_interest.user_interest_id IN ({_in(ui_ids)})"):
                u = r.user_interest
                ui[str(u.user_interest_id)] = f"{u.name} [{_name(u.taxonomy_type, 'UserInterestTaxonomyTypeEnum')}]"
        except Exception as e:
            errs.append(f"user_interest: {e}")
    if ca_ids:
        try:
            for r in run(ga, cid, "SELECT custom_audience.id, custom_audience.name, custom_audience.type, "
                                  "custom_audience.status, custom_audience.members "
                                  f"FROM custom_audience WHERE custom_audience.id IN ({_in(ca_ids)})"):
                c = r.custom_audience
                mem = []
                for m in c.members:
                    mt = _name(m.member_type, "CustomAudienceMemberTypeEnum")
                    val = m.keyword or m.url or m.place_category or m.app
                    mem.append(f"{mt}:{val}")
                ca[str(c.id)] = f"{c.name} [{_name(c.type_, 'CustomAudienceTypeEnum')}; members={len(mem)}: " + ", ".join(mem)[:600] + "]"
        except Exception as e:
            errs.append(f"custom_audience: {e}")
    return ul, ui, ca, errs


def fetch_audience_composition(ga, cid, only_ids=None, extra_ul=(), extra_ui=(), extra_ca=()):
    """Состав каждого Audience: измерения с НАЗВАНИЯМИ списков/интересов/custom audience."""
    q = ("SELECT audience.id, audience.name, audience.status, audience.dimensions, audience.exclusion_dimension "
         "FROM audience")
    auds = list(run(ga, cid, q))
    only = {str(i) for i in (only_ids or [])}
    parsed, ul_ids, ui_ids, ca_ids = [], set(extra_ul), set(extra_ui), set(extra_ca)
    for r in auds:
        a = r.audience
        if only and str(a.id) not in only:
            continue
        items = []  # (kind, id/text, excluded)
        for d in a.dimensions:
            for fld in ("age", "gender", "parental_status", "household_income"):
                sub = getattr(d, fld)
                if getattr(sub, "_pb", sub).ListFields():
                    items.append((fld, " ".join(str(sub).split()), False))
            for seg in d.audience_segments.segments:
                if seg.user_list.user_list:
                    ul_ids.add(_id(seg.user_list.user_list)); items.append(("user_list", _id(seg.user_list.user_list), False))
                if seg.user_interest.user_interest_category:
                    ui_ids.add(_id(seg.user_interest.user_interest_category)); items.append(("user_interest", _id(seg.user_interest.user_interest_category), False))
                if seg.custom_audience.custom_audience:
                    ca_ids.add(_id(seg.custom_audience.custom_audience)); items.append(("custom_audience", _id(seg.custom_audience.custom_audience), False))
                if seg.life_event.life_event:
                    items.append(("life_event", _id(seg.life_event.life_event), False))
                if seg.detailed_demographic.detailed_demographic:
                    items.append(("detailed_demographic", _id(seg.detailed_demographic.detailed_demographic), False))
        for ex in a.exclusion_dimension.exclusions:
            s = ex.segments if hasattr(ex, "segments") else None
            txt = " ".join(str(ex).split())
            items.append(("EXCLUSION", txt[:200], True))
        parsed.append((a, items))
    ul, ui, ca, errs = _lookup_names(ga, cid, ul_ids, ui_ids, ca_ids)
    for e in errs:
        print(f"[composition] ОШИБКА имён: {e[:500]}")
    maps = {"user_list": ul, "user_interest": ui, "custom_audience": ca}
    rows = []
    for a, items in parsed:
        if not items:
            rows.append({"Audience_id": a.id, "Audience_name": a.name, "Status": _name(a.status, "AudienceStatusEnum"),
                         "Kind": "", "Ref_id": "", "Name_or_detail": "(пустой состав)", "Excluded": False})
        for kind, ref, exc in items:
            rows.append({"Audience_id": a.id, "Audience_name": a.name, "Status": _name(a.status, "AudienceStatusEnum"),
                         "Kind": kind, "Ref_id": ref if kind in maps or kind in ("life_event", "detailed_demographic") else "",
                         "Name_or_detail": maps.get(kind, {}).get(ref, ref if kind not in maps else "?(имя не получено)"),
                         "Excluded": exc})
    # прямые id (user_list / user_interest / custom_audience), заданные в аргументах
    for k, mp, ids in (("user_list", ul, extra_ul), ("user_interest", ui, extra_ui), ("custom_audience", ca, extra_ca)):
        for i in ids:
            rows.append({"Audience_id": "", "Audience_name": "(прямой id)", "Status": "", "Kind": k, "Ref_id": str(i),
                         "Name_or_detail": mp.get(str(i), "?(не найден/нет доступа)"), "Excluded": False})
    return pd.DataFrame(rows)


def fetch_pmax_campaigns(ga, cid):
    """ENABLED PMax: бюджет, ставка, цели конверсий, гео, списки-исключения. Одна строка на кампанию."""
    camps = {}
    for r in run(ga, cid, "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
                          "campaign_budget.amount_micros FROM campaign "
                          "WHERE campaign.advertising_channel_type = PERFORMANCE_MAX AND campaign.status = ENABLED"):
        c = r.campaign
        camps[c.id] = {"Campaign_id": c.id, "Campaign": c.name, "Status": _name(c.status, "CampaignStatusEnum"),
                       "Bidding": _name(c.bidding_strategy_type, "BiddingStrategyTypeEnum"),
                       "Daily_budget": round(r.campaign_budget.amount_micros / 1e6, 2),
                       "Conv_goals": [], "Geo": [], "Excluded_lists": [], "Primary_actions": ""}
    if not camps:
        return pd.DataFrame()
    ids = _in(camps)
    def safe(label, fn):
        try:
            fn()
        except Exception as e:
            print(f"[pmax_campaigns] {label} ОШИБКА: {str(e)[:400]}")
    def goals():
        for r in run(ga, cid, "SELECT campaign.id, campaign_conversion_goal.category, campaign_conversion_goal.origin, "
                              f"campaign_conversion_goal.biddable FROM campaign_conversion_goal WHERE campaign.id IN ({ids})"):
            g = r.campaign_conversion_goal
            camps[r.campaign.id]["Conv_goals"].append(
                f"{_name(g.category, 'ConversionActionCategoryEnum')}/{_name(g.origin, 'ConversionOriginEnum')}:{'biddable' if g.biddable else 'not_biddable'}")
    def cfg():
        for r in run(ga, cid, "SELECT campaign.id, conversion_goal_campaign_config.goal_config_level, "
                              "conversion_goal_campaign_config.custom_conversion_goal "
                              f"FROM conversion_goal_campaign_config WHERE campaign.id IN ({ids})"):
            k = r.conversion_goal_campaign_config
            camps[r.campaign.id]["Conv_goals"].append(
                f"LEVEL={_name(k.goal_config_level, 'GoalConfigLevelEnum')}" + (f" custom={k.custom_conversion_goal}" if k.custom_conversion_goal else ""))
    def geo():
        gt = {}
        rows = list(run(ga, cid, "SELECT campaign.id, campaign_criterion.location.geo_target_constant, campaign_criterion.negative "
                                 f"FROM campaign_criterion WHERE campaign_criterion.type = LOCATION AND campaign.id IN ({ids})"))
        gids = {_id(r.campaign_criterion.location.geo_target_constant) for r in rows}
        if gids:
            for r in run(ga, cid, f"SELECT geo_target_constant.id, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.id IN ({_in(gids)})"):
                gt[str(r.geo_target_constant.id)] = r.geo_target_constant.name
        for r in rows:
            gid = _id(r.campaign_criterion.location.geo_target_constant)
            camps[r.campaign.id]["Geo"].append(("-" if r.campaign_criterion.negative else "") + gt.get(gid, gid))
    def excl():
        ul = fetch_user_lists(ga, cid).set_index("List_id")["Name"].to_dict()
        for r in run(ga, cid, "SELECT campaign.id, campaign_criterion.user_list.user_list FROM campaign_criterion "
                              f"WHERE campaign_criterion.type = USER_LIST AND campaign_criterion.negative = TRUE AND campaign.id IN ({ids})"):
            lid = _id(r.campaign_criterion.user_list.user_list)
            camps[r.campaign.id]["Excluded_lists"].append(f"{lid}={ul.get(int(lid), '?')}")
    safe("goals", goals); safe("goal_config", cfg); safe("geo", geo); safe("excluded_lists", excl)
    rows = []
    for c in camps.values():
        c = dict(c)
        for k in ("Conv_goals", "Geo", "Excluded_lists"):
            c[k] = "; ".join(c[k])
        rows.append(c)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description="Аудит аудиторий Google Ads (только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--only-asset-group-signals", action="store_true",
                    help="только разрез «сигналы групп ассетов PMax»")
    ap.add_argument("--campaign-id", help="фильтр кампании для сигналов групп ассетов")
    ap.add_argument("--check-audience-id", action="append", default=[],
                    help="id Audience-объекта: проверить подключение к группам ассетов (можно несколько раз)")
    ap.add_argument("--only-composition", action="store_true",
                    help="только расшифровка состава Audience-объектов (названия списков/интересов/custom audience) "
                         "+ сводка по ENABLED PMax; CSV gads_audiences_composition.csv, gads_pmax_campaigns.csv")
    ap.add_argument("--audience-id", action="append", default=[], help="фильтр: id Audience (можно несколько раз); пусто = все")
    ap.add_argument("--user-list-id", action="append", default=[], help="доп. id user_list для расшифровки")
    ap.add_argument("--user-interest-id", action="append", default=[], help="доп. id userInterests (in-market/affinity)")
    ap.add_argument("--custom-audience-id", action="append", default=[], help="доп. id custom_audience")
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
    jobs.append(("asset_group_signals", lambda: fetch_asset_group_signals(ga, cid, args.campaign_id),
                 "gads_audiences_asset_group_signals.csv"))
    if args.only_composition:
        jobs = [("composition", lambda: fetch_audience_composition(
                    ga, cid, args.audience_id, args.user_list_id, args.user_interest_id, args.custom_audience_id),
                 "gads_audiences_composition.csv"),
                ("pmax_campaigns", lambda: fetch_pmax_campaigns(ga, cid), "gads_pmax_campaigns.csv")]
    elif args.only_asset_group_signals:
        jobs = jobs[-1:]
    for label, fn, fname in jobs:
        try:
            df = fn()
        except Exception as e:
            print(f"[{label}] ОШИБКА: {str(e)[:300]}")
            continue
        df.to_csv(out / fname, index=False, encoding="utf-8")
        print(f"[{label}] {len(df)} строк -> {fname}")
        if label == "asset_group_signals":
            report_asset_group_signals(df, args.check_audience_id)
        if label in ("composition", "pmax_campaigns") and not df.empty:
            with pd.option_context("display.max_colwidth", 200, "display.width", 300, "display.max_rows", 1000):
                print(df.to_string(index=False))


if __name__ == "__main__":
    main()
