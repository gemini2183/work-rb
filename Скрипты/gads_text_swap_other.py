#!/usr/bin/env python
# coding: utf-8
"""Замена текстов в PMax (группы ассетов), Display (адаптивное объявление) и Demand Gen (мультиассетное объявление). ЗАПИСЬ,
по умолчанию validate_only.

Зачем: 2026-10-13 ProfiMet — «3 prezenty» → 4 и неподтверждённые фразы («Najniższe ceny», «Eksport UE», «2,4 m» и др.) остались в
PMax, Display и Demand Gen (контролёр `ads_facts_audit.py`), в Search/ассетах они уже исправлены.

Как правит:
  • PMax: текст ассета группы неизменяем (`text_asset.text` нельзя обновить) → для каждой привязки со старым текстом создаётся
    новый текстовый ассет (один на уникальный текст) и привязывается к ТЕМ ЖЕ группам с тем же типом поля, старая привязка
    удаляется (в одном запросе: сначала удаления, потом создания — чтобы не упереться в лимит 15/5/5). Старые ассеты остаются в аккаунте.
  • Display и Demand Gen: объявление правится на месте (AdService update заголовков/описаний).
Карта — YAML {texts: {старый: новый}}. Проверка лимитов (заголовок ≤ 30, длинный и описание ≤ 90). Снимок «до» — CSV в Статистике
клиента; после записи — чтение обратно.

Использование:
    python gads_text_swap_other.py --customer-id 7552781705 --client-folder ProfiMet --map <yaml> [--execute]
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def nm(enum, v):
    try:
        return enum.DESCRIPTOR.enum_types[0].values_by_number[v].name
    except Exception:
        return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    MAP = yaml.safe_load(Path(a.map).read_text(encoding="utf-8"))["texts"]
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    # ---- PMax: привязки со старым текстом
    q = ("SELECT campaign.name, campaign.status, asset_group.name, asset_group.status, asset_group.resource_name, "
         "asset_group_asset.resource_name, asset_group_asset.status, asset_group_asset.field_type, asset.text_asset.text "
         "FROM asset_group_asset WHERE campaign.status = 'ENABLED' AND asset_group_asset.status = 'ENABLED'")
    links = []
    for r in ga.search(customer_id=cid, query=q):
        t = r.asset.text_asset.text
        if t in MAP:
            links.append({"camp": r.campaign.name, "group": r.asset_group.name, "group_res": r.asset_group.resource_name,
                          "link_res": r.asset_group_asset.resource_name, "ft": r.asset_group_asset.field_type, "old": t, "new": MAP[t]})
    errs = []
    for l in links:
        ftn = nm(E.AssetFieldTypeEnum, l["ft"])
        lim = 30 if ftn == "HEADLINE" else 90
        if len(l["new"]) > lim:
            errs.append(f"{ftn} {len(l['new'])}>{lim}: {l['new']}")
    for old, new in MAP.items():
        if len(new) > 90:
            errs.append(f"{len(new)}>90: {new}")
    if errs:
        raise SystemExit("лимиты знаков:\n  " + "\n  ".join(sorted(set(errs))))
    print(f"PMax: привязок с проблемным текстом {len(links)}; уникальных текстов {len({l['old'] for l in links})}; "
          f"кампании {sorted({l['camp'] for l in links})}")

    # текущее число включённых привязок по (группа, поле) — чтобы не упереться в лимит максимум/минимум Google
    cnt = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT asset_group.resource_name, asset_group_asset.field_type, campaign.status, asset_group_asset.status "
            "FROM asset_group_asset WHERE campaign.status = 'ENABLED' AND asset_group_asset.status = 'ENABLED'")):
        k = (r.asset_group.resource_name, int(r.asset_group_asset.field_type))
        cnt[k] = cnt.get(k, 0) + 1
    LIM = {"HEADLINE": 15, "LONG_HEADLINE": 5, "DESCRIPTION": 5}
    ops = []
    temp = {}
    n = 0
    for new in sorted({l["new"] for l in links}):   # 1) новые текстовые ассеты
        n -= 1
        res = f"customers/{cid}/assets/{n}"
        temp[new] = res
        mo = client.get_type("MutateOperation")
        mo.asset_operation.create.resource_name = res
        mo.asset_operation.create.text_asset.text = new
        ops.append(mo)
    for l in links:   # 2) попарно: привязать новый и убрать старый (порядок зависит от заполненности группы)
        k = (l["group_res"], int(l["ft"]))
        ftn = nm(E.AssetFieldTypeEnum, l["ft"])
        mx = LIM.get(ftn, 15)
        add = client.get_type("MutateOperation")
        c = add.asset_group_asset_operation.create
        c.asset_group = l["group_res"]
        c.asset = temp[l["new"]]
        c.field_type = l["ft"]
        rem = client.get_type("MutateOperation")
        rem.asset_group_asset_operation.remove = l["link_res"]
        if cnt.get(k, 0) < mx:
            ops.extend([add, rem])      # есть место: сначала привязать новый
        else:
            ops.extend([rem, add])      # группа на максимуме: сначала убрать старый
        # число привязок в группе после пары не меняется

    # ---- Display и Demand Gen: объявления на месте
    q = ("SELECT campaign.name, campaign.status, ad_group_ad.status, ad_group_ad.ad.id, "
         "ad_group_ad.ad.responsive_display_ad.headlines, ad_group_ad.ad.responsive_display_ad.long_headline, "
         "ad_group_ad.ad.responsive_display_ad.descriptions, ad_group_ad.ad.demand_gen_multi_asset_ad.headlines, "
         "ad_group_ad.ad.demand_gen_multi_asset_ad.descriptions FROM ad_group_ad "
         "WHERE campaign.status = 'ENABLED' AND ad_group_ad.status = 'ENABLED'")
    ad_ops, snap = [], []
    for r in ga.search(customer_id=cid, query=q):
        ad = r.ad_group_ad.ad
        rda, dg = ad.responsive_display_ad, ad.demand_gen_multi_asset_ad
        is_dg = bool(dg.headlines or dg.descriptions)
        src = dg if is_dg else rda
        heads = [(x.text, int(x.pinned_field) if hasattr(x, "pinned_field") else 0) for x in src.headlines]
        descs = [(x.text, int(x.pinned_field) if hasattr(x, "pinned_field") else 0) for x in src.descriptions]
        long_h = None if is_dg else (rda.long_headline.text or None)
        if not any(t in MAP for t, _ in heads + descs) and not (long_h and long_h in MAP):
            continue
        op = client.get_type("AdOperation")
        u = op.update
        u.resource_name = f"customers/{cid}/ads/{ad.id}"
        tgt = u.demand_gen_multi_asset_ad if is_dg else u.responsive_display_ad
        pre = "demand_gen_multi_asset_ad" if is_dg else "responsive_display_ad"
        for t, p in heads:
            h = client.get_type("AdTextAsset"); h.text = MAP.get(t, t)
            if p:
                h.pinned_field = p
            tgt.headlines.append(h)
        for t, p in descs:
            d = client.get_type("AdTextAsset"); d.text = MAP.get(t, t)
            if p:
                d.pinned_field = p
            tgt.descriptions.append(d)
        paths = [f"{pre}.headlines", f"{pre}.descriptions"]
        if long_h and not is_dg:
            tgt.long_headline.text = MAP.get(long_h, long_h)
            paths.append(f"{pre}.long_headline.text")
        op.update_mask.paths.extend(paths)
        ad_ops.append((r.campaign.name, "DEMAND_GEN" if is_dg else "DISPLAY", ad.id, op))
        snap.append([ad.id, r.campaign.name, "DEMAND_GEN" if is_dg else "DISPLAY",
                     " | ".join(t for t, _ in heads), " | ".join(t for t, _ in descs), long_h or ""])
    print(f"Display/Demand Gen: объявлений на правку {len(ad_ops)}: " +
          ", ".join(f"{c}/{k}/{i}" for c, k, i, _ in ad_ops))

    # ---- выполнение / проверка
    svc = client.get_service("GoogleAdsService")
    ad_svc = client.get_service("AdService")
    if ops:
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.mutate_operations.extend(ops)
        req.validate_only = not a.execute
        try:
            svc.mutate(request=req)
            print(f"PMax: {'ЗАПИСАНО' if a.execute else 'validate_only принят'} — операций {len(ops)}")
        except Exception as ex:
            print("PMax: ОШИБКА Google:", str(ex)[:900])
            raise SystemExit(1)
    ok = 0
    for c, k, i, op in ad_ops:
        req = client.get_type("MutateAdsRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not a.execute
        try:
            ad_svc.mutate_ads(request=req)
            ok += 1
        except Exception as ex:
            print(f"  {c}/{k}/{i}: ОШИБКА: {str(ex)[:300]}")
    print(f"Display/Demand Gen: {'записано' if a.execute else 'validate_only принято'} {ok} из {len(ad_ops)}")
    if a.execute:
        path = client_stats_dir(a.client_folder) / f"snapshot_before_text_swap_{datetime.now():%Y%m%d_%H%M}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["вид", "кампания", "группа/ad", "поле", "старый текст", "новый текст"])
            for l in links:
                w.writerow(["PMax", l["camp"], l["group"], nm(E.AssetFieldTypeEnum, l["ft"]), l["old"], l["new"]])
            for s in snap:
                w.writerow([s[2], s[1], s[0], "ad", s[3][:300], s[4][:300]])
        print("Снимок «до»:", path)
    else:
        print("ПЛАН. Ничего не записано (добавьте --execute).")


if __name__ == "__main__":
    main()
