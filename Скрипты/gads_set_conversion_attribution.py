#!/usr/bin/env python
# coding: utf-8
"""Переводит модель атрибуции конверсионных действий Google Ads на «последний клик» (GOOGLE_ADS_LAST_CLICK).

Зачем (ProfiMet, решение пользователя 2026-10-09): оценка идёт по целым заявкам и сверяется с Ringostat; дробные конверсии
(«управляемая данными» атрибуция) не нужны; объёмы малые (около 130 конверсий в месяц на аккаунт). На число заявок не влияет,
меняется только, какой кампании записана заслуга (по данным 09.10 сдвиг ≈1 конверсии в месяц).

Меняются только включённые действия, у которых модель отлична от последнего клика и которые Google позволяет менять. Действия,
импортированные из GA4, управляются настройками GA4 (в Ads модель UNKNOWN) — пропускаются, их список печатается.

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись только с --execute. Снимок «до» — CSV в Статистика/ клиента; после записи читает обратно.

Использование:
    python gads_set_conversion_attribution.py --customer-id 7552781705 --client-folder ProfiMet
    ... --execute
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def read(client, ga, cid):
    E = client.enums
    q = ("SELECT conversion_action.resource_name, conversion_action.name, conversion_action.type, "
         "conversion_action.attribution_model_settings.attribution_model FROM conversion_action WHERE conversion_action.status = 'ENABLED'")
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        a = r.conversion_action
        rows.append({"resource": a.resource_name, "name": a.name,
                     "type": E.ConversionActionTypeEnum.ConversionActionType.Name(a.type_),
                     "model": E.AttributionModelEnum.AttributionModel.Name(a.attribution_model_settings.attribution_model)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    rows = read(client, ga, cid)
    target = "GOOGLE_ADS_LAST_CLICK"
    skip_ga4 = [r for r in rows if r["model"] == "UNKNOWN"]
    todo = [r for r in rows if r["model"] not in (target, "UNKNOWN")]
    print("Включённых действий:", len(rows), "| к смене на последний клик:", len(todo), "| GA4 (управляет GA4), пропущено:", len(skip_ga4))
    for r in todo:
        print(f"  {r['name'][:56]:56} {r['type'][:22]:22} {r['model']} → {target}")
    if not todo:
        return
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_attribution_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(todo[0].keys()))
        w.writeheader()
        w.writerows(todo)
    print("Снимок «до»:", snap)

    failed = []
    for r in todo:
        op = client.get_type("ConversionActionOperation")
        op.update.resource_name = r["resource"]
        op.update.attribution_model_settings.attribution_model = getattr(E.AttributionModelEnum, target)
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["attribution_model_settings.attribution_model"]))
        req = client.get_type("MutateConversionActionsRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not args.execute
        try:
            client.get_service("ConversionActionService").mutate_conversion_actions(request=req)
        except GoogleAdsException as ex:
            failed.append((r["name"], ex.failure.errors[0].message[:120]))
    print(f"{'записано' if args.execute else 'проверка пройдена'}: {len(todo) - len(failed)} из {len(todo)}")
    for name, msg in failed:
        print("  не удалось:", name, "→", msg)
    if args.execute:
        after = {r["resource"]: r for r in read(client, ga, cid)}
        print("Прочитано обратно:")
        for r in todo:
            print(f"  {r['name'][:56]:56} {after[r['resource']]['model']}")
    else:
        print("НИЧЕГО не изменено (validate_only).")


if __name__ == "__main__":
    main()
