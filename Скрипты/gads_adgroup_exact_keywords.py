#!/usr/bin/env python
# coding: utf-8
"""Точные ключи в СУЩЕСТВУЮЩИЕ группы Search-кампании + ставка групп.

ЗАПИСЬ в аккаунт: без --execute — validate_only (Google проверяет, ничего не меняет).
Только после согласования таблицы плана (CLAUDE.md, протокол записи в кабинет).

Чем отличается от `gads_exact_groups.py`: тот создаёт новые группы «<…> - Exact» и кладёт ключи
только в них; этот добавляет точные ключи в уже существующую группу и (по желанию) меняет
ставку отдельных групп, не трогая остальные.

План — CSV с колонками `keyword`, `group` (ПОЛНОЕ имя существующей группы, например «Car Accident - Exact»).
Ключ, который уже есть в группе как EXACT, пропускается. Исключаемая политика HEALTH_IN_PERSONALIZED_ADS
обрабатывается так же, как в `gads_exact_groups.py` (только она, только исключаемая, только то, что вернул Google).
Снимок «до» — в Статистика/ клиента; после записи — чтение обратно.

    python gads_adgroup_exact_keywords.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" \
        --plan-csv ".../Статистика/exact_add_car_truck_2026-10-14.csv" \
        --set-bid "Auto Accident=15" [--execute]
"""
import argparse
import json
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from gads_exact_groups import micros, read_groups, read_keywords

ALLOWED_EXEMPT = {"HEALTH_IN_PERSONALIZED_ADS"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--plan-csv", help="CSV keyword,group: точные ключи в существующие группы")
    ap.add_argument("--set-bid", action="append", default=[], help='"Имя группы=ставка $", можно повторять')
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    if not args.plan_csv and not args.set_bid:
        raise SystemExit("нужен --plan-csv и/или --set-bid")

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    groups = read_groups(ga, cid, args.campaign)
    kws = read_keywords(ga, cid, args.campaign, client)

    snap = client_stats_dir(args.client_folder) / f"snapshot_before_adgroup_keywords_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps({"groups": groups, "keyword_counts": {g: len(v) for g, v in kws.items()}},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print("Снимок «до»:", snap)

    bids = {}
    for s in args.set_bid:
        name, _, val = s.rpartition("=")
        if name not in groups:
            raise SystemExit(f"нет группы «{name}» в кампании")
        bids[name] = float(val)

    plan = {}
    if args.plan_csv:
        df = pd.read_csv(args.plan_csv)[["keyword", "group"]].drop_duplicates()
        df["keyword"] = df.keyword.str.strip().str.lower()
        for g, part in df.groupby("group"):
            if g not in groups:
                raise SystemExit(f"нет группы «{g}» в кампании")
            have = {t for t, m in kws.get(g, set()) if m == "EXACT"}
            plan[g] = [k for k in part.keyword if k not in have]

    print("\nОбъект | Действие | Было → Станет")
    for n, v in bids.items():
        print(f"группа «{n}» | ставка | ${groups[n]['bid']:.2f} → ${v:.2f}")
    for g, todo in plan.items():
        print(f"группа «{g}» | точных ключей к добавлению {len(todo)} (ставка группы ${groups[g]['bid']:.2f}):")
        for k in todo:
            print("     +", k)

    ag_svc = client.get_service("AdGroupService")

    def build(exempt, validate_only):
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.validate_only = validate_only
        op_kw = {}
        for n, v in bids.items():
            mo = client.get_type("MutateOperation")
            u = mo.ad_group_operation.update
            u.resource_name = groups[n]["rn"]
            u.cpc_bid_micros = micros(v)
            mo.ad_group_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
            req.mutate_operations.append(mo)
        for g, todo in plan.items():
            for kw in todo:
                mo = client.get_type("MutateOperation")
                c = mo.ad_group_criterion_operation.create
                c.ad_group = groups[g]["rn"]
                c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                c.keyword.text = kw
                c.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
                if kw in exempt:
                    key = client.get_type("PolicyViolationKey")
                    key.policy_name, key.violating_text = exempt[kw]
                    mo.ad_group_criterion_operation.exempt_policy_violation_keys.append(key)
                op_kw[len(req.mutate_operations)] = kw
                req.mutate_operations.append(mo)
        return req, op_kw

    def explain(ex):
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:12]:
            print("  -", err.message)
            d = err.details.policy_violation_details
            if d.key.policy_name:
                print(f"      политика: {d.key.policy_name}; текст: «{d.key.violating_text}»; можно исключение: {d.is_exemptible}")

    exempt = {}
    try:
        for _ in range(3):
            req, op_kw = build(exempt, True)
            if not req.mutate_operations:
                print("\nНечего менять: всё уже на месте.")
                return
            try:
                ga.mutate(request=req)
                break
            except GoogleAdsException as ex:
                found = 0
                for err in ex.failure.errors:
                    d = err.details.policy_violation_details
                    els = err.location.field_path_elements
                    idx = els[0].index if els and els[0].field_name == "mutate_operations" else None
                    kw = op_kw.get(idx)
                    if kw and d.key.policy_name in ALLOWED_EXEMPT and d.is_exemptible and kw not in exempt:
                        exempt[kw] = (d.key.policy_name, d.key.violating_text)
                        found += 1
                if not found:
                    explain(ex)
                    raise SystemExit(1)
        else:
            raise SystemExit("не удалось пройти проверку за 3 прохода")
        if exempt:
            print(f"\nИсключения политики HEALTH_IN_PERSONALIZED_ADS для {len(exempt)} ключей:")
            for kw in sorted(exempt):
                print("   ", kw)
        if args.execute:
            req, _ = build(exempt, False)
            ga.mutate(request=req)
        print("\nЗапись:", "ВЫПОЛНЕНО" if args.execute else "validate_only OK")
    except GoogleAdsException as ex:
        explain(ex)
        raise SystemExit(1)

    if not args.execute:
        print("validate_only: ничего не изменено.")
        return

    after_groups = read_groups(ga, cid, args.campaign)
    after_kws = read_keywords(ga, cid, args.campaign, client)
    print("\nЧтение обратно из аккаунта:")
    for n in sorted(set(bids) | set(plan)):
        k = after_kws.get(n, set())
        by = pd.Series([m for _, m in k]).value_counts().to_dict() if k else {}
        print(f"  «{n}»: ставка ${after_groups[n]['bid']:.2f}; ключи {by}")
    missing = [(g, k) for g, todo in plan.items() for k in todo if (k, "EXACT") not in after_kws.get(g, set())]
    print("  не найдено после записи:", missing or "нет")


if __name__ == "__main__":
    main()
