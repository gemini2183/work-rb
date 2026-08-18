#!/usr/bin/env python
# coding: utf-8
"""Адаптирует эталонное RSA-объявление под новые тематические группы + готовит sitelinks.

Читает Клиенты/<client-folder>/Кампании/Search/Эталонное-объявление-и-sitelinks.yaml
(снятый вручную образец: headlines/descriptions с ролью "themed" или "universal",
плюс список sitelinks) и Клиенты/<client-folder>/Семантика/Словарь-тем.yaml
(поле ad_phrase на тему — см. Клиенты/Юристы США/Решения.md).

Для каждой темы (--theme, по умолчанию все темы словаря) строит одно RSA-объявление
на группу "<label темы> <group-suffix>" (та же схема имени группы, что в
gads_geo_ad_group_builder.py): headlines/descriptions с role=themed получают
{ad_phrase} и {ad_phrase_title} (capitalize по словам) из словаря темы,
role=universal копируются из эталона без изменений.

Отдельно (--with-sitelinks) готовит CSV-блок sitelinks на уровень КАМПАНИИ
(не группы) — по одобренному решению они одинаковы для всех тем, заливаются
один раз на кампанию, не дублируются на каждую группу.

Ничего не тянет из Google Ads API и не пишет в аккаунт — только читает два
YAML-файла и собирает CSV в формате Google Ads Editor bulk upload для ручного
импорта, тем же файлом что и группы/ключи от gads_geo_ad_group_builder.py можно
сливать вручную перед импортом (или импортировать отдельно).

Использование:
    python gads_ad_adapter.py --client-folder "Юристы США" \
        --campaign "search / all injuries / la" --group-suffix "LA" \
        --theme bicycle --theme dog_bite --theme motorcycle --with-sitelinks
"""
import argparse
import csv
import os

import yaml


def _vault_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _dictionary_path(client_folder):
    return os.path.join(_vault_root(), "Клиенты", client_folder, "Семантика", "Словарь-тем.yaml")


def _reference_ad_path(client_folder):
    return os.path.join(_vault_root(), "Клиенты", client_folder, "Кампании", "Search",
                         "Эталонное-объявление-и-sitelinks.yaml")


def load_dictionary(client_folder):
    with open(_dictionary_path(client_folder), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_reference_ad(client_folder):
    with open(_reference_ad_path(client_folder), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _title_case(phrase):
    """Капитализация каждого слова фразы: 'car accident' -> 'Car Accident'."""
    return " ".join(w.capitalize() for w in phrase.split(" "))


_SHORTEN_PATTERNS = [" in CA", " CA", "CA "]


def adapt_line(text, ad_phrase, limit=None):
    """Подставляет {ad_phrase}/{ad_phrase_title} в текст headline/description; {{...}} -> {...} (экранирование YAML).

    Если limit задан и итоговый текст его превышает (после подстановки —
    длинные темы вроде "motorcycle accident"/"slip and fall accident" не
    влезают там, где влезал короткий эталонный "car accident"), пробует
    укоротить, срезая geo-хвост "in CA"/"CA" по очереди — это не тема-специфика,
    а общий для всех тем "довесок", им можно пожертвовать первым (см.
    Клиенты/Юристы США/Решения.md). Если после всех попыток всё ещё длиннее
    limit — возвращает как есть (уйдёт в предупреждение check_length_limits,
    останется на ручную правку).
    """
    ad_phrase_title = _title_case(ad_phrase)
    result = (
        text
        .replace("{ad_phrase_title}", ad_phrase_title)
        .replace("{ad_phrase}", ad_phrase)
        .replace("{{", "{")
        .replace("}}", "}")
    )
    if limit is None or len(result) <= limit:
        return result

    for pattern in _SHORTEN_PATTERNS:
        if pattern in result:
            shortened = result.replace(pattern, " ", 1)
            shortened = " ".join(shortened.split())  # схлопнуть двойные пробелы
            # восстановить знак препинания в конце, если replace его не задел
            if result.rstrip().endswith(("?", ".")) and not shortened.rstrip().endswith(("?", ".")):
                shortened = shortened.rstrip() + result.rstrip()[-1]
            if len(shortened) <= limit:
                return shortened
            result = shortened  # укоротили, но всё ещё длинно — пробуем следующий паттерн
    return result


def build_ad_row(campaign_name, group_name, reference_ad, ad_phrase):
    """Строит одну строку 'Responsive search ad' для bulksheet CSV на одну новую группу."""
    row = {
        "Row Type": "Responsive search ad",
        "Campaign": campaign_name,
        "Ad group": group_name,
        "Final URL": reference_ad.get("final_url", ""),
    }
    for i, h in enumerate(reference_ad.get("headlines", []), 1):
        row[f"Headline {i}"] = adapt_line(h["text"], ad_phrase, limit=30)
        if h.get("pin"):
            row[f"Headline {i} position"] = h["pin"].replace("H", "")
    for i, d in enumerate(reference_ad.get("descriptions", []), 1):
        row[f"Description {i}"] = adapt_line(d["text"], ad_phrase, limit=90)
        if d.get("pin"):
            row[f"Description {i} position"] = d["pin"].replace("D", "")
    return row


def build_sitelink_rows(campaign_name, reference_ad):
    """Строит строки 'Sitelink' на уровень кампании (Ad group не заполняется — привязка campaign-wide)."""
    rows = []
    for sl in reference_ad.get("sitelinks", []):
        rows.append({
            "Row Type": "Sitelink",
            "Campaign": campaign_name,
            "Ad group": "",
            "Final URL": sl.get("final_url", ""),
            "Link Text": sl.get("link_text", ""),
            "Description Line 1": sl.get("description1", ""),
            "Description Line 2": sl.get("description2", ""),
        })
    return rows


FIELDNAMES = (
    ["Row Type", "Campaign", "Ad group", "Final URL"]
    + [f"Headline {i}" for i in range(1, 16)]
    + [f"Headline {i} position" for i in range(1, 16)]
    + [f"Description {i}" for i in range(1, 5)]
    + [f"Description {i} position" for i in range(1, 5)]
    + ["Link Text", "Description Line 1", "Description Line 2"]
)


def write_csv(rows, out_path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def check_length_limits(rows):
    """Та же проверка лимитов Google Ads, что в gads_geo_ad_group_builder.py — переиспользуется логика.

    Дополнительно распознаёт {LOCATION(...):default}, не только {KeyWord:...} —
    у обеих вставок лимит считается по видимому тексту после раскрытия
    (для LOCATION это то, что после последнего ":", не default-надпись целиком
    с синтаксисом), см. Клиенты/Юристы США/Решения.md.
    """
    import re

    def displayed_length(text):
        # {KeyWord:...}/{LOCATION(...):...} могут быть частью более длинной
        # строки (напр. "Injured In {LOCATION(City):California}?"), не только
        # всей строкой целиком — заменяем вставку на её видимый текст (default
        # после последнего ":") внутри строки, потом считаем итоговую длину.
        resolved = re.sub(r"\{KeyWord:([^}]+)\}", r"\1", text)
        resolved = re.sub(r"\{LOCATION\([^)]*\):([^}]+)\}", r"\1", resolved)
        return len(resolved)

    warnings = []
    for row in rows:
        if row["Row Type"] != "Responsive search ad":
            continue
        for i in range(1, 16):
            text = row.get(f"Headline {i}")
            n = displayed_length(text) if text else 0
            if text and n > 30:
                warnings.append(f"  [{row['Ad group']}] Headline {i} ({n} симв.): {text}")
        for i in range(1, 5):
            text = row.get(f"Description {i}")
            n = displayed_length(text) if text else 0
            if text and n > 90:
                warnings.append(f"  [{row['Ad group']}] Description {i} ({n} симв.): {text}")
    if warnings:
        print(f"\nВНИМАНИЕ: {len(warnings)} строк превышают лимит символов Google Ads:")
        for w in warnings:
            print(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--campaign", required=True,
                     help='Кампания, в которую пойдут новые объявления/sitelinks, напр. "search / all injuries / la"')
    ap.add_argument("--group-suffix", default="",
                     help='Суффикс имени группы, добавляемый после label темы через пробел '
                          '(напр. "LA" -> "Bicycle Injury LA"). По умолчанию пусто — имя группы = label темы.')
    ap.add_argument("--theme", action="append",
                     help="Ключ темы из словаря. Повторить флаг для нескольких. По умолчанию — все темы словаря.")
    ap.add_argument("--with-sitelinks", action="store_true",
                     help="Добавить в CSV блок sitelinks на уровень кампании (один раз, не по группам)")
    ap.add_argument("--out", help="Путь к .csv файлу. По умолчанию — Клиенты/<client-folder>/Статистика/gads_ads_<campaign>.csv")
    args = ap.parse_args()

    dictionary = load_dictionary(args.client_folder)
    reference_ad = load_reference_ad(args.client_folder)

    theme_keys = args.theme or list(dictionary.keys())
    missing = [t for t in theme_keys if t not in dictionary]
    if missing:
        print(f"ВНИМАНИЕ: тем нет в словаре: {', '.join(missing)} (доступные: {', '.join(dictionary.keys())})")

    rows = []
    for theme_key in theme_keys:
        if theme_key not in dictionary:
            continue
        theme_data = dictionary[theme_key]
        ad_phrase = theme_data.get("ad_phrase")
        if not ad_phrase:
            print(f"ВНИМАНИЕ: у темы '{theme_key}' нет поля ad_phrase в словаре — пропущена")
            continue
        label = theme_data.get("label", theme_key)
        group_name = f"{label} {args.group_suffix}".strip()

        rows.append(build_ad_row(args.campaign, group_name, reference_ad, ad_phrase))

    if args.with_sitelinks:
        rows.extend(build_sitelink_rows(args.campaign, reference_ad))

    check_length_limits(rows)

    if args.out:
        out_path = args.out
    else:
        from _config import client_stats_dir
        out_dir = client_stats_dir(args.client_folder)
        safe_campaign = args.campaign.replace("/", "-").strip()
        out_path = out_dir / f"gads_ads_{safe_campaign}.csv"
    write_csv(rows, out_path)

    n_ads = sum(1 for r in rows if r["Row Type"] == "Responsive search ad")
    n_sitelinks = sum(1 for r in rows if r["Row Type"] == "Sitelink")
    print(f"\nСохранено: {out_path} ({n_ads} объявлений, {n_sitelinks} sitelinks)")


if __name__ == "__main__":
    main()
