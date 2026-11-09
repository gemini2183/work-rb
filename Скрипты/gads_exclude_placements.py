#!/usr/bin/env python
# coding: utf-8
"""Добавляет ВЕБ-САЙТЫ в исключения площадок на уровне АККАУНТА Google Ads (действуют на все кампании, включая Performance Max).

Источник списка — CSV с колонкой domain (например `apexnews.com`) и необязательной name/reason. БЕЗОПАСНОСТЬ: по умолчанию
validate_only (Google проверяет, ничего не создаёт). Запись — только с --execute. Перед записью читает уже существующие исключения
аккаунта (placement) и пропускает дубли, сохраняет снимок «до» в Статистика/ клиента, после записи читает исключения обратно.
Аналог `gads_exclude_youtube_channels.py` (там YouTube-каналы).

Использование (из папки Скрипты, PYTHONUTF8=1):
    python gads_exclude_placements.py --customer-id 8826134558 --client-folder EkspertAgro --csv "<путь к CSV>"
    ... --execute
Откат: удалить критерии в интерфейсе (Инструменты → Общая библиотека → Исключённые площадки на уровне аккаунта) или через
customer_negative_criterion REMOVE по ресурсу из снимка «до» (в снимке — список доменов, которые уже были).
"""
import argparse
import csv
import json
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

BATCH = 100


def existing_placements(ga, cid):
    q = ("SELECT customer_negative_criterion.placement.url FROM customer_negative_criterion "
         "WHERE customer_negative_criterion.type = 'PLACEMENT'")
    return {r.customer_negative_criterion.placement.url.lower() for r in ga.search(customer_id=cid, query=q)}


def total_negatives(ga, cid):
    return sum(1 for _ in ga.search(customer_id=cid, query="SELECT customer_negative_criterion.id FROM customer_negative_criterion"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--csv", required=True, help="CSV с колонкой domain")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    svc = client.get_service("CustomerNegativeCriterionService")

    rows = [r for r in csv.DictReader(open(args.csv, encoding="utf-8-sig")) if (r.get("domain") or "").strip()]
    exist = existing_placements(ga, cid)
    before_total = total_negatives(ga, cid)
    todo = [r for r in rows if r["domain"].strip().lower() not in exist]
    print(f"в файле сайтов: {len(rows)}, уже в исключениях аккаунта: {len(rows) - len(todo)}, к добавлению: {len(todo)}; "
          f"всего исключений в аккаунте до: {before_total}")

    snap = client_stats_dir(args.client_folder) / f"snapshot_before_placement_exclusions_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps({"existing_placements": sorted(exist), "total_negatives_before": before_total}, ensure_ascii=False), encoding="utf-8")
    print("Снимок «до»:", snap)

    added = 0
    try:
        for i in range(0, len(todo), BATCH):
            ops = []
            for r in todo[i:i + BATCH]:
                op = client.get_type("CustomerNegativeCriterionOperation")
                op.create.placement.url = r["domain"].strip().lower()
                ops.append(op)
            req = client.get_type("MutateCustomerNegativeCriteriaRequest")
            req.customer_id = cid
            req.operations.extend(ops)
            req.validate_only = not args.execute
            req.partial_failure = True
            resp = svc.mutate_customer_negative_criteria(request=req)
            fails = 0
            if resp.partial_failure_error and resp.partial_failure_error.message:
                fails = len(resp.partial_failure_error.details) or 1
                print("  частичные ошибки в пачке:", resp.partial_failure_error.message[:300])
            added += len(ops) - fails
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:5]:
            print("  -", err.message)
        raise SystemExit(1)

    if not args.execute:
        print(f"Проверка пройдена. НИЧЕГО не изменено (validate_only). Было бы добавлено ~{added} сайтов.")
        return
    after_total = total_negatives(ga, cid)
    after = existing_placements(ga, cid)
    missing = [r["domain"] for r in rows if r["domain"].strip().lower() not in after]
    print(f"Прочитано обратно: исключений в аккаунте {before_total} -> {after_total}; сайтов в исключениях: {len(after)}; "
          f"из списка не найдено в аккаунте: {len(missing)} {missing}")


if __name__ == "__main__":
    main()
