#!/usr/bin/env python
# coding: utf-8
"""План переноса настроек кампании в новую: читает источник (и, если есть, цель), считает операции API и подсказывает способ.
ТОЛЬКО ЧТЕНИЕ — в кабинет ничего не пишет. Запускать ДО таблицы «было → станет» при создании кампании на основе другой.

Зачем: суточный лимит basic access (15 000 операций) закрылся посреди копирования 1 699 минусов (П-001, 10.11.2026).
Здесь заранее видно, из чего состоит копия и сколько операций она стоит каждым способом.

    python gads_clone_plan.py --customer-id 213-621-6123 --source 24331208797 [--target 24447075486] \
        [--also 1] [--client-folder Andverpersonalinjury] [--api-budget 2000]

--target   кампания, куда уже копировали: считаем, чего в ней НЕ хватает (докопировать только остаток).
--also     сколько следующих кампаний (кроме цели) получат тот же полный список: от этого зависит, выгоден ли общий список.
--api-budget  порог «много для одного захода через API» (допущение, не лимит Google; по умолчанию 2000).
Способы переноса большого списка минусов:
  API         N операций на каждую кампанию.
  Общий список  N операций один раз (наполнение) + 1 операция на привязку к каждой кампании. Лимиты Google: 20 списков на аккаунт,
              5 000 слов в списке (help 6372658; сверено поиском 11.11.2026, на аккаунте не проверено).
  Интерфейс / Editor  0 операций нашего токена — это НЕ проверено (по документации API про Editor ничего нет); вручную.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import wrap_ga, summary as ledger_summary

NEAR_ME = ("near me", "nearby", "close to me", "near by")   # как в gads_landver_search_rebuild.py
SHARED_LISTS_PER_ACCOUNT = 20
WORDS_PER_SHARED_LIST = 5000


def q(ga, cid, query):
    if "campaign.id" in query and "campaign.id," not in query.split(" FROM ")[0]:
        query = query.replace("SELECT ", "SELECT campaign.id, ", 1)   # Google требует поле из фильтра в SELECT
    return list(ga.search(customer_id=cid, query=query))


def read_campaign(client, ga, cid, camp_id):
    E = client.enums
    out = {"id": camp_id}
    rows = q(ga, cid, "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, campaign_budget.amount_micros "
                      f"FROM campaign WHERE campaign.id = {camp_id}")
    if not rows:
        raise SystemExit(f"кампания {camp_id} не найдена")
    c = rows[0]
    out["name"] = c.campaign.name
    out["status"] = E.CampaignStatusEnum.CampaignStatus.Name(c.campaign.status)
    out["bidding"] = E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(c.campaign.bidding_strategy_type)
    out["budget"] = c.campaign_budget.amount_micros / 1e6

    neg, pos = [], {}
    for r in q(ga, cid, "SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.keyword.text, "
                        f"campaign_criterion.keyword.match_type FROM campaign_criterion WHERE campaign.id = {camp_id}"):
        cc = r.campaign_criterion
        t = E.CriterionTypeEnum.CriterionType.Name(cc.type_)
        if cc.type_ == E.CriterionTypeEnum.KEYWORD and cc.negative:
            neg.append([cc.keyword.text, E.KeywordMatchTypeEnum.KeywordMatchType.Name(cc.keyword.match_type)])
        else:
            key = t + (" (минус)" if cc.negative else "")
            pos[key] = pos.get(key, 0) + 1
    out["negatives"] = neg
    out["other_criteria"] = pos

    out["shared_sets"] = [[r.shared_set.id, r.shared_set.name, r.shared_set.member_count]
                          for r in q(ga, cid, "SELECT shared_set.id, shared_set.name, shared_set.member_count, campaign_shared_set.status "
                                              f"FROM campaign_shared_set WHERE campaign.id = {camp_id} AND campaign_shared_set.status = ENABLED")]
    out["ad_groups"] = len(q(ga, cid, f"SELECT ad_group.id FROM ad_group WHERE campaign.id = {camp_id} AND ad_group.status != REMOVED"))
    kw = {}
    for r in q(ga, cid, "SELECT ad_group_criterion.keyword.match_type, ad_group_criterion.negative FROM ad_group_criterion "
                        f"WHERE campaign.id = {camp_id} AND ad_group_criterion.type = KEYWORD AND ad_group_criterion.status != REMOVED"):
        k = ("минус " if r.ad_group_criterion.negative else "") + E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.ad_group_criterion.keyword.match_type)
        kw[k] = kw.get(k, 0) + 1
    out["group_keywords"] = kw
    out["ads"] = len(q(ga, cid, f"SELECT ad_group_ad.ad.id FROM ad_group_ad WHERE campaign.id = {camp_id} AND ad_group_ad.status != REMOVED"))
    ca = {}
    for r in q(ga, cid, f"SELECT campaign_asset.field_type FROM campaign_asset WHERE campaign.id = {camp_id} AND campaign_asset.status != REMOVED"):
        k = E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type)
        ca[k] = ca.get(k, 0) + 1
    out["campaign_assets"] = ca
    ga_ = {}
    for r in q(ga, cid, f"SELECT ad_group_asset.field_type FROM ad_group_asset WHERE campaign.id = {camp_id} AND ad_group_asset.status != REMOVED"):
        k = E.AssetFieldTypeEnum.AssetFieldType.Name(r.ad_group_asset.field_type)
        ga_[k] = ga_.get(k, 0) + 1
    out["ad_group_assets"] = ga_
    return out


def wanted_negatives(src, skip_near_me):
    want, skipped = [], 0
    for text, mt in src["negatives"]:
        if skip_near_me and mt == "EXACT" and any(w in text for w in NEAR_ME):
            skipped += 1
            continue
        want.append((text, mt))
    return want, skipped


def advise_remainder(n_missing, api_budget):
    """Докопировать остаток в уже созданную кампанию."""
    if n_missing == 0:
        return "ничего не нужно", "все слова уже есть"
    if n_missing <= api_budget:
        return "API", f"{n_missing} операций укладывается в порог {api_budget}; общий список для остатка не даёт выигрыша (слова пришлось бы убирать из кампании)"
    return "Интерфейс/Editor или API порциями по дням", f"{n_missing} больше порога {api_budget} за один заход"


def advise_future(n_full, also, api_budget):
    """Следующие кампании, которым нужен тот же полный список. Возвращает (варианты, рекомендация, причина)."""
    api_total = n_full * also
    shared_total = n_full + also
    opts = [
        ("API по слову", api_total, f"{n_full} × {also} кампаний"),
        ("Общий список", shared_total, f"{n_full} на наполнение один раз + {also} привязок"),
        ("Интерфейс/Editor", 0, "вручную; квоту токена не тратит — не проверено"),
    ]
    if also == 0:
        return opts, "не требуется", "следующих кампаний с этим списком не планируется"
    if n_full >= 200 and n_full <= WORDS_PER_SHARED_LIST and also >= 2:
        return opts, "Общий список", f"{api_total} против {shared_total} операций; лимит списка {WORDS_PER_SHARED_LIST} слов"
    if also == 1 and n_full >= 200:
        return opts, "API (порциями, если больше порога); общий список выгоден от 2 кампаний", f"при одной кампании операций поровну: {api_total} и {shared_total}"
    if n_full > api_budget:
        return opts, "Интерфейс/Editor или API порциями по дням", f"{n_full} больше порога {api_budget}"
    return opts, "API", "список короткий"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--source", type=int, required=True, help="id кампании-источника")
    ap.add_argument("--target", type=int, help="id кампании, куда копируем (если уже создана)")
    ap.add_argument("--also", type=int, default=0, help="сколько СЛЕДУЮЩИХ кампаний (кроме цели) получат тот же полный список минусов")
    ap.add_argument("--api-budget", type=int, default=2000)
    ap.add_argument("--keep-near-me", action="store_true", help="не пропускать точные минусы «near me»")
    ap.add_argument("--client-folder")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = wrap_ga(client.get_service("GoogleAdsService"), "gads_clone_plan")

    src = read_campaign(client, ga, cid, a.source)
    tgt = read_campaign(client, ga, cid, a.target) if a.target else None
    want, skipped = wanted_negatives(src, not a.keep_near_me)
    have = set(map(tuple, tgt["negatives"])) if tgt else set()
    missing = [x for x in want if x not in have]
    by_mt = {}
    for _, mt in missing:
        by_mt[mt] = by_mt.get(mt, 0) + 1

    print(f"=== Источник: {src['name']} (id {src['id']}, {src['status']}, ставки {src['bidding']}, бюджет {src['budget']:g}) ===")
    print(f"минусов кампании: {len(src['negatives'])}; пропускаем «near me» (точные): {skipped}; к переносу: {len(want)}")
    print("прочие критерии кампании:", src["other_criteria"] or "-")
    print("общие списки:", [f"{n} ({m} слов)" for _, n, m in src["shared_sets"]] or "-")
    print(f"групп {src['ad_groups']}, объявлений {src['ads']}, ключи групп {src['group_keywords'] or '-'}")
    print("ассеты кампании:", src["campaign_assets"] or "-", "| ассеты групп:", src["ad_group_assets"] or "-")
    if tgt:
        print(f"\n=== Цель: {tgt['name']} (id {tgt['id']}, {tgt['status']}) ===")
        print(f"минусов уже есть: {len(tgt['negatives'])}; из нужных {len(want)} НЕ хватает: {len(missing)} {by_mt or ''}")

    rows = []   # (часть, операций, как)
    other_crit = sum(src["other_criteria"].values())
    n_kw = sum(v for k, v in src["group_keywords"].items() if not k.startswith("минус"))
    n_asset = sum(src["campaign_assets"].values()) + sum(src["ad_group_assets"].values())
    if not tgt:
        rows += [("бюджет + кампания", 2, "API"), ("гео/язык/прочие критерии", other_crit, "API"),
                 ("привязка общих списков", len(src["shared_sets"]), "API (1 операция на привязку)"),
                 ("группы", src["ad_groups"], "API"), (f"ключи групп ({n_kw})", n_kw, "API" if n_kw <= a.api_budget else "порциями/интерфейс"),
                 ("объявления", src["ads"], "API"), ("привязки ассетов", n_asset, "API")]
    rem_rec, rem_why = advise_remainder(len(missing), a.api_budget)
    opts, rec, why = advise_future(len(want), a.also, a.api_budget)
    print("\n=== Решение 1. Докопировать остаток минусов в уже созданную кампанию ===" if tgt else "\n=== Решение 1. Минусы в эту кампанию ===")
    print(f"к записи: {len(missing)} операций. СПОСОБ: {rem_rec} — {rem_why}")
    print(f"\n=== Решение 2. Следующие кампании ({a.also}), которым нужен тот же список из {len(want)} слов ===")
    print(f"{'Вариант':22s} {'Операций':>9s}  Как считал")
    for name, ops, how in opts:
        print(f"{name:22s} {ops:>9d}  {how}")
    print(f"РЕКОМЕНДАЦИЯ: {rec} — {why}")
    base = sum(n for _, n, _ in rows)
    if rows:
        print("\n=== Остальные части копии (если кампания ещё не создана) ===")
        for part, n, how in rows:
            print(f"  {part:34s} {n:>6d}  {how}")
    print(f"\nИТОГО API сейчас: {base + len(missing)} (порог захода {a.api_budget} — допущение, не лимит Google)")
    print("\n=== Что уже потрачено нашими скриптами сегодня (нижняя оценка) ===")
    ledger_summary(1)

    if a.client_folder:
        d = Path(__file__).resolve().parent.parent / "Клиенты" / a.client_folder / "Статистика"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"clone_plan_{a.source}_{datetime.now():%Y%m%d_%H%M}.json"
        json.dump({"source": src, "target": tgt, "missing_negatives": len(missing), "remainder": rem_rec, "future": rec, "why": why},
                  open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("снимок источника сохранён:", f)


if __name__ == "__main__":
    main()
