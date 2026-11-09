#!/usr/bin/env python
# coding: utf-8
"""PMax с фидом: фильтр товаров группы ассетов — «все товары, КРОМЕ списка item_id». ЗАПИСЬ (по умолчанию validate_only).

Читает текущие узлы фильтра группы ассетов, сохраняет снимок «до» в Статистика/ клиента и заменяет дерево на:
    корень (SUBDIVISION по product_item_id)
      ├─ UNIT_EXCLUDED  item_id = <каждый из CSV>
      └─ UNIT_INCLUDED  «все остальные товары»
Работает только если сейчас в группе ровно один узел — корневой UNIT_INCLUDED («все товары»): иначе остановка (дерево с отбором
не перезаписываем вслепую). Всё в одном запросе: удаление старого корня + создание нового дерева на временных id.
Откат: снимок «до» хранит узлы; вернуть «все товары» — запустить с `--restore-all` (удалит дерево и создаст один узел UNIT_INCLUDED).

Использование (из папки Скрипты, PYTHONUTF8=1):
    python gads_pmax_listing_filter.py --customer-id 8826134558 --client-folder EkspertAgro --asset-group-id 6753252828 \
        --exclude-csv "<CSV с колонкой item_id>" [--execute]
    python gads_pmax_listing_filter.py ... --restore-all [--execute]
"""
import argparse
import csv
import json
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

TYPES = {2: "SUBDIVISION", 3: "UNIT_INCLUDED", 4: "UNIT_EXCLUDED"}


def read_nodes(ga, cid, ag):
    q = ("SELECT asset_group_listing_group_filter.resource_name, asset_group_listing_group_filter.id, "
         "asset_group_listing_group_filter.type, asset_group_listing_group_filter.parent_listing_group_filter, "
         "asset_group_listing_group_filter.case_value.product_item_id.value "
         f"FROM asset_group_listing_group_filter WHERE asset_group.id = {ag}")
    out = []
    for r in ga.search(customer_id=cid, query=q):
        f = r.asset_group_listing_group_filter
        out.append({"resource": f.resource_name, "id": f.id, "type": int(f.type_), "parent": f.parent_listing_group_filter,
                    "item": f.case_value.product_item_id.value})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--asset-group-id", required=True)
    ap.add_argument("--exclude-csv")
    ap.add_argument("--restore-all", action="store_true")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    a = ap.parse_args()
    if not a.restore_all and not a.exclude_csv:
        ap.error("нужен --exclude-csv или --restore-all")

    cid, ag = a.customer_id.replace("-", ""), str(a.asset_group_id)
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    svc = client.get_service("AssetGroupListingGroupFilterService")
    nodes = read_nodes(ga, cid, ag)
    print(f"узлов в фильтре группы {ag}: {len(nodes)}; по типам: " + str({TYPES.get(t, t): sum(1 for n in nodes if n['type'] == t) for t in {n['type'] for n in nodes}}))

    snap = client_stats_dir(a.client_folder) / f"snapshot_before_listing_filter_{ag}_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps(nodes, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Снимок «до»:", snap)

    def rn(i):
        return f"customers/{cid}/assetGroupListingGroupFilters/{ag}~{i}"

    def node(op_create, tmp_id, typ, parent=None, item=None, catch_all=False):
        n = op_create
        n.asset_group = f"customers/{cid}/assetGroups/{ag}"
        n.resource_name = rn(tmp_id)
        n.id = tmp_id
        n.type_ = typ
        n.listing_source = client.enums.ListingGroupFilterListingSourceEnum.SHOPPING
        if parent is not None:
            n.parent_listing_group_filter = rn(parent)
            if item:
                n.case_value.product_item_id.value = item
            elif catch_all:
                n.case_value.product_item_id.SetInParent()

    T = client.enums.ListingGroupFilterTypeEnum
    ops = []
    if a.restore_all:
        for n in nodes:
            if not n["parent"]:
                op = client.get_type("AssetGroupListingGroupFilterOperation"); op.remove = n["resource"]; ops.append(op)
        op = client.get_type("AssetGroupListingGroupFilterOperation")
        node(op.create, -1, T.UNIT_INCLUDED)
        ops.append(op)
        label = "вернуть «все товары»"
    else:
        if len(nodes) != 1 or nodes[0]["type"] != 3 or nodes[0]["parent"]:
            print("СТОП: в группе не один корневой узел «все товары» — дерево с отбором не перезаписываю. Нужен ручной разбор.")
            raise SystemExit(2)
        ids = [r["item_id"].strip() for r in csv.DictReader(open(a.exclude_csv, encoding="utf-8-sig")) if (r.get("item_id") or "").strip()]
        ids = list(dict.fromkeys(ids))
        op = client.get_type("AssetGroupListingGroupFilterOperation"); op.remove = nodes[0]["resource"]; ops.append(op)
        op = client.get_type("AssetGroupListingGroupFilterOperation"); node(op.create, -1, T.SUBDIVISION); ops.append(op)
        for k, item in enumerate(ids, start=2):
            op = client.get_type("AssetGroupListingGroupFilterOperation"); node(op.create, -k, T.UNIT_EXCLUDED, parent=-1, item=item); ops.append(op)
        op = client.get_type("AssetGroupListingGroupFilterOperation"); node(op.create, -(len(ids) + 2), T.UNIT_INCLUDED, parent=-1, catch_all=True); ops.append(op)
        label = f"все товары, кроме {len(ids)} из списка"
    print("План:", label, f"({len(ops)} операций)")

    req = client.get_type("MutateAssetGroupListingGroupFiltersRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not a.execute
    try:
        svc.mutate_asset_group_listing_group_filters(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:6]:
            print("  -", err.message)
        raise SystemExit(1)

    if not a.execute:
        print("Проверка пройдена. НИЧЕГО не изменено (validate_only).")
        return
    after = read_nodes(ga, cid, ag)
    ex_ = [n for n in after if n["type"] == 4]
    print(f"Прочитано обратно: узлов {len(after)}; по типам: " + str({TYPES.get(t, t): sum(1 for n in after if n['type'] == t) for t in {n['type'] for n in after}})
          + f"; исключённых товаров {len(ex_)}")


if __name__ == "__main__":
    main()
