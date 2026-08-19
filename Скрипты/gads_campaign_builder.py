#!/usr/bin/env python
# coding: utf-8
"""Собирает новую кампанию "с нуля" из словаря тем: группы + ключи + объявления + sitelinks.

Комбинирует три уже существующих строительных блока в один bulksheet CSV:
  - gads_semantics_generator.generate_phrases — broad/phrase-семантика по теме
    из Словарь-тем.yaml (тема x modifier x suffix).
  - gads_ad_adapter.build_ad_row / build_sitelink_rows — адаптированное RSA-
    объявление по эталону (Эталонное-объявление-и-sitelinks.yaml) и sitelinks
    на уровень кампании.

В отличие от gads_geo_ad_group_builder.py (который РАСШИРЯЕТ существующую
кампанию гео-вариантами уже загруженных ключей) этот скрипт строит кампанию
С НУЛЯ: новые группы называются "<label темы>" (без гео-суффикса) и заполняются
ИСКУССТВЕННО сгенерированной семантикой из словаря, не копией существующих
ключей — см. Клиенты/Andverpersonalinjury/Решения.md, запись про кампанию
"search / all injuries / broad".

Ключи заводятся с match type PHRASE (не BROAD, несмотря на название задачи
"широкая семантика" — так же, как уже загруженные вручную ключи в LA-кампаниях,
для консистентности). Ничего не тянет из Google Ads API и не пишет в аккаунт —
только читает Словарь-тем.yaml + эталон и собирает CSV для ручного импорта.

Использование:
    python gads_campaign_builder.py --client-folder "Юристы США" \
        --campaign "search / all injuries / broad" \
        --theme car --theme auto --theme motorcycle --theme truck \
        --theme 18_wheeler --theme bus --theme bicycle --theme rideshare \
        --theme pedestrian --theme slip_and_fall --theme dog_bite
"""
import argparse
import csv

from gads_ad_adapter import (
    build_ad_row,
    build_sitelink_rows,
    check_length_limits,
    load_dictionary,
    load_reference_ad,
)
from gads_semantics_generator import generate_phrases


def build_campaign_row(campaign_name, budget, status="Paused"):
    """Строит строку 'Campaign' с минимальными полями.

    Bulksheet-импорт группы/ключи/объявления обычно требует, чтобы кампания
    уже существовала — эта строка заводит её с нуля прямо тем же CSV. Бюджет
    и статус обязательны для создания; таргетинг/сети/расписание остаются на
    ручную настройку в Editor/интерфейсе после импорта — CSV их не задаёт.
    Статус по умолчанию Paused — чтобы кампания не начала показываться сразу
    по импорту, до ручной проверки бюджета и таргетинга (см. Решения.md).
    """
    return {
        "Row Type": "Campaign",
        "Campaign": campaign_name,
        "Campaign Type": "Search",
        "Budget": budget,
        "Status": status,
        "Networks": "Google search",
    }


def build_keyword_rows(campaign_name, theme_key, theme_data, match_type="PHRASE"):
    """Строит строки 'Keyword' для одной темы -> одна новая группа "<label>"."""
    label = theme_data.get("label", theme_key)
    group_name = label

    phrase_data = dict(theme_data)
    phrase_data.setdefault("text", theme_key.replace("_", " "))
    phrases = generate_phrases(phrase_data)

    rows = []
    for phrase in phrases:
        rows.append({
            "Row Type": "Keyword",
            "Campaign": campaign_name,
            "Ad group": group_name,
            "Keyword": phrase,
            "Match Type": match_type,
        })
    return rows, group_name


FIELDNAMES = (
    ["Row Type", "Campaign", "Campaign Type", "Budget", "Status", "Networks",
     "Ad group", "Keyword", "Match Type", "Final URL"]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--campaign", required=True,
                     help='Название НОВОЙ кампании, напр. "search / all injuries / broad"')
    ap.add_argument("--theme", action="append",
                     help="Ключ темы из словаря. Повторить флаг для нескольких. По умолчанию — все темы словаря.")
    ap.add_argument("--match-type", default="PHRASE", choices=["PHRASE", "BROAD", "EXACT"],
                     help="Тип соответствия для сгенерированных ключей. По умолчанию PHRASE "
                          "(консистентно с уже загруженными вручную ключами в LA-кампаниях).")
    ap.add_argument("--budget", type=float, default=50.0,
                     help="Дневной бюджет новой кампании в валюте аккаунта. По умолчанию 50 — "
                          "заглушка, скорректировать вручную в Editor/интерфейсе перед запуском.")
    ap.add_argument("--no-campaign-row", action="store_true",
                     help="Не добавлять строку 'Campaign' — использовать, если кампания уже создана вручную")
    ap.add_argument("--no-ads", action="store_true", help="Не добавлять объявления (только группы+ключи)")
    ap.add_argument("--no-sitelinks", action="store_true", help="Не добавлять sitelinks на уровень кампании")
    ap.add_argument("--out", help="Путь к .csv файлу. По умолчанию — Клиенты/<client-folder>/Статистика/gads_campaign_<campaign>.csv")
    args = ap.parse_args()

    dictionary = load_dictionary(args.client_folder)
    reference_ad = None if args.no_ads else load_reference_ad(args.client_folder)

    theme_keys = args.theme or list(dictionary.keys())
    missing = [t for t in theme_keys if t not in dictionary]
    if missing:
        print(f"ВНИМАНИЕ: тем нет в словаре: {', '.join(missing)} (доступные: {', '.join(dictionary.keys())})")

    rows = []
    if not args.no_campaign_row:
        rows.append(build_campaign_row(args.campaign, args.budget))

    n_groups = 0
    for theme_key in theme_keys:
        if theme_key not in dictionary:
            continue
        theme_data = dictionary[theme_key]

        kw_rows, group_name = build_keyword_rows(args.campaign, theme_key, theme_data, args.match_type)
        rows.extend(kw_rows)
        n_groups += 1

        if reference_ad is not None:
            ad_phrase = theme_data.get("ad_phrase")
            if ad_phrase:
                rows.append(build_ad_row(args.campaign, group_name, reference_ad, ad_phrase))
            else:
                print(f"ВНИМАНИЕ: у темы '{theme_key}' нет поля ad_phrase — объявление для группы '{group_name}' не создано")

    if reference_ad is not None and not args.no_sitelinks:
        rows.extend(build_sitelink_rows(args.campaign, reference_ad))

    check_length_limits(rows)

    if args.out:
        out_path = args.out
    else:
        from _config import client_stats_dir
        out_dir = client_stats_dir(args.client_folder)
        safe_campaign = args.campaign.replace("/", "-").strip()
        out_path = out_dir / f"gads_campaign_{safe_campaign}.csv"
    write_csv(rows, out_path)

    n_keywords = sum(1 for r in rows if r["Row Type"] == "Keyword")
    n_ads = sum(1 for r in rows if r["Row Type"] == "Responsive search ad")
    n_sitelinks = sum(1 for r in rows if r["Row Type"] == "Sitelink")
    print(f"\nСохранено: {out_path}")
    print(f"  {n_groups} групп, {n_keywords} ключей, {n_ads} объявлений, {n_sitelinks} sitelinks")
    if not args.no_campaign_row:
        print(f"  + строка Campaign (бюджет {args.budget}/день, статус Paused — исправить перед запуском)")
        print("ВАЖНО: перед импортом проверить/поправить бюджет и вручную настроить гео-таргетинг "
              "и стратегию назначения ставок в Editor — CSV их не задаёт.")
    print("Импорт: Google Ads Editor -> Account -> Import -> From File, выбрать 'Use Campaign/Ad group "
          "columns' при маппинге, проверить diff перед Post.")


if __name__ == "__main__":
    main()
