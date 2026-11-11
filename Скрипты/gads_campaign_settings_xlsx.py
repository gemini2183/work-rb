#!/usr/bin/env python
# coding: utf-8
"""Выгрузка ФАКТИЧЕСКИХ настроек Search-кампании Google Ads в Excel, по листам. ТОЛЬКО ЧТЕНИЕ.

Листы: Кампания, Цели конверсий, Группы и ключи, Минусы, Объявления, Быстрые ссылки, Callouts и ассеты, Картинки.
Это приложение к сводке по кампании (эталон — База_знаний/Агенты/Сводка_по_кампании_эталон.md): в чате короткая сводка,
полные тексты и списки — здесь. Файл: Клиенты/<Имя>/Статистика/campaign_settings_<id>_<дата_время>.xlsx

    python gads_campaign_settings_xlsx.py --customer-id 213-621-6123 --campaign-id 24447075486 --client-folder Andverpersonalinjury

Что читает (≈20 запросов GAQL, учитываются в журнале операций gads_quota_ledger): кампания и бюджет, критерии кампании (гео, язык,
устройства, расписание, минусы), цели конверсий и действия, группы, ключи группы с одобрением, общие списки минусов и их слова,
объявления (заголовки и описания с закреплениями), ассеты кампании / групп / аккаунта (быстрые ссылки, callouts, сниппеты, звонок,
логотип), картинки групп. Ничего не пишет в кабинет.
"""
import argparse
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import wrap_ga


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", type=int, required=True)
    ap.add_argument("--client-folder", required=True)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    camp = a.campaign_id
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    E = client.enums
    ga = wrap_ga(client.get_service("GoogleAdsService"), "gads_campaign_settings_xlsx")

    def q(query):
        return list(ga.search(customer_id=cid, query=query))

    def nm(enum, v):
        try:
            return enum.Name(v)
        except Exception:
            return str(v)

    wb = Workbook()

    def sheet(title, header, rows, widths=None):
        ws = wb.create_sheet(title)
        ws.append(header)
        for r in rows:
            ws.append(list(r))
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="305496")
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for i, h in enumerate(header, 1):
            w = (widths or {}).get(i)
            if not w:
                longest = max([len(str(h))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r)] or [10])
                w = min(max(12, longest + 2), 70)
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"
        return ws

    # ---------- 1. Кампания ----------
    r = q("SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status, campaign.bidding_strategy_type, "
          "campaign.network_settings.target_google_search, campaign.network_settings.target_search_network, "
          "campaign.network_settings.target_content_network, campaign.geo_target_type_setting.positive_geo_target_type, "
          "campaign.geo_target_type_setting.negative_geo_target_type, campaign.tracking_url_template, "
          "campaign_budget.amount_micros, campaign_budget.explicitly_shared FROM campaign "
          f"WHERE campaign.id = {camp}")[0]
    c = r.campaign
    info = [
        ("Название", c.name), ("ID", c.id), ("Статус", nm(E.CampaignStatusEnum.CampaignStatus, c.status)),
        ("Статус показа", nm(E.CampaignServingStatusEnum.CampaignServingStatus, c.serving_status)),
        ("Стратегия ставок", nm(E.BiddingStrategyTypeEnum.BiddingStrategyType, c.bidding_strategy_type)),
        ("Дневной бюджет", r.campaign_budget.amount_micros / 1e6),
        ("Поиск Google", c.network_settings.target_google_search), ("Поисковые партнёры", c.network_settings.target_search_network),
        ("Контекстно-медийная сеть", c.network_settings.target_content_network),
        ("Гео: режим включения", nm(E.PositiveGeoTargetTypeEnum.PositiveGeoTargetType, c.geo_target_type_setting.positive_geo_target_type)),
        ("Гео: режим исключения", nm(E.NegativeGeoTargetTypeEnum.NegativeGeoTargetType, c.geo_target_type_setting.negative_geo_target_type)),
        ("Шаблон отслеживания", c.tracking_url_template),
    ]
    crit = q("SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.bid_modifier, "
             "campaign_criterion.location.geo_target_constant, campaign_criterion.language.language_constant, "
             "campaign_criterion.device.type, campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
             "campaign_criterion.ad_schedule.end_hour, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type "
             f"FROM campaign_criterion WHERE campaign.id = {camp}")
    geo_names = {}
    geo_ids = {x.campaign_criterion.location.geo_target_constant for x in crit if x.campaign_criterion.location.geo_target_constant}
    for g in geo_ids:
        for gr in q(f"SELECT geo_target_constant.resource_name, geo_target_constant.name, geo_target_constant.canonical_name FROM geo_target_constant WHERE geo_target_constant.resource_name = '{g}'"):
            geo_names[g] = gr.geo_target_constant.canonical_name
    for x in crit:
        cc = x.campaign_criterion
        t = nm(E.CriterionTypeEnum.CriterionType, cc.type_)
        if t == "LOCATION":
            info.append(("Гео (минус)" if cc.negative else "Гео", geo_names.get(cc.location.geo_target_constant, cc.location.geo_target_constant)))
        elif t == "LANGUAGE":
            info.append(("Язык", cc.language.language_constant))
        elif t == "DEVICE":
            info.append(("Устройство: корректировка ставки", f"{nm(E.DeviceEnum.Device, cc.device.type_)}: {cc.bid_modifier if cc.bid_modifier else 'нет'}"))
        elif t == "AD_SCHEDULE":
            info.append(("Расписание", f"{nm(E.DayOfWeekEnum.DayOfWeek, cc.ad_schedule.day_of_week)} {cc.ad_schedule.start_hour}–{cc.ad_schedule.end_hour} ч"))
    sheet("Кампания", ["Параметр", "Значение"], info, {1: 34, 2: 90})

    # ---------- 2. Цели конверсий ----------
    cat, org = E.ConversionActionCategoryEnum.ConversionActionCategory, E.ConversionOriginEnum.ConversionOrigin
    goals = [(nm(cat, g.campaign_conversion_goal.category), nm(org, g.campaign_conversion_goal.origin),
              "ДА" if g.campaign_conversion_goal.biddable else "нет")
             for g in q("SELECT campaign.id, campaign_conversion_goal.category, campaign_conversion_goal.origin, campaign_conversion_goal.biddable "
                        f"FROM campaign_conversion_goal WHERE campaign.id = {camp}")]
    lvl = q(f"SELECT campaign.id, conversion_goal_campaign_config.goal_config_level FROM conversion_goal_campaign_config WHERE campaign.id = {camp}")
    lvl_txt = nm(E.GoalConfigLevelEnum.GoalConfigLevel, lvl[0].conversion_goal_campaign_config.goal_config_level) if lvl else "?"
    ws = sheet("Цели конверсий", ["Категория", "Источник", "В основных (biddable)"], sorted(goals), {1: 28, 2: 20, 3: 22})
    ws.append([]); ws.append([f"Уровень целей: {lvl_txt}"])
    ws.append([]); ws.append(["Действия аккаунта (включённые)", "Категория", "Источник / тип"])
    for x in q("SELECT conversion_action.name, conversion_action.category, conversion_action.origin, conversion_action.type, conversion_action.primary_for_goal "
               "FROM conversion_action WHERE conversion_action.status = ENABLED"):
        ca = x.conversion_action
        ws.append([ca.name, nm(cat, ca.category), f"{nm(org, ca.origin)} / {nm(E.ConversionActionTypeEnum.ConversionActionType, ca.type_)}"])

    # ---------- 3. Группы и ключи ----------
    groups = {x.ad_group.id: x.ad_group for x in q(
        f"SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros FROM ad_group WHERE campaign.id = {camp} AND ad_group.status != REMOVED")}
    rows = []
    for x in q("SELECT campaign.id, ad_group.id, ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status, "
               "ad_group_criterion.negative, ad_group_criterion.approval_status, ad_group_criterion.cpc_bid_micros, ad_group_criterion.quality_info.quality_score "
               f"FROM ad_group_criterion WHERE campaign.id = {camp} AND ad_group_criterion.type = KEYWORD AND ad_group_criterion.status != REMOVED"):
        k, g = x.ad_group_criterion, groups.get(x.ad_group.id)
        rows.append((x.ad_group.name, nm(E.AdGroupStatusEnum.AdGroupStatus, g.status) if g else "", (g.cpc_bid_micros / 1e6) if g else "",
                     k.keyword.text, nm(E.KeywordMatchTypeEnum.KeywordMatchType, k.keyword.match_type),
                     "минус группы" if k.negative else "ключ", nm(E.AdGroupCriterionStatusEnum.AdGroupCriterionStatus, k.status),
                     nm(E.PolicyApprovalStatusEnum.PolicyApprovalStatus, k.approval_status), k.cpc_bid_micros / 1e6 if k.cpc_bid_micros else "",
                     k.quality_info.quality_score or ""))
    if not rows:
        rows = [(g.name, nm(E.AdGroupStatusEnum.AdGroupStatus, g.status), g.cpc_bid_micros / 1e6, "", "", "", "", "", "", "") for g in groups.values()]
    sheet("Группы и ключи", ["Группа", "Статус группы", "Ставка группы $", "Ключ", "Соответствие", "Тип", "Статус ключа", "Одобрение", "Ставка ключа $", "Оценка качества"],
          sorted(rows), {1: 30, 4: 40})

    # ---------- 4. Минусы ----------
    neg = [(x.campaign_criterion.keyword.text, nm(E.KeywordMatchTypeEnum.KeywordMatchType, x.campaign_criterion.keyword.match_type), "кампания")
           for x in crit if x.campaign_criterion.negative and nm(E.CriterionTypeEnum.CriterionType, x.campaign_criterion.type_) == "KEYWORD"]
    shared = q(f"SELECT campaign.id, shared_set.id, shared_set.name, shared_set.type FROM campaign_shared_set WHERE campaign.id = {camp} AND campaign_shared_set.status = ENABLED")
    for s in shared:
        for w in q("SELECT shared_set.id, shared_set.name, shared_criterion.keyword.text, shared_criterion.keyword.match_type FROM shared_criterion "
                   f"WHERE shared_set.id = {s.shared_set.id}"):
            neg.append((w.shared_criterion.keyword.text, nm(E.KeywordMatchTypeEnum.KeywordMatchType, w.shared_criterion.keyword.match_type), f"общий список «{s.shared_set.name}»"))
    order = {"BROAD": 0, "PHRASE": 1, "EXACT": 2}
    sheet("Минусы", ["Минус-слово", "Соответствие", "Откуда"], sorted(neg, key=lambda t: (t[2], order.get(t[1], 9), t[0])), {1: 50, 2: 16, 3: 34})

    # ---------- 5. Объявления ----------
    ads = []
    for x in q("SELECT campaign.id, ad_group.name, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.policy_summary.approval_status, ad_group_ad.ad.final_urls, "
               "ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions, ad_group_ad.ad.responsive_search_ad.path1, "
               f"ad_group_ad.ad.responsive_search_ad.path2 FROM ad_group_ad WHERE campaign.id = {camp} AND ad_group_ad.status != REMOVED"):
        ad = x.ad_group_ad
        ads.append(("Объявление", x.ad_group.name, ad.ad.id, nm(E.AdGroupAdStatusEnum.AdGroupAdStatus, ad.status),
                    nm(E.PolicyApprovalStatusEnum.PolicyApprovalStatus, ad.policy_summary.approval_status), "", "", "", ""))
        ads.append(("", "", "", "", "", "Конечный URL", ", ".join(ad.ad.final_urls), "", ""))
        ads.append(("", "", "", "", "", "Путь", f"{ad.ad.responsive_search_ad.path1}/{ad.ad.responsive_search_ad.path2}", "", ""))
        for i, h in enumerate(ad.ad.responsive_search_ad.headlines, 1):
            ads.append(("", "", "", "", "", f"Заголовок {i}", h.text, len(h.text), nm(E.ServedAssetFieldTypeEnum.ServedAssetFieldType, h.pinned_field) if h.pinned_field else ""))
        for i, d in enumerate(ad.ad.responsive_search_ad.descriptions, 1):
            ads.append(("", "", "", "", "", f"Описание {i}", d.text, len(d.text), nm(E.ServedAssetFieldTypeEnum.ServedAssetFieldType, d.pinned_field) if d.pinned_field else ""))
    sheet("Объявления", ["", "Группа", "ID", "Статус", "Одобрение", "Поле", "Текст", "Знаков", "Закрепление"], ads, {2: 28, 6: 16, 7: 90})

    # ---------- 6. Быстрые ссылки ----------
    sl = []
    for level, query in (("группа", f"SELECT campaign.id, ad_group.name, ad_group_asset.status, ad_group_asset.primary_status, asset.id, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, asset.final_urls FROM ad_group_asset WHERE campaign.id = {camp} AND ad_group_asset.field_type = SITELINK AND ad_group_asset.status != REMOVED"),
                         ("кампания", f"SELECT campaign.id, campaign_asset.status, campaign_asset.primary_status, asset.id, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, asset.final_urls FROM campaign_asset WHERE campaign.id = {camp} AND campaign_asset.field_type = SITELINK AND campaign_asset.status != REMOVED")):
        for x in q(query):
            s = x.asset.sitelink_asset
            link = ad_status = prim = ""
            if level == "группа":
                ad_status, prim = nm(E.AssetLinkStatusEnum.AssetLinkStatus, x.ad_group_asset.status), nm(E.AssetLinkPrimaryStatusEnum.AssetLinkPrimaryStatus, x.ad_group_asset.primary_status)
            else:
                ad_status, prim = nm(E.AssetLinkStatusEnum.AssetLinkStatus, x.campaign_asset.status), nm(E.AssetLinkPrimaryStatusEnum.AssetLinkPrimaryStatus, x.campaign_asset.primary_status)
            url = list(x.asset.final_urls)[0] if x.asset.final_urls else ""
            base = url.split("?")[0]
            anchor = ("#" + url.split("#")[-1]) if "#" in url else ""
            sl.append((level, x.ad_group.name if level == "группа" else "", s.link_text, s.description1, s.description2, base, anchor, ad_status, prim, x.asset.id))
    sheet("Быстрые ссылки", ["Уровень", "Группа", "Текст ссылки", "Описание 1", "Описание 2", "Страница", "Якорь", "Статус", "Primary", "ID ассета"], sl, {3: 26, 4: 34, 5: 34, 6: 60})

    # ---------- 7. Callouts и ассеты ----------
    ass = []
    for lvl_name, query in (("кампания", f"SELECT campaign.id, campaign_asset.field_type, campaign_asset.status, campaign_asset.primary_status, asset.id, asset.callout_asset.callout_text, asset.call_asset.phone_number, asset.call_asset.country_code, asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.name FROM campaign_asset WHERE campaign.id = {camp} AND campaign_asset.status != REMOVED AND campaign_asset.field_type IN (CALLOUT, CALL, STRUCTURED_SNIPPET, BUSINESS_LOGO, BUSINESS_NAME, PROMOTION, PRICE)"),
                            ("аккаунт", "SELECT customer_asset.field_type, customer_asset.status, customer_asset.primary_status, asset.id, asset.callout_asset.callout_text, asset.call_asset.phone_number, asset.call_asset.country_code, asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.name FROM customer_asset WHERE customer_asset.status != REMOVED AND customer_asset.field_type IN (CALLOUT, CALL, STRUCTURED_SNIPPET, BUSINESS_LOGO, BUSINESS_NAME)")):
        for x in q(query):
            link = x.campaign_asset if lvl_name == "кампания" else x.customer_asset
            ft = nm(E.AssetFieldTypeEnum.AssetFieldType, link.field_type)
            a_ = x.asset
            text = a_.callout_asset.callout_text or a_.call_asset.phone_number or (a_.structured_snippet_asset.header + ": " + ", ".join(a_.structured_snippet_asset.values) if a_.structured_snippet_asset.header else a_.name)
            ass.append((lvl_name, ft, text, nm(E.AssetLinkStatusEnum.AssetLinkStatus, link.status), nm(E.AssetLinkPrimaryStatusEnum.AssetLinkPrimaryStatus, link.primary_status), a_.id))
    sheet("Callouts и ассеты", ["Уровень", "Тип", "Текст / значение", "Статус", "Primary", "ID ассета"], sorted(ass), {3: 70})

    # ---------- 8. Картинки ----------
    im = []
    for x in q("SELECT campaign.id, ad_group.name, ad_group_asset.status, ad_group_asset.primary_status, asset.id, asset.name, asset.image_asset.full_size.width_pixels, "
               f"asset.image_asset.full_size.height_pixels, asset.image_asset.full_size.url FROM ad_group_asset WHERE campaign.id = {camp} AND ad_group_asset.field_type = AD_IMAGE AND ad_group_asset.status != REMOVED"):
        i = x.asset.image_asset.full_size
        im.append((x.ad_group.name, x.asset.name, f"{i.width_pixels}×{i.height_pixels}", nm(E.AssetLinkStatusEnum.AssetLinkStatus, x.ad_group_asset.status),
                   nm(E.AssetLinkPrimaryStatusEnum.AssetLinkPrimaryStatus, x.ad_group_asset.primary_status), x.asset.id, i.url))
    sheet("Картинки", ["Группа", "Имя файла", "Размер", "Статус", "Primary", "ID ассета", "Ссылка на файл"], sorted(im), {1: 28, 2: 50, 7: 60})

    del wb["Sheet"]
    out_dir = Path(__file__).resolve().parent.parent / "Клиенты" / a.client_folder / "Статистика"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"campaign_settings_{camp}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    wb.save(out)
    print("Сохранено:", out)
    print("Листы:", ", ".join(wb.sheetnames))
    print(f"минусов всего: {len(neg)}, групп: {len(groups)}, ключей: {len([r for r in rows if r[3]])}, быстрых ссылок: {len(sl)}, картинок: {len(im)}")


if __name__ == "__main__":
    main()
