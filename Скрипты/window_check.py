#!/usr/bin/env python
# coding: utf-8
"""Проверка «чистоты окна» перед оценкой теста/кампании — ТОЛЬКО ЧТЕНИЕ. Запускать ДО подсчёта заявок и цены заявки.

Зачем: выводы по периоду верны, только если кампания в этот период работала полноценно. Выходные по расписанию, пауза,
половина дня, правка бюджета / цены / расписания посреди дня искажают расход, заявки и цену заявки. Правило пользователя
2026-10-19 (случай ProfiMet, Э-15): сначала выяснить, какие дни «чистые», и считать только по ним (или сравнивать
одинаковые дни недели), а остальные называть вслух и не смешивать.

По каждой кампании и дню печатает: день недели, запланированные часы по расписанию, часы с показами, расход, показы,
заявки (основные конверсии Ads), правки в этот день (кто, что, во сколько) и вердикт:
  ЧИСТЫЙ       — расписание отработано (≥ 80% запланированных часов с показами), правок настроек в этот день не было
  ВЫХОДНОЙ     — по расписанию день выключен, показов нет (в период не входит)
  ЧАСТИЧНЫЙ    — показы были меньше чем в 80% запланированных часов (пауза, пустой аукцион, лимит)
  ПЕРЕХОДНЫЙ   — в этот день менялись статус, бюджет, цена, расписание, ставки: до правки и после — разные режимы
  СОКРАЩЁННЫЙ  — по расписанию день короче будней (обычно суббота): отдельный режим, не смешивать с будними
  НЕ ЗАКОНЧЕН  — сегодняшний день
Ограничения: расписание берётся ТЕКУЩЕЕ (прошлые версии не хранятся — смотреть правки расписания в колонке правок);
заявки здесь — основные конверсии Ads, не Ringostat; правка до начала окна показа (например бюджет в 09:05 при показе с 10:00)
тоже даёт «ПЕРЕХОДНЫЙ» — решать вручную. Ничего не пишет ни в кабинет, ни в вики.

Использование (из папки Скрипты — путь к ключам относительный):
    python window_check.py --customer-id 7552781705 --from 2026-10-12 --to 2026-10-19 [--campaign "pmax1_test" ...]
Без --campaign берутся все кампании, у которых в периоде были показы или правки.
"""
import argparse
import io
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML

# поля change_event, которые меняют режим работы кампании (остальное — тексты, ключи, минуса — день не портит)
MODE_FIELDS = ("status", "amount_micros", "target_cpa", "target_roas", "bid_modifier", "ad_schedule", "cpc_bid_micros",
               "cpc_ceiling", "manual_cpc", "bidding_strategy", "geo_target", "maximize_", "target_")
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", required=True)
    ap.add_argument("--campaign", action="append", default=[])
    a = ap.parse_args()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    svc, E = client.get_service("GoogleAdsService"), client.enums
    q = lambda x: list(svc.search(customer_id=a.customer_id, query=x))

    camps = {r.campaign.resource_name: (r.campaign.name, E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status))
             for r in q("SELECT campaign.resource_name, campaign.name, campaign.status FROM campaign")}
    # расписание: {имя: {день_недели: минуты}}; нет строк вообще -> показ круглосуточно
    sched = defaultdict(lambda: defaultdict(int))
    has_sched = set()
    for r in q("SELECT campaign.name, campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour,"
               " campaign_criterion.ad_schedule.start_minute, campaign_criterion.ad_schedule.end_hour,"
               " campaign_criterion.ad_schedule.end_minute FROM campaign_criterion"
               " WHERE campaign_criterion.type = 'AD_SCHEDULE' AND campaign_criterion.status != 'REMOVED'"):
        s = r.campaign_criterion.ad_schedule
        # минуты в Google Ads — ENUM (ZERO/FIFTEEN/...); для оценки покрытия хватает часов
        has_sched.add(r.campaign.name)
        day = E.DayOfWeekEnum.DayOfWeek.Name(s.day_of_week)
        sched[r.campaign.name][day] += max(s.end_hour - s.start_hour, 0) * 60
    rows = defaultdict(lambda: defaultdict(lambda: {"cost": 0.0, "impr": 0, "conv": 0.0, "hours": set(), "dow": ""}))
    for r in q(f"SELECT campaign.name, segments.date, segments.day_of_week, segments.hour, metrics.cost_micros,"
               f" metrics.impressions, metrics.conversions FROM campaign"
               f" WHERE segments.date BETWEEN '{a.d_from}' AND '{a.d_to}'"):
        d = rows[r.campaign.name][r.segments.date]
        d["cost"] += r.metrics.cost_micros / 1e6
        d["impr"] += r.metrics.impressions
        d["conv"] += r.metrics.conversions
        d["dow"] = E.DayOfWeekEnum.DayOfWeek.Name(r.segments.day_of_week)
        if r.metrics.impressions > 0:
            d["hours"].add(r.segments.hour)
    changes = defaultdict(lambda: defaultdict(list))  # имя -> дата -> [(время, кто, что)]
    for r in q(f"SELECT change_event.change_date_time, change_event.user_email, change_event.change_resource_type,"
               f" change_event.resource_change_operation, change_event.changed_fields, change_event.campaign"
               f" FROM change_event WHERE change_event.change_date_time >= '{a.d_from} 00:00:00'"
               f" AND change_event.change_date_time <= '{a.d_to} 23:59:59' ORDER BY change_event.change_date_time LIMIT 10000"):
        e = r.change_event
        name = camps.get(e.campaign, ("", ""))[0]
        fields = ",".join(e.changed_fields.paths)
        rtype = E.ChangeEventResourceTypeEnum.ChangeEventResourceType.Name(e.change_resource_type)
        op = E.ResourceChangeOperationEnum.ResourceChangeOperation.Name(e.resource_change_operation)
        is_mode = (rtype == "CAMPAIGN_CRITERION" and "ad_schedule" in fields) or any(f in fields for f in MODE_FIELDS)
        if name and is_mode and rtype != "AD_GROUP_CRITERION_NEGATIVE":
            ts = str(e.change_date_time)
            changes[name][ts[:10]].append((ts[11:16], e.user_email.split("@")[0] or "api", f"{rtype} {op} {fields[:40]}"))

    today = date.today().isoformat()
    names = sorted(set(rows) | set(changes)) if not a.campaign else a.campaign
    for name in names:
        print(f"\n=== {name} ({camps_status(camps, name)}) ===")
        print("дата        день  по расписанию  с показами   расход  показы  заявки  вердикт / правки")
        day = date.fromisoformat(a.d_from)
        while day <= date.fromisoformat(a.d_to):
            ds = day.isoformat()
            dow = DAYS[day.weekday()]
            plan_h = 24 if name not in has_sched else math.ceil(sched[name].get(dow, 0) / 60)
            d = rows[name].get(ds)
            hrs = len(d["hours"]) if d else 0
            ch = changes[name].get(ds, [])
            if ds == today:
                verdict = "НЕ ЗАКОНЧЕН"
            elif plan_h == 0:
                verdict = "ВЫХОДНОЙ" if hrs == 0 else "ПОКАЗЫ ВНЕ РАСПИСАНИЯ"
            elif ch:
                verdict = "ПЕРЕХОДНЫЙ"
            elif hrs < 0.8 * plan_h:
                verdict = "ЧАСТИЧНЫЙ"
            elif name in has_sched and plan_h < 0.7 * max(math.ceil(m / 60) for m in sched[name].values()):
                verdict = "СОКРАЩЁННЫЙ (по расписанию, сравнивать только с такими же днями)"
            else:
                verdict = "ЧИСТЫЙ"
            cost, impr, conv = (d["cost"], d["impr"], d["conv"]) if d else (0, 0, 0)
            print(f"{ds}  {dow[:3]}  {plan_h:>9} ч  {hrs:>8} ч  {cost:7.2f}  {impr:6}  {conv:6.1f}  {verdict}")
            for t, who, what in ch[:6]:
                print(f"{'':>63}{t} {who}: {what}")
            if len(ch) > 6:
                print(f"{'':>63}… и ещё {len(ch) - 6} правок")
            day += timedelta(days=1)
    print("\nСчитать цену заявки и тренды — по ЧИСТЫМ дням (или одинаковым дням недели). ПЕРЕХОДНЫЕ, ЧАСТИЧНЫЕ, "
          "ВЫХОДНЫЕ называть вслух и не смешивать с чистыми.")


def camps_status(camps, name):
    for n, st in camps.values():
        if n == name:
            return st
    return "?"


if __name__ == "__main__":
    main()
