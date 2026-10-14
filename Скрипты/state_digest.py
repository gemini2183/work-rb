#!/usr/bin/env python
# coding: utf-8
"""Сводка «что изменилось без меня» — ТОЛЬКО ЧТЕНИЕ. Запускать в начале сессии по клиенту, до любых выводов.

Зачем: сторожа (`gads_spend_guard_cpa.py`) и пользователь меняют кампании между сессиями, а в вики это попадает с опозданием.
Скрипт собирает три вещи за последние N часов:
  1. события сторожа из `Статистика/gads_spend_guard_cpa_log.csv` (пауза, возобновление, бюджет, ручное включение, ошибки чтения);
  2. изменения кампаний и бюджетов из истории изменений Google Ads (`change_event`): кто (почта / клиент API или веб),
     что поменялось, статус было → стало; по остальным типам объектов (объявления, ассеты, ключи) — только счётчики;
  3. текущий статус и сегодняшний расход всех включённых кампаний.
Ничего не пишет ни в кабинет, ни в вики. Что из сводки стратегически значимо — вносит Claude в Журнал_изменений/Решения.

Использование:
    python state_digest.py --customer-id 7552781705 --client-folder ProfiMet [--hours 48]
"""
import argparse
import csv
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

TZ = ZoneInfo("Europe/Warsaw")
GUARD_LOG = "gads_spend_guard_cpa_log.csv"
ROUTINE = ("без изменений", "ошибка чтения")  # в строках сторожа это рутина, показываем только счётчик


def guard_events(folder, since):
    path = client_stats_dir(folder) / GUARD_LOG
    if not path.exists():
        print(f"  (лога сторожа нет: {path})")
        return
    rows, routine, errors = [], 0, 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                t = datetime.fromisoformat(r["time"])
            except (KeyError, ValueError):
                continue
            if t.replace(tzinfo=TZ) < since:
                continue
            ev = (r.get("event") or "").strip()
            if not ev:
                continue
            if ev.startswith("ошибка чтения"):
                errors += 1
            elif any(x in ev for x in ROUTINE):
                routine += 1
            else:
                rows.append((r["time"], r.get("campaign_id", ""), r.get("name", ""), r.get("status", ""),
                             r.get("cost_today", ""), r.get("leads", ""), ev))
    if not rows:
        print("  событий сторожа с действием нет")
    for t, cid, name, st, cost, leads, ev in rows:
        print(f"  {t}  {name or cid}: {ev}  [расход дня {cost} €, заявок {leads or '0'}]")
    print(f"  (рутина: «без изменений» {routine}, ошибок чтения {errors})")


def campaign_names(ga, cid):
    q = "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, campaign_budget.amount_micros FROM campaign"
    return {r.campaign.id: r for r in ga.search(customer_id=cid, query=q)}


def change_events(client, ga, cid, since, names):
    E = client.enums
    now = datetime.now(TZ)
    q = ("SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, "
         "change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields, "
         "change_event.campaign, change_event.old_resource, change_event.new_resource "
         f"FROM change_event WHERE change_event.change_date_time >= '{since.strftime('%Y-%m-%d %H:%M:%S')}' "
         f"AND change_event.change_date_time <= '{(now + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')}' "
         "ORDER BY change_event.change_date_time DESC LIMIT 1000")
    counts, detail = Counter(), []
    for r in ga.search(customer_id=cid, query=q):
        ev = r.change_event
        rtype = E.ChangeEventResourceTypeEnum.ChangeEventResourceType.Name(ev.change_resource_type)
        who = ev.user_email or "—"
        ctype = E.ChangeClientTypeEnum.ChangeClientType.Name(ev.client_type)
        op = E.ResourceChangeOperationEnum.ResourceChangeOperation.Name(ev.resource_change_operation)
        if rtype not in ("CAMPAIGN", "CAMPAIGN_BUDGET"):
            counts[(rtype, op, ctype, who)] += 1
            continue
        cid_num = int(ev.campaign.split("/")[-1]) if ev.campaign else None
        name = names[cid_num].campaign.name if cid_num in names else (ev.campaign or "?")
        paths = list(ev.changed_fields.paths)
        extra = ""
        if rtype == "CAMPAIGN" and "status" in paths:
            old = E.CampaignStatusEnum.CampaignStatus.Name(ev.old_resource.campaign.status)
            new = E.CampaignStatusEnum.CampaignStatus.Name(ev.new_resource.campaign.status)
            extra = f" статус {old} → {new}"
        if rtype == "CAMPAIGN_BUDGET" and "amount_micros" in paths:
            extra = (f" бюджет {ev.old_resource.campaign_budget.amount_micros / 1e6:.2f} → "
                     f"{ev.new_resource.campaign_budget.amount_micros / 1e6:.2f}")
        t = ev.change_date_time[:19]
        detail.append(f"  {t}  {name}: {rtype} {op}{extra}  [{ctype}, {who}; поля: {', '.join(paths)[:90]}]")
    for line in detail:
        print(line)
    if not detail:
        print("  изменений кампаний и бюджетов нет")
    if counts:
        print("  Прочие объекты (счётчики):")
        for (rtype, op, ctype, who), n in counts.most_common(12):
            print(f"    {rtype} {op}: {n}  [{ctype}, {who}]")


def current_state(client, ga, cid):
    E = client.enums
    q = ("SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
         "campaign_budget.amount_micros, metrics.cost_micros, metrics.impressions, metrics.clicks "
         "FROM campaign WHERE campaign.status != 'REMOVED' AND segments.date DURING TODAY")
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        rows.append((E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status), r.campaign.name,
                     r.campaign_budget.amount_micros / 1e6, r.metrics.cost_micros / 1e6, r.metrics.impressions, r.metrics.clicks))
    shown = [x for x in rows if x[0] == "ENABLED" or x[3] > 0]
    if not shown:
        print("  нет включённых кампаний и расхода сегодня")
    for st, name, bud, cost, imp, clk in sorted(shown, key=lambda x: (x[0] != "ENABLED", x[1])):
        print(f"  {st:8} {name}: бюджет {bud:.0f} €, расход сегодня {cost:.2f} €, показы {imp}, клики {clk}")
    paused_today = [x for x in rows if x[0] == "PAUSED" and x[3] > 0]
    if paused_today:
        print("  ВНИМАНИЕ: на паузе, но с расходом сегодня (остановлены в течение дня): " + ", ".join(x[1] for x in paused_today))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--hours", type=int, default=48)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    since = datetime.now(TZ) - timedelta(hours=a.hours)
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    print(f"=== Сводка изменений за {a.hours} ч (с {since:%Y-%m-%d %H:%M}, Варшава), клиент {a.client_folder} ===")
    print("\n[1] События сторожа:")
    guard_events(a.client_folder, since)
    print("\n[2] Изменения в кабинете (история изменений Google Ads):")
    names = campaign_names(ga, cid)
    change_events(client, ga, cid, since, names)
    print("\n[3] Состояние сейчас:")
    current_state(client, ga, cid)
    print("\nЭто чтение. Что значимо — внести в Журнал_изменений/Решения и в задачи.")


if __name__ == "__main__":
    main()
