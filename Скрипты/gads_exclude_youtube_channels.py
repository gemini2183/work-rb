#!/usr/bin/env python
# coding: utf-8
"""Добавляет YouTube-каналы в исключения площадок на уровне АККАУНТА Google Ads (действуют на все кампании,
включая Performance Max, Demand Gen и Display).

Источник списка — CSV с колонкой channel_id (UC...) и name. БЕЗОПАСНОСТЬ: по умолчанию validate_only (Google
проверяет, ничего не создаёт). Запись — только с --execute. Перед записью читает уже существующие исключения
аккаунта и пропускает дубли; сохраняет снимок «до» в Статистика/ клиента; после записи читает число исключений обратно.

Использование:
    python gads_exclude_youtube_channels.py --customer-id 7552781705 --client-folder ProfiMet \
        --csv "D:\\GitHub\\work-rb\\Клиенты\\ProfiMet\\Исключения_площадок\\youtube_детские_каналы_2026-10-08.csv"
    ... --execute
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


def existing_channels(ga, cid, client):
    q = ("SELECT customer_negative_criterion.type, customer_negative_criterion.youtube_channel.channel_id "
         "FROM customer_negative_criterion WHERE customer_negative_criterion.type = 'YOUTUBE_CHANNEL'")
    out = set()
    for r in ga.search(customer_id=cid, query=q):
        out.add(r.customer_negative_criterion.youtube_channel.channel_id)
    return out


def total_negatives(ga, cid):
    n = 0
    for _ in ga.search(customer_id=cid, query="SELECT customer_negative_criterion.id FROM customer_negative_criterion"):
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--csv", required=True, help="CSV с колонками channel_id, name")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    svc = client.get_service("CustomerNegativeCriterionService")

    rows = [r for r in csv.DictReader(open(args.csv, encoding="utf-8-sig")) if r.get("channel_id", "").startswith("UC")]
    exist = existing_channels(ga, cid, client)
    before_total = total_negatives(ga, cid)
    todo = [r for r in rows if r["channel_id"] not in exist]
    print(f"в файле каналов: {len(rows)}, уже в исключениях аккаунта: {len(rows) - len(todo)}, к добавлению: {len(todo)}; всего исключений в аккаунте до: {before_total}")

    snap = client_stats_dir(args.client_folder) / f"snapshot_before_youtube_exclusions_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps({"existing_youtube_channels": sorted(exist), "total_negatives_before": before_total}, ensure_ascii=False), encoding="utf-8")
    print("Снимок «до»:", snap)

    added = 0
    try:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            ops = []
            for r in chunk:
                op = client.get_type("CustomerNegativeCriterionOperation")
                op.create.youtube_channel.channel_id = r["channel_id"]
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
            added += len(chunk) - fails
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:5]:
            print("  -", err.message)
        raise SystemExit(1)

    if not args.execute:
        print(f"Проверка пройдена. НИЧЕГО не изменено (validate_only). Было бы добавлено ~{added} каналов.")
        return
    after_total = total_negatives(ga, cid)
    after_ch = existing_channels(ga, cid, client)
    print(f"Прочитано обратно: исключений в аккаунте {before_total} -> {after_total}; YouTube-каналов в исключениях: {len(after_ch)}")


if __name__ == "__main__":
    main()
