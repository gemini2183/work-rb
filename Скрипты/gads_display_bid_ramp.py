#!/usr/bin/env python
# coding: utf-8
"""Ступенчатый подъём потолка максимальной цены клика у новых Display-кампаний (Maximize clicks),
пока не появятся показы. Служит диагностикой: если потолок дошёл до верхнего предела, а показов нет —
дело не в ставке (аудитория, одобрение, расписание), а в другом.

Один запуск = одна проверка (скрипт без памяти внутри процесса; память — файл состояния).
Запускать по расписанию каждые 30 минут (см. README, раздел «Display: подъём потолка ставки»).

БЕЗОПАСНОСТЬ: по умолчанию ничего не пишет в кабинет (только лог «что сделал бы»). Запись — только с --execute.
Поднимает потолок только вверх, только у ENABLED-кампаний со стратегией TARGET_SPEND (Maximize clicks),
только внутри расписания показов кампании, не выше --cap. Снимок «до» и каждое действие — в
Клиенты/<клиент>/Статистика/gads_display_bid_ramp_log.csv, состояние — gads_display_bid_ramp_state.json.

Использование:
    python gads_display_bid_ramp.py --customer-id 7552781705 --client-folder ProfiMet \
        --campaign-ids 24331349689,24335049091 --step 0.05 --cap 0.40 --cooldown-min 60
    ... --execute
"""
import argparse
import csv
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

ABS_MAX_CAP = 1.0  # защита от опечатки в --cap, в валюте аккаунта
LOG_FIELDS = ["ts", "campaign_id", "campaign", "ceiling_before", "ceiling_after", "impressions_since_start",
              "clicks_since_start", "cost_since_start", "action", "comment"]


def _minute(name):
    return {"ZERO": 0, "FIFTEEN": 15, "THIRTY": 30, "FORTY_FIVE": 45}.get(name, 0)


def in_schedule(client, ga, cid, campaign_id, now):
    """True, если now (с таймзоной аккаунта) попадает в расписание показов. Нет расписания = всегда."""
    q = ("SELECT campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
         "campaign_criterion.ad_schedule.start_minute, campaign_criterion.ad_schedule.end_hour, "
         "campaign_criterion.ad_schedule.end_minute FROM campaign_criterion "
         f"WHERE campaign_criterion.type = 'AD_SCHEDULE' AND campaign.id = {campaign_id} "
         "AND campaign_criterion.status != 'REMOVED'")
    windows = []
    for r in ga.search(customer_id=cid, query=q):
        s = r.campaign_criterion.ad_schedule
        day = client.enums.DayOfWeekEnum.DayOfWeek.Name(s.day_of_week)
        sm = client.enums.MinuteOfHourEnum.MinuteOfHour.Name(s.start_minute)
        em = client.enums.MinuteOfHourEnum.MinuteOfHour.Name(s.end_minute)
        windows.append((day, s.start_hour * 60 + _minute(sm), s.end_hour * 60 + _minute(em)))
    if not windows:
        return True
    today = now.strftime("%A").upper()
    minute = now.hour * 60 + now.minute
    return any(d == today and a <= minute < b for d, a, b in windows)


def read_campaign(client, ga, cid, campaign_id, since):
    q = ("SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
         "campaign.target_spend.cpc_bid_ceiling_micros FROM campaign "
         f"WHERE campaign.id = {campaign_id}")
    rows = list(ga.search(customer_id=cid, query=q))
    if not rows:
        raise SystemExit(f"кампания {campaign_id} не найдена")
    c = rows[0].campaign
    info = {
        "id": campaign_id,
        "name": c.name,
        "status": client.enums.CampaignStatusEnum.CampaignStatus.Name(c.status),
        "strategy": client.enums.BiddingStrategyTypeEnum.BiddingStrategyType.Name(c.bidding_strategy_type),
        "ceiling": c.target_spend.cpc_bid_ceiling_micros / 1_000_000,
    }
    q2 = ("SELECT metrics.impressions, metrics.clicks, metrics.cost_micros FROM campaign "
          f"WHERE campaign.id = {campaign_id} AND segments.date BETWEEN '{since}' AND '{datetime.now().strftime('%Y-%m-%d')}'")
    imp = clk = cost = 0
    for r in ga.search(customer_id=cid, query=q2):
        imp += r.metrics.impressions
        clk += r.metrics.clicks
        cost += r.metrics.cost_micros
    info.update(impressions=imp, clicks=clk, cost=cost / 1_000_000)
    return info


def set_ceiling(client, cid, campaign_id, new_value, execute):
    op = client.get_type("CampaignOperation")
    op.update.resource_name = client.get_service("CampaignService").campaign_path(cid, campaign_id)
    op.update.target_spend.cpc_bid_ceiling_micros = int(round(new_value * 1_000_000))
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["target_spend.cpc_bid_ceiling_micros"]))
    req = client.get_type("MutateCampaignsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    client.get_service("CampaignService").mutate_campaigns(request=req)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-ids", required=True, help="через запятую")
    ap.add_argument("--step", type=float, default=0.05, help="шаг подъёма, в валюте аккаунта")
    ap.add_argument("--cap", type=float, required=True, help="верхний предел потолка, в валюте аккаунта")
    ap.add_argument("--cooldown-min", type=int, default=60, help="минимум минут между подъёмами")
    ap.add_argument("--min-impressions", type=int, default=1, help="сколько показов считать «показы пошли»")
    ap.add_argument("--tz", default="Europe/Warsaw", help="часовой пояс аккаунта")
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — только лог «что сделал бы»")
    ap.add_argument("--loop-min", type=int, default=0,
                    help="повторять проверку каждые N минут, пока процесс открыт (0 = одна проверка). Остановка: Ctrl+C")
    ap.add_argument("--loop-hours", type=float, default=12, help="предохранитель: максимум часов работы в режиме --loop-min")
    args = ap.parse_args()
    if args.cap > ABS_MAX_CAP:
        raise SystemExit(f"--cap {args.cap} выше жёсткой защиты {ABS_MAX_CAP}")
    return args


def check_once(args, client):
    """Одна проверка всех кампаний. Возвращает True, если по всем кампаниям работа закончена
    (показы пошли / предел достигнут / кампания не в статусе для работы)."""
    cid = args.customer_id.replace("-", "").strip()
    ga = client.get_service("GoogleAdsService")
    now = datetime.now(ZoneInfo(args.tz))

    out_dir = client_stats_dir(args.client_folder)
    state_path = out_dir / "gads_display_bid_ramp_state.json"
    log_path = out_dir / "gads_display_bid_ramp_log.csv"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    new_log = not log_path.exists()

    log_rows = []
    finished = []
    campaign_ids = [x.strip() for x in args.campaign_ids.split(",") if x.strip()]
    for cmp_id in campaign_ids:
        st = state.setdefault(cmp_id, {"start_date": now.strftime("%Y-%m-%d"), "last_change": None, "done": None})
        info = read_campaign(client, ga, cid, cmp_id, st["start_date"])
        row = {"ts": now.strftime("%Y-%m-%d %H:%M"), "campaign_id": cmp_id, "campaign": info["name"],
               "ceiling_before": info["ceiling"], "ceiling_after": info["ceiling"],
               "impressions_since_start": info["impressions"], "clicks_since_start": info["clicks"],
               "cost_since_start": round(info["cost"], 2), "action": "", "comment": ""}

        if st["done"]:
            row.update(action="остановлено", comment=f"ранее завершено: {st['done']}")
        elif info["status"] != "ENABLED" or info["strategy"] != "TARGET_SPEND":
            row.update(action="пропуск", comment=f"статус {info['status']}, стратегия {info['strategy']} — не трогаю")
        elif info["impressions"] >= args.min_impressions:
            st["done"] = f"показы пошли на потолке {info['ceiling']} ({now:%Y-%m-%d %H:%M})"
            row.update(action="показы пошли", comment=f"поднимать больше не нужно; потолок {info['ceiling']}")
        elif not in_schedule(client, ga, cid, cmp_id, now):
            row.update(action="вне расписания", comment="проверка не засчитана")
        elif st["last_change"] and now - datetime.fromisoformat(st["last_change"]) < timedelta(minutes=args.cooldown_min):
            row.update(action="ждём", comment=f"после последнего подъёма меньше {args.cooldown_min} мин")
        elif info["ceiling"] >= args.cap - 1e-9:
            st["done"] = f"потолок {info['ceiling']} достиг предела {args.cap}, показов нет — дело не в ставке"
            row.update(action="предел достигнут", comment=st["done"])
        else:
            new = round(min(args.cap, info["ceiling"] + args.step), 2)
            try:
                set_ceiling(client, cid, cmp_id, new, args.execute)
            except GoogleAdsException as ex:
                row.update(action="ОШИБКА", comment="; ".join(e.message for e in ex.failure.errors))
            else:
                if args.execute:
                    back = read_campaign(client, ga, cid, cmp_id, st["start_date"])
                    st["last_change"] = now.isoformat()
                    row.update(ceiling_after=back["ceiling"], action="поднят",
                               comment=f"{info['ceiling']} -> {back['ceiling']} (прочитано обратно)")
                else:
                    row.update(ceiling_after=new, action="поднял бы (dry-run)",
                               comment=f"{info['ceiling']} -> {new}; проверка validate_only пройдена")
        if st["done"] or row["action"] == "пропуск":
            finished.append(cmp_id)
        if args.execute and row["action"] not in ("остановлено", "вне расписания"):
            log_rows.append(row)  # шум (ночные и повторные проверки) и dry-run в лог не пишем
        print(f"[{row['ts']}] {info['name']}: потолок {row['ceiling_before']} -> {row['ceiling_after']}, "
              f"показов с {st['start_date']}: {info['impressions']}, кликов {info['clicks']}, "
              f"расход {row['cost_since_start']} | {row['action']}: {row['comment']}", flush=True)

    with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_log:
            w.writeheader()
        w.writerows(log_rows)
    if args.execute:
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(finished) == len(campaign_ids)


def main():
    args = parse_args()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    if not args.loop_min:
        check_once(args, client)
        return
    deadline = time.time() + args.loop_hours * 3600
    print(f"Режим цикла: проверка каждые {args.loop_min} мин, не дольше {args.loop_hours} ч. Остановка: Ctrl+C.", flush=True)
    try:
        while True:
            if check_once(args, client):
                print("Все кампании обработаны (показы пошли / предел достигнут) — цикл завершён.", flush=True)
                return
            if time.time() + args.loop_min * 60 > deadline:
                print("Достигнут предохранитель --loop-hours — цикл завершён.", flush=True)
                return
            time.sleep(args.loop_min * 60)
    except KeyboardInterrupt:
        print("Остановлено пользователем (Ctrl+C).", flush=True)


if __name__ == "__main__":
    main()
