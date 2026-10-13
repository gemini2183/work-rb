#!/usr/bin/env python
# coding: utf-8
"""Тексты ассетов кампаний (сайтлинки, уточнения, структурные сниппеты, цены): правка на месте и добавление. ЗАПИСЬ, по умолчанию
validate_only.

Зачем: 2026-10-13 ProfiMet — в общем стандартном наборе ассетов (5 кампаний) остались «3 prezenty» (на сайте 4) и «Nowość:
MOCNA Went Plus» (недоказанный ярлык); плюс добавляются «вкусные» ассеты из фактов сайта (отзывы 4,9, скидка 100 zł, сертификат).
Google разрешает править тексты ассета на месте (проверено validate_only 13.10) — правка действует сразу во всех кампаниях, где
ассет подключён.

Режимы:
    --fix    правка на месте (список FIXES)
    --add    создать новые ассеты (список ADDS) и подключить к кампаниям TARGETS
Без --execute ничего не пишется (проверка Google). Снимок «до» — CSV в Статистике клиента; после записи — чтение обратно.

Использование:
    python gads_assets_text_fix.py --customer-id 7552781705 --client-folder ProfiMet --fix [--execute]
    python gads_assets_text_fix.py --customer-id 7552781705 --client-folder ProfiMet --add [--execute]
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

BASE = "https://mocnaszklarnia.pl/"
# Кампании стандартного набора (Search и PMax).
TARGETS = {19153311519: "Search | Brand | Pl", 19158580966: "Search | Poliweglan | Pl", 23775369828: "pmax1_test",
           24332178236: "pmax01_call_test", 24341712952: "search / szklarnia generic"}

# Правка на месте: (id ассета, тип, поля) — только то, что меняется.
FIXES = [
    {"id": 428690900321, "type": "SITELINK", "set": {"link_text": "4 prezenty gratis", "description1": "Korzyść od 290 do 430 zł"}},
    {"id": 428793370450, "type": "SITELINK", "set": {"link_text": "MOCNA Went Plus"}},
    {"id": 323619279423, "type": "CALLOUT", "set": {"callout_text": "4 prezenty gratis"}},
    {"id": 428810156029, "type": "PRICE", "offering": {"header": "Domek HOBBY, dwuspadowy", "description": "4 prezenty gratis"}},
]
# Новые ассеты (факты сайта 2026-10-13: отзывы 4,9 / 80+, скидка 100 zł за 2+ шт., значок ECJiP, 45 000+ заказов, комплект и поддержка).
ADDS = [
    {"type": "CALLOUT", "text": "Ocena 4,9 – 80+ opinii"},
    {"type": "CALLOUT", "text": "Rabat 100 zł przy 2 szt."},
    {"type": "CALLOUT", "text": "Wyprodukowano w Polsce"},
    {"type": "CALLOUT", "text": "45 000+ zamówień rocznie"},
    {"type": "SITELINK", "text": "Opinie klientów 4,9", "d1": "Ponad 80 recenzji na stronie", "d2": "Sprawdź, co piszą kupujący", "url": BASE},
    {"type": "SITELINK", "text": "Rabat przy 2 szklarniach", "d1": "100 zł rabatu przy 2+ szt.", "d2": "Dostawa pod ten sam adres", "url": BASE},
    {"type": "SNIPPET", "header": "Service catalog",
     "values": ["Dostawa w całej Polsce", "Płatność przy odbiorze", "Przelew bankowy", "Części zamienne", "Wsparcie posprzedażowe"]},
]
LIMITS = {"callout": 25, "link": 25, "desc": 35, "snippet": 25}


def check_limits():
    errs = []
    for f in FIXES:
        for k, v in f.get("set", {}).items():
            lim = LIMITS["desc"] if k.startswith("desc") else LIMITS["link"]
            if len(v) > lim:
                errs.append(f"{k} {len(v)}>{lim}: {v}")
    for a in ADDS:
        if a["type"] == "CALLOUT" and len(a["text"]) > 25:
            errs.append(f"callout {len(a['text'])}>25: {a['text']}")
        if a["type"] == "SITELINK":
            for k, lim in (("text", 25), ("d1", 35), ("d2", 35)):
                if len(a[k]) > lim:
                    errs.append(f"sitelink {k} {len(a[k])}>{lim}: {a[k]}")
        if a["type"] == "SNIPPET":
            for v in a["values"]:
                if len(v) > 25:
                    errs.append(f"snippet {len(v)}>25: {v}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if not (a.fix or a.add):
        ap.error("укажите --fix и/или --add")
    cid = a.customer_id.replace("-", "")
    errs = check_limits()
    if errs:
        raise SystemExit("лимиты знаков нарушены:\n  " + "\n  ".join(errs))
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    ops, snap = [], []

    if a.fix:
        for f in FIXES:
            res = f"customers/{cid}/assets/{f['id']}"
            cur = next(iter(ga.search(customer_id=cid, query=(
                "SELECT asset.id, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, "
                "asset.callout_asset.callout_text, asset.price_asset.price_offerings, asset.price_asset.type, "
                "asset.price_asset.price_qualifier, asset.price_asset.language_code "
                f"FROM asset WHERE asset.id = {f['id']}"))), None)
            if cur is None:
                print("  не найден ассет", f["id"])
                continue
            asset = cur.asset
            mo = client.get_type("MutateOperation")
            op = mo.asset_operation
            op.update.resource_name = res
            paths = []
            if f["type"] == "SITELINK":
                snap.append([f["id"], "SITELINK", asset.sitelink_asset.link_text, asset.sitelink_asset.description1,
                             asset.sitelink_asset.description2])
                for k, v in f["set"].items():
                    setattr(op.update.sitelink_asset, k, v)
                    paths.append(f"sitelink_asset.{k}")
            elif f["type"] == "CALLOUT":
                snap.append([f["id"], "CALLOUT", asset.callout_asset.callout_text, "", ""])
                op.update.callout_asset.callout_text = f["set"]["callout_text"]
                paths.append("callout_asset.callout_text")
            elif f["type"] == "PRICE":
                op.update.price_asset.CopyFrom(asset.price_asset)
                snap.append([f["id"], "PRICE", "; ".join(f"{po.header}|{po.description}" for po in asset.price_asset.price_offerings), "", ""])
                for po in op.update.price_asset.price_offerings:
                    if po.header == f["offering"]["header"]:
                        po.description = f["offering"]["description"]
                paths.append("price_asset.price_offerings")
            op.update_mask.paths.extend(paths)
            ops.append(mo)

    if a.add:
        n = 0
        for item in ADDS:
            n -= 1
            temp = f"customers/{cid}/assets/{n}"
            mo = client.get_type("MutateOperation")
            op = mo.asset_operation
            op.create.resource_name = temp
            if item["type"] == "CALLOUT":
                op.create.callout_asset.callout_text = item["text"]
                field = client.enums.AssetFieldTypeEnum.CALLOUT
            elif item["type"] == "SITELINK":
                op.create.sitelink_asset.link_text = item["text"]
                op.create.sitelink_asset.description1 = item["d1"]
                op.create.sitelink_asset.description2 = item["d2"]
                op.create.final_urls.append(item["url"])
                field = client.enums.AssetFieldTypeEnum.SITELINK
            else:
                op.create.structured_snippet_asset.header = item["header"]
                op.create.structured_snippet_asset.values.extend(item["values"])
                field = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
            ops.append(mo)
            for camp in TARGETS:
                lk = client.get_type("MutateOperation")
                c = lk.campaign_asset_operation.create
                c.campaign = f"customers/{cid}/campaigns/{camp}"
                c.asset = temp
                c.field_type = field
                ops.append(lk)
            snap.append(["NEW", item["type"], item.get("text") or item.get("header"), item.get("d1", ""), item.get("d2", "")])

    print(f"операций: {len(ops)} (ассеты на правку: {len(FIXES) if a.fix else 0}, новых: {len(ADDS) if a.add else 0}, "
          f"кампаний подключения: {len(TARGETS)})")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not a.execute
    svc = client.get_service("GoogleAdsService")
    try:
        svc.mutate(request=req)
    except Exception as ex:
        print("ОШИБКА Google:", str(ex)[:1200])
        raise SystemExit(1)
    if not a.execute:
        print("validate_only: Google принял. ПЛАН, ничего не записано (добавьте --execute).")
        return
    path = client_stats_dir(a.client_folder) / f"snapshot_before_assets_text_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["asset_id", "тип", "было / текст", "описание1", "описание2"])
        w.writerows(snap)
    print("ВЫПОЛНЕНО. Снимок «до»:", path)


if __name__ == "__main__":
    main()
