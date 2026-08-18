#!/usr/bin/env python
# coding: utf-8
"""Строит гео-варианты групп объявлений (ключи + RSA) для загрузки через Google Ads Editor.

Тянет из кампании все группы объявлений: активные ключевые слова
(ad_group_criterion) и тексты RSA-объявлений (headlines/descriptions) — тем же
способом, что gads_semantics.py (fetch_keywords) и gads_ads_dump.py (fetch_ads).
Для каждой исходной группы строит N новых групп-вариантов, добавляя к каждому
ключевому слову указанный geo-суффикс (напр. "Los Angeles" и "LA" отдельно) и
копируя тексты объявлений как есть — RSA не зависят от гео и обычно достаточно
общие, чтобы не требовать правки под конкретный город; если тексты объявлений
тоже нужно адаплировать под город, это делается вручную после импорта.

Только ENABLED-ключи (PAUSED/REMOVED пропускаются — не имеет смысла тиражировать
неактивную семантику). Названия новых групп — "<исходное имя> - <суффикс>"
(см. Клиенты/Юристы США/Решения.md, запись про гео-расширение LA).

Результат — один CSV в формате Google Ads Editor bulk upload (секции Keyword и
Responsive search ad вперемешку, как их принимает импорт по колонкам Campaign/
Ad group/Row type) в Клиенты/<client-folder>/Статистика/.

Использование:
    python gads_geo_ad_group_builder.py --customer-id 213-621-6123 \
        --client-folder "Юристы США" --campaign "Search / All Injuries" \
        --geo "Los Angeles" --geo "LA"
"""
import argparse
import csv

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


def _pin_label(pinned_field: int) -> str:
    if not pinned_field:
        return ""
    name = _enum_name("ServedAssetFieldTypeEnum", "ServedAssetFieldType", pinned_field)
    return name.replace("HEADLINE_", "H").replace("DESCRIPTION_", "D")


def fetch_keywords_by_group(ga_service, customer_id, campaign_name):
    """Активные ключевые слова кампании -> {ad_group_name: [(text, match_type), ...]}.

    Только ENABLED ad_group_criterion. Запрос идёт через ad_group_criterion, не
    keyword_view — keyword_view требует наличия статистики за период и молча
    пропускает ключи без показов (проверено на аккаунте Andverpersonalinjury:
    группы с 0 показов за последнее время давали 0 строк через keyword_view,
    хотя ad_group_criterion.type='KEYWORD' их видит).
    """
    query = f"""
        SELECT
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status
        FROM ad_group_criterion
        WHERE campaign.name = '{campaign_name}'
            AND ad_group_criterion.type = 'KEYWORD'
            AND ad_group_criterion.status = 'ENABLED'
    """
    by_group = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            match_type = _enum_name(
                "KeywordMatchTypeEnum", "KeywordMatchType", row.ad_group_criterion.keyword.match_type
            )
            by_group.setdefault(row.ad_group.name, []).append(
                (row.ad_group_criterion.keyword.text, match_type)
            )
    return by_group


def fetch_ads_by_group(ga_service, customer_id, campaign_name):
    """RSA-объявления кампании -> {ad_group_name: [ad, ...]} (та же форма, что gads_ads_dump.fetch_ads)."""
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
            AND ad_group_ad.status = 'ENABLED'
            AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
    """
    by_group = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            ad = row.ad_group_ad.ad.responsive_search_ad
            by_group.setdefault(row.ad_group.name, []).append({
                "AdId": row.ad_group_ad.ad.id,
                "FinalUrls": list(row.ad_group_ad.ad.final_urls),
                "Headlines": [(a.text, _pin_label(a.pinned_field)) for a in ad.headlines],
                "Descriptions": [(a.text, _pin_label(a.pinned_field)) for a in ad.descriptions],
            })
    return by_group


def build_rows(campaign_name, keywords_by_group, ads_by_group, geo_suffixes):
    """Строит плоский список строк для bulksheet CSV — по одной новой группе на (исходная группа x geo)."""
    rows = []
    for group_name, keywords in keywords_by_group.items():
        if not keywords:
            continue
        for geo in geo_suffixes:
            new_group = f"{group_name} - {geo}"

            for text, match_type in keywords:
                new_text = f"{text} {geo}"
                rows.append({
                    "Row Type": "Keyword",
                    "Campaign": campaign_name,
                    "Ad group": new_group,
                    "Keyword": new_text,
                    "Match Type": match_type,
                })

            for ad in ads_by_group.get(group_name, []):
                row = {
                    "Row Type": "Responsive search ad",
                    "Campaign": campaign_name,
                    "Ad group": new_group,
                    "Final URL": ad["FinalUrls"][0] if ad["FinalUrls"] else "",
                }
                for i, (text, pin) in enumerate(ad["Headlines"], 1):
                    row[f"Headline {i}"] = text
                    if pin:
                        row[f"Headline {i} position"] = pin.replace("H", "")
                for i, (text, pin) in enumerate(ad["Descriptions"], 1):
                    row[f"Description {i}"] = text
                    if pin:
                        row[f"Description {i} position"] = pin.replace("D", "")
                rows.append(row)

    return rows


def write_csv(rows, out_path):
    fieldnames = ["Row Type", "Campaign", "Ad group", "Keyword", "Match Type", "Final URL"]
    fieldnames += [f"Headline {i}" for i in range(1, 16)]
    fieldnames += [f"Headline {i} position" for i in range(1, 16)]
    fieldnames += [f"Description {i}" for i in range(1, 5)]
    fieldnames += [f"Description {i} position" for i in range(1, 5)]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True, help="Формат XXX-XXX-XXXX или без дефисов")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--campaign", required=True, help='Точное название кампании, напр. "Search / All Injuries"')
    ap.add_argument("--geo", action="append", required=True,
                     help='Суффикс, добавляемый к ключам и имени группы. Повторить флаг для нескольких '
                          '(напр. --geo "Los Angeles" --geo "LA")')
    args = ap.parse_args()

    customer_id = args.customer_id.replace("-", "").strip()

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | кампания: {args.campaign} | geo: {', '.join(args.geo)}")

    keywords_by_group = fetch_keywords_by_group(ga_service, customer_id, args.campaign)
    if not keywords_by_group:
        print("Активных ключевых слов не найдено — проверь точное название кампании и customer_id")
        return
    ads_by_group = fetch_ads_by_group(ga_service, customer_id, args.campaign)

    rows = build_rows(args.campaign, keywords_by_group, ads_by_group, args.geo)

    out_dir = client_stats_dir(args.client_folder)
    safe_campaign = args.campaign.replace("/", "-").strip()
    safe_geo = "_".join(g.replace(" ", "") for g in args.geo)
    out_path = out_dir / f"gads_geo_bulksheet_{safe_campaign}_{safe_geo}.csv"
    write_csv(rows, out_path)

    n_groups = len(keywords_by_group) * len(args.geo)
    print(f"Сохранено: {out_path} ({n_groups} новых групп, {len(rows)} строк)")
    print("Импорт: Google Ads Editor -> Account -> Import -> From File, выбрать 'Use Campaign/Ad group "
          "columns' при маппинге, проверить diff перед Post.")


if __name__ == "__main__":
    main()
