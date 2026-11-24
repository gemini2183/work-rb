#!/usr/bin/env python
# coding: utf-8
"""Отвязать / привязать СУЩЕСТВУЮЩИЙ ассет к кампании Google Ads (любой тип AssetFieldType). ЗАПИСЬ только с --execute.

Зачем (EkspertAgro 2026-11-23): снять с кампании промо-ассет (PROMOTION) без удаления самого ассета и вернуть обратно
(откат). Тот же скрипт для SITELINK, CALLOUT, STRUCTURED_SNIPPET, CALL, PRICE и других значений AssetFieldType.
`gads_campaign_assets_swap.py` умеет только создавать НОВЫЕ ссылки/callout; этот скрипт работает с уже существующими id.

Что делает:
  - находит кампанию (--campaign "имя" или --campaign-id);
  - читает campaign_asset кампании по типу (кроме REMOVED) и печатает «было»;
  - --unlink-assets: стоп, если asset_id не привязан к кампании с этим типом; удаляет ТОЛЬКО привязку (campaign_asset), ассет остаётся;
  - --link-assets: стоп, если уже привязан или ассета нет / тип ассета не подходит; создаёт привязку campaign_asset;
  - предупреждает, если ассет привязан ещё к другим кампаниям, группам или аккаунту (customer_asset);
  - снимок «до» (CSV) в Клиенты/<Имя>/Статистика/snapshot_before_campaign_asset_link_<кампания>_<время>.csv;
  - привязки других типов не трогает; ассеты не создаёт и не удаляет.
Режимы: по умолчанию validate_only (печатает «было -> станет», проверка Google, ничего не меняется);
с --execute пишет и читает обратно («стало»). Одна транзакция.

Примеры (из Скрипты/, PYTHONUTF8=1):
    python gads_campaign_asset_link.py --customer-id 8826134558 --client-folder EkspertAgro --campaign-id 24479597485 \\
        --field-type PROMOTION --unlink-assets 315547243524
    python gads_campaign_asset_link.py ... --field-type PROMOTION --link-assets 315547243524 --execute   # откат

Дата: 2026-11-23.
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_quota_ledger import record_mutate
from gads_stats import GOOGLE_ADS_YAML

SCRIPT = "gads_campaign_asset_link"

# Поля, по которым печатаем описание ассета (общие для всех типов; лишние пустые)
ASSET_SELECT = (
    "asset.id, asset.type, asset.name, asset.final_urls, "
    "asset.sitelink_asset.link_text, asset.sitelink_asset.description1, asset.sitelink_asset.description2, "
    "asset.callout_asset.callout_text, "
    "asset.promotion_asset.promotion_target, asset.promotion_asset.percent_off, asset.promotion_asset.occasion, "
    "asset.structured_snippet_asset.header, asset.structured_snippet_asset.values, "
    "asset.call_asset.phone_number, asset.price_asset.type"
)
CSV_FIELDS = ["rn", "campaign_id", "field_type", "status", "asset_id", "asset_type", "desc", "url"]


def describe(a):
    """Короткое описание ассета любого типа."""
    parts = []
    if a.sitelink_asset.link_text:
        parts += [a.sitelink_asset.link_text, a.sitelink_asset.description1, a.sitelink_asset.description2]
    if a.callout_asset.callout_text:
        parts.append(a.callout_asset.callout_text)
    if a.promotion_asset.promotion_target:
        parts.append(f"{a.promotion_asset.promotion_target} | {a.promotion_asset.percent_off / 10000:g}%"
                     if a.promotion_asset.percent_off else a.promotion_asset.promotion_target)
    if a.structured_snippet_asset.header:
        parts.append(f"{a.structured_snippet_asset.header}: {', '.join(a.structured_snippet_asset.values)}")
    if a.call_asset.phone_number:
        parts.append(a.call_asset.phone_number)
    if not parts and a.name:
        parts.append(a.name)
    return " | ".join(p for p in parts if p)


def read_links(ga, cid, camp_id, field_type, E):
    """campaign_asset кампании по типу, кроме REMOVED."""
    rows = []
    for r in ga.search(customer_id=cid, query=(
            f"SELECT campaign.id, campaign_asset.resource_name, campaign_asset.field_type, campaign_asset.status, {ASSET_SELECT} "
            f"FROM campaign_asset WHERE campaign.id = {camp_id} AND campaign_asset.field_type = {field_type} "
            "AND campaign_asset.status != 'REMOVED'")):
        rows.append({"rn": r.campaign_asset.resource_name, "campaign_id": camp_id, "field_type": field_type,
                     "status": E.AssetLinkStatusEnum.AssetLinkStatus.Name(r.campaign_asset.status),
                     "asset_id": r.asset.id, "asset_type": E.AssetTypeEnum.AssetType.Name(r.asset.type_),
                     "desc": describe(r.asset), "url": ";".join(r.asset.final_urls)})
    return rows


def other_links(ga, cid, camp_id, ids):
    """Где ещё привязаны ассеты: другие кампании, группы объявлений, аккаунт."""
    out = []
    idl = ", ".join(str(i) for i in ids)
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, asset.id, campaign_asset.field_type FROM campaign_asset "
            f"WHERE asset.id IN ({idl}) AND campaign_asset.status != 'REMOVED' AND campaign.id != {camp_id}")):
        out.append((r.asset.id, f"кампания {r.campaign.id} «{r.campaign.name}»"))
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, ad_group.id, ad_group.name, asset.id FROM ad_group_asset "
            f"WHERE asset.id IN ({idl}) AND ad_group_asset.status != 'REMOVED'")):
        out.append((r.asset.id, f"группа {r.ad_group.id} «{r.ad_group.name}» (кампания {r.campaign.id})"))
    for r in ga.search(customer_id=cid, query=(
            f"SELECT asset.id FROM customer_asset WHERE asset.id IN ({idl}) AND customer_asset.status != 'REMOVED'")):
        out.append((r.asset.id, "уровень аккаунта (customer_asset)"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True, help="папка клиента для снимка «до» (Клиенты/<Имя>/Статистика)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--campaign", help="точное имя кампании")
    g.add_argument("--campaign-id", type=int)
    ap.add_argument("--field-type", required=True, help="AssetFieldType: PROMOTION, SITELINK, CALLOUT, STRUCTURED_SNIPPET, CALL, PRICE, ...")
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--unlink-assets", nargs="+", type=int, metavar="ID", help="снять привязку (ассет остаётся)")
    m.add_argument("--link-assets", nargs="+", type=int, metavar="ID", help="привязать существующие ассеты")
    ap.add_argument("--execute", action="store_true", help="записать (по умолчанию validate_only)")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    E = client.enums
    ft = args.field_type.upper()
    try:
        ft_val = E.AssetFieldTypeEnum.AssetFieldType.Value(ft)
    except Exception:
        raise SystemExit(f"Неизвестный --field-type {ft}. Допустимо значение AssetFieldType (PROMOTION, SITELINK, CALLOUT, ...).")
    ga = client.get_service("GoogleAdsService")

    if args.campaign_id:
        q = f"SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.id = {args.campaign_id}"
    else:
        name = args.campaign.replace("\\", "\\\\").replace("'", "\\'")
        q = ("SELECT campaign.id, campaign.name, campaign.status FROM campaign "
             f"WHERE campaign.name = '{name}' AND campaign.status != 'REMOVED'")
    camp = list(ga.search(customer_id=cid, query=q))
    if len(camp) != 1:
        raise SystemExit(f"СТОП: кампаний найдено {len(camp)} (нужна ровно одна).")
    camp_id = camp[0].campaign.id
    camp_rn = f"customers/{cid}/campaigns/{camp_id}"
    print(f"Кампания: {camp_id} «{camp[0].campaign.name}» ({E.CampaignStatusEnum.CampaignStatus.Name(camp[0].campaign.status)}); тип {ft}")

    before = read_links(ga, cid, camp_id, ft, E)
    by_asset = {r["asset_id"]: r for r in before}
    unlink = bool(args.unlink_assets)
    ids = args.unlink_assets or args.link_assets
    if len(set(ids)) != len(ids):
        raise SystemExit("СТОП: повторяющиеся id в списке.")

    print(f"\nБЫЛО: привязок {ft} у кампании: {len(before)}")
    for r in before:
        mark = "  <-- в плане" if r["asset_id"] in ids else ""
        print(f"  {r['asset_id']} [{r['status']}] {r['desc']} {r['url']}{mark}")

    # снимок «до» всегда пишем (в том числе в validate_only: это чтение состояния)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_campaign_asset_link_{camp_id}_{ft}_{ts}.csv"
    with open(snap, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(before)
    print(f"Снимок «до»: {snap}")

    ops = []
    if unlink:
        missing = [a for a in ids if a not in by_asset]
        if missing:
            raise SystemExit(f"СТОП: не привязаны к кампании {camp_id} с типом {ft}: {missing}")
        print(f"\nПЛАН: отвязать {len(ids)} (сам ассет не удаляется):")
        for a in ids:
            r = by_asset[a]
            print(f"  {a} {r['desc']}: привязан -> НЕ привязан")
            op = client.get_type("MutateOperation")
            op.campaign_asset_operation.remove = r["rn"]
            ops.append(op)
        infos = other_links(ga, cid, camp_id, ids)
    else:
        already = [a for a in ids if a in by_asset]
        if already:
            raise SystemExit(f"СТОП: уже привязаны к кампании {camp_id} с типом {ft}: {already}")
        idl = ", ".join(str(i) for i in ids)
        found = {r.asset.id: r for r in ga.search(customer_id=cid, query=(
            f"SELECT {ASSET_SELECT} FROM asset WHERE asset.id IN ({idl})"))}
        absent = [a for a in ids if a not in found]
        if absent:
            raise SystemExit(f"СТОП: ассетов нет в аккаунте {cid}: {absent}")
        print(f"\nПЛАН: привязать {len(ids)} (ассеты существуют, не создаются):")
        for a in ids:
            at = E.AssetTypeEnum.AssetType.Name(found[a].asset.type_)
            if at != ft:
                print(f"  ПРЕДУПРЕЖДЕНИЕ: ассет {a} имеет тип {at}, а привязка {ft}; Google может отклонить")
            print(f"  {a} [{at}] {describe(found[a].asset)}: НЕ привязан -> привязан")
            op = client.get_type("MutateOperation")
            ca = op.campaign_asset_operation.create
            ca.campaign = camp_rn
            ca.asset = f"customers/{cid}/assets/{a}"
            ca.field_type = ft_val
            ops.append(op)
        infos = other_links(ga, cid, camp_id, ids)

    if infos:
        print("\nПРЕДУПРЕЖДЕНИЕ: эти ассеты привязаны ещё и в других местах (их привязки скрипт не трогает):")
        for a, where in infos:
            print(f"  ассет {a}: {where}")
    else:
        print("\nДругих привязок этих ассетов (кампании, группы, аккаунт) не найдено.")

    print(f"\nОпераций: {len(ops)}")
    try:
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = cid
        req.mutate_operations.extend(ops)
        req.validate_only = not args.execute
        record_mutate(SCRIPT, len(ops), validate_only=not args.execute)
        ga.mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)

    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не изменено (validate_only). Запись — с --execute.")
        return
    after = read_links(ga, cid, camp_id, ft, E)
    print(f"\nСТАЛО (чтение обратно): привязок {ft}: {len(after)}")
    for r in after:
        print(f"  {r['asset_id']} [{r['status']}] {r['desc']} {r['url']}")
    got = {r["asset_id"] for r in after}
    ok = all((a not in got) if unlink else (a in got) for a in ids)
    print("Результат совпадает с планом." if ok else "ВНИМАНИЕ: результат НЕ совпал с планом, проверить вручную.")


if __name__ == "__main__":
    main()
