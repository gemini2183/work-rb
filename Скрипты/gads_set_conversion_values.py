#!/usr/bin/env python
# coding: utf-8
"""Убирает «ценность» у лид-конверсий Google Ads: значение 0 и «всегда использовать значение по умолчанию».

Зачем (ProfiMet, решение пользователя 2026-10-09): оценка идёт по заявкам и цене заявки, а не по прибыли; у звонков стояла
заглушка 1 за конверсию, у формы 0 — из-за этого Google предлагал Target ROAS (ROAS 2.2% из заглушек). Конверсии «Отгружено»
(офлайн, реальная сумма продаж) не трогаем. На число и учёт конверсий не влияет (меняется только ценность).

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись только с --execute. Снимок «до» (id, имя, значение, режим) — CSV в Статистика/ клиента;
после записи читает значения обратно.

Использование:
    python gads_set_conversion_values.py --customer-id 7552781705 --client-folder ProfiMet
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

KEEP_NAME_PARTS = ("Отгружено",)  # реальная ценность продаж


def read_actions(ga):
    q = ("SELECT conversion_action.resource_name, conversion_action.id, conversion_action.name, conversion_action.primary_for_goal, "
         "conversion_action.value_settings.default_value, conversion_action.value_settings.always_use_default_value "
         "FROM conversion_action WHERE conversion_action.status = 'ENABLED'")
    return [(r.conversion_action.resource_name, r.conversion_action.id, r.conversion_action.name,
             r.conversion_action.primary_for_goal, r.conversion_action.value_settings.default_value,
             r.conversion_action.value_settings.always_use_default_value) for r in ga.search(customer_id=CID, query=q)]


def main():
    global CID
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()
    CID = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    rows = read_actions(ga)
    todo = [r for r in rows if not any(k in r[2] for k in KEEP_NAME_PARTS) and (r[4] != 0 or not r[5])]
    print("Включённые конверсионные действия: всего", len(rows), "| к изменению:", len(todo))
    print(f"{'действие':58} {'осн':5} {'было':>10} → стало")
    for _, _, name, prim, dv, always in todo:
        print(f"{name[:58]:58} {prim!s:5} {dv:>5} {'всегда' if always else 'из события'} → 0 всегда")
    print("Не меняем:", [r[2] for r in rows if r not in todo])
    if not todo:
        return
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_conversion_values_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["resource_name", "id", "name", "primary", "default_value", "always_use_default_value"])
        for r in todo:
            w.writerow(r)
    print("Снимок «до»:", snap)

    failed = []
    for rn, _id, name, *_ in todo:
        op = client.get_type("ConversionActionOperation")
        op.update.resource_name = rn
        op.update.value_settings.default_value = 0.0
        op.update.value_settings.always_use_default_value = True
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["value_settings.default_value", "value_settings.always_use_default_value"]))
        req = client.get_type("MutateConversionActionsRequest")
        req.customer_id = CID
        req.operations.append(op)
        req.validate_only = not args.execute
        try:
            client.get_service("ConversionActionService").mutate_conversion_actions(request=req)
        except GoogleAdsException as ex:
            failed.append((name, ex.failure.errors[0].message[:120]))
    print(f"{'записано' if args.execute else 'проверка пройдена'}: {len(todo) - len(failed)} из {len(todo)}")
    for name, msg in failed:
        print("  не удалось:", name, "→", msg)
    if args.execute:
        after = {r[0]: r for r in read_actions(ga)}
        print("Прочитано обратно:")
        for rn, _id, name, *_ in todo:
            a = after.get(rn)
            print(f"  {name[:58]:58} значение {a[4]} всегда {a[5]}")
    else:
        print("НИЧЕГО не изменено (validate_only).")


CID = None

if __name__ == "__main__":
    main()
