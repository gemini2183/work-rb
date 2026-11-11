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
    # ТОЧЕЧНО (с 2026-11-11): одна кампания, в том числе на ПАУЗЕ, и только ссылки с нужным куском адреса:
    python gads_sitelink_utm_fix.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / car+truck injuries / s / lp - tilda" --url-contains pedestrian-bicycle-accident-lawyer-california [--execute]
    С --campaign метки берутся из шаблона ЭТОЙ кампании (не из константы); ссылка, привязанная ещё к чужой кампании, не трогается
    (скрипт останавливается до записи), потому что правка ассета на месте меняла бы и чужую кампанию.
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


def live_assets(ga, cid, campaign=None):
    """Уникальные быстрые ссылки включённых кампаний: id -> (текст, адрес, шаблон, [где привязана])."""
    out = {}
    cond = "campaign.status = 'ENABLED'" if not campaign else "campaign.name = '%s'" % campaign.replace("\\", "\\\\").replace("'", "\\'")
    q1 = ("SELECT campaign.name, campaign.status, asset.id, asset.resource_name, asset.sitelink_asset.link_text, asset.final_urls, asset.tracking_url_template "
          "FROM campaign_asset WHERE campaign_asset.field_type = 'SITELINK' AND campaign_asset.status != 'REMOVED' AND " + cond)
    q2 = ("SELECT campaign.name, campaign.status, ad_group.name, asset.id, asset.resource_name, asset.sitelink_asset.link_text, asset.final_urls, asset.tracking_url_template "
          "FROM ad_group_asset WHERE ad_group_asset.field_type = 'SITELINK' AND ad_group_asset.status != 'REMOVED' AND " + cond)
    for q, grp in ((q1, False), (q2, True)):
        for r in ga.search(customer_id=cid, query=q):
            a = r.asset
            where = f"{r.campaign.name[:20]} / {r.ad_group.name}" if grp else f"{r.campaign.name[:20]} (кампания)"
            e = out.setdefault(a.id, [a.resource_name, a.sitelink_asset.link_text, list(a.final_urls)[0], a.tracking_url_template, []])
            e[4].append(where)
    return out


def new_url(url, utm=None):
    base, anchor = url.split("#", 1)
    return f"{base}?{utm or UTM}#{anchor}"


def campaign_utm(ga, cid, campaign):
    """Метки из шаблона отслеживания самой кампании: `{lpurl}?<метки>`. Нет такого шаблона — стоп, ничего не пишем."""
    q = "SELECT campaign.id, campaign.tracking_url_template FROM campaign WHERE campaign.name = '%s'" % campaign.replace("\\", "\\\\").replace("'", "\\'")
    rows = list(ga.search(customer_id=cid, query=q))
    if len(rows) != 1:
        raise SystemExit(f"СТОП: кампаний с именем «{campaign}» найдено {len(rows)}, нужна ровно одна")
    t = rows[0].campaign.tracking_url_template
    if not t.startswith("{lpurl}?") or "utm_source" not in t:
        raise SystemExit(f"СТОП: шаблон кампании не вида `{{lpurl}}?utm_…`: «{t}». Метки автоматически не вывести")
    return t[len("{lpurl}?"):]


def foreign_attachments(ga, cid, ids, campaign):
    """Привязки этих ассетов к ДРУГИМ кампаниям (любой статус): ассет правится на месте, чужая кампания изменилась бы тоже."""
    if not ids:
        return []
    lst = ",".join(str(i) for i in ids)
    out = []
    for q in (f"SELECT campaign.name, asset.id, asset.sitelink_asset.link_text FROM campaign_asset WHERE asset.id IN ({lst}) AND campaign_asset.status != 'REMOVED'",
              f"SELECT campaign.name, asset.id, asset.sitelink_asset.link_text FROM ad_group_asset WHERE asset.id IN ({lst}) AND ad_group_asset.status != 'REMOVED'"):
        for r in ga.search(customer_id=cid, query=q):
            if r.campaign.name != campaign:
                out.append((r.asset.id, r.asset.sitelink_asset.link_text, r.campaign.name))
    return out


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
    ap.add_argument("--campaign", help="точное имя ОДНОЙ кампании (любой статус, в т.ч. на паузе); метки берутся из её шаблона. Без флага — прежнее поведение: все включённые")
    ap.add_argument("--url-contains", help="трогать только ссылки, в адресе которых есть этот кусок (напр. pedestrian-bicycle-accident-lawyer-california)")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if a.url_contains and not a.campaign:
        raise SystemExit("--url-contains имеет смысл только вместе с --campaign")
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    if a.rollback:
        rows = list(csv.DictReader(open(a.rollback, encoding="utf-8")))
        print(f"Откат по снимку {a.rollback}: ссылок {len(rows)}")
        mutate(client, cid, [(r["resource_name"], r["url"], r["template"]) for r in rows], a.execute)
        return print("Откат выполнен." if a.execute else "Проверка Google пройдена (validate_only). НИЧЕГО не изменено. Для отката: --execute")

    utm = campaign_utm(ga, cid, a.campaign) if a.campaign else UTM
    if a.campaign and utm != UTM:
        print("ВНИМАНИЕ: метки шаблона кампании отличаются от константы скрипта; беру шаблон кампании.")
    live = live_assets(ga, cid, a.campaign)
    todo = {k: v for k, v in live.items() if "#" in v[2] and "utm_source" not in v[2]
            and (not a.url_contains or a.url_contains in v[2])}
    print(f"Быстрых ссылок {'кампании «' + a.campaign + '»' if a.campaign else 'у включённых кампаний'}: {len(live)}; "
          f"с якорем и без меток{' и с «' + a.url_contains + '» в адресе' if a.url_contains else ''}: {len(todo)}\n")
    if a.campaign:
        foreign = foreign_attachments(ga, cid, list(todo), a.campaign)
        if foreign:
            for f in foreign:
                print(f"  ЧУЖАЯ ПРИВЯЗКА: ассет {f[0]} «{f[1]}» привязан ещё к «{f[2]}»")
            raise SystemExit("СТОП: правка на месте затронула бы чужие кампании. Ничего не записано.")
        if a.execute and not todo:
            raise SystemExit("СТОП: подходящих ссылок нет (создайте ссылки раньше). Ничего не записано.")
    if not todo:
        return print("Нечего менять.")
    for k, v in sorted(todo.items(), key=lambda kv: (kv[1][2], kv[0])):
        print(f"{k} | {v[1]} | {v[2].split('//')[1][:70]}  | шаблон ссылки: {v[3] or '—'} | привязок: {len(v[4])}")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_sitelink_utm_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["asset_id", "resource_name", "text", "url", "template", "links"])
        for k, v in todo.items():
            w.writerow([k, v[0], v[1], v[2], v[3], " ; ".join(v[4])])
    print(f"\nСнимок «до»: {snap}")
    print("Образец «станет»:", new_url(next(iter(todo.values()))[2], utm))
    mutate(client, cid, [(v[0], new_url(v[2], utm), TEMPLATE) for v in todo.values()], a.execute)
    if not a.execute:
        return print("\nПроверка Google пройдена (validate_only). НИЧЕГО не изменено. Для записи: --execute")
    after = live_assets(ga, cid, a.campaign)
    print("\nЧтение обратно:")
    bad = 0
    for k in todo:
        v = after[k]
        ok = v[3] == TEMPLATE and v[2] == new_url(todo[k][2], utm)
        bad += not ok
        print(("OK  " if ok else "ОШИБКА "), k, v[1], "|", v[2].split("#")[1], "| шаблон:", v[3])
    print("\nРасхождений:", bad, "\nОткат: --rollback", snap, "--execute")


if __name__ == "__main__":
    main()
