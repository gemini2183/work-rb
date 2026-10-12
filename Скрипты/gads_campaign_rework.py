#!/usr/bin/env python
# coding: utf-8
"""Переработка Search-кампании Google Ads по файлу плана (JSON) — одним атомарным пакетом.

Что умеет (всё по файлу плана, в коде клиент-специфики нет):
  * создать общий список минус-слов из JSON-файла, подключить к кампании, отключить указанные списки;
  * удалить кампанийные минус-слова (по тексту и типу соответствия);
  * создать группу объявлений (по умолчанию на паузе) с ключами PHRASE / EXACT / BROAD;
  * добавить RSA в указанные группы (и в новую), закрепления заголовков/описаний;
  * поставить на паузу объявления по id;
  * создать сайтлинки / выноски / структурированный сниппет, привязать к кампании, отвязать старые;
  * сменить статус групп (`set_group_status`: [{"group": имя, "status": ENABLED|PAUSED}]).

Режимы:
  без флагов     — ТОЛЬКО проверка (validate_only): Google проверяет весь пакет, ничего не создаёт;
  --execute      — запись; пакет атомарный (всё или ничего); до записи сохраняется снимок «до»
                   (Статистика/<папка>/<имя>_before.json) для отката; после записи состояние
                   читается обратно из аккаунта и печатается.

Пакет идёт одним GoogleAdsService.mutate с временными id (partial_failure=False).
Протокол записи в кабинет — CLAUDE.md («предложил → согласовали → записал»), новые группы — на паузе.

Использование:
    python gads_campaign_rework.py --plan "Клиенты/LuxeBrokers/Кампании/Search/gold_stage1_plan.json"
    python gads_campaign_rework.py --plan ... --execute
"""
import argparse
import json
import os
import sys
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from gads_stats import GOOGLE_ADS_YAML
from gads_change_history import _enum_name


def nm(enum_type, field, value):
    """Имя значения enum (в этой конфигурации клиента enum приходят числом)."""
    return _enum_name(enum_type, field, value)

ROOT = Path(__file__).resolve().parent.parent


def load_plan(path: str) -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return json.loads(p.read_text(encoding="utf-8")), p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--execute", action="store_true", help="записать в кабинет (иначе только validate_only)")
    args = ap.parse_args()

    plan, plan_path = load_plan(args.plan)
    cid = plan["customer_id"]
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    def q(query):
        # GAQL требует, чтобы поле из WHERE (campaign.id) было и в SELECT
        import re
        parts = re.split(r"\sFROM\s", query, maxsplit=1)
        if len(parts) == 2 and "campaign.id" in parts[1] and "campaign.id" not in parts[0]:
            query = parts[0] + ", campaign.id FROM " + parts[1]
        out = []
        for b in ga.search_stream(customer_id=cid, query=query):
            out += list(b.results)
        return out

    # ---------- состояние «до» ----------
    camp_rows = q(f"SELECT campaign.id, campaign.resource_name FROM campaign WHERE campaign.name = '{plan['campaign']}'")
    if len(camp_rows) != 1:
        sys.exit(f"Кампания '{plan['campaign']}' найдена {len(camp_rows)} раз(а)")
    camp_id = camp_rows[0].campaign.id
    camp_rn = camp_rows[0].campaign.resource_name

    groups = {r.ad_group.name: (r.ad_group.id, r.ad_group.resource_name) for r in q(
        f"SELECT ad_group.id, ad_group.name, ad_group.resource_name FROM ad_group WHERE campaign.id = {camp_id} AND ad_group.status != 'REMOVED'")}

    before = {"campaign": plan["campaign"], "campaign_id": camp_id}
    before["campaign_shared_sets"] = [(r.shared_set.name, r.campaign_shared_set.resource_name) for r in q(
        f"SELECT shared_set.name, campaign_shared_set.resource_name FROM campaign_shared_set WHERE campaign.id = {camp_id} AND campaign_shared_set.status = 'ENABLED'")]
    before["campaign_negatives"] = [(r.campaign_criterion.keyword.text, nm('KeywordMatchTypeEnum', 'KeywordMatchType', r.campaign_criterion.keyword.match_type), r.campaign_criterion.resource_name) for r in q(
        f"SELECT campaign_criterion.resource_name, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type FROM campaign_criterion "
        f"WHERE campaign.id = {camp_id} AND campaign_criterion.type = 'KEYWORD' AND campaign_criterion.negative = TRUE")]
    ads = {}
    for r in q(f"SELECT ad_group_ad.resource_name, ad_group_ad.ad.id, ad_group_ad.status, ad_group.name FROM ad_group_ad "
               f"WHERE campaign.id = {camp_id} AND ad_group_ad.status != 'REMOVED'"):
        ads[r.ad_group_ad.ad.id] = (r.ad_group_ad.resource_name, nm('AdGroupAdStatusEnum', 'AdGroupAdStatus', r.ad_group_ad.status), r.ad_group.name)
    before["ads"] = {str(k): v for k, v in ads.items()}
    links = []
    for r in q(f"SELECT campaign_asset.resource_name, campaign_asset.field_type, campaign_asset.status, asset.id FROM campaign_asset "
               f"WHERE campaign.id = {camp_id} AND campaign_asset.status != 'REMOVED'"):
        links.append((r.campaign_asset.resource_name, nm('AssetFieldTypeEnum', 'AssetFieldType', r.campaign_asset.field_type), r.asset.id))
    before["campaign_assets"] = links

    out_dir = ROOT / "Клиенты" / plan_path.parts[plan_path.parts.index("Клиенты") + 1] / "Статистика"
    snap = out_dir / f"{plan_path.stem}_before.json"
    snap.write_text(json.dumps(before, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Снимок «до»: {snap}")

    # ---------- сборка пакета ----------
    ops = []

    def mop():
        return client.get_type("MutateOperation")

    shared_set_svc = client.get_service("SharedSetService")
    ad_group_svc = client.get_service("AdGroupService")
    asset_svc = client.get_service("AssetService")

    # 0. паузы объявлений — первыми (лимит 3 включённых RSA в группе)
    for ad_id in plan.get("pause_ads", []):
        if ad_id not in ads:
            sys.exit(f"Объявление {ad_id} не найдено в кампании")
        op = mop()
        u = op.ad_group_ad_operation.update
        u.resource_name = ads[ad_id][0]
        u.status = E.AdGroupAdStatusEnum.PAUSED
        op.ad_group_ad_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
        ops.append(op)

    # 0b. статус групп (например, включение после модерации) — отдельное согласование
    for item in plan.get("set_group_status", []):
        if item["group"] not in groups:
            sys.exit(f"Группа '{item['group']}' не найдена в кампании")
        op = mop()
        u = op.ad_group_operation.update
        u.resource_name = groups[item["group"]][1]
        u.status = getattr(E.AdGroupStatusEnum, item["status"])
        op.ad_group_operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
        ops.append(op)

    # 1. список минусов
    nl = plan.get("negative_list")
    if nl:
        members = json.loads((ROOT / nl["members_file"]).read_text(encoding="utf-8"))["v2"]
        ss_rn = shared_set_svc.shared_set_path(cid, -1)
        op = mop()
        s = op.shared_set_operation.create
        s.resource_name = ss_rn
        s.name = nl["name"]
        s.type_ = E.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        ops.append(op)
        for text, mt in members:
            op = mop()
            c = op.shared_criterion_operation.create
            c.shared_set = ss_rn
            c.keyword.text = text
            c.keyword.match_type = getattr(E.KeywordMatchTypeEnum, mt)
            ops.append(op)
        op = mop()
        cs = op.campaign_shared_set_operation.create
        cs.campaign = camp_rn
        cs.shared_set = ss_rn
        ops.append(op)
        for name in nl.get("detach_lists", []):
            hit = [rn for n, rn in before["campaign_shared_sets"] if n == name]
            if len(hit) != 1:
                sys.exit(f"Список '{name}' не подключён к кампании (найдено {len(hit)})")
            op = mop()
            op.campaign_shared_set_operation.remove = hit[0]
            ops.append(op)

    # 2. кампанийные минусы на удаление
    for item in plan.get("remove_campaign_negatives", []):
        hit = [rn for t, m, rn in before["campaign_negatives"] if t.lower() == item["text"].lower() and m == item["match"]]
        if len(hit) != 1:
            sys.exit(f"Кампанийный минус {item} найден {len(hit)} раз(а)")
        op = mop()
        op.campaign_criterion_operation.remove = hit[0]
        ops.append(op)

    # 3. новая группа + ключи
    ng = plan.get("new_group")
    new_group_rn = None
    if ng:
        new_group_rn = ad_group_svc.ad_group_path(cid, -2)
        op = mop()
        g = op.ad_group_operation.create
        g.resource_name = new_group_rn
        g.name = ng["name"]
        g.campaign = camp_rn
        g.status = getattr(E.AdGroupStatusEnum, ng.get("status", "PAUSED"))
        g.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
        if ng.get("cpc_bid_micros"):
            g.cpc_bid_micros = ng["cpc_bid_micros"]
        ops.append(op)
        for kw in ng["keywords"]:
            op = mop()
            c = op.ad_group_criterion_operation.create
            c.ad_group = new_group_rn
            c.status = E.AdGroupCriterionStatusEnum.ENABLED
            c.keyword.text = kw
            c.keyword.match_type = getattr(E.KeywordMatchTypeEnum, ng.get("match", "PHRASE"))
            ops.append(op)

    # 4. RSA
    rsa = plan.get("rsa")
    if rsa:
        targets = []
        for name in rsa["ad_groups"]:
            if name not in groups:
                sys.exit(f"Группа '{name}' не найдена в кампании")
            targets.append(groups[name][1])
        if rsa.get("also_new_group") and new_group_rn:
            targets.append(new_group_rn)
        for ag_rn in targets:
            op = mop()
            aa = op.ad_group_ad_operation.create
            aa.ad_group = ag_rn
            aa.status = E.AdGroupAdStatusEnum.ENABLED
            aa.ad.final_urls.append(rsa["final_url"])
            r = aa.ad.responsive_search_ad
            for h in rsa["headlines"]:
                t = client.get_type("AdTextAsset")
                t.text = h["text"]
                if h.get("pin"):
                    t.pinned_field = getattr(E.ServedAssetFieldTypeEnum, h["pin"])
                r.headlines.append(t)
            for d in rsa["descriptions"]:
                t = client.get_type("AdTextAsset")
                t.text = d["text"]
                if d.get("pin"):
                    t.pinned_field = getattr(E.ServedAssetFieldTypeEnum, d["pin"])
                r.descriptions.append(t)
            if rsa.get("path1"):
                r.path1 = rsa["path1"]
            if rsa.get("path2"):
                r.path2 = rsa["path2"]
            ops.append(op)

    # 5. активы
    temp = [-10]

    def next_asset_rn():
        temp[0] -= 1
        return asset_svc.asset_path(cid, temp[0])

    def link(asset_rn, field):
        op = mop()
        ca = op.campaign_asset_operation.create
        ca.asset = asset_rn
        ca.campaign = camp_rn
        ca.field_type = getattr(E.AssetFieldTypeEnum, field)
        ops.append(op)

    def unlink_existing(field):
        for rn, ft, _aid in before["campaign_assets"]:
            if ft == field:
                op = mop()
                op.campaign_asset_operation.remove = rn
                ops.append(op)

    sl = plan.get("sitelinks")
    if sl:
        for it in sl["items"]:
            rn = next_asset_rn()
            op = mop()
            a = op.asset_operation.create
            a.resource_name = rn
            a.sitelink_asset.link_text = it["text"]
            a.sitelink_asset.description1 = it["d1"]
            a.sitelink_asset.description2 = it["d2"]
            url = it["url"]
            if sl.get("utm_query"):
                url += "?" + sl["utm_query"]
            if it.get("anchor"):
                url += "#" + it["anchor"]
            a.final_urls.append(url)
            if sl.get("tracking_url_template"):
                a.tracking_url_template = sl["tracking_url_template"]
            ops.append(op)
            link(rn, "SITELINK")
        if sl.get("unlink_existing"):
            unlink_existing("SITELINK")

    for text in plan.get("callouts", []):
        rn = next_asset_rn()
        op = mop()
        a = op.asset_operation.create
        a.resource_name = rn
        a.callout_asset.callout_text = text
        ops.append(op)
        link(rn, "CALLOUT")

    sn = plan.get("snippet")
    if sn:
        rn = next_asset_rn()
        op = mop()
        a = op.asset_operation.create
        a.resource_name = rn
        a.structured_snippet_asset.header = sn["header"]
        a.structured_snippet_asset.values.extend(sn["values"])
        ops.append(op)
        link(rn, "STRUCTURED_SNIPPET")
        if sn.get("unlink_existing"):
            unlink_existing("STRUCTURED_SNIPPET")

    kinds = {}
    for op in ops:
        k = op._pb.WhichOneof("operation") if hasattr(op, "_pb") else op.WhichOneof("operation")
        kinds[k] = kinds.get(k, 0) + 1
    print(f"Операций в пакете: {len(ops)}")
    for k, v in sorted(kinds.items()):
        print(f"  {k}: {v}")

    # ---------- проверка и запись ----------
    def send(validate: bool):
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.mutate_operations.extend(ops)
        req.partial_failure = False
        req.validate_only = validate
        return ga.mutate(request=req)

    try:
        send(True)
        print("validate_only: ОК — Google принял пакет без ошибок")
    except GoogleAdsException as ex:
        print("validate_only: ОШИБКА")
        for e in ex.failure.errors:
            idx = [str(el.index) for el in e.location.field_path_elements if el.field_name == "mutate_operations"] if e.location else []
            print(f"  - {e.message} | операция {idx}")
        sys.exit(2)

    if not args.execute:
        print("Режим проверки: ничего не записано. Для записи — флаг --execute.")
        return

    resp = send(False)
    print(f"ЗАПИСАНО: {len(resp.mutate_operation_responses)} операций")

    # ---------- чтение обратно ----------
    print("\n=== Состояние после записи (читаем из аккаунта) ===")
    for r in q(f"SELECT shared_set.name, shared_set.member_count, campaign_shared_set.status FROM campaign_shared_set WHERE campaign.id = {camp_id}"):
        print("список минусов:", r.shared_set.name, "| членов:", r.shared_set.member_count, "|", nm('CampaignSharedSetStatusEnum', 'CampaignSharedSetStatus', r.campaign_shared_set.status))
    neg = [r.campaign_criterion.keyword.text for r in q(
        f"SELECT campaign_criterion.keyword.text FROM campaign_criterion WHERE campaign.id = {camp_id} AND campaign_criterion.type='KEYWORD' AND campaign_criterion.negative=TRUE")]
    print("кампанийных минусов:", len(neg), "| 'hollywood' есть:", "hollywood" in [n.lower() for n in neg])
    if ng:
        for r in q(f"SELECT ad_group.name, ad_group.status FROM ad_group WHERE campaign.id = {camp_id} AND ad_group.name = '{ng['name']}'"):
            print("группа:", r.ad_group.name, "|", nm('AdGroupStatusEnum', 'AdGroupStatus', r.ad_group.status))
        kws = q(f"SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status FROM ad_group_criterion "
                f"WHERE ad_group.name = '{ng['name']}' AND campaign.id = {camp_id} AND ad_group_criterion.type='KEYWORD'")
        print("ключей в новой группе:", len(kws), "| типы:", sorted({nm('KeywordMatchTypeEnum', 'KeywordMatchType', k.ad_group_criterion.keyword.match_type) for k in kws}))
    for item in plan.get("set_group_status", []):
        for r in q(f"SELECT ad_group.name, ad_group.status FROM ad_group WHERE campaign.id = {camp_id} AND ad_group.name = '{item['group']}'"):
            print("группа:", r.ad_group.name, "|", nm('AdGroupStatusEnum', 'AdGroupStatus', r.ad_group.status))
    print("объявления кампании (включённые / на паузе) по группам:")
    cnt = {}
    for r in q(f"SELECT ad_group.name, ad_group_ad.status FROM ad_group_ad WHERE campaign.id = {camp_id} AND ad_group_ad.status != 'REMOVED'"):
        stn = nm('AdGroupAdStatusEnum', 'AdGroupAdStatus', r.ad_group_ad.status)
        cnt.setdefault(r.ad_group.name, {}).setdefault(stn, 0)
        cnt[r.ad_group.name][stn] += 1
    for g, d in sorted(cnt.items()):
        print(f"  {g}: {d}")
    for r in q(f"SELECT campaign_asset.field_type, campaign_asset.status, asset.sitelink_asset.link_text, asset.callout_asset.callout_text, "
               f"asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, asset.final_urls, asset.tracking_url_template "
               f"FROM campaign_asset WHERE campaign.id = {camp_id} AND campaign_asset.status = 'ENABLED' "
               f"AND campaign_asset.field_type IN ('SITELINK','CALLOUT','STRUCTURED_SNIPPET')"):
        a = r.asset
        label = a.sitelink_asset.link_text or a.callout_asset.callout_text or f"{a.structured_snippet_asset.header}: {', '.join(a.structured_snippet_asset.values)}"
        extra = f" -> {list(a.final_urls)[0]}  [tpl: {a.tracking_url_template or 'наследует кампанию'}]" if a.final_urls else ""
        print(f"  {nm('AssetFieldTypeEnum', 'AssetFieldType', r.campaign_asset.field_type)}: {label}{extra}")
    print("\nГотово. Откат — по снимку «до» (", snap, ")")


if __name__ == "__main__":
    main()
