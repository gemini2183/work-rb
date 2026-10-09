#!/usr/bin/env python
# coding: utf-8
"""Гео-таргетинг кампании OpenAI Ads (реклама в ChatGPT): список городов клиента -> почтовые индексы.

В OpenAI Ads нет городов: локации задаются штатом, рынком DMA или почтовым индексом.
Поэтому город из списка клиента переводится в набор индексов.

Подкоманды:
    resolve — ТОЛЬКО ЧТЕНИЕ. По списку локаций (файл «Название|тип») и таблице индексов GeoNames
              (US.txt, https://download.geonames.org/export/zip/US.zip) подбирает индексы Калифорнии,
              проверяет каждый в поиске локаций OpenAI (/geo_lookup/search) и пишет план в JSON.
    apply   — меняет locations.include у кампании на состав из плана. По умолчанию печатает
              «было -> станет» и ничего не пишет; запись только с --execute, после неё локации
              читаются обратно и печатается фактическое состояние.

Как подбираются индексы (границы индекса и города не совпадают, это приближение):
    city   — индексы, где название места в GeoNames (USPS) равно названию города. Районы города
             с собственным названием (например, Van Nuys у Los Angeles) таким способом не попадают.
    county — индексы, у которых в GeoNames указан этот округ (Orange County -> округ Orange).
    market — рынок DMA ищется по названию в OpenAI, индексы не подбираются.
ID индекса в OpenAI = 9 000 000 + индекс; каждый всё равно проверяется поиском.

Использование:
    python openai_ads_geo.py resolve --locations <файл> --zips <US.txt> --out <plan.json>
    python openai_ads_geo.py apply   --campaign cmpn_... --plan <plan.json>              # план
    python openai_ads_geo.py apply   --campaign cmpn_... --plan <plan.json> --execute    # запись

Ключ и вызовы API — как в openai_ads.py (переменная OPENAI_ADS_API_KEY, curl, значение не печатается).
"""
import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from openai_ads import call

MAX_LOCATIONS = 2500  # лимит ID на кампанию (docs/запись базы знаний от 2026-10-07)


def read_locations(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, typ = line.partition("|")
        out.append((name.strip(), (typ or "city").strip()))
    return out


def read_zips(path):
    """GeoNames US.txt: страна, индекс, место, штат, код штата, округ, код округа, ..."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if len(r) > 5 and r[4] == "CA":
                rows.append({"zip": r[1], "place": r[2], "county": r[5]})
    return rows


def lookup(q):
    return call("GET", "/geo_lookup/search", [("q", q)]).get("results", [])


def check_zip(z):
    """Подтверждает индекс в поиске OpenAI: тип postal_code, штат California."""
    for r in lookup(z):
        if r["type"] == "postal_code" and r["name"] == z and "California" in r["canonical_name"]:
            return {"id": r["id"], "canonical_name": r["canonical_name"]}
    return None


def cmd_resolve(a):
    zips = read_zips(a.zips)
    plan = {"locations": [], "unresolved": []}
    candidates = {}  # индекс -> список названий из списка клиента
    for name, typ in read_locations(a.locations):
        if typ == "market":
            res = [r for r in lookup(name) if r["type"] == "market" and r["name"].lower().startswith(name.lower())]
            ids = [{"id": r["id"], "type": "market", "name": r["name"]} for r in res]
            plan["locations"].append({"name": name, "type": typ, "markets": ids, "zips": []})
            if not ids:
                plan["unresolved"].append(name)
            continue
        if typ == "county":
            county = name.replace(" County", "")
            found = sorted({r["zip"] for r in zips if r["county"].lower() == county.lower()})
        else:
            found = sorted({r["zip"] for r in zips if r["place"].lower() == name.lower()})
        plan["locations"].append({"name": name, "type": typ, "markets": [], "zips": found})
        if not found:
            plan["unresolved"].append(name)
        for z in found:
            candidates.setdefault(z, []).append(name)

    print(f"Индексов-кандидатов (уникальных): {len(candidates)}; проверяю в поиске OpenAI...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=3) as ex:
        checked = dict(zip(candidates, ex.map(check_zip, candidates)))
    plan["zip_info"] = {z: v for z, v in checked.items() if v}
    plan["zip_missing_in_openai"] = sorted(z for z, v in checked.items() if not v)

    print("Локация | тип | индексов подобрано | найдено в OpenAI | нет в OpenAI")
    for loc in plan["locations"]:
        if loc["type"] == "market":
            print(f"{loc['name']} | market | рынок: {', '.join(m['name'] + ' ' + m['id'] for m in loc['markets']) or 'не найден'}")
            continue
        ok = [z for z in loc["zips"] if checked.get(z)]
        print(f"{loc['name']} | {loc['type']} | {len(loc['zips'])} | {len(ok)} | {len(loc['zips']) - len(ok)}")
    shared = {z: n for z, n in candidates.items() if len(n) > 1}
    print(f"\nИТОГО уникальных индексов в OpenAI: {len(plan['zip_info'])} (лимит {MAX_LOCATIONS}); "
          f"индексов, общих у нескольких локаций: {len(shared)}")
    if plan["unresolved"]:
        print("Не подобраны индексы/рынок: " + ", ".join(plan["unresolved"]))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    print(f"План записан: {a.out}")


def current_locations(campaign):
    c = call("GET", f"/campaigns/{campaign}")
    return c["targeting"]["locations"]["include"]


def loc_text(x):
    return f"{x['type']} {x['id']} {x['name']}"


def cmd_apply(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    new = []  # [{"id":..}] без дублей, порядок: рынки, затем индексы
    seen = set()
    for loc in plan["locations"]:
        for m in loc["markets"]:
            if m["id"] not in seen:
                seen.add(m["id"]); new.append({"id": m["id"]})
    for z, info in sorted(plan["zip_info"].items()):
        if info["id"] not in seen:
            seen.add(info["id"]); new.append({"id": info["id"]})
    if len(new) > MAX_LOCATIONS:
        sys.exit(f"Больше лимита: {len(new)} > {MAX_LOCATIONS}")
    old = current_locations(a.campaign)
    old_ids = {x["id"] for x in old}
    new_ids = {x["id"] for x in new}
    print("Объект | Действие | Было → Станет")
    print(f"Кампания {a.campaign} | locations.include | {len(old)} локаций → {len(new)} локаций")
    print("Уходят из таргетинга: " + (", ".join(loc_text(x) for x in old if x["id"] not in new_ids) or "ничего"))
    print(f"Остаются: {len([x for x in old if x['id'] in new_ids])}; добавляются: {len(new_ids - old_ids)}")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    call("POST", f"/campaigns/{a.campaign}", body={"targeting": {"locations": {"include": new}}})
    after = current_locations(a.campaign)
    print("\nПрочитано обратно из аккаунта:")
    kinds = {}
    for x in after:
        kinds[x["type"]] = kinds.get(x["type"], 0) + 1
    print(f"Локаций: {len(after)}; по типам: {kinds}")
    print("Совпадает с планом: " + ("да" if {x['id'] for x in after} == new_ids else "НЕТ, проверить вручную"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--locations", required=True); r.add_argument("--zips", required=True)
    r.add_argument("--out", required=True); r.set_defaults(f=cmd_resolve)
    s = sub.add_parser("apply")
    s.add_argument("--campaign", required=True); s.add_argument("--plan", required=True)
    s.add_argument("--execute", action="store_true"); s.set_defaults(f=cmd_apply)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
