#!/usr/bin/env python
# coding: utf-8
"""Новые группы с ТОЧНЫМИ ключами в существующей Search-кампании + ставка существующих групп.

ЗАПИСЬ в аккаунт: без --execute — validate_only (Google проверяет, ничего не меняет).
Только после согласования таблицы плана (CLAUDE.md, протокол записи в кабинет).

Что делает (в таком порядке, каждое — отдельный вызов API):
  1. Ставка существующих групп кампании (`--phrase-bid`), чтобы после перехода на ручное CPC
     у фразовых ключей была осмысленная ставка (при автостратегии она не используется).
  2. Для каждой группы из плана создаёт `<группа> - Exact` со ставкой `--exact-bid`, точными
     ключами из плана и ДОСЛОВНОЙ копией объявления исходной группы (заголовки, описания, закрепления,
     пути, final URL). Тексты не меняются. Всё одним атомарным вызовом (временные id).
Идемпотентность: группа `<…> - Exact`, которая уже есть, пропускается; ключ, который в ней уже есть, не дублируется.
Смена стратегии на ручное CPC — отдельным скриптом `gads_set_campaign_bidding.py --strategy MANUAL_CPC`.
Снимок «до» — в Статистика/ клиента; после записи — чтение обратно.

План — CSV с колонками `keyword`, `group` (имя исходной группы: «Car Accident», «Truck Accident»).

    python gads_exact_groups.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" \
        --plan-csv "…/Статистика/exact_plan_car_truck_2026-10-12.csv" --exact-bid 50 --phrase-bid 25 [--execute]
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

SUFFIX = " - Exact"


def micros(x: float) -> int:
    return int(round(x * 1_000_000))


def read_groups(ga, cid, campaign):
    q = (f"SELECT campaign.name, ad_group.id, ad_group.name, ad_group.resource_name, ad_group.status, ad_group.cpc_bid_micros "
         f"FROM ad_group WHERE campaign.name = '{campaign}' AND ad_group.status != 'REMOVED'")
    return {r.ad_group.name: {"id": r.ad_group.id, "rn": r.ad_group.resource_name,
                              "bid": r.ad_group.cpc_bid_micros / 1e6, "status": int(r.ad_group.status)}
            for r in ga.search(customer_id=cid, query=q)}


def read_keywords(ga, cid, campaign, client):
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType
    q = (f"SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
         f"FROM ad_group_criterion WHERE campaign.name = '{campaign}' AND ad_group_criterion.type = 'KEYWORD' "
         f"AND ad_group_criterion.negative = FALSE AND ad_group_criterion.status != 'REMOVED'")
    out = {}
    for r in ga.search(customer_id=cid, query=q):
        out.setdefault(r.ad_group.name, set()).add(
            (r.ad_group_criterion.keyword.text.lower(), mt.Name(r.ad_group_criterion.keyword.match_type)))
    return out


def read_source_ads(ga, cid, campaign):
    q = (f"SELECT campaign.name, ad_group.name, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.path1, "
         f"ad_group_ad.ad.responsive_search_ad.path2, ad_group_ad.ad.responsive_search_ad.headlines, "
         f"ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad "
         f"WHERE campaign.name = '{campaign}' AND ad_group_ad.status = 'ENABLED'")
    out = {}
    for r in ga.search(customer_id=cid, query=q):
        a = r.ad_group_ad.ad
        rsa = a.responsive_search_ad
        out[r.ad_group.name] = {
            "final_urls": list(a.final_urls), "path1": rsa.path1, "path2": rsa.path2,
            "headlines": [(h.text, int(h.pinned_field)) for h in rsa.headlines],
            "descriptions": [(d.text, int(d.pinned_field)) for d in rsa.descriptions],
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--plan-csv", required=True)
    ap.add_argument("--exact-bid", type=float, required=True, help="ставка новых точных групп, $")
    ap.add_argument("--phrase-bid", type=float, required=True, help="ставка существующих групп, $")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    plan = pd.read_csv(args.plan_csv)[["keyword", "group"]].drop_duplicates()
    plan["keyword"] = plan.keyword.str.strip().str.lower()

    groups = read_groups(ga, cid, args.campaign)
    kws = read_keywords(ga, cid, args.campaign, client)
    ads = read_source_ads(ga, cid, args.campaign)
    camp_rn = client.get_service("CampaignService").campaign_path(
        cid, [r.campaign.id for r in ga.search(customer_id=cid, query=(
            f"SELECT campaign.id, campaign.name FROM campaign WHERE campaign.name = '{args.campaign}'"))][0])

    snap = client_stats_dir(args.client_folder) / f"snapshot_before_exact_groups_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps({"groups": groups, "keyword_counts": {g: len(v) for g, v in kws.items()}},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print("Снимок «до»:", snap)

    old_groups = {n: g for n, g in groups.items() if not n.endswith(SUFFIX)}
    print("\nОбъект | Действие | Было → Станет")
    for n, g in old_groups.items():
        print(f"группа «{n}» | ставка | ${g['bid']:.2f} → ${args.phrase_bid:.2f}")

    new_plan = {}
    for src_group, part in plan.groupby("group"):
        name = src_group + SUFFIX
        if src_group not in ads:
            raise SystemExit(f"нет активного объявления в исходной группе «{src_group}»")
        have = kws.get(name, set())
        todo = [k for k in part.keyword if (k, "EXACT") not in have]
        new_plan[name] = {"src": src_group, "exists": name in groups, "todo": todo}
        state = "уже есть" if name in groups else "нет → создать, ставка $%.2f" % args.exact_bid
        print(f"группа «{name}» | {state}; точных ключей к добавлению {len(todo)}; объявление — копия «{src_group}»")

    # --- шаг 1: ставки существующих групп
    req = client.get_type("MutateAdGroupsRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for n, g in old_groups.items():
        op = client.get_type("AdGroupOperation")
        op.update.resource_name = g["rn"]
        op.update.cpc_bid_micros = micros(args.phrase_bid)
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
        req.operations.append(op)

    # --- шаг 2: новые группы + ключи + объявления одним вызовом
    ag_svc = client.get_service("AdGroupService")
    ALLOWED_EXEMPT = {"HEALTH_IN_PERSONALIZED_ADS"}  # только эта политика, только исключаемая, только то, что вернул Google

    def build(exempt, validate_only):
        mreq = client.get_type("MutateGoogleAdsRequest")
        mreq.customer_id = cid
        mreq.validate_only = validate_only
        op_kw = {}
        tmp = -1
        for name, info in new_plan.items():
            if info["exists"]:
                continue
            ag_rn = ag_svc.ad_group_path(cid, tmp)
            tmp -= 1
            mo = client.get_type("MutateOperation")
            g = mo.ad_group_operation.create
            g.resource_name = ag_rn
            g.name = name
            g.campaign = camp_rn
            g.status = client.enums.AdGroupStatusEnum.ENABLED
            g.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
            g.cpc_bid_micros = micros(args.exact_bid)
            mreq.mutate_operations.append(mo)
            for kw in info["todo"]:
                mo = client.get_type("MutateOperation")
                c = mo.ad_group_criterion_operation.create
                c.ad_group = ag_rn
                c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                c.keyword.text = kw
                c.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
                if kw in exempt:
                    key = client.get_type("PolicyViolationKey")
                    key.policy_name, key.violating_text = exempt[kw]
                    mo.ad_group_criterion_operation.exempt_policy_violation_keys.append(key)
                op_kw[len(mreq.mutate_operations)] = kw
                mreq.mutate_operations.append(mo)
            src = ads[info["src"]]
            mo = client.get_type("MutateOperation")
            aa = mo.ad_group_ad_operation.create
            aa.ad_group = ag_rn
            aa.status = client.enums.AdGroupAdStatusEnum.ENABLED
            aa.ad.final_urls.extend(src["final_urls"])
            rsa = aa.ad.responsive_search_ad
            rsa.path1, rsa.path2 = src["path1"], src["path2"]
            for text, pin in src["headlines"]:
                h = client.get_type("AdTextAsset")
                h.text = text
                if pin:
                    h.pinned_field = pin
                rsa.headlines.append(h)
            for text, pin in src["descriptions"]:
                d = client.get_type("AdTextAsset")
                d.text = text
                if pin:
                    d.pinned_field = pin
                rsa.descriptions.append(d)
            mreq.mutate_operations.append(mo)
        return mreq, op_kw

    def explain(ex):
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:12]:
            print("  -", err.message)
            d = err.details.policy_violation_details
            if d.key.policy_name:
                print(f"      политика: {d.key.policy_name}; текст: «{d.key.violating_text}»; можно исключение: {d.is_exemptible}")

    exempt = {}  # ключевая фраза -> (политика, violating_text)
    try:
        # поиск исключаемых нарушений политики (validate_only), максимум 3 прохода
        for _ in range(3):
            mreq, op_kw = build(exempt, True)
            if not mreq.mutate_operations:
                break
            try:
                ga.mutate(request=mreq)
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
            print(f"\nИсключения политики HEALTH_IN_PERSONALIZED_ADS для {len(exempt)} ключей (флаг тот же, что у всех "
                  f"ключей кампании; показ при нём ELIGIBLE):")
            for kw in sorted(exempt):
                print("   ", kw)

        if req.operations:
            client.get_service("AdGroupService").mutate_ad_groups(request=req)
            print("\nШаг 1 (ставки существующих групп):", "ВЫПОЛНЕНО" if args.execute else "validate_only OK")
        if mreq.mutate_operations:
            if args.execute:
                mreq, _ = build(exempt, False)
                ga.mutate(request=mreq)
            print("Шаг 2 (новые группы, ключи, объявления):", "ВЫПОЛНЕНО" if args.execute else "validate_only OK")
    except GoogleAdsException as ex:
        explain(ex)
        raise SystemExit(1)

    if not args.execute:
        print("\nvalidate_only: ничего не изменено.")
        return

    after_groups = read_groups(ga, cid, args.campaign)
    after_kws = read_keywords(ga, cid, args.campaign, client)
    after_ads = read_source_ads(ga, cid, args.campaign)
    print("\nЧтение обратно из аккаунта:")
    for n, g in after_groups.items():
        k = after_kws.get(n, set())
        by = pd.Series([m for _, m in k]).value_counts().to_dict() if k else {}
        ad = after_ads.get(n)
        ad_s = f"объявление: {len(ad['headlines'])} заголовков, {len(ad['descriptions'])} описаний, " \
               f"закреплений {sum(1 for _, p in ad['headlines'] + ad['descriptions'] if p)}, path {ad['path1']}/{ad['path2']}" if ad else "объявления нет"
        print(f"  «{n}»: ставка ${g['bid']:.2f}; ключи {by}; {ad_s}")


if __name__ == "__main__":
    main()
