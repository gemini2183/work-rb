#!/usr/bin/env python
# coding: utf-8
"""Выгрузка текстов объявлений (Responsive Search Ads) по группам объявлений
одной кампании — без метрик, без периода. Нужна как рабочая копия для ручной/
построчной правки текстов (не для анализа эффективности).

customer_id передаётся напрямую, без похода в общую Google-таблицу Adwhite —
для клиентов, ещё не заведённых там строкой (см. Клиенты/Юристы США/Решения.md,
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


def fetch_ads(ga_service, customer_id, campaign_name):
    """Группы объявлений + тексты RSA (headlines/descriptions) одной кампании.

    Возвращает список словарей: {AdGroup, AdId, Status, Headlines: [...], Descriptions: [...]}.
    Только ENABLED/PAUSED объявления (REMOVED пропускаются — не актуальны для правки).
    campaign_name сравнивается регистрозависимо (GAQL) — передавать точно как в аккаунте.
    """
    query = f"""
        SELECT
            ad_group.name,
            ad_group_ad.ad.id,
            ad_group_ad.status,
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
                "Headlines": [a.text for a in ad.headlines],
                "Descriptions": [a.text for a in ad.descriptions],
            })
    return ads


def render_markdown(campaign_name, ads):
    lines = [f"# {campaign_name} — объявления по группам\n"]

    by_group = {}
    for ad in ads:
        by_group.setdefault(ad["AdGroup"], []).append(ad)

    for group_name, group_ads in by_group.items():
        lines.append(f"## {group_name}\n")
        for ad in group_ads:
            lines.append(f"### AdId {ad['AdId']} ({ad['Status']})\n")
            lines.append("Заголовки:")
            for i, h in enumerate(ad["Headlines"], 1):
                lines.append(f"{i}. {h}")
            lines.append("")
            lines.append("Описания:")
            for i, d in enumerate(ad["Descriptions"], 1):
                lines.append(f"{i}. {d}")
            lines.append("")

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

    out_dir = client_stats_dir(args.client_folder)
    safe_campaign = args.campaign.replace("/", "-").strip()
    out_path = out_dir / f"gads_ads_{safe_campaign}.md"
    out_path.write_text(render_markdown(args.campaign, ads), encoding="utf-8")

    print(f"Сохранено: {out_path} ({len(ads)} объявлений)")


if __name__ == "__main__":
    main()
