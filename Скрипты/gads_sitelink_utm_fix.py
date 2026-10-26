#!/usr/bin/env python
# coding: utf-8
"""Быстрые ссылки с якорем (#) теряют UTM шаблона кампании. ЗАПИСЬ только с --execute.

Зачем (Landver, 2026-10-26): шаблон кампании `{lpurl}?utm_…` дописывает метки ПОСЛЕ `#`, поэтому метки уходят во фрагмент адреса,
не доходят до GA4/Ringostat, а браузер не находит блок по якорю (`#ldv-reviews?utm…` ≠ `#ldv-reviews`). Исправление на каждой
быстрой ссылке: метки (с теми же ValueTrack, что в шаблоне кампании) кладутся в конечный URL ДО `#`, а на самой ссылке
ставится свой шаблон `{lpurl}` — он перекрывает шаблон кампании и ничего не дописывает. Ссылка обновляется на месте (id и
привязки сохраняются).
Вики: База_знаний/Инструменты/Шаблон-отслеживания-lpurl-и-якорь-в-быстрой-ссылке.md

Область: быстрые ссылки (SITELINK), привязанные к включённым кампаниям (на уровне кампании или группы), у которых в адресе есть `#`
и ещё нет `utm_source`. Без --execute: список «было → станет» и проверка Google (validate_only), ничего не меняется.
Снимок «до» — Статистика/snapshot_before_sitelink_utm_<время>.csv; откат — `--rollback <снимок> --execute`.

    python gads_sitelink_utm_fix.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury [--execute]
    python gads_sitelink_utm_fix.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury --rollback <снимок.csv> [--execute]
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

# те же метки, что в шаблоне кампании «search / car+truck injuries / s / lp - tilda» (прочитано из кабинета 2026-10-26)
UTM = ("utm_source=google&utm_medium=cpc&utm_campaign={campaignid}_{ifsearch:search}{ifcontent:context}"
       "&utm_content=rb_cid_{campaignid}_{ifsearch:search}{ifcontent:context}|gid_{adgroupid}|aid_{creative}|pos_{adposition}"
       "|dev_{device}|plc_{placement}|region_id_{loc_physical_ms}|targetid_{targetid}|gclid_{gclid}&utm_term={keyword}")
TEMPLATE = "{lpurl}"


def live_assets(ga, cid):
    """Уникальные быстрые ссылки включённых кампаний: id -> (текст, адрес, шаблон, [где привязана])."""
    out = {}
    q1 = ("SELECT campaign.name, campaign.status, asset.id, asset.resource_name, asset.sitelink_asset.link_text, asset.final_urls, asset.tracking_url_template "
          "FROM campaign_asset WHERE campaign_asset.field_type = 'SITELINK' AND campaign_asset.status != 'REMOVED' AND campaign.status = 'ENABLED'")
    q2 = ("SELECT campaign.name, campaign.status, ad_group.name, asset.id, asset.resource_name, asset.sitelink_asset.link_text, asset.final_urls, asset.tracking_url_template "
          "FROM ad_group_asset WHERE ad_group_asset.field_type = 'SITELINK' AND ad_group_asset.status != 'REMOVED' AND campaign.status = 'ENABLED'")
    for q, grp in ((q1, False), (q2, True)):
        for r in ga.search(customer_id=cid, query=q):
            a = r.asset
            where = f"{r.campaign.name[:20]} / {r.ad_group.name}" if grp else f"{r.campaign.name[:20]} (кампания)"
            e = out.setdefault(a.id, [a.resource_name, a.sitelink_asset.link_text, list(a.final_urls)[0], a.tracking_url_template, []])
            e[4].append(where)
    return out


def new_url(url):
    base, anchor = url.split("#", 1)
    return f"{base}?{UTM}#{anchor}"


def mutate(client, cid, rows, execute):
    """rows: [(resource_name, final_url, template)] — обновление на месте."""
    ops = []
    for rn, url, tmpl in rows:
        op = client.get_type("AssetOperation")
        op.update.resource_name = rn
        op.update.final_urls.append(url)
        op.update.tracking_url_template = tmpl
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["final_urls", "tracking_url_template"]))
        ops.append(op)
    req = client.get_type("MutateAssetsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not execute
    try:
        client.get_service("AssetService").mutate_assets(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors:
            print("  ОШИБКА:", e.message)
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--rollback", help="CSV-снимок «до»: вернуть адреса и шаблоны из него")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    if a.rollback:
        rows = list(csv.DictReader(open(a.rollback, encoding="utf-8")))
        print(f"Откат по снимку {a.rollback}: ссылок {len(rows)}")
        mutate(client, cid, [(r["resource_name"], r["url"], r["template"]) for r in rows], a.execute)
        return print("Откат выполнен." if a.execute else "Проверка Google пройдена (validate_only). НИЧЕГО не изменено. Для отката: --execute")

    live = live_assets(ga, cid)
    todo = {k: v for k, v in live.items() if "#" in v[2] and "utm_source" not in v[2]}
    print(f"Быстрых ссылок у включённых кампаний: {len(live)}; с якорем и без меток: {len(todo)}\n")
    for k, v in sorted(todo.items(), key=lambda kv: (kv[1][2], kv[0])):
        print(f"{k} | {v[1]} | {v[2].split('//')[1][:70]}  | шаблон ссылки: {v[3] or '—'} | привязок: {len(v[4])}")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_sitelink_utm_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["asset_id", "resource_name", "text", "url", "template", "links"])
        for k, v in todo.items():
            w.writerow([k, v[0], v[1], v[2], v[3], " ; ".join(v[4])])
    print(f"\nСнимок «до»: {snap}")
    print("Образец «станет»:", new_url(next(iter(todo.values()))[2]))
    mutate(client, cid, [(v[0], new_url(v[2]), TEMPLATE) for v in todo.values()], a.execute)
    if not a.execute:
        return print("\nПроверка Google пройдена (validate_only). НИЧЕГО не изменено. Для записи: --execute")
    after = live_assets(ga, cid)
    print("\nЧтение обратно:")
    bad = 0
    for k in todo:
        v = after[k]
        ok = v[3] == TEMPLATE and v[2] == new_url(todo[k][2])
        bad += not ok
        print(("OK  " if ok else "ОШИБКА "), k, v[1], "|", v[2].split("#")[1], "| шаблон:", v[3])
    print("\nРасхождений:", bad, "\nОткат: --rollback", snap, "--execute")


if __name__ == "__main__":
    main()
