#!/usr/bin/env python
# coding: utf-8
"""Создаёт look-alike список аудитории (UserListService.mutate_user_lists, lookalike_user_list)
по одному или нескольким спискам-основам. Общий скрипт, привязок к клиенту нет. 2026-11-23.

Зачем: look-alike для Demand Gen / Display / YouTube создаётся одной и той же операцией; раньше она
была зашита в gads_demand_gen_builder.py (create_lookalike, под ProfiMet).

Что делает:
  1. Читает списки-основы (имя, тип, размер Display/Search, статус) и печатает: от чего строится.
  2. Показывает план: было (есть ли уже look-alike с таким именем) -> станет.
  3. Отправляет mutate_user_lists. По умолчанию validate_only: Google проверяет, ничего не создаёт.
  4. Только с --execute: создаёт и читает список обратно GAQL (id, name, type, size, статус, seed).

Режимы: проверка (по умолчанию, validate_only) | запись (--execute). Публикации/привязки к кампаниям нет.
Размер основы: у списка-основы должно быть достаточно участников (Google требует ~100+ в сети за 30 дней),
иначе validate_only вернёт ошибку.

Уровни: NARROW = 2.5% охвата страны, BALANCED = 5%, BROAD = 10%.
Имя по умолчанию: "look-a-like / crm customers / 2.5% narrow ГГГГММДД" (для другого типа основы задайте --name).

Ключи: берутся из gads_stats.GOOGLE_ADS_YAML (secrets/google-ads.yaml), в вывод не печатаются.

Примеры:
    python gads_lookalike_create.py --customer-id 8826134558 --seed-list-id 9475706784 --level NARROW --country PL
    python gads_lookalike_create.py --customer-id <ID> --seed-list-id 111 222 --level BALANCED --country PL DE --execute
"""
import argparse
import sys
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

LEVELS = {"NARROW": "2.5%", "BALANCED": "5%", "BROAD": "10%"}


def read_lists(client, cid, ids=None, name=None):
    """Читает списки аудитории: по id или по точному имени. Возвращает список dict."""
    ga = client.get_service("GoogleAdsService")
    where = []
    if ids:
        where.append("user_list.id IN (%s)" % ",".join(str(int(i)) for i in ids))
    if name:
        where.append("user_list.name = '%s'" % name.replace("\\", "\\\\").replace("'", "\\'"))
    q = ("SELECT user_list.id, user_list.name, user_list.type, user_list.size_range_for_display, "
         "user_list.size_range_for_search, user_list.size_for_display, user_list.size_for_search, "
         "user_list.membership_status, user_list.membership_life_span, "
         "user_list.lookalike_user_list.seed_user_list_ids, user_list.lookalike_user_list.expansion_level, "
         "user_list.lookalike_user_list.country_codes FROM user_list WHERE " + " AND ".join(where))
    out = []
    en = client.enums

    def nm(enum_cls, v):
        try:
            return enum_cls.DESCRIPTOR.enum_types[0].values_by_number[int(v)].name
        except Exception:
            return str(v)

    for r in ga.search(customer_id=cid, query=q):
        u = r.user_list
        out.append({
            "id": u.id, "name": u.name, "type": nm(en.UserListTypeEnum, u.type_),
            "size_display": u.size_for_display, "size_search": u.size_for_search,
            "range_display": nm(en.UserListSizeRangeEnum, u.size_range_for_display), "range_search": nm(en.UserListSizeRangeEnum, u.size_range_for_search),
            "status": nm(en.UserListMembershipStatusEnum, u.membership_status), "life_span": u.membership_life_span,
            "seed": list(u.lookalike_user_list.seed_user_list_ids),
            "level": nm(en.LookalikeExpansionLevelEnum, u.lookalike_user_list.expansion_level),
            "countries": list(u.lookalike_user_list.country_codes),
        })
    return out


def print_lists(title, rows):
    print(title)
    if not rows:
        print("  (нет)")
    for x in rows:
        line = (f"  id={x['id']} | {x['name']} | тип={x['type']} | размер Display={x['size_display']} ({x['range_display']}) "
                f"| Search={x['size_search']} ({x['range_search']}) | статус={x['status']} | срок={x['life_span']} дн.")
        if x["type"] == "LOOKALIKE":
            line += f" | seed={x['seed']} | уровень={x['level']} | страны={x['countries']}"
        print(line)


def main():
    ap = argparse.ArgumentParser(description="Создать look-alike список по спискам-основам (по умолчанию validate_only)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--seed-list-id", type=int, nargs="+", required=True, help="id списка(ов)-основы")
    ap.add_argument("--level", choices=list(LEVELS), default="NARROW", help="NARROW 2.5%% | BALANCED 5%% | BROAD 10%%")
    ap.add_argument("--country", nargs="+", default=["PL"], help="коды стран, по умолчанию PL")
    ap.add_argument("--name", help="имя списка; по умолчанию 'look-a-like / crm customers / 2.5%% narrow ГГГГММДД'")
    ap.add_argument("--description", help="описание списка (по умолчанию формируется из уровня и основ)")
    ap.add_argument("--life-span", type=int, default=540, help="срок членства, дней (по умолчанию 540)")
    ap.add_argument("--execute", action="store_true", help="создать на самом деле (без флага — validate_only)")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    cid = a.customer_id.replace("-", "")
    name = a.name or f"look-a-like / crm customers / {LEVELS[a.level]} {a.level.lower()} " + datetime.now().strftime("%Y%m%d")
    desc = a.description or f"Look-alike {a.level} ({LEVELS[a.level]}) от списков {', '.join(map(str, a.seed_list_id))}"

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    try:
        seeds = read_lists(client, cid, ids=a.seed_list_id)
        print_lists(f"Списки-основы (customer {cid}):", seeds)
        found = {x["id"] for x in seeds}
        missing = [i for i in a.seed_list_id if i not in found]
        if missing:
            print("ОШИБКА: списки-основы не найдены:", missing)
            sys.exit(2)

        before = read_lists(client, cid, name=name)
        print_lists("Было (списки с таким именем):", before)
        print(f"Станет: новый look-alike '{name}', уровень {a.level} ({LEVELS[a.level]}), страны {a.country}, "
              f"основы {a.seed_list_id}, срок {a.life_span} дн. Режим: {'ЗАПИСЬ' if a.execute else 'validate_only'}")
        if before:
            print("ВНИМАНИЕ: список с таким именем уже есть; Google может отклонить дубль имени (задайте --name).")

        svc = client.get_service("UserListService")
        op = client.get_type("UserListOperation")
        ul = op.create
        ul.name = name
        ul.description = desc
        ul.membership_life_span = a.life_span
        for s in a.seed_list_id:
            ul.lookalike_user_list.seed_user_list_ids.append(s)
        ul.lookalike_user_list.expansion_level = getattr(client.enums.LookalikeExpansionLevelEnum, a.level)
        for c in a.country:
            ul.lookalike_user_list.country_codes.append(c)
        req = client.get_type("MutateUserListsRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not a.execute
        resp = svc.mutate_user_lists(request=req)

        if not a.execute:
            print("Проверка пройдена. НИЧЕГО не создано (validate_only). Для записи добавьте --execute.")
            return
        rn = resp.results[0].resource_name
        print("Создан look-alike:", rn)
        new_id = int(rn.split("/")[-1])
        print_lists("Стало (прочитано обратно из аккаунта):", read_lists(client, cid, ids=[new_id]))
    except GoogleAdsException as ex:
        print("GoogleAdsException:", ex.request_id)
        for e in ex.failure.errors:
            print("  ", e.error_code, "-", e.message)
        sys.exit(1)


if __name__ == "__main__":
    main()
