#!/usr/bin/env python
# coding: utf-8
"""Строит гео-расширенные группы объявлений (ключи + RSA) для загрузки через Google Ads Editor.

Берёт из кампании-источника вручную отобранный список групп объявлений (--ad-groups):
активные ключевые слова (ad_group_criterion) и тексты RSA-объявлений — тем же
способом, что gads_semantics.py и gads_ads_dump.py, но напрямую через
ad_group_criterion, а не keyword_view (см. docstring fetch_keywords_by_group —
keyword_view молча пропускает ключи без статистики за период).

На каждую исходную группу строится ОДНА новая группа "<исходное имя> <group-suffix>"
(не по группе на geo-вариант!). Внутри неё каждое ключевое слово дублируется по
числу --geo: например --geo LA --geo "Los Angeles" даёt для ключа "car injury
lawyer" два новых ключа "car injury lawyer LA" и "car injury lawyer Los Angeles"
в одной группе "Car Injury LA". Текст объявления один на группу — упоминания
"CA"/"California" в нём заменяются на --ad-geo-text (по умолчанию "LA", а не
"Los Angeles" — на аккаунте Andverpersonalinjury проверено, что "Los Angeles"
почти везде выталкивает заголовки за лимит 30 символов, "LA" почти всегда
укладывается, см. Клиенты/Andverpersonalinjury/Решения.md).

Новые группы можно направить в другую (уже существующую) кампанию через
--target-campaign — например, у Andverpersonalinjury уже есть отдельная
кампания "search / all injuries / la" для гео-расширения, заполняемая вручную
по частям; этот скрипт достраивает в неё оставшиеся группы, не трогая исходную
"search / all injuries".

Только ENABLED-ключи (PAUSED/REMOVED пропускаются — не имеет смысла тиражировать
неактивную семантику).

Результат — один CSV в формате Google Ads Editor bulk upload (секции Keyword и
Responsive search ad вперемешку, как их принимает импорт по колонкам Campaign/
Ad group/Row type) в Клиенты/<client-folder>/Статистика/.

Использование:
    python gads_geo_ad_group_builder.py --customer-id 213-621-6123 \
        --client-folder "Юристы США" --campaign "search / all injuries" \
        --target-campaign "search / all injuries / la" \
        --ad-groups "Bicycle Injury,Dog Bite Injury,Motorcycle Injury,Pedestrian Injury,Slip and Fall Injury,Bus Injury" \
        --geo "LA" --geo "Los Angeles" --group-suffix "LA" --ad-geo-text "LA"
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


def build_rows(campaign_name, keywords_by_group, ads_by_group, geo_suffixes, group_suffix,
               ad_geo_text):
    """Строит плоский список строк для bulksheet CSV.

    По одной новой группе "<исходное имя> <group_suffix>" на исходную группу
    (не по группе на geo!) — внутри неё ключи дублируются в вариантах под каждый
    geo_suffixes (напр. "... LA" и "... Los Angeles" как отдельные ключи одной
    группы). Текст объявления один на группу — geo-упоминания в нём (CA/California)
    заменяются на ad_geo_text (обычно короткий вариант "LA", чтобы уложиться в
    лимит 30 символов заголовка — см. Клиенты/Andverpersonalinjury/Решения.md).
    """
    rows = []
    for group_name, keywords in keywords_by_group.items():
        if not keywords:
            continue
        new_group = f"{group_name} {group_suffix}"

        for text, match_type in keywords:
            for geo in geo_suffixes:
                if _contains_geo(text, geo):
                    # ключ уже содержит этот geo-вариант (напр. "...Los Angeles lawyer")
                    # — не дублировать его же суффиксом ещё раз.
                    continue
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
                new_text = _geo_replace(text, ad_geo_text)
                new_text = _shrink_keyword_insertion(new_text, limit=30)
                row[f"Headline {i}"] = new_text
                if pin:
                    row[f"Headline {i} position"] = pin.replace("H", "")
            for i, (text, pin) in enumerate(ad["Descriptions"], 1):
                row[f"Description {i}"] = _geo_replace(text, ad_geo_text)
                if pin:
                    row[f"Description {i} position"] = pin.replace("D", "")
            rows.append(row)

    return rows


_GEO_PATTERN = None


def _geo_replace(text, geo_text):
    """Заменяет 'CA'/'California' (целыми словами) на geo_text в тексте объявления."""
    import re
    global _GEO_PATTERN
    if _GEO_PATTERN is None:
        _GEO_PATTERN = re.compile(r"\bCalifornia\b|\bCA\b")
    return _GEO_PATTERN.sub(geo_text, text)


def _contains_geo(keyword_text, geo):
    """True, если keyword_text уже содержит geo как отдельное слово/фразу (регистронезависимо).

    Нужно, чтобы не дублировать geo-суффикс на ключах, где он уже есть
    (напр. исходный ключ "trip and fall attorney LA" не должен получить ещё
    один суффикс "LA" поверх, см. Клиенты/Andverpersonalinjury/Решения.md).
    """
    import re
    pattern = r"\b" + re.escape(geo) + r"\b"
    return re.search(pattern, keyword_text, re.IGNORECASE) is not None


def _shrink_keyword_insertion(text, limit=30):
    """Укорачивает дефолтный текст динамической вставки {KeyWord:...} до limit символов.

    Google Ads показывает текст после двоеточия, только если он умещается в
    заголовок (30 симв.) — иначе объявление с таким дефолтом Editor отклоняет
    при импорте. Обрезка идёт по границе слов с конца, без многоточия (сам
    формат {KeyWord:...} не поддерживает произвольные символы после текста).
    Если фигурных скобок в строке нет — строка возвращается как есть.
    """
    import re
    m = re.match(r"^\{KeyWord:(.+)\}$", text)
    if not m:
        return text
    inner = m.group(1)
    if len(inner) <= limit:
        return text
    words = inner.split(" ")
    while words and len(" ".join(words)) > limit:
        words.pop()
    return "{KeyWord:" + " ".join(words) + "}"


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


def _displayed_length(text):
    """Длина текста, которую реально проверяет Google Ads на лимит.

    Для {KeyWord:...}/{LOCATION(...):...} лимит применяется к тексту ПОСЛЕ
    двоеточия (то, что реально показывается как дефолт/подстановка), не к
    синтаксической обёртке целиком. Вставка может быть частью более длинной
    строки (напр. "Injured In {LOCATION(City):California}?"), не только всей
    строкой — заменяем её на видимый текст внутри строки, не требуем полного
    совпадения (см. gads_ad_adapter.py, тот же принцип).
    """
    import re
    resolved = re.sub(r"\{KeyWord:([^}]+)\}", r"\1", text)
    resolved = re.sub(r"\{LOCATION\([^)]*\):([^}]+)\}", r"\1", resolved)
    return len(resolved)


def check_length_limits(rows):
    """Печатает предупреждения по строкам объявлений, превышающим лимиты Google Ads

    (30 символов на Headline, 90 на Description) — включая случаи, унаследованные
    из исходного объявления, не только те, что возникли из-за geo-замены.
    """
    warnings = []
    for row in rows:
        if row["Row Type"] != "Responsive search ad":
            continue
        for i in range(1, 16):
            text = row.get(f"Headline {i}")
            n = _displayed_length(text) if text else 0
            if text and n > 30:
                warnings.append(f"  [{row['Ad group']}] Headline {i} ({n} симв.): {text}")
        for i in range(1, 5):
            text = row.get(f"Description {i}")
            n = _displayed_length(text) if text else 0
            if text and n > 90:
                warnings.append(f"  [{row['Ad group']}] Description {i} ({n} симв.): {text}")
    if warnings:
        print(f"\nВНИМАНИЕ: {len(warnings)} строк объявлений превышают лимит символов Google Ads "
              "(Editor их не примет без ручной правки):")
        for w in warnings:
            print(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True, help="Формат XXX-XXX-XXXX или без дефисов")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--campaign", required=True,
                     help='Точное название кампании-источника (откуда берутся ключи/объявления), '
                          'напр. "search / all injuries"')
    ap.add_argument("--target-campaign",
                     help='Название кампании, ПОД которой в CSV должны оказаться новые группы '
                          '(напр. уже существующая "search / all injuries / la"). По умолчанию — '
                          'то же, что --campaign.')
    ap.add_argument("--ad-groups", required=True,
                     help='Список исходных групп через запятую, которые нужно взять для гео-расширения '
                          '(остальные группы кампании игнорируются), напр. '
                          '"Bicycle Injury,Dog Bite Injury,Motorcycle Injury"')
    ap.add_argument("--group-suffix", default="LA",
                     help='Суффикс имени новой группы, напр. "Car Injury" -> "Car Injury LA". По умолчанию "LA".')
    ap.add_argument("--geo", action="append", required=True,
                     help='Вариант geo-суффикса, добавляемый к тексту КАЖДОГО ключевого слова как отдельный '
                          'дубль внутри новой группы. Повторить флаг для нескольких '
                          '(напр. --geo "LA" --geo "Los Angeles" даёт по 2 варианта на каждый исходный ключ).')
    ap.add_argument("--ad-geo-text", default="LA",
                     help='Чем заменять "CA"/"California" в текстах объявлений (заголовки/описания). '
                          'По умолчанию "LA" — короче, обычно укладывается в лимит 30 символов заголовка.')
    args = ap.parse_args()

    customer_id = args.customer_id.replace("-", "").strip()
    target_campaign = args.target_campaign or args.campaign
    selected_groups = [g.strip() for g in args.ad_groups.split(",") if g.strip()]

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | источник: {args.campaign} -> цель: {target_campaign}")
    print(f"Группы: {', '.join(selected_groups)} | geo-варианты ключей: {', '.join(args.geo)} "
          f"| geo в тексте объявления: {args.ad_geo_text}")

    keywords_by_group_all = fetch_keywords_by_group(ga_service, customer_id, args.campaign)
    ads_by_group_all = fetch_ads_by_group(ga_service, customer_id, args.campaign)

    missing = [g for g in selected_groups if g not in keywords_by_group_all]
    if missing:
        print(f"ВНИМАНИЕ: группы не найдены (или без активных ключей) в кампании: {', '.join(missing)}")

    keywords_by_group = {g: keywords_by_group_all[g] for g in selected_groups if g in keywords_by_group_all}
    if not keywords_by_group:
        print("Ни одной подходящей группы не найдено — проверь названия --ad-groups")
        return
    ads_by_group = {g: ads_by_group_all[g] for g in selected_groups if g in ads_by_group_all}

    rows = build_rows(target_campaign, keywords_by_group, ads_by_group, args.geo,
                       args.group_suffix, args.ad_geo_text)
    check_length_limits(rows)

    out_dir = client_stats_dir(args.client_folder)
    safe_campaign = target_campaign.replace("/", "-").strip()
    safe_geo = "_".join(g.replace(" ", "") for g in args.geo)
    out_path = out_dir / f"gads_geo_bulksheet_{safe_campaign}_{safe_geo}.csv"
    write_csv(rows, out_path)

    print(f"\nСохранено: {out_path} ({len(keywords_by_group)} новых групп, {len(rows)} строк)")
    print("Импорт: Google Ads Editor -> Account -> Import -> From File, выбрать 'Use Campaign/Ad group "
          "columns' при маппинге, проверить diff перед Post.")


if __name__ == "__main__":
    main()
