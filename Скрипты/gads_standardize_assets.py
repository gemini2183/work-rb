#!/usr/bin/env python
# coding: utf-8
"""Приводит ассеты включённых кампаний ProfiMet к единому стандарту.

Эталон — набор ассетов кампании `search / szklarnia generic` (id 24341712952): сайтлинки, уточнения, структурированный
сниппет, картинки (только для Search). Дополнительно создаётся новый ценовой ассет (5 моделей, без «HIT» и «Najniższa
cena») и подключается всем целевым кампаниям.

Для каждой целевой кампании: привязки этих типов ассетов, которых нет в эталоне, снимаются (сами ассеты остаются в
аккаунте), недостающие эталонные подключаются. Одна транзакция GoogleAdsService.mutate на все кампании.
Типы: Search — SITELINK, CALLOUT, STRUCTURED_SNIPPET, AD_IMAGE, PRICE; PMax — SITELINK, CALLOUT, STRUCTURED_SNIPPET, PRICE
(картинки PMax живут в группах ассетов). Звонок аккаунта, лого, название компании, промо и кампанийные звонки не трогаем.

Решение пользователя 2026-10-09: стандартизировать во всех включённых кампаниях, включая Poliweglan и pmax1_test
(окно покоя до 22.10 касается ставок и целей; риск повторной проверки объявлений принят). Старая `search / szklarnia/tunel`
в списке не участвует (ставится на паузу после запуска новой).

БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google проверяет, ничего не меняет). Запись — только с --execute.
Снимок «до» (снятые привязки: кампания, тип, ассет, статус, resource_name) — CSV в Статистика/ клиента.
После записи читает привязки обратно и печатает число по типам.

Использование:
    python gads_standardize_assets.py --customer-id 7552781705 --client-folder ProfiMet
    ... --execute
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

SOURCE_CAMPAIGN = 24341712952  # search / szklarnia generic — эталон
TARGETS = {  # id: (имя, канал)
    19153311519: ("Search | Brand | Pl", "SEARCH"),
    19158580966: ("Search | Poliweglan | Pl", "SEARCH"),
    23775369828: ("pmax1_test", "PMAX"),
    24332178236: ("pmax01_call_test", "PMAX"),
}
FIELDS = {"SEARCH": ["SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "AD_IMAGE", "PRICE"],
          "PMAX": ["SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "PRICE"]}
BASE = "https://mocnaszklarnia.pl/"
# Цены «от» (поликарбонат 4 мм) сверены с текстом главной 2026-10-09; MAXI и Went Plus — минимальная длина 4 м, остальные 2 м.
# Подписи только из фактов сайта: оплата при получении, доставка по Польше бесплатно 3–7 дней, 3 подарка, гарантия 5 лет на
# поликарбонат; без «HIT», «Najniższa cena», «Nowość» (не подтверждены клиентом). Решение пользователя 2026-10-09.
PRICE_OFFERINGS = [  # (заголовок <=25, подпись <=25, цена zł, якорь)
    ("Szklarnia MOCNA 3 m", "Płać przy odbiorze", 1299, "#mocna"),
    ("NORDSTAR, proste ściany", "Dostawa gratis, 3-7 dni", 1949, "#nordstar"),
    ("Domek HOBBY, dwuspadowy", "3 prezenty gratis", 1599, "#hobby"),
    ("MOCNA MAXI, wys. 2,2 m", "Szer. 4 m, dostawa gratis", 2249, "#maxi"),
    ("Szklarnia MINI 2 m", "Na małą działkę", 1199, "#mini"),
    ("MOCNA KOMPAKT 2,5 m", "Gwarancja do 5 lat", 1299, "#kompakt"),
    ("MOCNA Went Plus 3 m", "Z wentylacją", 1729, "#wentplus"),
    ("STANDARD PLUS 3 m", "Profil 20x20 mm", 1199, "#standard"),
]


def read_links(client, ga, cid, campaign_id, fields):
    E = client.enums
    names = ", ".join(f"'{f}'" for f in fields)
    q = ("SELECT campaign.id, campaign_asset.resource_name, campaign_asset.field_type, campaign_asset.status, asset.id, "
         "asset.sitelink_asset.link_text, asset.callout_asset.callout_text "
         f"FROM campaign_asset WHERE campaign.id = {campaign_id} AND campaign_asset.status != 'REMOVED' "
         f"AND campaign_asset.field_type IN ({names})")
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        rows.append({"campaign_id": campaign_id,
                     "field": E.AssetFieldTypeEnum.AssetFieldType.Name(r.campaign_asset.field_type),
                     "status": E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status),
                     "asset_id": r.asset.id, "link": r.campaign_asset.resource_name,
                     "text": r.asset.sitelink_asset.link_text or r.asset.callout_asset.callout_text})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    ap.add_argument("--only-campaign-id", type=int, help="привести к стандарту только эту кампанию (Search)")
    ap.add_argument("--price-asset-id", type=int, help="использовать готовый ценовой ассет вместо создания нового")
    ap.add_argument("--price-only", action="store_true", help="заменить только ценовой ассет во всех целевых кампаниях и в эталонной")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    std = {}
    for r in read_links(client, ga, cid, SOURCE_CAMPAIGN, [f for f in FIELDS["SEARCH"] if f != "PRICE"]):
        if r["status"] == "ENABLED":
            std.setdefault(r["field"], set()).add(r["asset_id"])
    print("Эталон (кампания", SOURCE_CAMPAIGN, "):", {k: len(v) for k, v in std.items()})
    assert std.get("SITELINK") and std.get("CALLOUT") and std.get("STRUCTURED_SNIPPET") and std.get("AD_IMAGE"), "эталон неполный"

    targets = dict(TARGETS)
    if args.price_only:
        targets[SOURCE_CAMPAIGN] = ("search / szklarnia generic", "SEARCH")
        targets[23439487425] = ("search / szklarnia/tunel (excl. poliweglan)", "SEARCH")  # на паузе, но актуальная (решение 2026-10-09)
    if args.only_campaign_id:
        nm = next(iter(ga.search(customer_id=cid, query=f"SELECT campaign.name FROM campaign WHERE campaign.id = {args.only_campaign_id}"))).campaign.name
        targets = {args.only_campaign_id: (nm, "SEARCH")}
    ops = []
    price_rn = f"customers/{cid}/assets/-900"
    if args.price_asset_id:
        price_rn = f"customers/{cid}/assets/{args.price_asset_id}"
    op = client.get_type("MutateOperation")
    a = op.asset_operation.create
    a.resource_name = price_rn
    a.price_asset.type_ = E.PriceExtensionTypeEnum.PRODUCT_TIERS
    a.price_asset.price_qualifier = E.PriceExtensionPriceQualifierEnum.FROM
    a.price_asset.language_code = "pl"
    for header, desc, price, anchor in PRICE_OFFERINGS:
        assert len(header) <= 25 and len(desc) <= 25, (header, len(header), desc, len(desc))
        o = a.price_asset.price_offerings.add()
        o.header = header
        o.description = desc
        o.price.amount_micros = price * 1_000_000
        o.price.currency_code = "PLN"
        o.unit = E.PriceExtensionPriceUnitEnum.UNSPECIFIED
        o.final_url = BASE + anchor
    if not args.price_asset_id:
        ops.append(op)

    snapshot = []
    summary = []
    for camp_id, (name, channel) in targets.items():
        fields = ["PRICE"] if args.price_only else FIELDS[channel]
        current = read_links(client, ga, cid, camp_id, fields)
        remove, add = [], []
        for field in fields:
            if field == "PRICE":
                remove += [r for r in current if r["field"] == "PRICE"]
                add.append(("PRICE", price_rn))
                continue
            have = {r["asset_id"] for r in current if r["field"] == field}
            remove += [r for r in current if r["field"] == field and r["asset_id"] not in std[field]]
            for aid in sorted(std[field] - have):
                add.append((field, f"customers/{cid}/assets/{aid}"))
        for r in remove:
            op = client.get_type("MutateOperation")
            op.campaign_asset_operation.remove = r["link"]
            ops.append(op)
            snapshot.append({**r, "campaign": name})
        for field, rn in add:
            op = client.get_type("MutateOperation")
            ca = op.campaign_asset_operation.create
            ca.campaign = f"customers/{cid}/campaigns/{camp_id}"
            ca.asset = rn
            ca.field_type = getattr(E.AssetFieldTypeEnum, field)
            ops.append(op)
        summary.append((name, len(remove), len(add)))

    print("\nПлан (снять привязок / подключить):")
    for name, rm, ad in summary:
        print(f"  {name}: снять {rm}, подключить {ad}")
    if snapshot:
        snap = client_stats_dir(args.client_folder) / f"snapshot_before_standardize_assets_{datetime.now():%Y%m%d_%H%M}.csv"
        with open(snap, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(snapshot[0].keys()))
            w.writeheader()
            w.writerows(snapshot)
        print("Снимок «до»:", snap)

    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not args.execute
    try:
        client.get_service("GoogleAdsService").mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:8]:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)
    if not args.execute:
        print(f"\nПроверка пройдена ({len(ops)} операций). НИЧЕГО не изменено (validate_only).")
        return
    print(f"\nЗаписано ({len(ops)} операций). Чтение обратно:")
    for camp_id, (name, channel) in targets.items():
        counts = {}
        for r in read_links(client, ga, cid, camp_id, ["PRICE"] if args.price_only else FIELDS[channel]):
            counts[(r["field"], r["status"])] = counts.get((r["field"], r["status"]), 0) + 1
        print(" ", name, dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
