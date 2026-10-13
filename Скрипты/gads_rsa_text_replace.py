#!/usr/bin/env python
# coding: utf-8
"""Замена текстов в RSA-объявлениях Search: новое объявление с исправленными текстами, старое на паузу. ЗАПИСЬ, по умолчанию
validate_only.

Зачем: 2026-10-13 ProfiMet — убрать из заголовков и описаний утверждения, которых нет на сайте или которые устарели («100 000+»,
«ponad 10 lat», «Modele 2025 roku», «najniższe ceny»), обновить «3 prezenty» → «4 prezenty». RSA нельзя править на месте:
создаётся новое объявление в той же группе (те же остальные тексты, закрепления, пути, ссылки), старое ставится на паузу в ОДНОМ
запросе (атомарно: либо оба действия, либо ни одного).

Карта замен — YAML: {headlines: {старый: новый}, descriptions: {старый: новый}}. Лимиты: заголовок ≤ 30, описание ≤ 90 знаков;
дубли текстов внутри объявления запрещены. Перед записью пишется снимок старых объявлений
`Статистика/snapshot_before_rsa_replace_<время>.csv`; откат — включить старые, поставить новые на паузу (id в выводе).

Использование:
    python gads_rsa_text_replace.py --customer-id 7552781705 --client-folder ProfiMet \
        --campaign-ids 19158580966 19153311519 24341712952 --map "Клиенты/ProfiMet/Креативы/rsa_replacements_2026-10-13.yaml"
    ... --execute        # записать (после «да»)
"""
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

SUSPECT = re.compile(r"100[  ]?000|2[.,]4 ?m|10\+? ?lat|ponad 10|2008|2025|HIT!?|najniższ|najlepsz|najdłuż|najsilniejsz|"
                     r"najtańsz|numer 1|eksport|instalacj|certyfikowan|3 prezent|trzy prezent|ochrony termin", re.I)


def read_ads(ga, cid, campaign_ids):
    ids = ",".join(campaign_ids)
    q = ("SELECT campaign.id, campaign.name, ad_group.id, ad_group.resource_name, ad_group.name, ad_group_ad.resource_name, "
         "ad_group_ad.ad.id, ad_group_ad.ad.final_urls, ad_group_ad.ad.final_mobile_urls, ad_group_ad.ad.tracking_url_template, "
         "ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions, "
         "ad_group_ad.ad.responsive_search_ad.path1, ad_group_ad.ad.responsive_search_ad.path2 "
         f"FROM ad_group_ad WHERE campaign.id IN ({ids}) AND ad_group_ad.status = 'ENABLED' AND ad_group.status = 'ENABLED' "
         "AND campaign.status = 'ENABLED'")
    out = []
    for r in ga.search(customer_id=cid, query=q):
        a = r.ad_group_ad.ad
        rsa = a.responsive_search_ad
        if not rsa.headlines:
            continue
        out.append({
            "campaign": r.campaign.name, "ad_group": r.ad_group.name, "ad_group_res": r.ad_group.resource_name,
            "ad_res": r.ad_group_ad.resource_name, "ad_id": a.id,
            "headlines": [(h.text, int(h.pinned_field)) for h in rsa.headlines],
            "descriptions": [(d.text, int(d.pinned_field)) for d in rsa.descriptions],
            "path1": rsa.path1, "path2": rsa.path2, "final_urls": list(a.final_urls),
            "final_mobile_urls": list(a.final_mobile_urls), "tracking": a.tracking_url_template,
        })
    return out


DKI = re.compile(r"\{keyword:([^}]*)\}", re.I)


def shown_len(t):
    """Длина для лимита Google: у {Keyword:текст} считается текст по умолчанию, не скобки."""
    return len(DKI.sub(lambda m: m.group(1), t))


def plan(ads, rep):
    rows, problems, unresolved = [], [], {}
    for ad in ads:
        new_h = [(rep["headlines"].get(t, t), p) for t, p in ad["headlines"]]
        new_d = [(rep["descriptions"].get(t, t), p) for t, p in ad["descriptions"]]
        changed = new_h != ad["headlines"] or new_d != ad["descriptions"]
        for t, _ in ad["headlines"] + ad["descriptions"]:
            if SUSPECT.search(t) and t not in rep["headlines"] and t not in rep["descriptions"]:
                unresolved.setdefault(t, set()).add(ad["ad_id"])
        if not changed:
            continue
        errs = []
        for t, _ in new_h:
            if shown_len(t) > 30:
                errs.append(f"заголовок {shown_len(t)}>30: {t}")
        for t, _ in new_d:
            if len(t) > 90:
                errs.append(f"описание {len(t)}>90: {t}")
        if len({t.lower() for t, _ in new_h}) != len(new_h):
            errs.append("дубль заголовка после замены")
        if len({t.lower() for t, _ in new_d}) != len(new_d):
            errs.append("дубль описания после замены")
        if errs:
            problems.append((ad["ad_id"], errs))
            continue
        rows.append({**ad, "new_h": new_h, "new_d": new_d})
    return rows, problems, unresolved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-ids", nargs="+", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    rep = yaml.safe_load(Path(a.map).read_text(encoding="utf-8"))
    rep.setdefault("headlines", {}); rep.setdefault("descriptions", {})
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    ads = read_ads(ga, cid, a.campaign_ids)
    rows, problems, unresolved = plan(ads, rep)
    print(f"включённых RSA: {len(ads)} | к замене: {len(rows)} | с ошибками: {len(problems)}")
    for ad_id, errs in problems:
        print("  ОШИБКА", ad_id, errs)
    by = {}
    for r in rows:
        by.setdefault(r["campaign"], []).append(r)
    for c, rs in by.items():
        print(f"  {c}: {len(rs)} объявлений")
    if unresolved:
        print("\nТРЕБУЮТ РЕШЕНИЯ (подозрительные фразы без замены в карте):")
        for t, ids in unresolved.items():
            print(f"  [{len(ids)} объявл.] {t}")
    if not rows:
        return
    ad_svc = client.get_service("AdGroupAdService")
    ops_all = []
    for r in rows:
        pause = client.get_type("AdGroupAdOperation")
        pause.update.resource_name = r["ad_res"]
        pause.update.status = client.enums.AdGroupAdStatusEnum.PAUSED
        pause.update_mask.paths.append("status")
        create = client.get_type("AdGroupAdOperation")
        n = create.create
        n.ad_group = r["ad_group_res"]
        n.status = client.enums.AdGroupAdStatusEnum.ENABLED
        n.ad.final_urls.extend(r["final_urls"])
        n.ad.final_mobile_urls.extend(r["final_mobile_urls"])
        if r["tracking"]:
            n.ad.tracking_url_template = r["tracking"]
        rsa = n.ad.responsive_search_ad
        if r["path1"]:
            rsa.path1 = r["path1"]
        if r["path2"]:
            rsa.path2 = r["path2"]
        for t, p in r["new_h"]:
            h = client.get_type("AdTextAsset"); h.text = t
            if p:
                h.pinned_field = p
            rsa.headlines.append(h)
        for t, p in r["new_d"]:
            d = client.get_type("AdTextAsset"); d.text = t
            if p:
                d.pinned_field = p
            rsa.descriptions.append(d)
        ops_all.append((r, [pause, create]))
    if not a.execute:
        ok = 0
        for r, ops in ops_all:   # проверка Google без записи, по одному объявлению
            req = client.get_type("MutateAdGroupAdsRequest")
            req.customer_id = cid
            req.operations.extend(ops)
            req.validate_only = True
            try:
                ad_svc.mutate_ad_group_ads(request=req)
                ok += 1
            except Exception as ex:
                print(f"  validate ОШИБКА {r['ad_id']}: {str(ex)[:300]}")
        print(f"\nvalidate_only: прошло {ok} из {len(ops_all)}. ПЛАН. Ничего не записано (добавьте --execute).")
        return
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_rsa_replace_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ad_id", "campaign", "ad_group", "headlines(pin)", "descriptions(pin)", "path1", "path2", "final_urls"])
        for r in rows:
            w.writerow([r["ad_id"], r["campaign"], r["ad_group"],
                        " | ".join(f"{t}[{p}]" for t, p in r["headlines"]),
                        " | ".join(f"{t}[{p}]" for t, p in r["descriptions"]), r["path1"], r["path2"], " ".join(r["final_urls"])])
    print("Снимок «до»:", snap)
    done = 0
    for r, ops in ops_all:
        resp = ad_svc.mutate_ad_group_ads(customer_id=cid, operations=ops)
        done += 1
        print(f"  {r['campaign']} / {r['ad_group'][:30]}: старое {r['ad_id']} → пауза; новое {resp.results[1].resource_name.split('~')[-1]}")
    print(f"выполнено: {done} из {len(ops_all)}")


if __name__ == "__main__":
    main()
