#!/usr/bin/env python
# coding: utf-8
"""Генерирует широкие (broad) ключевые фразы из словаря тем/синонимов клиента.

Читает Клиенты/<client-folder>/Семантика/Словарь-тем.yaml: на каждую тему
(car, motorcycle, slip_and_fall, ...) — свой набор modifiers (существительные
происшествия, специфичные для темы — "accident/crash" звучит для транспортных
тем, но не для slip and fall/dog bite, см. Клиенты/Юристы США/Решения.md) и
общий suffixes (lawyer/attorney). Строит все комбинации "<тема> <modifier>
<suffix>" как broad-фразы.

Опционально (--geo) достраивает гео-вариант на каждую сгенерированную фразу —
та же идея дублирования, что в gads_geo_ad_group_builder.py, но здесь без
привязки к существующей группе/аккаунту: это шаг ДО группировки.

Ничего не тянет из Google Ads API и не пишет в аккаунт — только читает словарь
и печатает/сохраняет список фраз для ручного просмотра и одобрения. Сверка
"что уже загружено в аккаунте" и раскладка по группам/объявлениям в CSV —
отдельные последующие шаги (см. gads_geo_ad_group_builder.py для второго).

Использование:
    python gads_semantics_generator.py --client-folder "Юристы США"
    python gads_semantics_generator.py --client-folder "Юристы США" --theme car --theme motorcycle
    python gads_semantics_generator.py --client-folder "Юристы США" --theme car --geo LA --geo "Los Angeles"
    python gads_semantics_generator.py --client-folder "Юристы США" --out phrases.txt
"""
import argparse

import yaml

VAULT_ROOT_MARKER = "Клиенты"


def _dictionary_path(client_folder):
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    vault_root = os.path.dirname(here)
    return os.path.join(vault_root, "Клиенты", client_folder, "Семантика", "Словарь-тем.yaml")


def load_dictionary(client_folder):
    path = _dictionary_path(client_folder)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def generate_phrases(theme_data, geo_suffixes=None):
    """Строит broad-фразы для одной темы -> список строк.

    "<тема-текст> <modifier> <suffix>" на каждую комбинацию modifiers x suffixes;
    если modifiers пуст (тема без естественного модификатора, напр.
    wrongful_death) — фраза строится как "<тема-текст> <suffix>" напрямую.
    Если geo_suffixes задан, каждая фраза дублируется с добавлением geo в конце
    (как отдельная дополнительная фраза, не замена).
    """
    theme_text = theme_data["text"]
    modifiers = theme_data.get("modifiers") or [None]
    suffixes = theme_data.get("suffixes", [])

    phrases = []
    for modifier in modifiers:
        for suffix in suffixes:
            parts = [theme_text]
            if modifier:
                parts.append(modifier)
            parts.append(suffix)
            phrases.append(" ".join(parts))

    if geo_suffixes:
        with_geo = []
        for phrase in phrases:
            for geo in geo_suffixes:
                with_geo.append(f"{phrase} {geo}")
        phrases = with_geo

    return phrases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--theme", action="append",
                     help="Ключ темы из словаря (напр. car, slip_and_fall). Повторить флаг для нескольких. "
                          "По умолчанию — все темы словаря.")
    ap.add_argument("--geo", action="append",
                     help='Опционально: добавить гео-вариант к каждой фразе (можно несколько раз, '
                          'напр. --geo "LA" --geo "Beverly Hills"). По умолчанию фразы без гео.')
    ap.add_argument("--out", help="Путь к .txt файлу для сохранения результата (по умолчанию — только на экран)")
    args = ap.parse_args()

    dictionary = load_dictionary(args.client_folder)

    theme_keys = args.theme or list(dictionary.keys())
    missing = [t for t in theme_keys if t not in dictionary]
    if missing:
        print(f"ВНИМАНИЕ: тем нет в словаре: {', '.join(missing)} (доступные: {', '.join(dictionary.keys())})")

    lines = []
    total = 0
    for theme_key in theme_keys:
        if theme_key not in dictionary:
            continue
        theme_data = dict(dictionary[theme_key])
        theme_data["text"] = theme_key.replace("_", " ")
        label = dictionary[theme_key].get("label", theme_key)

        phrases = generate_phrases(theme_data, args.geo)
        total += len(phrases)

        lines.append(f"=== {theme_key} ({label}) — {len(phrases)} фраз ===")
        lines.extend(phrases)
        lines.append("")

    output = "\n".join(lines)
    print(output)
    print(f"Итого фраз: {total}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\nСохранено: {args.out}")


if __name__ == "__main__":
    main()
