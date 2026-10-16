#!/usr/bin/env python
# coding: utf-8
"""Пакет правок групп и ключей Search-кампании по JSON-плану.

ЗАПИСЬ в аккаунт: без --execute — validate_only (Google проверяет, ничего не меняет).
Только после согласования таблицы плана (CLAUDE.md, протокол записи в кабинет).

Что умеет (то, чего нет вместе в gads_exact_groups.py / gads_campaign_rework.py):
  pause_groups    — пауза групп по имени;
  pause_keywords  — пауза ключей: [{"group", "text", "match"}];
  group_bids      — ставка группы: [{"group", "bid"}];
  group_tcpa      — цель по CPA группы (Maximize conversions/Target CPA), EUR: [{"group", "tcpa"}]; 0 — снять;
  keyword_bids    — ставка отдельного ключа: [{"group", "text", "match", "bid"}];
  new_groups      — новая группа со своей ставкой, ключами и ДОСЛОВНОЙ копией включённого объявления другой группы:
                    [{"name", "bid", "copy_ad_from", "status": "ENABLED"|"PAUSED", "keywords": [{"text", "match"}]}].
Проверки до записи: группы/ключи из плана существуют; новая группа с таким именем ещё не создана;
ключ новой группы не совпадает с включённым ключом того же типа в другой группе (кроме тех, что в этом же плане ставятся на паузу).
Нарушения политики HEALTH_IN_PERSONALIZED_ADS у ключей (флаг у всех ключей юр-кампаний) обходятся исключением,
как в gads_exact_groups.py; любые другие ошибки — остановка.
Снимок «до» — Статистика/ клиента; после записи — чтение обратно.

    python gads_adgroup_plan.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --plan "Клиенты/Andverpersonalinjury/Кампании/Search/car_truck_plan_2026-10-15.json" [--execute]
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import VAULT_ROOT, client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

ALLOWED_EXEMPT = {"HEALTH_IN_PERSONALIZED_ADS"}


def micros(x: float) -> int:
    return int(round(x * 1_000_000))


def read_state(ga, client, cid, campaign):
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType
    st = client.enums.AdGroupCriterionStatusEnum.AdGroupCriterionStatus
    gst = client.enums.AdGroupStatusEnum.AdGroupStatus
    camp = f"campaign.name = '{campaign}'"
    groups = {r.ad_group.name: {"rn": r.ad_group.resource_name, "bid": r.ad_group.cpc_bid_micros / 1e6,
                                "tcpa": r.ad_group.target_cpa_micros / 1e6,
                                "status": gst.Name(r.ad_group.status)}
              for r in ga.search(customer_id=cid, query=(
                  f"SELECT campaign.id, ad_group.name, ad_group.resource_name, ad_group.cpc_bid_micros, ad_group.target_cpa_micros, ad_group.status "
                  f"FROM ad_group WHERE {camp} AND ad_group.status != 'REMOVED'"))}
    kws = {}
    for r in ga.search(customer_id=cid, query=(
            f"SELECT ad_group.name, ad_group_criterion.resource_name, ad_group_criterion.keyword.text, "
            f"ad_group_criterion.keyword.match_type, ad_group_criterion.status, ad_group_criterion.cpc_bid_micros, "
            f"ad_group_criterion.effective_cpc_bid_micros FROM ad_group_criterion WHERE {camp} "
            f"AND ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.negative = FALSE "
            f"AND ad_group_criterion.status != 'REMOVED'")):
        k = r.ad_group_criterion
        kws[(r.ad_group.name, k.keyword.text.lower(), mt.Name(k.keyword.match_type))] = {
            "rn": k.resource_name, "status": st.Name(k.status), "bid": k.cpc_bid_micros / 1e6,
            "effective_bid": k.effective_cpc_bid_micros / 1e6}
    ads = {}
    for r in ga.search(customer_id=cid, query=(
            f"SELECT ad_group.name, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.path1, "
            f"ad_group_ad.ad.responsive_search_ad.path2, ad_group_ad.ad.responsive_search_ad.headlines, "
            f"ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad "
            f"WHERE {camp} AND ad_group_ad.status = 'ENABLED'")):
        a, rsa = r.ad_group_ad.ad, r.ad_group_ad.ad.responsive_search_ad
        ads.setdefault(r.ad_group.name, []).append({
            "final_urls": list(a.final_urls), "path1": rsa.path1, "path2": rsa.path2,
            "headlines": [(h.text, int(h.pinned_field)) for h in rsa.headlines],
            "descriptions": [(d.text, int(d.pinned_field)) for d in rsa.descriptions]})
    return groups, kws, ads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--plan", required=True, help="JSON-план (путь от корня вики или абсолютный)")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()

    plan_path = Path(a.plan) if Path(a.plan).is_absolute() else VAULT_ROOT / a.plan
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    campaign = plan["campaign"]
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    groups, kws, ads = read_state(ga, client, cid, campaign)
    camp_ids = [r.campaign.id for r in ga.search(customer_id=cid, query=(
        f"SELECT campaign.id FROM campaign WHERE campaign.name = '{campaign}'"))]
    if not camp_ids:
        raise SystemExit(f"кампания не найдена: {campaign}")
    camp_rn = client.get_service("CampaignService").campaign_path(cid, camp_ids[0])

    snap = client_stats_dir(a.client_folder) / f"snapshot_before_adgroup_plan_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps({"plan": plan, "groups": groups,
                                "keywords": {" | ".join(k): v for k, v in kws.items()}}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("Снимок «до»:", snap)

    def kw_key(x):
        return (x["group"], x["text"].lower(), x["match"].upper())

    errors = []
    print("\nОбъект | Действие | Было → Станет")
    for g in plan.get("pause_groups", []):
        if g not in groups:
            errors.append(f"нет группы «{g}»")
        else:
            print(f"группа «{g}» | пауза | {groups[g]['status']} → PAUSED")
    for g in plan.get("enable_groups", []):
        if g not in groups:
            errors.append(f"нет группы «{g}»")
        else:
            print(f"группа «{g}» | включение | {groups[g]['status']} → ENABLED")
    for x in plan.get("group_bids", []):
        if x["group"] not in groups:
            errors.append(f"нет группы «{x['group']}»")
        else:
            print(f"группа «{x['group']}» | ставка группы | ${groups[x['group']]['bid']:.2f} → ${x['bid']:.2f}")
    for x in plan.get("group_tcpa", []):
        if x["group"] not in groups:
            errors.append(f"нет группы «{x['group']}»")
        else:
            print(f"группа «{x['group']}» | tCPA группы | {groups[x['group']]['tcpa']:.2f} → {x['tcpa']:.2f}")
    paused_now = set()
    for x in plan.get("pause_keywords", []):
        k = kw_key(x)
        if k not in kws:
            errors.append(f"нет ключа {k}")
        else:
            paused_now.add(k)
            print(f"ключ [{k[2]}] {k[1]} («{k[0]}») | пауза | {kws[k]['status']} → PAUSED")
    for x in plan.get("keyword_bids", []):
        k = kw_key(x)
        if k not in kws:
            errors.append(f"нет ключа {k}")
        else:
            was = kws[k]["bid"] or kws[k]["effective_bid"]
            print(f"ключ [{k[2]}] {k[1]} («{k[0]}») | ставка ключа | ${was:.2f} → ${x['bid']:.2f}")
    for ng in plan.get("new_groups", []):
        if ng["name"] in groups:
            errors.append(f"группа «{ng['name']}» уже есть")
        if ng["copy_ad_from"] not in ads:
            errors.append(f"нет включённого объявления в «{ng['copy_ad_from']}»")
        elif len(ads[ng["copy_ad_from"]]) > 1:
            errors.append(f"в «{ng['copy_ad_from']}» больше одного включённого объявления — укажите, какое копировать")
        for w in ng["keywords"]:
            dup = [k for k, v in kws.items() if k[1] == w["text"].lower() and k[2] == w["match"].upper()
                   and v["status"] == "ENABLED" and k not in paused_now and k[0] not in plan.get("pause_groups", [])]
            if dup:
                errors.append(f"ключ [{w['match']}] {w['text']} уже включён в «{dup[0][0]}»")
        print(f"группа «{ng['name']}» | создать, {ng.get('status', 'ENABLED')}, ставка ${ng['bid']:.2f}, "
              f"{len(ng['keywords'])} ключей, объявление — копия «{ng['copy_ad_from']}» | нет → есть")
        for w in ng["keywords"]:
            print(f"    [{w['match'].upper()}] {w['text']}")
    if errors:
        print("\nОСТАНОВКА, план не сходится с кабинетом:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)

    ag_svc = client.get_service("AdGroupService")

    def build(exempt, validate_only):
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.validate_only = validate_only
        op_kw = {}
        for g in plan.get("pause_groups", []):
            mo = client.get_type("MutateOperation")
            mo.ad_group_operation.update.resource_name = groups[g]["rn"]
            mo.ad_group_operation.update.status = E.AdGroupStatusEnum.PAUSED
            mo.ad_group_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            req.mutate_operations.append(mo)
        for g in plan.get("enable_groups", []):
            mo = client.get_type("MutateOperation")
            mo.ad_group_operation.update.resource_name = groups[g]["rn"]
            mo.ad_group_operation.update.status = E.AdGroupStatusEnum.ENABLED
            mo.ad_group_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            req.mutate_operations.append(mo)
        for x in plan.get("group_bids", []):
            mo = client.get_type("MutateOperation")
            mo.ad_group_operation.update.resource_name = groups[x["group"]]["rn"]
            mo.ad_group_operation.update.cpc_bid_micros = micros(x["bid"])
            mo.ad_group_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
            req.mutate_operations.append(mo)
        for x in plan.get("group_tcpa", []):
            mo = client.get_type("MutateOperation")
            mo.ad_group_operation.update.resource_name = groups[x["group"]]["rn"]
            mo.ad_group_operation.update.target_cpa_micros = micros(x["tcpa"])
            mo.ad_group_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["target_cpa_micros"]))
            req.mutate_operations.append(mo)
        for x in plan.get("pause_keywords", []):
            mo = client.get_type("MutateOperation")
            mo.ad_group_criterion_operation.update.resource_name = kws[kw_key(x)]["rn"]
            mo.ad_group_criterion_operation.update.status = E.AdGroupCriterionStatusEnum.PAUSED
            mo.ad_group_criterion_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
            req.mutate_operations.append(mo)
        for x in plan.get("keyword_bids", []):
            mo = client.get_type("MutateOperation")
            mo.ad_group_criterion_operation.update.resource_name = kws[kw_key(x)]["rn"]
            mo.ad_group_criterion_operation.update.cpc_bid_micros = micros(x["bid"])
            mo.ad_group_criterion_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
            req.mutate_operations.append(mo)
        tmp = -1
        for ng in plan.get("new_groups", []):
            ag_rn = ag_svc.ad_group_path(cid, tmp)
            tmp -= 1
            mo = client.get_type("MutateOperation")
            g = mo.ad_group_operation.create
            g.resource_name = ag_rn
            g.name = ng["name"]
            g.campaign = camp_rn
            g.status = getattr(E.AdGroupStatusEnum, ng.get("status", "ENABLED"))
            g.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
            g.cpc_bid_micros = micros(ng["bid"])
            req.mutate_operations.append(mo)
            for w in ng["keywords"]:
                mo = client.get_type("MutateOperation")
                c = mo.ad_group_criterion_operation.create
                c.ad_group = ag_rn
                c.status = E.AdGroupCriterionStatusEnum.ENABLED
                c.keyword.text = w["text"]
                c.keyword.match_type = getattr(E.KeywordMatchTypeEnum, w["match"].upper())
                if w["text"] in exempt:
                    key = client.get_type("PolicyViolationKey")
                    key.policy_name, key.violating_text = exempt[w["text"]]
                    mo.ad_group_criterion_operation.exempt_policy_violation_keys.append(key)
                op_kw[len(req.mutate_operations)] = w["text"]
                req.mutate_operations.append(mo)
            src = ads[ng["copy_ad_from"]][0]
            mo = client.get_type("MutateOperation")
            aa = mo.ad_group_ad_operation.create
            aa.ad_group = ag_rn
            aa.status = E.AdGroupAdStatusEnum.ENABLED
            aa.ad.final_urls.extend(src["final_urls"])
            rsa = aa.ad.responsive_search_ad
            rsa.path1, rsa.path2 = src["path1"], src["path2"]
            for items, target in ((src["headlines"], rsa.headlines), (src["descriptions"], rsa.descriptions)):
                for text, pin in items:
                    t = client.get_type("AdTextAsset")
                    t.text = text
                    if pin:
                        t.pinned_field = pin
                    target.append(t)
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
            print(f"\nИсключения политики HEALTH_IN_PERSONALIZED_ADS: {len(exempt)} ключей")
        print("\nvalidate_only OK")
        if not a.execute:
            print("validate_only: ничего не изменено.")
            return
        req, _ = build(exempt, False)
        ga.mutate(request=req)
        print("ВЫПОЛНЕНО (одним атомарным вызовом)")
    except GoogleAdsException as ex:
        explain(ex)
        raise SystemExit(1)

    groups2, kws2, ads2 = read_state(ga, client, cid, campaign)
    print("\nЧтение обратно из аккаунта:")
    for g in plan.get("pause_groups", []) + plan.get("enable_groups", []):
        print(f"  группа «{g}»: {groups2[g]['status']}")
    for x in plan.get("group_bids", []):
        print(f"  группа «{x['group']}»: ставка ${groups2[x['group']]['bid']:.2f}")
    for x in plan.get("group_tcpa", []):
        print(f"  группа «{x['group']}»: tCPA {groups2[x['group']]['tcpa']:.2f}")
    for x in plan.get("pause_keywords", []):
        k = kw_key(x)
        print(f"  ключ [{k[2]}] {k[1]} («{k[0]}»): {kws2[k]['status']}")
    for x in plan.get("keyword_bids", []):
        k = kw_key(x)
        print(f"  ключ [{k[2]}] {k[1]} («{k[0]}»): ставка ${kws2[k]['bid']:.2f}")
    for ng in plan.get("new_groups", []):
        g = groups2.get(ng["name"])
        if not g:
            print(f"  группа «{ng['name']}»: НЕ НАЙДЕНА")
            continue
        mine = [k for k in kws2 if k[0] == ng["name"]]
        ad = (ads2.get(ng["name"]) or [None])[0]
        ad_s = (f"объявление: {len(ad['headlines'])} заголовков, {len(ad['descriptions'])} описаний, "
                f"закреплений {sum(1 for _, p in ad['headlines'] + ad['descriptions'] if p)}, {ad['final_urls'][0]}") if ad else "объявления нет"
        print(f"  группа «{ng['name']}»: {g['status']}, ставка ${g['bid']:.2f}, ключей {len(mine)}; {ad_s}")


if __name__ == "__main__":
    main()
