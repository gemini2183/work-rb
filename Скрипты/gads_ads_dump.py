#!/usr/bin/env python
# coding: utf-8
"""Выгрузка текстов объявлений (Responsive Search Ads) по группам объявлений
одной кампании — без метрик, без периода. Нужна как рабочая копия для ручной/
построчной правки текстов (не для анализа эффективности).

customer_id передаётся напрямую, без похода в общую Google-таблицу Adwhite —
для клиентов, ещё не заведённых там строкой (см. Клиенты/Andverpersonalinjury/Решения.md,
запись про Land Your Personal Injury).

Использование:
    python gads_ads_dump.py --customer-id 213-621-6123 --client-folder "Юристы США" \
        --campaign "Search / All Injuries"
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

# ad_group_ad.status приходит из search_stream как int, не как объект с .name
# (см. аналогичное примечание в gads_semantics.py) — резолвится через enum-клиент.
_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def _pin_label(pinned_field: int) -> str:
    """UNSPECIFIED/0 -> не закреплён; иначе короткая метка позиции (H1, D2, ...)."""
    if not pinned_field:
        return ""
    name = _enum_name("ServedAssetFieldTypeEnum", "ServedAssetFieldType", pinned_field)
    # HEADLINE_1 -> H1, DESCRIPTION_2 -> D2
    return name.replace("HEADLINE_", "H").replace("DESCRIPTION_", "D")


def fetch_ads(ga_service, customer_id, campaign_name):
    """Группы объявлений + тексты RSA (headlines/descriptions) одной кампании.

    Возвращает список словарей: {AdGroup, AdId, Status, FinalUrls, Headlines: [(text, pin)],
    Descriptions: [(text, pin)]}. pin — "" если не закреплён, иначе "H1".."H3"/"D1".."D2".
    Только ENABLED/PAUSED объявления (REMOVED пропускаются — не актуальны для правки).
    campaign_name сравнивается регистрозависимо (GAQL) — передавать точно как в аккаунте.
    """
    query = f"""
        SELECT
            ad_group.name,
            ad_group_ad.ad.id,
            ad_group_ad.status,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions
        FROM ad_group_ad
        WHERE campaign.name = '{campaign_name}'
            AND ad_group_ad.status != 'REMOVED'
            AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
        ORDER BY ad_group.name
    """

    ads = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            ad = row.ad_group_ad.ad.responsive_search_ad
            ads.append({
                "AdGroup": row.ad_group.name,
                "AdId": row.ad_group_ad.ad.id,
                "Status": _enum_name("AdGroupAdStatusEnum", "AdGroupAdStatus", row.ad_group_ad.status),
                "FinalUrls": list(row.ad_group_ad.ad.final_urls),
                "Headlines": [(a.text, _pin_label(a.pinned_field)) for a in ad.headlines],
                "Descriptions": [(a.text, _pin_label(a.pinned_field)) for a in ad.descriptions],
            })
    return ads


def _sitelink_dict(asset_row, status_enum_value):
    sl = asset_row.sitelink_asset
    return {
        "LinkText": sl.link_text,
        "Description1": sl.description1,
        "Description2": sl.description2,
        "FinalUrl": asset_row.final_urls[0] if asset_row.final_urls else "",
        "Status": _enum_name("AssetLinkStatusEnum", "AssetLinkStatus", status_enum_value),
    }


def fetch_sitelinks(ga_service, customer_id, campaign_name):
    """Быстрые ссылки (sitelinks) кампании на всех трёх уровнях привязки.

    В Google Ads sitelinks — asset, который можно закрепить на уровне ad_group,
    campaign или всего аккаунта (customer); группа без своих sitelinks наследует
    показ с более широкого уровня. Возвращает:
        by_group: {ad_group_name: [sitelink, ...]}   — только уровень ad_group_asset
        campaign_level: [sitelink, ...]                — уровень campaign_asset (этой кампании)
        account_level: [sitelink, ...]                 — уровень customer_asset (весь аккаунт)
    Каждый список содержит все статусы (в т.ч. REMOVED) — фильтрация по ENABLED
    делается в рендере, REMOVED нужен отдельно как «пул того, что когда-то было».
    """
    by_group = {}
    q_group = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_asset.status,
            asset.sitelink_asset.link_text,
            asset.sitelink_asset.description1,
            asset.sitelink_asset.description2,
            asset.final_urls
        FROM ad_group_asset
        WHERE campaign.name = '{campaign_name}'
            AND asset.type = 'SITELINK'
    """
    for batch in ga_service.search_stream(customer_id=customer_id, query=q_group):
        for row in batch.results:
            by_group.setdefault(row.ad_group.name, []).append(
                _sitelink_dict(row.asset, row.ad_group_asset.status)
            )

    campaign_level = []
    q_campaign = f"""
        SELECT
            campaign.name,
            campaign_asset.status,
            asset.sitelink_asset.link_text,
            asset.sitelink_asset.description1,
            asset.sitelink_asset.description2,
            asset.final_urls
        FROM campaign_asset
        WHERE campaign.name = '{campaign_name}'
            AND asset.type = 'SITELINK'
    """
    for batch in ga_service.search_stream(customer_id=customer_id, query=q_campaign):
        for row in batch.results:
            campaign_level.append(_sitelink_dict(row.asset, row.campaign_asset.status))

    account_level = []
    q_account = """
        SELECT
            customer_asset.status,
            asset.sitelink_asset.link_text,
            asset.sitelink_asset.description1,
            asset.sitelink_asset.description2,
            asset.final_urls
        FROM customer_asset
        WHERE asset.type = 'SITELINK'
    """
    for batch in ga_service.search_stream(customer_id=customer_id, query=q_account):
        for row in batch.results:
            account_level.append(_sitelink_dict(row.asset, row.customer_asset.status))

    return by_group, campaign_level, account_level


def fetch_all_sitelink_assets(ga_service, customer_id):
    """Полный справочник sitelink-ассетов аккаунта (весь пул, привязан он сейчас или нет).

    Нужен, чтобы видеть, что вообще когда-либо было сделано и доступно для
    переиспользования — не только то, что сейчас закреплено на этой кампании.
    """
    query = """
        SELECT
            asset.id,
            asset.sitelink_asset.link_text,
            asset.sitelink_asset.description1,
            asset.sitelink_asset.description2,
            asset.final_urls
        FROM asset
        WHERE asset.type = 'SITELINK'
        ORDER BY asset.sitelink_asset.link_text
    """
    assets = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            sl = row.asset.sitelink_asset
            assets.append({
                "AssetId": row.asset.id,
                "LinkText": sl.link_text,
                "Description1": sl.description1,
                "Description2": sl.description2,
                "FinalUrl": row.asset.final_urls[0] if row.asset.final_urls else "",
            })
    return assets


def _format_sitelink_line(sl, level_label):
    desc = f" — {sl['Description1']} / {sl['Description2']}" if sl["Description1"] else ""
    return f"- ({level_label}) {sl['LinkText']}{desc} → {sl['FinalUrl']}"


def render_markdown(campaign_name, ads, sitelinks_by_group, campaign_sitelinks,
                     account_sitelinks, all_account_sitelinks):
    lines = [f"# {campaign_name} — объявления по группам\n"]

    by_group = {}
    for ad in ads:
        by_group.setdefault(ad["AdGroup"], []).append(ad)

    campaign_enabled = [sl for sl in campaign_sitelinks if sl["Status"] == "ENABLED"]
    account_enabled = [sl for sl in account_sitelinks if sl["Status"] == "ENABLED"]

    for group_name, group_ads in by_group.items():
        lines.append(f"## {group_name}\n")
        for ad in group_ads:
            lines.append(f"### AdId {ad['AdId']} ({ad['Status']})\n")
            if ad["FinalUrls"]:
                lines.append(f"Ссылка: {', '.join(ad['FinalUrls'])}\n")
            lines.append("Заголовки:")
            for i, (h, pin) in enumerate(ad["Headlines"], 1):
                suffix = f" [закреплён: {pin}]" if pin else ""
                lines.append(f"{i}. {h}{suffix}")
            lines.append("")
            lines.append("Описания:")
            for i, (d, pin) in enumerate(ad["Descriptions"], 1):
                suffix = f" [закреплён: {pin}]" if pin else ""
                lines.append(f"{i}. {d}{suffix}")
            lines.append("")

        group_enabled = [sl for sl in sitelinks_by_group.get(group_name, []) if sl["Status"] == "ENABLED"]
        effective = (
            [(sl, "уровень группы") for sl in group_enabled]
            or [(sl, "уровень кампании") for sl in campaign_enabled]
            or [(sl, "уровень аккаунта") for sl in account_enabled]
        )
        if effective:
            lines.append("Быстрые ссылки, реально показывающиеся с этой группой:")
            for sl, level_label in effective:
                lines.append(_format_sitelink_line(sl, level_label))
            lines.append("")
        else:
            lines.append("Быстрые ссылки: не найдено ни на уровне группы, ни кампании, ни аккаунта.\n")

    lines.append("---\n")
    lines.append(f"## Справочник — все sitelink-ассеты аккаунта ({len(all_account_sitelinks)})\n")
    lines.append("Весь пул когда-либо созданных быстрых ссылок в аккаунте, независимо от того,")
    lines.append("привязаны ли они сейчас к этой кампании — для переиспользования при правке.\n")
    for sl in all_account_sitelinks:
        desc = f" — {sl['Description1']} / {sl['Description2']}" if sl["Description1"] else ""
        lines.append(f"- [{sl['AssetId']}] {sl['LinkText']}{desc} → {sl['FinalUrl']}")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True, help="Формат XXX-XXX-XXXX или без дефисов")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--campaign", required=True, help='Точное название кампании, напр. "Search / All Injuries"')
    args = ap.parse_args()

    customer_id = args.customer_id.replace("-", "").strip()

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | кампания: {args.campaign}")
    ads = fetch_ads(ga_service, customer_id, args.campaign)

    if not ads:
        print("Объявлений не найдено — проверь точное название кампании и customer_id")
        return

    sitelinks_by_group, campaign_sitelinks, account_sitelinks = fetch_sitelinks(
        ga_service, customer_id, args.campaign
    )
    all_account_sitelinks = fetch_all_sitelink_assets(ga_service, customer_id)

    out_dir = client_stats_dir(args.client_folder)
    safe_campaign = args.campaign.replace("/", "-").strip()
    out_path = out_dir / f"gads_ads_{safe_campaign}.md"
    out_path.write_text(
        render_markdown(args.campaign, ads, sitelinks_by_group, campaign_sitelinks,
                         account_sitelinks, all_account_sitelinks),
        encoding="utf-8",
    )

    print(f"Сохранено: {out_path} ({len(ads)} объявлений)")


if __name__ == "__main__":
    main()
