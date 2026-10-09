#!/usr/bin/env python
# coding: utf-8
"""Сторож расхода: ставит кампанию на паузу по заранее согласованным правилам и пишет «инерцию» после паузы.

Зачем: у Google нет жёсткого предела дневного расхода. 08.10.2026 старая `pmax01` (бюджет 30) потратила 108.6 за
39 минут (Discover), и пауза после превышения пришла поздно. Сторож опрашивает кабинет каждые --loop-min минут.

Правила паузы (решение пользователя 2026-10-08), для каждой кампании:
  1. расход сегодня >= --soft-share от дневного бюджета (по умолчанию 0.95) И конверсий сегодня 0;
  2. расход сегодня >= --hard-mult от бюджета (по умолчанию 1.5) независимо от конверсий;
  3. общий расход с даты --since >= --total-limit (по умолчанию 250), если задан.
После паузы сторож ещё --watch-min минут (по умолчанию 30) продолжает опрос и пишет, сколько успело списаться
(«инерция»), в CSV. Сторож сам кампанию НЕ включает.

Оговорка: конверсии в Ads приходят с задержкой (звонки Ringostat через GA4 — на часы); правило 1 смотрит только то, что
Ads уже засчитал по основным целям кампании (metrics.conversions). Без этого правила бюджет не ограничивается.

БЕЗОПАСНОСТЬ: по умолчанию только печатает, что сделал бы (dry-run). Реальная пауза — только с --execute.

Использование (цикл запускает пользователь в терминале, как gads_display_bid_ramp.py):
    python gads_spend_guard.py --customer-id 7552781705 --campaign-ids 12345 --since 2026-10-12 --loop-min 10 --execute
Без --loop-min — одна проверка.
"""
import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.protobuf import field_mask_pb2

from gads_stats import GOOGLE_ADS_YAML

LOG = Path(__file__).resolve().parent.parent / "Клиенты" / "ProfiMet" / "Статистика" / "gads_spend_guard_log.csv"


def read_state(ga, cid, campaign_id, since):
    today = ga.search(customer_id=cid, query=(
        "SELECT campaign.name, campaign.status, campaign_budget.amount_micros, metrics.cost_micros, metrics.conversions "
        f"FROM campaign WHERE campaign.id = {campaign_id} AND segments.date DURING TODAY"))
    row = next(iter(today), None)
    if row is None:
        info = next(iter(ga.search(customer_id=cid, query=(
            "SELECT campaign.name, campaign.status, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {campaign_id}"))))
        cost, conv = 0.0, 0.0
    else:
        info = row
        cost, conv = row.metrics.cost_micros / 1e6, row.metrics.conversions
    total = None
    if since:
        total = 0.0
        for r in ga.search(customer_id=cid, query=(
                f"SELECT metrics.cost_micros FROM campaign WHERE campaign.id = {campaign_id} "
                f"AND segments.date BETWEEN '{since}' AND '{datetime.now():%Y-%m-%d}'")):
            total += r.metrics.cost_micros / 1e6
    return {"name": info.campaign.name, "status": info.campaign.status,
            "budget": info.campaign_budget.amount_micros / 1e6, "cost": cost, "conv": conv, "total": total}


def pause(client, cid, campaign_id):
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{cid}/campaigns/{campaign_id}"
    op.update.status = client.enums.CampaignStatusEnum.PAUSED
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    svc.mutate_campaigns(customer_id=cid, operations=[op])


def log_row(row):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "campaign_id", "name", "status", "budget", "cost_today", "conv_today", "total", "event", "inertia_after_pause"])
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-ids", nargs="+", required=True)
    ap.add_argument("--soft-share", type=float, default=0.95)
    ap.add_argument("--hard-mult", type=float, default=1.5)
    ap.add_argument("--total-limit", type=float, default=250.0)
    ap.add_argument("--since", help="дата начала теста ГГГГ-ММ-ДД для общего лимита")
    ap.add_argument("--loop-min", type=float, help="повторять каждые N минут; без флага — одна проверка")
    ap.add_argument("--watch-min", type=float, default=30.0, help="сколько минут после паузы фиксировать инерцию")
    ap.add_argument("--execute", action="store_true", help="Реально ставить на паузу. Без флага — dry-run")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    enums = client.enums.CampaignStatusEnum
    paused_at = {}   # campaign_id -> (время паузы, расход на момент паузы)

    while True:
        for campaign_id in args.campaign_ids:
            try:
                s = read_state(ga, cid, campaign_id, args.since)
            except Exception as ex:  # сбой сети/API не должен ронять сторожа: пропускаем проверку, пробуем снова
                now = datetime.now()
                print(f"{now:%H:%M:%S} кампания {campaign_id}: ошибка чтения, пропуск ({type(ex).__name__}: {str(ex)[:120]})")
                log_row([now.isoformat(timespec="seconds"), campaign_id, "", "", "", "", "", "", "ошибка чтения: " + type(ex).__name__, ""])
                continue
            now = datetime.now()
            event, inertia = "", ""
            if campaign_id in paused_at:
                t0, cost0 = paused_at[campaign_id]
                inertia = round(s["cost"] - cost0, 2)
                event = "после паузы"
            elif s["status"] == enums.ENABLED:
                reason = None
                if s["budget"] and s["cost"] >= s["budget"] * args.hard_mult:
                    reason = f"расход {s['cost']:.2f} >= {args.hard_mult} x бюджет {s['budget']:.2f}"
                elif s["budget"] and s["cost"] >= s["budget"] * args.soft_share and s["conv"] == 0:
                    reason = f"расход {s['cost']:.2f} >= {args.soft_share:.0%} бюджета {s['budget']:.2f} и конверсий 0"
                elif args.since and s["total"] is not None and s["total"] >= args.total_limit:
                    reason = f"общий расход {s['total']:.2f} >= {args.total_limit}"
                if reason:
                    event = f"ПАУЗА: {reason}"
                    if args.execute:
                        pause(client, cid, campaign_id)
                    else:
                        event += " (dry-run, не выполнено)"
                    paused_at[campaign_id] = (now, s["cost"])
            print(f"{now:%H:%M:%S} {s['name']}: расход {s['cost']:.2f} / бюджет {s['budget']:.2f}, конверсий {s['conv']:.1f}"
                  f"{'' if s['total'] is None else f', всего {s['total']:.2f}'} {event} {inertia}")
            log_row([now.isoformat(timespec="seconds"), campaign_id, s["name"], s["status"], s["budget"],
                     round(s["cost"], 2), round(s["conv"], 2), "" if s["total"] is None else round(s["total"], 2), event, inertia])
        # снять с наблюдения те, что прошли --watch-min после паузы
        for cid_, (t0, _) in list(paused_at.items()):
            if (datetime.now() - t0).total_seconds() / 60 >= args.watch_min:
                print(f"наблюдение за {cid_} после паузы завершено")
                del paused_at[cid_]
                args.campaign_ids = [c for c in args.campaign_ids if c != cid_]
        if not args.loop_min or not args.campaign_ids:
            break
        time.sleep(args.loop_min * 60)


if __name__ == "__main__":
    main()
