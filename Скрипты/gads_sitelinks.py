#!/usr/bin/env python
# coding: utf-8
"""Быстрые ссылки (sitelinks) на уровне групп объявлений Search-кампании. ЗАПИСЬ только с --execute.

Зачем (Landver, 2026-10-26): адреса объявлений перевели на новые страницы, а кампанийные быстрые ссылки остались на старой
странице и старой главной. Ссылки группы перекрывают кампанийные (ad_group_asset > campaign_asset), поэтому новые страницы получают
свои ссылки, а кампанийные (для групп Truck) не трогаются.

План — YAML: список блоков {groups: [...], sitelinks: [{text, desc1, desc2, url}]}. Лимиты Google: текст ≤25, описание ≤35 знаков.
Скрипт сам проверяет лимиты, наличие групп и якоря (#id) на живой странице. Без --execute только проверка и план. После записи
читает привязки обратно. Снимок «до» — привязки SITELINK групп в Статистика/ клиента. Откат — --remove (отвязывает ссылки плана от групп).

    python gads_sitelinks.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" --plan ../Клиенты/Andverpersonalinjury/Креативы/sitelinks_car_settlement_2026-10-26.yaml [--execute] [--remove]
"""
import argparse
import csv
import re
import urllib.request
from datetime import datetime

import yaml
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def page_ids(url, cache={}):
    base = url.split("#")[0]
    if base not in cache:
        req = urllib.request.Request(base, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/124", "Accept-Language": "en-US"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        cache[base] = set(re.findall(r'id="([^"]+)"', html))
    return cache[base]


def check_plan(plan):
    errs = []
    for b in plan:
        for s in b["sitelinks"]:
            for k, lim in (("text", 25), ("desc1", 35), ("desc2", 35)):
                if len(s[k]) > lim:
                    errs.append(f"{k} {len(s[k])}>{lim}: {s[k]}")
            if "#" in s["url"] and s["url"].split("#")[1] not in page_ids(s["url"]):
                errs.append(f"якоря нет на странице: {s['url']}")
    return errs


def group_map(ga, cid, campaign):
    q = ("SELECT ad_group.id, ad_group.name, ad_group.resource_name FROM ad_group "
         f"WHERE campaign.name = '{campaign}' AND ad_group.status != 'REMOVED'")
    return {r.ad_group.name: r.ad_group.resource_name for r in ga.search(customer_id=cid, query=q)}


def group_sitelinks(ga, cid, campaign):
    q = ("SELECT campaign.name, ad_group.name, ad_group_asset.resource_name, ad_group_asset.status, asset.id, asset.sitelink_asset.link_text, asset.final_urls "
         f"FROM ad_group_asset WHERE campaign.name = '{campaign}' AND ad_group_asset.field_type = 'SITELINK' AND ad_group_asset.status != 'REMOVED'")
    return [(r.ad_group.name, r.ad_group_asset.resource_name, r.asset.id, r.asset.sitelink_asset.link_text, list(r.asset.final_urls)[0]) for r in ga.search(customer_id=cid, query=q)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--remove", action="store_true", help="откат: отвязать ссылки плана от групп плана")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    plan = yaml.safe_load(open(a.plan, encoding="utf-8"))
    errs = check_plan(plan)
    if errs:
        raise SystemExit("ОШИБКИ ПЛАНА:\n  " + "\n  ".join(errs))
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    groups = group_map(ga, cid, a.campaign)
    for b in plan:
        miss = [g for g in b["groups"] if g not in groups]
        if miss:
            raise SystemExit(f"групп нет в кампании: {miss}")
    before = group_sitelinks(ga, cid, a.campaign)
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_sitelinks_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["group", "link_resource", "asset_id", "text", "url"])
        w.writerows(before)
    print(f"Снимок «до»: {snap} (привязок на уровне групп: {len(before)})")
    for b in plan:
        print(f"\nГруппы: {b['groups']}")
        for s in b["sitelinks"]:
            print(f"  {s['text']} ({len(s['text'])}) | {s['desc1']} ({len(s['desc1'])}) | {s['desc2']} ({len(s['desc2'])}) -> {s['url']}")

    if a.remove:
        want = {(g, s["text"]) for b in plan for g in b["groups"] for s in b["sitelinks"]}
        todo = [x for x in before if (x[0], x[3]) in want and x[4] in {s["url"] for b in plan for s in b["sitelinks"]}]
        print(f"\nК отвязке: {len(todo)}")
        if not a.execute:
            return print("НИЧЕГО не изменено. Для отката: --remove --execute")
        svc = client.get_service("AdGroupAssetService")
        ops = []
        for x in todo:
            op = client.get_type("AdGroupAssetOperation"); op.remove = x[1]; ops.append(op)
        svc.mutate_ad_group_assets(customer_id=cid, operations=ops)
        return print("Отвязано:", len(ops))

    asset_svc = client.get_service("AssetService")
    link_svc = client.get_service("AdGroupAssetService")
    ops = []
    for b in plan:
        for s in b["sitelinks"]:
            op = client.get_type("AssetOperation")
            sl = op.create.sitelink_asset
            sl.link_text, sl.description1, sl.description2 = s["text"], s["desc1"], s["desc2"]
            op.create.final_urls.append(s["url"])
            ops.append(op)
    try:
        req = client.get_type("MutateAssetsRequest")
        req.customer_id = cid
        req.operations.extend(ops)
        req.validate_only = not a.execute
        res = asset_svc.mutate_assets(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors:
            print("  ОШИБКА:", e.message)
        raise SystemExit(1)
    if not a.execute:
        print("\nПроверка Google пройдена (validate_only). НИЧЕГО не изменено. Для записи: --execute")
        return
    names = [r.resource_name for r in res.results]
    i = 0
    link_ops = []
    for b in plan:
        for s in b["sitelinks"]:
            for g in b["groups"]:
                lo = client.get_type("AdGroupAssetOperation")
                lo.create.ad_group = groups[g]
                lo.create.asset = names[i]
                lo.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
                link_ops.append(lo)
            i += 1
    link_svc.mutate_ad_group_assets(customer_id=cid, operations=link_ops)
    print(f"\nСоздано ссылок: {len(names)}, привязок к группам: {len(link_ops)}")
    after = group_sitelinks(ga, cid, a.campaign)
    print("\nЧтение обратно (привязки групп плана):")
    for g, _, aid, t, u in sorted(after):
        if g in {x for b in plan for x in b["groups"]}:
            print(f"  {g} | {t} | {u}")
    print("\nОткат: --remove --execute с тем же планом")


if __name__ == "__main__":
    main()
