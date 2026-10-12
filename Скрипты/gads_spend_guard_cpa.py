#!/usr/bin/env python
# coding: utf-8
"""Сторож по ЦЕНЕ ЗАЯВКИ: пауза и возобновление кампании по реальным заявкам (Ringostat + Supabase), а не по лагающим
конверсиям Google Ads. Решение пользователя 2026-10-12 после того, как `gads_spend_guard.py` остановил `pmax01_call_test`
при 1 конверсии в Ads (через 20 минут их стало 3, по Ringostat — 3 уникальных звонка, ≈18 € за звонок).

Идея: «допустимый расход» растёт с каждой заявкой, как банк.
    допустимый расход A = (grace + n) × T,   n — реальные заявки за сегодня, T — целевая цена заявки, grace — «кредит»
    в долях T на первую заявку (по умолчанию 1.0).
Эквивалент в цене заявки (grace = 1): n=1 → 200% от T, n=2 → 150%, n=3 → 133%, n=5 → 120%, n=10 → 110%. При малой
выборке цена заявки скачет в разы, поэтому плоская линия «95%/105%» шумит: единая формула даёт запас на малых n и
сходится к ~100–110% на больших.

Правила (на кампанию, раз в --loop-min минут):
  1. ВКЛЮЧЕНА и расход ≥ A                      → ПАУЗА (причина «цена заявки»), кроме жёсткого предела ниже.
  2. ВКЛЮЧЕНА и расход ≥ warn-share × A          → ПРЕДУПРЕЖДЕНИЕ (один раз), без действий.
  3. ВКЛЮЧЕНА и расход ≥ abs-mult × дневной бюджет → ПАУЗА «жёсткий предел» независимо от заявок (страховка от сбоя
     источников заявок и от дрейфа учёта); в этот день не возобновляется.
  4. НА ПАУЗЕ ПО НАШЕЙ ПРИЧИНЕ СЕГОДНЯ, заявок стало больше, чем на момент паузы, и расход ≤ resume-share × A
     → ВОЗОБНОВИТЬ (не более --max-reenable раз в день). Только с --allow-reenable и --execute.
  5. На паузе по решению пользователя (мы её не ставили) → не трогаем. Пауза сторожа в прошлый день → не возобновляем
     (новый день — новое решение человека).
Если кампанию включили руками после паузы сторожа — это записывается событием, правила работают как обычно
(т.е. включённая, но неэффективная кампания будет остановлена снова; поправка — через --target / --grace).

Источники заявок — ровно та логика, что в проекте мониторинга `E:\\PythonProjects\\RedBird\\monitoring scripts`
(модули `sources.ringostat`, `sources.supabase`; описание — Инфраструктура.md, запись 2026-10-12): уникальные звонки
Ringostat по `utm_campaign` (ID кампании в utm или имя кампании) + заявки с формы из Supabase. Оговорки:
  • звонки/формы без привязки к кампании (форма без UTM — известный баг GTM-тега) НЕ учитываются, их число пишется в лог;
  • расход из API Ads отстаёт на 15–60+ минут, поэтому цена заявки по расходу занижена — отсюда жёсткий предел;
  • «монотонность»: число заявок за день не убывает (при сбое Ringostat/Supabase берётся последнее известное).
Ключи Ringostat/Supabase/Telegram читаются из yaml монитора и нигде не печатаются.

БЕЗОПАСНОСТЬ: по умолчанию dry-run (только печать и лог). Пауза — с --execute; возобновление — с --execute И
--allow-reenable. Telegram — только с --telegram. Состояние — `Статистика/gads_spend_guard_state.json`.

Использование:
    python gads_spend_guard_cpa.py --customer-id 7552781705 --target 24332178236=45 --target 23775369828=48 \
        --loop-min 2 --execute --allow-reenable --telegram
Без --loop-min — одна проверка.
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient
from google.protobuf import field_mask_pb2

from gads_spend_guard import pause, read_state
from gads_stats import GOOGLE_ADS_YAML

MONITORING_DIR = r"E:\PythonProjects\RedBird\monitoring scripts\monitoring"
MONITORING_CFG = MONITORING_DIR + r"\config\profimet.yaml"
STATS = Path(__file__).resolve().parent.parent / "Клиенты" / "ProfiMet" / "Статистика"
LOG = STATS / "gads_spend_guard_cpa_log.csv"
STATE = STATS / "gads_spend_guard_state.json"
UNRESOLVED = "__unresolved_pmax__"   # чтобы UTM без ID и имени не склеивались в «первую попавшуюся PMax»

LOG_HEADER = ["time", "campaign_id", "name", "status", "budget", "cost_today", "target_cpa", "calls", "leads",
              "n", "allowance", "cost_share_of_allowance", "cpa_real", "event", "inertia_after_pause"]


def enable(client, cid, campaign_id):
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{cid}/campaigns/{campaign_id}"
    op.update.status = client.enums.CampaignStatusEnum.ENABLED
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    svc.mutate_campaigns(customer_id=cid, operations=[op])


def log_row(row):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_HEADER)
        w.writerow(row)


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def load_monitoring(mon_dir, cfg_path):
    """Подключает модули проекта мониторинга (Ringostat/Supabase/Telegram) и конфиг клиента. Секреты не печатаются."""
    if mon_dir not in sys.path:
        sys.path.insert(1, mon_dir)
    from sources import ringostat as m_ringostat  # noqa: E402
    from sources import supabase as m_supabase    # noqa: E402
    from reports import telegram as m_telegram    # noqa: E402
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return m_ringostat, m_supabase, m_telegram, cfg


def all_campaign_names(ga, cid):
    out = {}
    for r in ga.search(customer_id=cid, query="SELECT campaign.id, campaign.name FROM campaign WHERE campaign.status != 'REMOVED'"):
        out[str(r.campaign.id)] = r.campaign.name
    return out


def real_conversions(cfg, m_ringostat, m_supabase, id_to_name):
    """→ ({имя_кампании: уникальные_звонки}, {имя_кампании: формы}, формы_без_кампании). Ошибки источников не роняют цикл."""
    calls, leads_by, unattributed = {}, {}, 0
    try:
        for name, d in (m_ringostat.get_calls_today(cfg, id_to_name, UNRESOLVED) or {}).items():
            calls[name] = int(d.get("unique", 0))
    except Exception as ex:
        print(f"  Ringostat: ошибка {type(ex).__name__}: {str(ex)[:100]} — берём последнее известное")
    try:
        rs = cfg.get("ringostat", {})
        regex = rs.get("campaign_id_regex", r"s_(\d+)_")
        kw = rs.get("pmax_keywords", ["pmax", "performance max"])
        for lead in (m_supabase.get_leads_today(cfg) or []):
            if lead.get("_burst"):
                continue
            row = {"utm_source": lead.get("utm_source") or "", "utm_campaign": lead.get("utm_campaign") or "",
                   "pool_name": ""}
            name = m_ringostat._resolve_campaign_name(row, id_to_name, UNRESOLVED, regex, kw, "")
            if name in ("(без кампании)", UNRESOLVED):
                unattributed += 1
            else:
                leads_by[name] = leads_by.get(name, 0) + 1
    except Exception as ex:
        print(f"  Supabase: ошибка {type(ex).__name__}: {str(ex)[:100]} — берём последнее известное")
    return calls, leads_by, unattributed


def parse_targets(items):
    out = {}
    for it in items:
        k, v = it.split("=", 1)
        out[k.strip()] = float(v.replace(",", "."))
    return out


def main():
    ap = argparse.ArgumentParser(description="Сторож по цене заявки (Ringostat + Supabase)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--target", action="append", required=True, metavar="ID=EUR",
                    help="целевая цена заявки по кампании, можно несколько раз: 24332178236=45")
    ap.add_argument("--grace", type=float, default=1.0, help="кредит на первую заявку в долях цели (по умолчанию 1.0)")
    ap.add_argument("--warn-share", type=float, default=0.9)
    ap.add_argument("--resume-share", type=float, default=0.85)
    ap.add_argument("--abs-mult", type=float, default=3.0, help="жёсткий предел от дневного бюджета независимо от заявок")
    ap.add_argument("--max-reenable", type=int, default=2)
    ap.add_argument("--watch-min", type=float, default=30.0, help="сколько минут после паузы писать «инерцию»")
    ap.add_argument("--loop-min", type=float, help="повторять каждые N минут; без флага — одна проверка")
    ap.add_argument("--execute", action="store_true", help="реально ставить на паузу (без флага — dry-run)")
    ap.add_argument("--allow-reenable", action="store_true", help="разрешить автоматическое возобновление (нужен и --execute)")
    ap.add_argument("--telegram", action="store_true", help="слать события в Telegram чат монитора")
    ap.add_argument("--monitoring-dir", default=MONITORING_DIR)
    ap.add_argument("--monitoring-config", default=MONITORING_CFG)
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    targets = parse_targets(args.target)
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    enums = client.enums.CampaignStatusEnum
    m_ringostat, m_supabase, m_telegram, cfg = load_monitoring(args.monitoring_dir, args.monitoring_config)
    state = load_state()

    def notify(text):
        if args.telegram:
            try:
                m_telegram.send_text(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"], text)
            except Exception as ex:
                print(f"  Telegram: ошибка {type(ex).__name__}")

    mode = ("БОЕВОЙ: пауза" + (" + возобновление" if args.allow_reenable else "")) if args.execute else "DRY-RUN"
    print(f"=== сторож по цене заявки, {mode}; цели: {targets}; grace {args.grace}, предупреждение {args.warn_share:.0%}, "
          f"возврат {args.resume_share:.0%}, жёсткий предел {args.abs_mult}× бюджета ===")

    while True:
        today = date.today().isoformat()
        try:
            id_to_name = all_campaign_names(ga, cid)
        except Exception as ex:
            print(f"{datetime.now():%H:%M:%S} ошибка списка кампаний: {type(ex).__name__}")
            id_to_name = {}
        calls, leads_by, unattributed = real_conversions(cfg, m_ringostat, m_supabase, id_to_name)

        for campaign_id, T in targets.items():
            now = datetime.now()
            try:
                s = read_state(ga, cid, campaign_id, None)
            except Exception as ex:
                print(f"{now:%H:%M:%S} кампания {campaign_id}: ошибка чтения Ads ({type(ex).__name__}), пропуск")
                log_row([now.isoformat(timespec="seconds"), campaign_id, "", "", "", "", T, "", "", "", "", "", "",
                         "ошибка чтения: " + type(ex).__name__, ""])
                continue
            st = state.setdefault(campaign_id, {})
            if st.get("date") != today:   # новый день: счётчики и «пауза сторожа» обнуляются
                st.clear()
                st.update({"date": today, "calls_max": 0, "leads_max": 0, "reenabled": 0, "warned": False,
                           "paused_by_guard": False, "no_resume": False})
            name = s["name"]
            st["calls_max"] = max(st["calls_max"], calls.get(name, 0))
            st["leads_max"] = max(st["leads_max"], leads_by.get(name, 0))
            n = st["calls_max"] + st["leads_max"]
            cost, budget = s["cost"], s["budget"]
            allowance = (args.grace + n) * T
            share = cost / allowance if allowance else 0.0
            cpa_real = round(cost / n, 1) if n else ""
            status = s["status"]
            event = ""
            inertia = ""

            if status == enums.ENABLED:
                if st.get("paused_by_guard"):
                    event = "ручное включение после паузы сторожа; "
                    st["paused_by_guard"] = False
                if budget and cost >= args.abs_mult * budget:
                    event += f"ПАУЗА жёсткий предел: расход {cost:.2f} ≥ {args.abs_mult}× бюджета {budget:.2f} (заявок {n})"
                    do_pause, st["no_resume"], reason = True, True, "жёсткий предел"
                elif cost >= allowance:
                    event += (f"ПАУЗА цена заявки: расход {cost:.2f} ≥ допустимого {allowance:.2f} "
                              f"= ({args.grace:g}+{n})×{T:g}")
                    do_pause, reason = True, "цена заявки"
                else:
                    do_pause, reason = False, ""
                    if cost >= args.warn_share * allowance and not st["warned"]:
                        event += f"ПРЕДУПРЕЖДЕНИЕ: расход {cost:.2f} = {share:.0%} допустимого {allowance:.2f} (заявок {n})"
                        st["warned"] = True
                if do_pause:
                    if args.execute:
                        pause(client, cid, campaign_id)
                        st["paused_by_guard"] = True
                        st["paused_at"] = now.isoformat(timespec="seconds")
                        st["cost_at_pause"] = cost
                        st["n_at_pause"] = n
                        st["pause_reason"] = reason
                        notify(f"⛔ {name}: ПАУЗА ({reason}). Расход {cost:.2f} €, заявок {n}, "
                               f"допустимо {allowance:.2f} €, цель {T:g} €")
                    else:
                        event += " (dry-run, не выполнено)"
            elif st.get("paused_by_guard"):
                t0 = datetime.fromisoformat(st["paused_at"])
                if (now - t0).total_seconds() / 60 <= args.watch_min:
                    inertia = round(cost - st.get("cost_at_pause", cost), 2)
                if (not st.get("no_resume") and st.get("n_at_pause", 0) < n and cost <= args.resume_share * allowance
                        and st["reenabled"] < args.max_reenable):
                    event = (f"ВОЗОБНОВЛЕНИЕ: заявок стало {n} (было {st.get('n_at_pause')} при паузе), "
                             f"расход {cost:.2f} ≤ {args.resume_share:.0%} от допустимого {allowance:.2f}")
                    if args.execute and args.allow_reenable:
                        enable(client, cid, campaign_id)
                        st["paused_by_guard"] = False
                        st["reenabled"] += 1
                        st["warned"] = False
                        notify(f"✅ {name}: ВОЗОБНОВЛЕНА — поздние заявки (теперь {n}), расход {cost:.2f} €, "
                               f"допустимо {allowance:.2f} €")
                    else:
                        event += " (dry-run или без --allow-reenable, не выполнено)"
            # иначе: на паузе по решению человека — не трогаем

            print(f"{now:%H:%M:%S} {name}: статус {'ВКЛ' if status == enums.ENABLED else 'ПАУЗА'}, расход {cost:.2f}/"
                  f"бюджет {budget:.2f}, заявок {n} (звонки {st['calls_max']} + формы {st['leads_max']}), допустимо "
                  f"{allowance:.2f} ({share:.0%}), цена заявки {cpa_real or '—'} {event} {inertia}")
            log_row([now.isoformat(timespec="seconds"), campaign_id, name, status, budget, round(cost, 2), T,
                     st["calls_max"], st["leads_max"], n, round(allowance, 2), round(share, 3), cpa_real, event, inertia])

        if unattributed:
            print(f"  (форм без кампании/UTM сегодня: {unattributed} — не учтены ни в одной кампании)")
        save_state(state)
        if not args.loop_min:
            break
        time.sleep(args.loop_min * 60)


if __name__ == "__main__":
    main()
