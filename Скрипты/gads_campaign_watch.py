#!/usr/bin/env python
# coding: utf-8
"""Наблюдатель за кампанией Google Ads: раз в N минут читает расход, показы, клики, конверсии за сегодня
(кампания + группы ассетов PMax), пишет строку в CSV и печатает ALERT при событиях. ТОЛЬКО ЧТЕНИЕ, ничего не пишет в кабинет.

Зачем: после всплеска (ExpertAgro `general_pmax`, 2026-10-12) нужно видеть, идут ли показы и не повторяется ли
рывок, при этом сторож с паузой для этого случая не годится (расход за день уже выше его порогов; в API расход
приходит с задержкой 15–30 минут). Здесь — наблюдение без действий, решение остаётся за человеком.

ALERT печатается, когда:
  - сменился статус кампании или группы ассетов;
  - расход за интервал >= --alert-delta;
  - расход за день >= --alert-cost;
  - кампания включена, а показы не росли --stall-ticks проверок подряд (один раз на серию).
Остальное — только в CSV (`Клиенты/<папка>/Статистика/campaign_watch_<id>_<дата>.csv`).

Использование:
    python gads_campaign_watch.py --customer-id 8826134558 --campaign-id 23593683252 --client-folder "EkspertAgro/Теплицы_Польша" \
        --loop-min 5 --alert-delta 20 --alert-cost 650
Без --loop-min — одна проверка.
"""
import argparse
import csv
import time
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def read_state(ga, E, cid, campaign_id):
    camp = None
    for r in ga.search(timeout=60, customer_id=cid, query=(
            "SELECT campaign.name, campaign.status, campaign.primary_status, campaign_budget.amount_micros, metrics.cost_micros, "
            "metrics.clicks, metrics.impressions, metrics.conversions FROM campaign "
            f"WHERE campaign.id = {campaign_id} AND segments.date DURING TODAY")):
        camp = r
    if camp is None:  # нет строки за сегодня (ни показов, ни расхода)
        for r in ga.search(timeout=60, customer_id=cid, query=(
                "SELECT campaign.name, campaign.status, campaign.primary_status, campaign_budget.amount_micros FROM campaign "
                f"WHERE campaign.id = {campaign_id}")):
            camp = r
    st = {
        "name": camp.campaign.name,
        "status": E.CampaignStatusEnum.CampaignStatus.Name(camp.campaign.status),
        "primary": E.CampaignPrimaryStatusEnum.CampaignPrimaryStatus.Name(camp.campaign.primary_status),
        "budget": camp.campaign_budget.amount_micros / 1e6,
        "cost": camp.metrics.cost_micros / 1e6,
        "clicks": camp.metrics.clicks,
        "impr": camp.metrics.impressions,
        "conv": camp.metrics.conversions,
        "groups": {},
    }
    # Группы ассетов (есть только у PMax); для других типов запрос вернёт пусто или ошибку — не критично
    try:
        names = {}
        for r in ga.search(timeout=60, customer_id=cid, query=(
                f"SELECT asset_group.id, asset_group.name, asset_group.status FROM asset_group WHERE campaign.id = {campaign_id}")):
            names[r.asset_group.id] = [r.asset_group.name, E.AssetGroupStatusEnum.AssetGroupStatus.Name(r.asset_group.status), 0.0, 0]
        for r in ga.search(timeout=60, customer_id=cid, query=(
                "SELECT asset_group.id, metrics.cost_micros, metrics.impressions FROM asset_group "
                f"WHERE campaign.id = {campaign_id} AND segments.date DURING TODAY")):
            if r.asset_group.id in names:
                names[r.asset_group.id][2] = r.metrics.cost_micros / 1e6
                names[r.asset_group.id][3] = r.metrics.impressions
        st["groups"] = {v[0]: {"status": v[1], "cost": v[2], "impr": v[3]} for v in names.values()}
    except Exception:
        pass
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--client-folder", required=True, help='напр. "EkspertAgro/Теплицы_Польша"')
    ap.add_argument("--loop-min", type=float, help="повторять каждые N минут; без флага — одна проверка")
    ap.add_argument("--alert-delta", type=float, default=20.0, help="ALERT, если расход за интервал >= N")
    ap.add_argument("--alert-cost", type=float, default=0.0, help="ALERT, если расход за день >= N (0 — выключено)")
    ap.add_argument("--stall-ticks", type=int, default=6, help="ALERT, если показы не росли N проверок подряд при ENABLED")
    ap.add_argument("--wake-impr", type=int, default=50, help="ALERT «показы пошли», если прирост показов за интервал >= N")
    ap.add_argument("--stall-min-impr", type=int, default=5, help="прирост показов за интервал меньше N считается «не росли»")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    out = client_stats_dir(args.client_folder) / f"campaign_watch_{args.campaign_id}_{datetime.now():%Y-%m-%d}.csv"
    new = not out.exists()
    prev, stall, stall_alerted, cost_alerted = None, 0, False, False

    while True:
        now = datetime.now()
        try:
            s = read_state(ga, E, cid, args.campaign_id)
        except Exception as ex:  # сбой сети/API не должен ронять наблюдателя
            print(f"{now:%H:%M:%S} ошибка чтения: {type(ex).__name__}: {str(ex)[:100]}", flush=True)
            if not args.loop_min:
                break
            time.sleep(args.loop_min * 60)
            continue

        d_cost = s["cost"] - prev["cost"] if prev else 0.0
        d_impr = s["impr"] - prev["impr"] if prev else 0
        alerts = []
        if prev:
            if s["status"] != prev["status"]:
                alerts.append(f"статус кампании {prev['status']} → {s['status']}")
            if s["primary"] != prev["primary"]:
                alerts.append(f"состояние кампании {prev['primary']} → {s['primary']}")
            for g, v in s["groups"].items():
                pg = prev["groups"].get(g)
                if pg and pg["status"] != v["status"]:
                    alerts.append(f"группа «{g}»: {pg['status']} → {v['status']}")
            if d_cost >= args.alert_delta:
                alerts.append(f"расход за интервал +{d_cost:.1f} (порог {args.alert_delta:.0f})")
            # Инерция: на паузе расход по данным API всё ещё меняется (догрузка отчётов или реальные хвосты показов).
            # Рост = данные догружаются / хвост; снижение = корректировка отчёта. Без различения — это видно по знаку.
            if s["status"] != "ENABLED" and prev["status"] != "ENABLED":
                for g, v in s["groups"].items():
                    pg = prev["groups"].get(g)
                    if pg and abs(v["cost"] - pg["cost"]) >= 1.0:
                        alerts.append(f"инерция: группа «{g}» ({v['status']}) расход {v['cost'] - pg['cost']:+.1f}")
                if abs(d_cost) >= 1.0 and not s["groups"]:
                    alerts.append(f"инерция: кампания на паузе, расход {d_cost:+.1f}")
            if s["status"] == "ENABLED":
                stall = stall + 1 if d_impr < args.stall_min_impr else 0
                if stall >= args.stall_ticks and not stall_alerted:
                    alerts.append(f"показы не растут {stall} проверок подряд (≈{stall * (args.loop_min or 0):.0f} мин)")
                    stall_alerted = True
                if d_impr >= args.stall_min_impr:
                    stall_alerted = False
                if d_impr >= args.wake_impr:
                    alerts.append(f"показы пошли: +{d_impr} за интервал (≥ {args.wake_impr})")
        if args.alert_cost and s["cost"] >= args.alert_cost and not cost_alerted:
            alerts.append(f"расход за день {s['cost']:.1f} >= {args.alert_cost:.0f}")
            cost_alerted = True

        groups_txt = "; ".join(f"{g}:{v['status'][:3]} {v['cost']:.0f}zl/{v['impr']}п" for g, v in s["groups"].items())
        line = (f"{now:%H:%M:%S} {s['name']} {s['status']}/{s['primary']} | бюджет {s['budget']:.0f} | расход {s['cost']:.1f} ({d_cost:+.1f}) | "
                f"показы {s['impr']} ({d_impr:+d}) | клики {s['clicks']} | конв {s['conv']:.1f} | {groups_txt}")
        print(("ALERT " + "; ".join(alerts) + " || " if alerts else "") + line, flush=True)

        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "status", "primary_status", "budget", "cost_today", "d_cost", "impressions", "d_impr", "clicks", "conversions",
                            "groups", "alerts"])
                new = False
            w.writerow([now.isoformat(timespec="seconds"), s["status"], s["primary"], s["budget"], round(s["cost"], 2), round(d_cost, 2),
                        s["impr"], d_impr, s["clicks"], round(s["conv"], 2), groups_txt, " | ".join(alerts)])
        prev = s
        if not args.loop_min:
            break
        time.sleep(args.loop_min * 60)


if __name__ == "__main__":
    main()
