#!/usr/bin/env python
# coding: utf-8
"""Расписание показов кампании (ad schedule): прочитать и убрать интервалы. ЗАПИСЬ, по умолчанию validate_only.

Зачем: 2026-10-13 Brand ProfiMet — вернуть расписание ПН–ПТ 07–17, убрав вечерние интервалы 17:00–21:00, добавленные 08.09
(вечер дал 70 € на 1 звонок). Скрипт ничего не добавляет: только показывает интервалы и удаляет выбранные.

Использование:
    python gads_ad_schedule.py --customer-id 7552781705 --client-folder ProfiMet --campaign-id 19153311519            # показать
    python gads_ad_schedule.py ... --remove-window 17:00-21:00                       # план удаления (validate_only)
    python gads_ad_schedule.py ... --remove-window 17:00-21:00 --execute             # удалить, прочитать обратно
    python gads_ad_schedule.py ... --set-window 10:00-15:00                          # план: заменить все интервалы на одно окно
                                                                                      # в те же дни (множитель ставки сохраняется)
    python gads_ad_schedule.py ... --set-window 10:00-15:00 --execute                # записать, прочитать обратно

Перед записью снимок интервалов пишется в `Статистика/snapshot_before_ad_schedule_<id>_<время>.csv`; откат — заново создать
интервалы из снимка (день, начало, конец, множитель ставки).
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

DAYS = {2: "пн", 3: "вт", 4: "ср", 5: "чт", 6: "пт", 7: "сб", 8: "вс"}
MINUTES = {2: 0, 3: 15, 4: 30, 5: 45}   # enum MinuteOfHour: ZERO=2, FIFTEEN=3, THIRTY=4, FORTY_FIVE=5


def read_schedule(ga, cid, campaign_id):
    q = ("SELECT campaign_criterion.criterion_id, campaign_criterion.resource_name, campaign_criterion.bid_modifier, "
         "campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
         "campaign_criterion.ad_schedule.start_minute, campaign_criterion.ad_schedule.end_hour, "
         "campaign_criterion.ad_schedule.end_minute FROM campaign_criterion "
         f"WHERE campaign.id = {campaign_id} AND campaign_criterion.type = AD_SCHEDULE")
    out = []
    for r in ga.search(customer_id=cid, query=q):
        c = r.campaign_criterion
        s = c.ad_schedule
        out.append({"id": c.criterion_id, "resource": c.resource_name, "day": DAYS.get(s.day_of_week, str(s.day_of_week)),
                    "start": f"{s.start_hour:02d}:{MINUTES.get(s.start_minute, 0):02d}",
                    "end": f"{s.end_hour:02d}:{MINUTES.get(s.end_minute, 0):02d}",
                    "bid_modifier": round(c.bid_modifier, 2)})
    return sorted(out, key=lambda x: (list(DAYS.values()).index(x["day"]) if x["day"] in DAYS.values() else 9, x["start"]))


def show(rows, title):
    print(f"\n== {title}: {len(rows)} интервалов")
    for r in rows:
        print(f"   {r['day']} {r['start']}–{r['end']} | множитель {r['bid_modifier']} | id {r['id']}")


MIN_ENUM = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}
DAY_ENUM = {"пн": "MONDAY", "вт": "TUESDAY", "ср": "WEDNESDAY", "чт": "THURSDAY", "пт": "FRIDAY", "сб": "SATURDAY", "вс": "SUNDAY"}


def set_window(client, ga, cid, a, rows):
    """Заменяет все интервалы одним окном в те же дни (атомарно: удаление старых + создание новых)."""
    start, end = a.set_window.split("-")
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    if sm not in MIN_ENUM or em not in MIN_ENUM:
        raise SystemExit("минуты — только 00/15/30/45")
    days = sorted({r["day"] for r in rows}, key=lambda d: list(DAYS.values()).index(d))
    mods = {r["day"]: r["bid_modifier"] for r in rows}
    print(f"\nПЛАН: {len(rows)} старых интервалов удалить; создать {len(days)}: {', '.join(days)} {start}–{end}")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_ad_schedule_{a.campaign_id}_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "day", "start", "end", "bid_modifier", "resource"])
        w.writeheader()
        w.writerows(rows)
    print("Снимок «до»:", snap)
    camp_rn = client.get_service("CampaignService").campaign_path(cid, a.campaign_id)
    ops = []
    for r in rows:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = r["resource"]
        ops.append(op)
    for d in days:
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = camp_rn
        c.ad_schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, DAY_ENUM[d])
        c.ad_schedule.start_hour, c.ad_schedule.end_hour = sh, eh
        c.ad_schedule.start_minute = getattr(client.enums.MinuteOfHourEnum, MIN_ENUM[sm])
        c.ad_schedule.end_minute = getattr(client.enums.MinuteOfHourEnum, MIN_ENUM[em])
        if mods.get(d):
            c.bid_modifier = mods[d]
        ops.append(op)
    svc = client.get_service("CampaignCriterionService")
    req = client.get_type("MutateCampaignCriteriaRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = True
    svc.mutate_campaign_criteria(request=req)
    print("validate_only OK")
    if not a.execute:
        print("ПЛАН. Ничего не записано (добавьте --execute).")
        return
    req.validate_only = False
    svc.mutate_campaign_criteria(request=req)
    show(read_schedule(ga, cid, a.campaign_id), "прочитано обратно")


def main():
    ap = argparse.ArgumentParser(description="Расписание показов кампании: показать / удалить интервалы")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--remove-window", help="удалить интервалы с точным окном ЧЧ:ММ-ЧЧ:ММ, например 17:00-21:00")
    ap.add_argument("--set-window", help="заменить ВСЕ интервалы одним окном ЧЧ:ММ-ЧЧ:ММ в те же дни, что есть сейчас")
    ap.add_argument("--execute", action="store_true", help="реально записать (без флага — validate_only/план)")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    rows = read_schedule(ga, cid, a.campaign_id)
    show(rows, f"расписание кампании {a.campaign_id} сейчас")
    if a.set_window:
        set_window(client, ga, cid, a, rows)
        return
    if not a.remove_window:
        return
    start, end = a.remove_window.split("-")
    todo = [r for r in rows if r["start"] == start and r["end"] == end]
    print(f"\nК удалению (окно {start}–{end}): {len(todo)}")
    for r in todo:
        print(f"   - {r['day']} {r['start']}–{r['end']} id {r['id']}")
    if not todo:
        return
    if not a.execute:
        print("\nПЛАН. Ничего не записано (добавьте --execute).")
        return
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_ad_schedule_{a.campaign_id}_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "day", "start", "end", "bid_modifier", "resource"])
        w.writeheader()
        w.writerows(rows)
    print("Снимок «до»:", snap)
    svc = client.get_service("CampaignCriterionService")
    ops = []
    for r in todo:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = r["resource"]
        ops.append(op)
    svc.mutate_campaign_criteria(customer_id=cid, operations=ops)
    show(read_schedule(ga, cid, a.campaign_id), "прочитано обратно")


if __name__ == "__main__":
    main()
