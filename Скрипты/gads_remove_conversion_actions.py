#!/usr/bin/env python
# coding: utf-8
"""Удаляет (статус REMOVED) конверсионные действия Google Ads по id. По умолчанию validate_only; запись только с --execute.

Зачем (LuxeBrokers, 2026-11-04): мёртвые импорты GA4 (`form_submit`, `click_phone_num`) — события в GA4 не приходят, конверсий
ноль, статус «Misconfigured». Скрипт сначала показывает, что именно удаляет, и ОСТАНАВЛИВАЕТСЯ, если у действия есть конверсии
за период проверки (--check-from), — удалённое действие не вернуть, только создать заново.

Что печатает: имя, тип, основное ли, событие GA4, конверсии за период. Снимок «до» — CSV в Статистика/ клиента. После записи
читает статус обратно.

    python gads_remove_conversion_actions.py --customer-id 953-486-5605 --client-folder LuxeBrokers --ids 6854417675 6854648769
    ... --execute
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--ids", nargs="+", required=True, help="id конверсионных действий")
    ap.add_argument("--check-from", default="2026-01-01", help="с какой даты искать конверсии у действия (по умолчанию 2026-01-01)")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    today = datetime.now().strftime("%Y-%m-%d")

    ids = ", ".join(a.ids)
    rows = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT conversion_action.id, conversion_action.resource_name, conversion_action.name, conversion_action.type, "
            "conversion_action.status, conversion_action.primary_for_goal, conversion_action.google_analytics_4_settings.event_name "
            f"FROM conversion_action WHERE conversion_action.id IN ({ids})")):
        x = r.conversion_action
        rows[str(x.id)] = {"id": str(x.id), "resource": x.resource_name, "name": x.name,
                           "type": E.ConversionActionTypeEnum.ConversionActionType.Name(x.type_),
                           "status": E.ConversionActionStatusEnum.ConversionActionStatus.Name(x.status),
                           "primary": x.primary_for_goal, "ga4_event": x.google_analytics_4_settings.event_name, "conv": 0.0}
    missing = [i for i in a.ids if i not in rows]
    if missing:
        raise SystemExit(f"ОСТАНОВКА: не найдены id {missing}")
    names = {r["name"]: r["id"] for r in rows.values()}
    for r in ga.search(customer_id=cid, query=(
            "SELECT segments.conversion_action_name, metrics.all_conversions FROM customer "
            f"WHERE segments.date BETWEEN '{a.check_from}' AND '{today}'")):
        i = names.get(r.segments.conversion_action_name)
        if i:
            rows[i]["conv"] += r.metrics.all_conversions

    print(f"Проверка конверсий с {a.check_from} по {today}:")
    blocked = False
    for r in rows.values():
        print(f"  {r['id']} {r['name']} | {r['type']} | {r['status']} | {'основное' if r['primary'] else 'второстепенное'} | "
              f"событие GA4 «{r['ga4_event']}» | конверсий: {r['conv']:.1f}")
        if r["conv"] > 0:
            blocked = True
        if r["status"] != "ENABLED":
            print("     (уже не включено)")
    if blocked:
        raise SystemExit("ОСТАНОВКА: у действия есть конверсии за период — удалять нельзя без отдельного решения")

    snap = client_stats_dir(a.client_folder) / f"snapshot_before_remove_conversions_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(next(iter(rows.values())).keys()))
        w.writeheader()
        w.writerows(rows.values())
    print("Снимок «до»:", snap)

    ops = []
    for r in rows.values():
        op = client.get_type("ConversionActionOperation")
        op.remove = r["resource"]
        ops.append(op)
    req = client.get_type("MutateConversionActionsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not a.execute
    try:
        client.get_service("ConversionActionService").mutate_conversion_actions(request=req)
    except GoogleAdsException as e:
        raise SystemExit("Ошибка API: " + "; ".join(er.message for er in e.failure.errors))
    if not a.execute:
        print("validate_only: Google принял план, ничего не удалено (нужен --execute).")
        return
    print("Удалено. Читаю обратно:")
    for r in ga.search(customer_id=cid, query=(
            "SELECT conversion_action.id, conversion_action.name, conversion_action.status FROM conversion_action "
            f"WHERE conversion_action.id IN ({ids})")):
        x = r.conversion_action
        print(f"  {x.id} {x.name}: {E.ConversionActionStatusEnum.ConversionActionStatus.Name(x.status)}")


if __name__ == "__main__":
    main()
