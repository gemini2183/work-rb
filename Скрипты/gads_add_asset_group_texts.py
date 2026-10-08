#!/usr/bin/env python
# coding: utf-8
"""Добавляет текстовые ассеты (заголовки, длинные заголовки, описания) во все включённые группы ассетов кампании PMax.

Тексты берутся из JSON: {"HEADLINE": [...], "LONG_HEADLINE": [...], "DESCRIPTION": [...]}. Каждый текст создаётся как ассет один раз
и привязывается ко всем выбранным группам; уже привязанные к группе тексты пропускаются. Проверяет лимиты Google (заголовок до 30,
длинный до 90, описание до 90; в группе до 15 заголовков, 5 длинных, 5 описаний).

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не создаёт). Запись — только с --execute.
После записи читает из аккаунта число текстов по типам и оценку группы (Ad strength).

Использование:
    python gads_add_asset_group_texts.py --customer-id 7552781705 --campaign-id 24332178236 --texts-file texts.json [--groups g1 g2] [--execute]
"""
import argparse
import json
from collections import Counter

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from gads_stats import GOOGLE_ADS_YAML

LIMITS = {"HEADLINE": (30, 15), "LONG_HEADLINE": (90, 5), "DESCRIPTION": (90, 5)}


def state(client, ga, cid, campaign_id):
    E = client.enums
    groups = {}
    for r in ga.search(customer_id=cid, query=f"SELECT campaign.id, asset_group.id, asset_group.name, asset_group.status, asset_group.ad_strength FROM asset_group WHERE campaign.id = {campaign_id}"):
        groups[r.asset_group.id] = {"name": r.asset_group.name, "status": E.AssetGroupStatusEnum.AssetGroupStatus.Name(r.asset_group.status),
                                    "strength": E.AdStrengthEnum.AdStrength.Name(r.asset_group.ad_strength), "texts": {}, "rn": None}
    for r in ga.search(customer_id=cid, query=f"SELECT campaign.id, asset_group.id, asset_group.resource_name FROM asset_group WHERE campaign.id = {campaign_id}"):
        groups[r.asset_group.id]["rn"] = r.asset_group.resource_name
    for r in ga.search(customer_id=cid, query=("SELECT campaign.id, asset_group.id, asset_group_asset.field_type, asset.text_asset.text FROM asset_group_asset "
                                              f"WHERE campaign.id = {campaign_id} AND asset_group_asset.status != 'REMOVED'")):
        ft = E.AssetFieldTypeEnum.AssetFieldType.Name(r.asset_group_asset.field_type)
        if ft in LIMITS:
            groups[r.asset_group.id]["texts"].setdefault(ft, set()).add(r.asset.text_asset.text)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--texts-file", required=True)
    ap.add_argument("--groups", nargs="*", help="названия групп (по умолчанию все включённые)")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    texts = json.load(open(args.texts_file, encoding="utf-8"))
    for field, items in texts.items():
        for t in items:
            assert len(t) <= LIMITS[field][0], f"{field} длиннее {LIMITS[field][0]}: {t} ({len(t)})"
    groups = state(client, ga, cid, args.campaign_id)
    sel = {gid: g for gid, g in groups.items() if g["status"] == "ENABLED" and (not args.groups or g["name"] in args.groups)}
    print("группы:", [g["name"] for g in sel.values()])

    E = client.enums
    ops = []
    temp = [100]
    asset_rns = {}
    for field, items in texts.items():
        for t in items:
            temp[0] += 1
            rn = f"customers/{cid}/assets/-{temp[0]}"
            asset_rns[(field, t)] = rn
    used = set()
    planned = Counter()
    for gid, g in sel.items():
        for field, items in texts.items():
            have = g["texts"].get(field, set())
            new = [t for t in items if t not in have]
            if len(have) + len(new) > LIMITS[field][1]:
                raise SystemExit(f"в группе {g['name']} {field}: было {len(have)}, добавляем {len(new)} — больше лимита {LIMITS[field][1]}")
            for t in new:
                if (field, t) not in used:
                    mo = client.get_type("MutateOperation")
                    a = mo.asset_operation.create
                    a.resource_name = asset_rns[(field, t)]
                    a.text_asset.text = t
                    ops.append(mo)
                    used.add((field, t))
                mo = client.get_type("MutateOperation")
                aga = mo.asset_group_asset_operation.create
                aga.asset_group = g["rn"]
                aga.asset = asset_rns[(field, t)]
                aga.field_type = getattr(E.AssetFieldTypeEnum, field)
                ops.append(mo)
                planned[(g["name"], field)] += 1
    print("добавится:", dict(planned))
    if not ops:
        print("нечего добавлять")
        return
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not args.execute
    try:
        client.get_service("GoogleAdsService").mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:8]:
            print("  -", err.message, "|", [str(p.field_name) for p in err.location.field_path_elements][:4])
        raise SystemExit(1)
    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не создано (validate_only).")
        return
    after = state(client, ga, cid, args.campaign_id)
    for gid, g in after.items():
        if gid in sel:
            print(f"{g['name']}: заголовков {len(g['texts'].get('HEADLINE', []))}, длинных {len(g['texts'].get('LONG_HEADLINE', []))}, описаний {len(g['texts'].get('DESCRIPTION', []))}, оценка {g['strength']}")


if __name__ == "__main__":
    main()
