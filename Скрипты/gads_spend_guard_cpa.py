#!/usr/bin/env python
# coding: utf-8
"""Сторож по ЦЕНЕ ЗАЯВКИ + управление дневным бюджетом: пауза и возобновление по реальным заявкам (Ringostat + Supabase),
а не по лагающим конверсиям Google Ads; бюджет растёт «по чуть-чуть» только за доказанную эффективность.
Решение пользователя 2026-10-12 (после того, как `gads_spend_guard.py` остановил `pmax01_call_test` при 1 конверсии в Ads,
а через 20 минут их стало 3 — ≈18 € за звонок по Ringostat; и после всплеска ExpertAgro: 600 zł за полчаса при бюджете 300).

ТРИ СЛОЯ
1) Цена заявки (всегда включён). «Допустимый расход» растёт с каждой заявкой, как банк:
       A = (grace + n) × T,   n — реальные заявки за сегодня, T — целевая цена заявки, grace — аванс в долях T.
   ВКЛЮЧЕНА и расход ≥ A → ПАУЗА; расход ≥ warn-share × A → предупреждение; НА ПАУЗЕ ПО НАШЕЙ ПРИЧИНЕ СЕГОДНЯ, заявок
   стало больше и расход ≤ resume-share × A → ВОЗОБНОВИТЬ (не более --max-reenable раз в день, нужен --allow-reenable).
   Запасные правила: жёсткий предел --abs-mult × текущий бюджет (страховка от ложных звонков/сбоя источников) и «темп»:
   за --pace-min минут расход вырос на ≥ --pace-share бюджета, а заявок не прибавилось → пауза.
2) Дневной «люфт» бюджета (--flex): кампания эффективна сегодня (заявок ≥ --flex-min-leads, цена ≤ --flex-cpa-share × T) и
   расход дошёл до --flex-cost-share бюджета → бюджет на сегодня поднимается выше фактического расхода (не выше
   --max-budget, не чаще --flex-max-per-day раз); в --restore-at бюджет возвращается к базовому. Если сторож был
   остановлен и люфт остался висеть — при следующем запуске/дне он будет откатан.
3) Базовый бюджет (--flex): утром первого тика дня — если последние --efficient-days календарных дня подряд (уже на
   текущем бюджете) были эффективны (расход > 0, заявок ≥ --day-min-leads, цена ≤ T) → базовый бюджет +--step-pct%
   (до --max-budget); если вчера «плохой день» (расход выше A) → на один шаг вниз, но не ниже стартового.
   Так бюджет растёт только за подтверждённые дни и не даёт «сливов» от внезапных скачков.

ЧЕСТНЫЕ ОГРАНИЧЕНИЯ
  • Google может потратить до 2× дневного бюджета за день; расход в API отстаёт на 15–60+ минут. Единственный тормоз
    в реальном времени — сам уровень бюджета, поэтому он растёт ступенями. Сторож не может предотвратить скачок за
    полчаса целиком, он ограничивает его цену.
  • Звонки/формы без привязки к кампании (форма без UTM — известный баг GTM-тега) не учитываются, число пишется в консоль.
  • История дней: звонки Ringostat (уникальные, по utm_campaign) + формы `form_submit_gtm` из Ads по дате конверсии;
    сегодня: Ringostat + заявки Supabase. Число заявок за день не убывает (при сбое источника берётся последнее известное).
  • Бюджет общий для нескольких кампаний (shared) — управление пропускается.
  • Лимит правок бюджета в сутки у Google — не проверено на практике, поэтому люфт ≤ 2 раз в день.

Источники заявок — логика проекта мониторинга `E:\\PythonProjects\\RedBird\\monitoring scripts` (модули `sources.ringostat`,
`sources.supabase`, `reports.telegram`; конфиг `config\\profimet.yaml`; ключи не печатаются). Описание — Инфраструктура.md.

БЕЗОПАСНОСТЬ: по умолчанию dry-run. Пауза — с --execute; возобновление — --execute + --allow-reenable; правки бюджета —
--execute + --allow-budget (без --flex бюджет не трогается вообще). Telegram — только с --telegram.
Состояние — `Статистика/gads_spend_guard_state.json`, лог — `gads_spend_guard_cpa_log.csv`.

Использование:
    python gads_spend_guard_cpa.py --customer-id 7552781705 --target 24332178236=25 --target 23775369828=22 --grace 2.0 \
        --loop-min 2 --execute --allow-reenable --telegram
    # + управление бюджетом:
    ... --flex --allow-budget --base-budget 24332178236=40 --base-budget 23775369828=120 \
        --max-budget 24332178236=80 --max-budget 23775369828=150
Без --loop-min — одна проверка.
"""
import argparse
import csv
import json
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
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
FORM_ACTION = "form_submit_gtm"

LOG_HEADER = ["time", "campaign_id", "name", "status", "budget", "cost_today", "target_cpa", "calls", "leads",
              "n", "allowance", "cost_share_of_allowance", "cpa_real", "event", "inertia_after_pause"]


# ---------- запись в кабинет ----------

def enable(client, cid, campaign_id):
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{cid}/campaigns/{campaign_id}"
    op.update.status = client.enums.CampaignStatusEnum.ENABLED
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    svc.mutate_campaigns(customer_id=cid, operations=[op])


def set_budget(client, cid, resource_name, amount_eur):
    svc = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    op.update.resource_name = resource_name
    op.update.amount_micros = int(round(amount_eur)) * 1_000_000   # целые евро
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))
    svc.mutate_campaign_budgets(customer_id=cid, operations=[op])


def read_budget(ga, cid, campaign_id):
    """→ (resource_name, сумма в €, общий ли бюджет)."""
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.campaign_budget, campaign_budget.amount_micros, campaign_budget.explicitly_shared "
            f"FROM campaign WHERE campaign.id = {campaign_id}")):
        return r.campaign.campaign_budget, r.campaign_budget.amount_micros / 1e6, r.campaign_budget.explicitly_shared
    return None, None, None


# ---------- лог и состояние ----------

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


# ---------- источники заявок ----------

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


def calls_by_day(cfg, m, id_to_name):
    """Уникальные звонки Google Ads по (дата, кампания) за последние 10 дней — та же логика, что в мониторе
    (`sources.ringostat.get_calls_today`), но по дням. None — источник недоступен."""
    rs = cfg["ringostat"]
    today = date.today()
    google_keywords = list(rs.get("source_filter", {}).get("include_keywords", ["google", "dspl", "kms"]))
    if "performance_max" not in google_keywords:
        google_keywords.append("performance_max")
    excluded = set(rs.get("excluded_campaigns", []))
    regex = rs.get("campaign_id_regex", r"s_(\d+)_")
    kw = rs.get("pmax_keywords", ["pmax", "performance max"])
    resp = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": rs["date_from"], "to": today.strftime("%Y-%m-%d 23:59:59"),
                "fields": "calldate,caller,utm_source,utm_medium,utm_campaign,pool_name"},
        headers={"Content-Type": "application/json; charset=utf-8", "Auth-key": rs["auth_key"]}, timeout=180)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data:
        return {}
    df = pd.DataFrame(data)
    for c in ("utm_source", "utm_medium", "utm_campaign"):
        df[c] = df[c].fillna("")
    df["call_date"] = df["calldate"].apply(m._parse_local_date)
    df = df[df["call_date"].notna()].copy()
    df["date_only"] = df["call_date"].dt.date
    df["category"] = df.apply(
        lambda r: m.categorize_source(str(r["utm_source"]), str(r["utm_medium"]), google_keywords), axis=1)
    df.loc[df["utm_campaign"].isin(excluded), "category"] = "No Source"
    tracked = df[df["category"].isin(m.TRACKED_CATEGORIES)].copy()
    if tracked.empty:
        return {}
    cl = m._classify_calls(tracked)
    cl = cl[(cl["category"] == m.GOOGLE_ADS) & (cl["call_type"] == "unique")]
    cl = cl[cl["date_only"] >= today - timedelta(days=10)].copy()
    if cl.empty:
        return {}
    cl["camp"] = cl.apply(lambda r: m._resolve_campaign_name(r, id_to_name, UNRESOLVED, regex, kw, ""), axis=1)
    out = {}
    for (d, c), g in cl.groupby(["date_only", "camp"]):
        out[(d.isoformat(), c)] = len(g)
    return out


def leads_today(cfg, m_ringostat, m_supabase, id_to_name):
    """→ ({имя_кампании: формы}, формы_без_кампании). Ошибка источника не роняет цикл (пустой результат)."""
    leads_by, unattributed = {}, 0
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
    return leads_by, unattributed


def ads_history(ga, cid, campaign_ids, days=8):
    """Расход и формы (`form_submit_gtm`) по (id кампании, дата) за последние дни из Google Ads."""
    since = (date.today() - timedelta(days=days)).isoformat()
    until = date.today().isoformat()
    ids = ",".join(campaign_ids)
    cost, forms = {}, {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, segments.date, metrics.cost_micros FROM campaign "
            f"WHERE campaign.id IN ({ids}) AND segments.date BETWEEN '{since}' AND '{until}'")):
        cost[(str(r.campaign.id), r.segments.date)] = r.metrics.cost_micros / 1e6
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, segments.date, segments.conversion_action_name, metrics.all_conversions FROM campaign "
            f"WHERE campaign.id IN ({ids}) AND segments.date BETWEEN '{since}' AND '{until}' "
            "AND metrics.all_conversions > 0")):
        if r.segments.conversion_action_name == FORM_ACTION:
            k = (str(r.campaign.id), r.segments.date)
            forms[k] = forms.get(k, 0.0) + r.metrics.all_conversions
    return cost, forms


# ---------- вспомогательное ----------

def parse_map(items):
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        out[k.strip()] = float(v.replace(",", "."))
    return out


def parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def main():
    ap = argparse.ArgumentParser(description="Сторож по цене заявки + управление бюджетом (Ringostat + Supabase)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--target", action="append", required=True, metavar="ID=EUR",
                    help="целевая цена заявки по кампании, можно несколько раз: 24332178236=25")
    ap.add_argument("--grace", type=float, default=2.0, help="аванс на первую заявку в долях цели (по умолчанию 2.0)")
    ap.add_argument("--warn-share", type=float, default=0.9)
    ap.add_argument("--resume-share", type=float, default=0.85)
    ap.add_argument("--abs-mult", type=float, default=3.0, help="жёсткий предел от текущего дневного бюджета")
    ap.add_argument("--max-reenable", type=int, default=2)
    ap.add_argument("--pace-share", type=float, default=0.4, help="«темп»: рост расхода за окно ≥ доли бюджета при 0 новых заявок")
    ap.add_argument("--pace-min", type=float, default=30.0, help="окно «темпа», минут")
    ap.add_argument("--watch-min", type=float, default=30.0, help="сколько минут после паузы писать «инерцию»")
    ap.add_argument("--loop-min", type=float, help="повторять каждые N минут; без флага — одна проверка")
    # управление бюджетом
    ap.add_argument("--flex", action="store_true", help="включить управление бюджетом (дневной люфт и базовый шаг)")
    ap.add_argument("--allow-budget", action="store_true", help="разрешить реальные правки бюджета (нужен и --execute)")
    ap.add_argument("--base-budget", action="append", metavar="ID=EUR", help="базовый (стартовый) дневной бюджет")
    ap.add_argument("--max-budget", action="append", metavar="ID=EUR", help="потолок дневного бюджета")
    ap.add_argument("--step-pct", type=float, default=20.0, help="шаг роста базового бюджета, %%")
    ap.add_argument("--big-step-pct", type=float, default=35.0, help="большой шаг при большом запасе по цене, %%")
    ap.add_argument("--big-step-cpa-share", type=float, default=0.6, help="большой шаг, если цена заявки ≤ доли цели")
    ap.add_argument("--big-step-min-leads", type=float, default=5.0, help="и заявок в день в среднем не меньше")
    ap.add_argument("--constrained-share", type=float, default=0.8,
                    help="день подходит для роста, только если расход ≥ доли базового бюджета (упиралась в лимит)")
    ap.add_argument("--plan-daily", type=float, help="дневной план проекта, €: сумма базовых бюджетов под сторожем не выше")
    ap.add_argument("--efficient-days", type=int, default=3, help="сколько эффективных дней подряд для шага роста")
    ap.add_argument("--day-min-leads", type=int, default=2, help="минимум заявок за день, чтобы день считался эффективным")
    ap.add_argument("--flex-min-leads", type=int, default=3)
    ap.add_argument("--flex-cpa-share", type=float, default=0.8, help="люфт, если цена заявки ≤ доли цели")
    ap.add_argument("--flex-cost-share", type=float, default=0.85, help="люфт, если расход ≥ доли текущего бюджета")
    ap.add_argument("--flex-max-per-day", type=int, default=2)
    ap.add_argument("--restore-at", default="23:30", help="во сколько вернуть бюджет к базовому (ЧЧ:ММ)")
    ap.add_argument("--execute", action="store_true", help="реально ставить на паузу (без флага — dry-run)")
    ap.add_argument("--allow-reenable", action="store_true", help="разрешить автоматическое возобновление (нужен и --execute)")
    ap.add_argument("--telegram", action="store_true", help="слать события в Telegram чат монитора")
    ap.add_argument("--monitoring-dir", default=MONITORING_DIR)
    ap.add_argument("--monitoring-config", default=MONITORING_CFG)
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    targets = parse_map(args.target)
    base_arg = parse_map(args.base_budget)
    max_budget = parse_map(args.max_budget)
    restore_min = parse_hhmm(args.restore_at)
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    enums = client.enums.CampaignStatusEnum
    m_ringostat, m_supabase, m_telegram, cfg = load_monitoring(args.monitoring_dir, args.monitoring_config)
    state = load_state()
    budget_state = state.setdefault("_budget", {})

    def notify(text):
        if args.telegram:
            try:
                m_telegram.send_text(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"], text)
            except Exception as ex:
                print(f"  Telegram: ошибка {type(ex).__name__}")

    mode = ("БОЕВОЙ: пауза" + (" + возобновление" if args.allow_reenable else "")) if args.execute else "DRY-RUN"
    if args.flex:
        mode += ", бюджет: " + ("ПИШЕТ" if (args.execute and args.allow_budget) else "только план")
    print(f"=== сторож по цене заявки, {mode}; цели: {targets}; аванс {args.grace}, предупреждение {args.warn_share:.0%}, "
          f"возврат {args.resume_share:.0%}, предел {args.abs_mult}× бюджета, темп {args.pace_share:.0%}/{args.pace_min:g} мин ===")
    notify(f"🛡 Сторож по цене заявки запущен ({mode}). Цели заявки: {targets}, аванс {args.grace:g}, "
           f"проверка каждые {args.loop_min or 0:g} мин")

    calls_cache = {}
    while True:
        now0 = datetime.now()
        today = date.today().isoformat()
        try:
            id_to_name = all_campaign_names(ga, cid)
        except Exception as ex:
            print(f"{now0:%H:%M:%S} ошибка списка кампаний: {type(ex).__name__}")
            id_to_name = {}
        try:
            calls_map = calls_by_day(cfg, m_ringostat, id_to_name)
        except Exception as ex:
            print(f"  Ringostat: ошибка {type(ex).__name__}: {str(ex)[:100]} — берём последнее известное")
            calls_map = None
        if calls_map is not None:
            calls_cache = calls_map
        else:
            calls_map = calls_cache
        leads_by, unattributed = leads_today(cfg, m_ringostat, m_supabase, id_to_name)

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
                           "paused_by_guard": False, "no_resume": False, "flex_count": 0, "samples": []})
            name = s["name"]
            st["calls_max"] = max(st["calls_max"], calls_map.get((today, name), 0))
            st["leads_max"] = max(st["leads_max"], leads_by.get(name, 0))
            n = st["calls_max"] + st["leads_max"]
            cost, budget = s["cost"], s["budget"]
            allowance = (args.grace + n) * T
            share = cost / allowance if allowance else 0.0
            cpa_real = round(cost / n, 1) if n else ""
            status = s["status"]
            events = []
            inertia = ""
            paused_now = resumed_now = False

            # --- темп: рост расхода за окно без новых заявок
            pace_hit = False
            samples = st.setdefault("samples", [])
            samples.append([now.isoformat(timespec="seconds"), cost, n])
            samples[:] = [x for x in samples if (now - datetime.fromisoformat(x[0])).total_seconds() <= 3600]
            ref = None
            for x in samples:   # самая свежая точка не моложе окна
                if (now - datetime.fromisoformat(x[0])).total_seconds() >= args.pace_min * 60:
                    ref = x
            if ref and budget and n == ref[2] and cost - ref[1] >= args.pace_share * budget:
                pace_hit = True

            # --- пауза / возобновление по цене заявки
            if status == enums.ENABLED:
                if st.get("paused_by_guard"):
                    events.append("ручное включение после паузы сторожа")
                    st["paused_by_guard"] = False
                reason = None
                if budget and cost >= args.abs_mult * budget:
                    reason = "жёсткий предел"
                    st["no_resume"] = True
                    events.append(f"ПАУЗА жёсткий предел: расход {cost:.2f} ≥ {args.abs_mult}× бюджета {budget:.2f} (заявок {n})")
                elif cost >= allowance:
                    reason = "цена заявки"
                    events.append(f"ПАУЗА цена заявки: расход {cost:.2f} ≥ допустимого {allowance:.2f} "
                                  f"= ({args.grace:g}+{n})×{T:g}")
                elif pace_hit:
                    reason = "темп"
                    events.append(f"ПАУЗА темп: за {args.pace_min:g} мин расход +{cost - ref[1]:.2f} при {n} заявках "
                                  f"(бюджет {budget:.2f})")
                elif cost >= args.warn_share * allowance and not st["warned"]:
                    events.append(f"ПРЕДУПРЕЖДЕНИЕ: расход {cost:.2f} = {share:.0%} допустимого {allowance:.2f} (заявок {n})")
                    st["warned"] = True
                    notify(f"⚠️ {name}: расход {cost:.2f} € = {share:.0%} допустимого {allowance:.2f} € (заявок {n})")
                if reason:
                    if args.execute:
                        pause(client, cid, campaign_id)
                        st["paused_by_guard"] = True
                        st["paused_at"] = now.isoformat(timespec="seconds")
                        st["cost_at_pause"] = cost
                        st["n_at_pause"] = n
                        st["pause_reason"] = reason
                        paused_now = True
                        notify(f"⛔ {name}: ПАУЗА ({reason}). Расход {cost:.2f} €, заявок {n}, "
                               f"допустимо {allowance:.2f} €, цель {T:g} €")
                    else:
                        events[-1] += " (dry-run, не выполнено)"
            elif st.get("paused_by_guard"):
                t0 = datetime.fromisoformat(st["paused_at"])
                if (now - t0).total_seconds() / 60 <= args.watch_min:
                    inertia = round(cost - st.get("cost_at_pause", cost), 2)
                if (not st.get("no_resume") and st.get("n_at_pause", 0) < n and cost <= args.resume_share * allowance
                        and st["reenabled"] < args.max_reenable):
                    msg = (f"ВОЗОБНОВЛЕНИЕ: заявок стало {n} (было {st.get('n_at_pause')} при паузе), "
                           f"расход {cost:.2f} ≤ {args.resume_share:.0%} от допустимого {allowance:.2f}")
                    if args.execute and args.allow_reenable:
                        enable(client, cid, campaign_id)
                        st["paused_by_guard"] = False
                        st["reenabled"] += 1
                        st["warned"] = False
                        resumed_now = True
                        notify(f"✅ {name}: ВОЗОБНОВЛЕНА — поздние заявки (теперь {n}), расход {cost:.2f} €, "
                               f"допустимо {allowance:.2f} €")
                    else:
                        msg += " (dry-run или без --allow-reenable, не выполнено)"
                    events.append(msg)
            # иначе: на паузе по решению человека — не трогаем

            # --- бюджет
            if args.flex:
                try:
                    res, bud_now, shared = read_budget(ga, cid, campaign_id)
                    if res is None:
                        raise RuntimeError("бюджет не найден")
                    if shared:
                        events.append("бюджет общий для нескольких кампаний — управление пропущено")
                    else:
                        pb = budget_state.setdefault(campaign_id, {})
                        if campaign_id in base_arg:   # явно заданный базовый бюджет важнее сохранённого (бюджет могли поднять руками)
                            pb["base"] = base_arg[campaign_id]
                            pb["floor"] = base_arg[campaign_id]
                        pb.setdefault("floor", bud_now)
                        pb.setdefault("base", bud_now)
                        ceiling = max_budget.get(campaign_id, pb["base"])
                        can_write = args.execute and args.allow_budget

                        def apply_budget(value, why):
                            """Ставит бюджет (или только планирует). Возвращает True, если запись выполнена."""
                            value = int(round(value))
                            msg = f"БЮДЖЕТ {bud_now:g} → {value} €: {why}"
                            if can_write:
                                set_budget(client, cid, res, value)
                                events.append(msg)
                                notify(f"💶 {name}: {msg}")
                                return True
                            events.append(msg + " (план, не выполнено)")
                            return False

                        # 1) утренний шаг: откат висящего люфта, базовый шаг вверх/вниз по истории
                        if pb.get("day_done") != today:
                            if pb.get("flexed") and bud_now != pb["base"]:
                                if apply_budget(pb["base"], "откат люфта прошлого дня к базовому"):
                                    bud_now = pb["base"]
                            pb["flexed"] = False
                            cost_h, forms_h = ads_history(ga, cid, [campaign_id])
                            streak, last_bad = 0, False
                            days = [(date.today() - timedelta(days=i)).isoformat() for i in range(1, 8)]
                            hist = []
                            for d in days:
                                c = cost_h.get((campaign_id, d), 0.0)
                                nn = calls_map.get((d, name), 0) + int(round(forms_h.get((campaign_id, d), 0.0)))
                                hist.append((d, c, nn))
                            changed_on = pb.get("changed_on", "")
                            streak_days = []
                            for d, c, nn in hist:
                                if d < changed_on:
                                    break
                                # подходящий день: цена ≤ цели И кампания упиралась в бюджет (иначе подъём лишь добавляет риск)
                                if (c > 0 and nn >= args.day_min_leads and c / nn <= T
                                        and c >= args.constrained_share * pb["base"]):
                                    streak += 1
                                    streak_days.append((c, nn))
                                else:
                                    break
                            y = hist[0]
                            last_bad = (y[1] > 0 and y[1] > (args.grace + y[2]) * T)
                            new_base = None
                            if streak >= args.efficient_days:
                                window = streak_days[:args.efficient_days]
                                sum_c = sum(x[0] for x in window)
                                sum_n = sum(x[1] for x in window)
                                avg_cpa = sum_c / sum_n if sum_n else 1e9
                                avg_leads = sum_n / len(window)
                                big = avg_cpa <= args.big_step_cpa_share * T and avg_leads >= args.big_step_min_leads
                                step = args.big_step_pct if big else args.step_pct
                                cand = min(ceiling, math.ceil(pb["base"] * (1 + step / 100)))
                                if args.plan_daily:   # сумма базовых бюджетов под сторожем не выше дневного плана
                                    others = sum(v.get("base", 0) for k, v in budget_state.items()
                                                 if k != campaign_id and k in targets)
                                    cand = min(cand, max(pb["base"], math.floor(args.plan_daily - others)))
                                if cand > pb["base"]:
                                    new_base = cand
                                    why = (f"{streak} дня подряд цена ≤ {T:g} € и расход ≥ {args.constrained_share:.0%} бюджета, "
                                           f"шаг +{step:g}%" + (" (большой запас по цене)" if big else ""))
                                else:
                                    events.append(f"рост бюджета не выполнен: потолок {ceiling:g} € или дневной план "
                                                  f"{args.plan_daily or 0:g} € (сумма базовых других кампаний)")
                            elif last_bad and pb["base"] > pb["floor"]:
                                new_base = max(pb["floor"], math.floor(pb["base"] / (1 + args.step_pct / 100)))
                                why = f"вчера расход {y[1]:.0f} € при {y[2]} заявках — выше допустимого"
                            if new_base is not None and new_base != pb["base"]:
                                if apply_budget(new_base, "базовый шаг: " + why):
                                    pb["base"] = new_base
                                    pb["changed_on"] = today
                                    bud_now = new_base
                            else:
                                events.append(f"базовый бюджет {pb['base']:g} € без изменений (подходящих дней подряд: "
                                              f"{streak} из {args.efficient_days}; нужно: цена ≤ цели и расход ≥ "
                                              f"{args.constrained_share:.0%} бюджета)")
                            pb["day_done"] = today

                        # 2) дневной люфт: эффективна и упирается в бюджет → поднять выше факта
                        enabled_now = (status == enums.ENABLED and not paused_now) or resumed_now
                        if (enabled_now and n >= args.flex_min_leads and cost / n <= args.flex_cpa_share * T
                                and cost >= args.flex_cost_share * bud_now and st["flex_count"] < args.flex_max_per_day
                                and bud_now < ceiling):
                            target = min(ceiling, math.ceil(max(cost * 1.3, bud_now * 1.25)))
                            if target > bud_now:
                                if apply_budget(target, f"люфт: заявок {n}, цена {cost / n:.1f} € ≤ {args.flex_cpa_share:.0%} "
                                                        f"цели, расход {cost:.1f} ≥ {args.flex_cost_share:.0%} бюджета"):
                                    pb["flexed"] = True
                                    st["flex_count"] += 1
                                    bud_now = target

                        # 3) вечерний возврат люфта
                        if pb.get("flexed") and now.hour * 60 + now.minute >= restore_min and bud_now != pb["base"]:
                            if apply_budget(pb["base"], "вечерний возврат к базовому"):
                                pb["flexed"] = False
                                bud_now = pb["base"]
                except Exception as ex:
                    events.append(f"бюджет: ошибка {type(ex).__name__}: {str(ex)[:120]}")

            event = "; ".join(events)
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
