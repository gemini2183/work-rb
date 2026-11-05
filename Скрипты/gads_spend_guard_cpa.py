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
   за --pace-min минут расход вырос на ≥ --pace-share бюджета, а заявок за сегодня 0 → пауза (с 2026-11-04; раньше —
   «в окне не прибавилось»).
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

# консоль Windows в cp1251 не печатает «×»/«≤» из сообщений — 14.10 из-за этого процесс упал на старте
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MONITORING_DIR = r"E:\PythonProjects\RedBird\monitoring scripts\monitoring"
MONITORING_CFG = MONITORING_DIR + r"\config\profimet.yaml"
CUR = "€"   # подпись валюты в сообщениях: из guard_config.yaml (`currency`) или из валюты аккаунта (PLN → zł)
CURRENCY_LABELS = {"PLN": "zł", "EUR": "€", "USD": "$", "UAH": "₴", "GBP": "£"}
CLIENTS_DIR = Path(__file__).resolve().parent.parent / "Клиенты"
STATS = CLIENTS_DIR / "ProfiMet" / "Статистика"
LOG = STATS / "gads_spend_guard_cpa_log.csv"
STATE = STATS / "gads_spend_guard_state.json"
_PLAN_MODULE = None   # campaign_analyzer/sources.py (read_plan), грузится при первом чтении плана
UNRESOLVED = "__unresolved_pmax__"   # чтобы UTM без ID и имени не склеивались в «первую попавшуюся PMax»
FORM_ACTION = "form_submit_gtm"
AD_CALL_ACTIONS = []   # названия конверсий «звонок по номеру из объявления» (Google Ads; Ringostat их по кампании не определяет)

LOG_HEADER = ["time", "campaign_id", "name", "status", "budget", "cost_today", "target_cpa", "calls", "leads",
              "n", "allowance", "cost_share_of_allowance", "cpa_real", "event", "inertia_after_pause"]
INTERV = STATS / "gads_spend_guard_interventions.csv"   # журнал вмешательств не сторожем (бюджет, статус, стратегия, расписание)
INTERV_HEADER = ["time", "campaign_id", "name", "what", "was", "now", "who"]
SOURCE_ALERT_MIN = 15.0   # источник заявок недоступен дольше N минут → предупреждение в Telegram
LEAD_JUMP_N = 3           # скачок заявок: прибавилось ≥ N ...
LEAD_JUMP_MIN = 10.0      # ... за ≤ M минут → предупреждение (возможен спам/дубли)


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


DRY_MULT = 3.0            # «расход без заявок подряд»: пауза, когда расход с последней заявки (через дни) ≥ N × цели; exp(−3) ≈ 5% ложной паузы у кампании «на цели»
ZERO_CAP_MAX_FALSE = 0.10   # правило «N × бюджет при нуле заявок» включается, только если exp(−бюджет/цена заявки) ≤ 10%
HOLD_STATES = {"hold_rebuild", "hold_off", "staging", "retired"}
STATE_RU = {"hold_rebuild": "на пересборке", "hold_off": "пауза «ждём»", "staging": "создана на паузе, включение отдельным «да»",
            "retired": "снята с работы"}


def load_passport(path):
    """Паспорт кампаний клиента (Клиенты/<Имя>/Паспорт_кампаний.yaml): пишут люди и я, сторож ТОЛЬКО читает.
    Любая ошибка чтения — пустой паспорт (сторож не должен падать из-за файла)."""
    try:
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        camps = {str(k): (v or {}) for k, v in (d.get("campaigns") or {}).items()}
        return {"campaigns": camps, "agreed": list(d.get("agreed_changes") or [])}
    except Exception as ex:
        print(f"  паспорт кампаний не прочитан ({type(ex).__name__}: {str(ex)[:80]}), работаю без него")
        return {"campaigns": {}, "agreed": []}


def hold_text(pp):
    parts = [STATE_RU.get(pp.get("state"), str(pp.get("state")))]
    if pp.get("why"):
        parts.append(str(pp["why"]))
    if pp.get("to_enable_when"):
        parts.append("до включения: " + "; ".join(str(x) for x in pp["to_enable_when"]))
    if pp.get("review_by"):
        parts.append(f"пересмотр {pp['review_by']}")
    return ", ".join(parts)


def dry_replay(campaign_id, today):
    """Расход с последней заявки по ЗАВЕРШЁННЫМ дням (до today) по боевому логу сторожа. Нет лога — 0.
    День с заявками обнуляет счёт, день без заявок прибавляет расход дня (максимум cost_today за день)."""
    p = STATS / "gads_spend_guard_cpa_log.csv"
    try:
        import csv as _csv
        by_day = {}
        with open(p, encoding="utf-8", newline="") as f:
            for r in _csv.DictReader(f):
                if r.get("campaign_id") != str(campaign_id) or not r.get("cost_today"):
                    continue
                d_ = r["time"][:10]
                if d_ >= today:
                    continue
                c_, n_ = float(r["cost_today"]), float(r.get("n") or 0)
                o = by_day.setdefault(d_, [0.0, 0.0])
                o[0], o[1] = max(o[0], c_), max(o[1], n_)
        carry = 0.0
        for d_ in sorted(by_day):
            carry = 0.0 if by_day[d_][1] > 0 else carry + by_day[d_][0]
        return round(carry, 2)
    except Exception:
        return 0.0


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
                "fields": "calldate,caller,call_type,utm_source,utm_medium,utm_campaign,pool_name"},
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
    # Как в мониторе после 2026-10-21 (sources.ringostat.get_calls_today): только входящие, цепочка окон по chain_key
    df = df[df["call_type"] == "in"].copy()
    if rs.get("unique_scheme", "channels") == "clients":
        df["client"] = df.apply(m._determine_client, axis=1)
        chain = df[df["client"].notna()].copy()
        chain["chain_key"] = chain["client"] + "|" + chain["caller"].astype(str)
    else:
        chain = df
        if not rs.get("count_other_channels", False):
            chain = df[df["category"].isin(m.TRACKED_CATEGORIES)].copy()
        chain["chain_key"] = chain["caller"].astype(str)
    if chain[chain["category"] == m.GOOGLE_ADS].empty:
        return {}
    cl = m._mark_new_calls(chain, int(rs.get("unique_window_days", 60)))
    cl = cl[(cl["category"] == m.GOOGLE_ADS) & (cl["call_type_unique"] == "unique")]
    cl = cl[cl["date_only"] >= today - timedelta(days=10)].copy()
    if cl.empty:
        return {}
    static = rs.get("pmax_static_name", "")
    cl["camp"] = cl.apply(lambda r: m._resolve_campaign_name(r, id_to_name, UNRESOLVED, regex, kw, static), axis=1)
    out = {}
    for (d, c), g in cl.groupby(["date_only", "camp"]):
        out[(d.isoformat(), c)] = len(g)
    return out


def leads_today(cfg, m_ringostat, m_supabase, id_to_name):
    """→ ({имя_кампании: формы}, формы_без_кампании, источник_доступен). Ошибка источника не роняет цикл (пустой результат)."""
    leads_by, unattributed, ok = {}, 0, True
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
        ok = False
        print(f"  Supabase: ошибка {type(ex).__name__}: {str(ex)[:100]} — берём последнее известное")
    return leads_by, unattributed, ok


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
        if r.segments.conversion_action_name == FORM_ACTION or r.segments.conversion_action_name in AD_CALL_ACTIONS:
            k = (str(r.campaign.id), r.segments.date)
            forms[k] = forms.get(k, 0.0) + r.metrics.all_conversions
    return cost, forms


def ad_calls_today(ga, cid, campaign_ids):
    """{id кампании: звонки по номеру из объявлений сегодня} — только из Google Ads (в Ringostat у них нет кампании)."""
    out = {}
    if not AD_CALL_ACTIONS or not campaign_ids:
        return out
    names = ",".join("'" + n.replace("'", "\\'") + "'" for n in AD_CALL_ACTIONS)
    ids = ",".join(campaign_ids)
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, segments.conversion_action_name, metrics.all_conversions FROM campaign "
            f"WHERE campaign.id IN ({ids}) AND segments.date DURING TODAY "
            f"AND segments.conversion_action_name IN ({names})")):
        out[str(r.campaign.id)] = out.get(str(r.campaign.id), 0.0) + r.metrics.all_conversions
    return out


# ---------- вмешательства не сторожем и незнакомые кампании (решение пользователя 2026-11-04) ----------

def log_intervention(row):
    INTERV.parent.mkdir(parents=True, exist_ok=True)
    new = not INTERV.exists()
    with open(INTERV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(INTERV_HEADER)
        w.writerow(row)


def _enum_label(client, enum_name, value):
    """Имя значения enum по номеру (в результатах поиска enum приходит числом)."""
    try:
        return getattr(client.enums, enum_name).DESCRIPTOR.enum_types[0].values_by_number[int(value)].name
    except Exception:
        return str(value)


def read_settings(client, ga, cid, ids):
    """→ ({id: 'СТРАТЕГИЯ, tCPA X'}, {id: tCPA числом или 0}) — стратегия ставок и целевая цена кампании. Строка нужна для
    обнаружения правок не сторожем, число — для целей `target: auto`. Общие (портфельные) стратегии не читаются: там tCPA = 0."""
    out, tcpa = {}, {}
    if not ids:
        return out, tcpa
    q = ("SELECT campaign.id, campaign.bidding_strategy_type, campaign.target_cpa.target_cpa_micros, "
         "campaign.maximize_conversions.target_cpa_micros, campaign.target_roas.target_roas, "
         "campaign.maximize_conversion_value.target_roas FROM campaign WHERE campaign.id IN (" + ",".join(ids) + ")")
    for r in ga.search(customer_id=cid, query=q):
        c = r.campaign
        parts = [_enum_label(client, "BiddingStrategyTypeEnum", c.bidding_strategy_type)]
        for nm, v in (("tCPA", c.target_cpa.target_cpa_micros / 1e6), ("tCPA", c.maximize_conversions.target_cpa_micros / 1e6),
                      ("tROAS", c.target_roas.target_roas), ("tROAS", c.maximize_conversion_value.target_roas)):
            if v:
                parts.append(f"{nm} {v:g}")
        out[str(c.id)] = ", ".join(parts)
        tcpa[str(c.id)] = (c.target_cpa.target_cpa_micros or c.maximize_conversions.target_cpa_micros) / 1e6
    return out, tcpa


def read_schedule(ga, cid, ids):
    """{id кампании: 'отсортированная строка интервалов расписания'} (пусто = без расписания)."""
    if not ids:
        return {}
    out = {i: [] for i in ids}
    q = ("SELECT campaign.id, campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
         "campaign_criterion.ad_schedule.start_minute, campaign_criterion.ad_schedule.end_hour, "
         "campaign_criterion.ad_schedule.end_minute, campaign_criterion.bid_modifier FROM campaign_criterion "
         "WHERE campaign_criterion.type = AD_SCHEDULE AND campaign.id IN (" + ",".join(ids) + ")")
    for r in ga.search(customer_id=cid, query=q):
        a = r.campaign_criterion.ad_schedule
        out.setdefault(str(r.campaign.id), []).append(
            f"{int(a.day_of_week)}/{a.start_hour}:{int(a.start_minute)}-{a.end_hour}:{int(a.end_minute)}x{r.campaign_criterion.bid_modifier:g}")
    return {k: "; ".join(sorted(v)) for k, v in out.items()}


def who_changed(client, ga, cid, campaign_id, minutes=180):
    """Кто последним менял кампанию (или её бюджет) за последние минуты: история изменений Google Ads (change_event);
    она отстаёт на минуты, поэтому пустой ответ не значит «никто». → короткая строка или ''."""
    try:
        since = datetime.now() - timedelta(minutes=minutes)
        q = ("SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, change_event.campaign "
             f"FROM change_event WHERE change_event.change_date_time >= '{since:%Y-%m-%d %H:%M:%S}' "
             f"AND change_event.change_date_time <= '{datetime.now() + timedelta(minutes=10):%Y-%m-%d %H:%M:%S}' "
             "ORDER BY change_event.change_date_time DESC LIMIT 500")
        for r in ga.search(customer_id=cid, query=q):
            ce = r.change_event
            if str(ce.campaign).endswith(f"/campaigns/{campaign_id}"):
                kind = _enum_label(client, "ChangeClientTypeEnum", ce.client_type)
                return f"{ce.user_email or 'без пользователя'} через {kind}, {str(ce.change_date_time)[11:16]}"
    except Exception as ex:
        return f"история изменений не прочитана ({type(ex).__name__})"
    return ""


def list_enabled(client, ga, cid):
    """{id: {name, budget, shared}} — все ВКЛЮЧЁННЫЕ кампании аккаунта (кроме Local Services: у них свой бюджет и модель)."""
    skip = client.enums.AdvertisingChannelTypeEnum.LOCAL_SERVICES
    out = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.advertising_channel_type, campaign_budget.amount_micros, "
            "campaign_budget.explicitly_shared FROM campaign WHERE campaign.status = 'ENABLED'")):
        if r.campaign.advertising_channel_type == skip:
            continue
        out[str(r.campaign.id)] = {"name": r.campaign.name, "budget": r.campaign_budget.amount_micros / 1e6,
                                   "shared": r.campaign_budget.explicitly_shared}
    return out


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


def read_plan_cpa(client_dir, row=None):
    """План месяца из «Цели2 Адвайта» (analysis_config.yaml клиента). row — имя строки плана; без него — client_name из конфига.
    → {tab, cpa, leads, budget}. Правило пользователя 2026-11-04: цель заявки по умолчанию — из плана месяца, число в конфиге —
    только осознанное исключение (расчёт от цены продажи и т.п.)."""
    # модуль грузится по пути под своим именем: имя `sources` занято пакетом проекта мониторинга (Ringostat/Supabase)
    global _PLAN_MODULE
    if _PLAN_MODULE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("campaign_analyzer_sources",
                                                      str(Path(__file__).resolve().parent / "campaign_analyzer" / "sources.py"))
        _PLAN_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PLAN_MODULE)
    read_plan = _PLAN_MODULE.read_plan
    acfg = yaml.safe_load((Path(client_dir) / "analysis_config.yaml").read_text(encoding="utf-8"))
    if row:
        acfg["plan"] = dict(acfg["plan"], client_name=row)
    return read_plan(acfg, pd.Timestamp(date.today()))


def load_guard_config(path):
    """Читает `Клиенты/<Имя>/guard_config.yaml` и приводит к значениям по умолчанию для аргументов командной строки.
    Флаги командной строки всегда важнее файла. Файл НЕ содержит `execute` — боевой режим включается только флагом.
    Возвращает (defaults для argparse, доп. настройки по кампаниям, описание кампаний для печати)."""
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    client_dir = Path(path).resolve().parent
    camps = cfg.get("campaigns") or []
    plan_cache = {}   # имя строки плана (None = по умолчанию из analysis_config.yaml) -> план

    def plan_for(row):
        if row not in plan_cache:
            plan_cache[row] = read_plan_cpa(client_dir, row)
        return plan_cache[row]
    plan_ids = {}     # id кампании -> имя строки плана: цель берётся из плана и обновляется раз в сутки
    auto_ids = {}     # id кампании -> строка плана: цель = tCPA кампании, а если его нет — план
    plan = None
    targets, bases, maxes, flex_ids = [], [], [], []
    hard_mult_by, total_limit_by, since_by, rows = {}, {}, {}, []
    zero_cap_by = {}
    for c in camps:
        cid_ = str(c["id"])
        t = c.get("target")
        if t is None or str(t).strip().lower() in ("auto", "plan"):
            # auto (и по умолчанию): tCPA кампании из кабинета, если выставлен, иначе цель из плана; plan: всегда из плана
            plan_ids[cid_] = c.get("plan_row")
            if str(t).strip().lower() != "plan":
                auto_ids[cid_] = c.get("plan_row")
            plan = plan_for(c.get("plan_row"))
            t = plan["cpa"]
        else:
            t = float(t)
        targets.append(f"{cid_}={t:g}")
        control = bool(c.get("budget_control", False))
        base = c.get("base_budget")
        if control:
            flex_ids.append(cid_)
            base = 2 * t if str(base).strip().lower() == "auto" else float(base)
            mx = float(c.get("max_budget", base))
            bases.append(f"{cid_}={base:g}")
            maxes.append(f"{cid_}={mx:g}")
        if c.get("hard_mult") is not None:
            hard_mult_by[cid_] = float(c["hard_mult"])
        if c.get("zero_cap") is not None:   # пауза при расходе ≥ N × бюджета, только пока заявок за день 0
            zero_cap_by[cid_] = float(c["zero_cap"])
        if c.get("total_limit") is not None:
            total_limit_by[cid_] = float(c["total_limit"])
            since_by[cid_] = str(c.get("since") or date.today().replace(day=1).isoformat())
        rows.append((cid_, c.get("name", "") + ((" [авто: tCPA кампании или план]" if cid_ in auto_ids else " [план]" if cid_ in plan_ids else " [вручную]")), t, control, base if control else None,
                     float(c.get("max_budget", base)) if control else None,
                     hard_mult_by.get(cid_), total_limit_by.get(cid_), since_by.get(cid_)))
    defaults = {"customer_id": str(cfg.get("customer_id", "")) or None,
                "target": targets or None,
                "base_budget": bases or None,
                "max_budget": maxes or None,
                "flex": bool(flex_ids),
                "allow_budget": bool(cfg.get("allow_budget", False)),
                "allow_reenable": bool(cfg.get("allow_reenable", False)),
                "morning_resume": bool(cfg.get("morning_resume", False)),
                "telegram": bool(cfg.get("telegram", False))}
    for k_cfg, k_arg in (("grace", "grace"), ("plan_daily", "plan_daily"), ("loop_min", "loop_min"),
                         ("heartbeat_min", "heartbeat_min"), ("restore_at", "restore_at"),
                         ("pace_share", "pace_share"), ("pace_min", "pace_min"), ("abs_mult", "abs_mult"),
                         ("pace_min_allow_share", "pace_min_allow_share"), ("morning_resume_at", "morning_resume_at")):
        if cfg.get(k_cfg) is not None:
            defaults[k_arg] = cfg[k_cfg]
    if cfg.get("monitoring_config"):
        defaults["monitoring_config"] = str(Path(MONITORING_DIR) / "config" / cfg["monitoring_config"])
    extra = {"flex_ids": set(flex_ids), "hard_mult_by": hard_mult_by, "total_limit_by": total_limit_by,
             "since_by": since_by, "stats": client_dir / "Статистика", "form_action": cfg.get("form_action", FORM_ACTION),
             "ad_call_actions": list(cfg.get("ad_call_actions") or []),
             "plan": plan, "currency": cfg.get("currency"),
             # незнакомые включённые кампании: берутся под минимальную защиту с этой целью заявки (нет ключа — только предупреждение)
             "default_is_plan": str(cfg.get("default_target", "")).strip().lower() == "plan",
             "default_plan_row": cfg.get("default_plan_row"),
             "plan_ids": plan_ids, "auto_ids": auto_ids, "client_dir": client_dir,
             "plan_by_row": {k: v["cpa"] for k, v in plan_cache.items()},
             "default_target": (None if cfg.get("default_target") is None else
                                (plan_for(cfg.get("default_plan_row"))["cpa"]
                                 if str(cfg["default_target"]).strip().lower() == "plan" else float(cfg["default_target"]))),
             "unmanaged_ok": {str(x) for x in (cfg.get("unmanaged_ok") or [])},   # id кампаний, сознательно вне охраны (напр. Brand)
             "zero_cap_by": zero_cap_by,
             "dry_mult": float(cfg.get("dry_mult", DRY_MULT)),   # 0 — правило выключено
             "source_alert_min": float(cfg.get("source_alert_min", SOURCE_ALERT_MIN)),
             "lead_jump_n": int(cfg.get("lead_jump_n", LEAD_JUMP_N)),
             "lead_jump_min": float(cfg.get("lead_jump_min", LEAD_JUMP_MIN))}
    return defaults, extra, rows


def main():
    global STATS, LOG, STATE, INTERV, FORM_ACTION, AD_CALL_ACTIONS, CUR
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--client")
    pre.add_argument("--config")
    known, _ = pre.parse_known_args()
    cfg_path = known.config or (str(CLIENTS_DIR / known.client / "guard_config.yaml") if known.client else None)
    cfg_defaults, extra, cfg_rows = {}, {"flex_ids": None, "hard_mult_by": {}, "total_limit_by": {}, "since_by": {},
                                         "stats": None, "form_action": FORM_ACTION, "ad_call_actions": [], "plan": None,
                                         "currency": None, "default_target": None, "default_is_plan": False, "default_plan_row": None,
                                         "plan_ids": {}, "auto_ids": {}, "plan_by_row": {}, "client_dir": None, "unmanaged_ok": set(), "zero_cap_by": {},
                                         "source_alert_min": SOURCE_ALERT_MIN, "lead_jump_n": LEAD_JUMP_N,
                                         "lead_jump_min": LEAD_JUMP_MIN}, []
    if cfg_path:
        cfg_defaults, extra, cfg_rows = load_guard_config(cfg_path)

    ap = argparse.ArgumentParser(description="Сторож по цене заявки + управление бюджетом (Ringostat + Supabase)")
    ap.add_argument("--client", help="имя папки клиента: настройки берутся из Клиенты/<Имя>/guard_config.yaml "
                                     "(флаги командной строки важнее файла)")
    ap.add_argument("--config", help="путь к guard_config.yaml, если не в стандартном месте")
    ap.add_argument("--print-config", action="store_true", help="показать итоговые правила по кампаниям и выйти (без API)")
    ap.add_argument("--once", action="store_true", help="одна проверка и выход (игнорирует loop_min из конфига)")
    ap.add_argument("--heartbeat-min", type=float, default=0.0,
                    help="раз в N минут слать в Telegram «сторож жив» (0 — выключено); тишина = процесс не работает")
    ap.add_argument("--customer-id")
    ap.add_argument("--target", action="append", metavar="ID=EUR",
                    help="целевая цена заявки по кампании, можно несколько раз: 24332178236=25")
    ap.add_argument("--grace", type=float, default=2.0, help="аванс на первую заявку в долях цели (по умолчанию 2.0)")
    ap.add_argument("--warn-share", type=float, default=0.9)
    ap.add_argument("--resume-share", type=float, default=0.85)
    ap.add_argument("--abs-mult", type=float, default=3.0, help="жёсткий предел от текущего дневного бюджета")
    ap.add_argument("--max-reenable", type=int, default=2)
    ap.add_argument("--pace-share", type=float, default=0.4, help="«темп»: рост расхода за окно ≥ доли бюджета при 0 новых заявок")
    ap.add_argument("--pace-min", type=float, default=30.0, help="окно «темпа», минут")
    ap.add_argument("--pace-min-allow-share", type=float, default=0.0,
                    help="«темп» срабатывает, только если расход дня уже ≥ этой доли допустимого (0 — как раньше). "
                         "23.10 ExpertAgro: пауза при 43 из 330 zł и 1 заявке из-за бюджета 50 zł")
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
    ap.add_argument("--idle-share", type=float, default=0.2,
                    help="день с расходом меньше доли базового бюджета (выходной, пауза, пара кликов) пропускается при подсчёте "
                         "дней подряд: не засчитывается и серию не рвёт (решение пользователя 2026-10-29)")
    ap.add_argument("--plan-daily", type=float, help="дневной план проекта, €: сумма базовых бюджетов под сторожем не выше")
    ap.add_argument("--efficient-days", type=int, default=3, help="сколько эффективных дней подряд для шага роста")
    ap.add_argument("--day-min-leads", type=int, default=2, help="минимум заявок за день, чтобы день считался эффективным")
    ap.add_argument("--flex-min-leads", type=int, default=3)
    ap.add_argument("--flex-cpa-share", type=float, default=1.0,
                    help="люфт, если цена заявки ≤ доли цели (1.0 = «эффективно» = цена в цели; решение пользователя 2026-10-12)")
    ap.add_argument("--flex-cost-share", type=float, default=0.85, help="люфт, если расход ≥ доли текущего бюджета")
    ap.add_argument("--flex-max-per-day", type=int, default=2)
    ap.add_argument("--restore-at", default="23:30", help="во сколько вернуть бюджет к базовому (ЧЧ:ММ)")
    ap.add_argument("--execute", action="store_true", help="реально ставить на паузу (без флага — dry-run)")
    ap.add_argument("--allow-reenable", action="store_true", help="разрешить автоматическое возобновление (нужен и --execute)")
    ap.add_argument("--morning-resume", action="store_true",
                    help="утром следующего дня включать кампании, которые сторож поставил на паузу вчера по цене заявки или «темпу» "
                         "(решение пользователя 2026-11-04; нужен и --execute); после второй такой паузы за 3 дня — не включает")
    ap.add_argument("--morning-resume-at", default="07:30", help="не раньше какого времени (ЧЧ:ММ, часы компьютера) включать утром")
    ap.add_argument("--telegram", action="store_true", help="слать события в Telegram чат монитора")
    ap.add_argument("--monitoring-dir", default=MONITORING_DIR)
    ap.add_argument("--monitoring-config", default=MONITORING_CFG)
    ap.set_defaults(**{k: v for k, v in cfg_defaults.items() if v is not None})
    args = ap.parse_args()
    if not args.customer_id or not args.target:
        ap.error("нужны --customer-id и хотя бы один --target (или --client с guard_config.yaml)")
    if args.once:
        args.loop_min = 0
    if extra["stats"]:
        STATS = extra["stats"]
    FORM_ACTION = extra["form_action"]
    if extra.get("currency"):
        CUR = str(extra["currency"])
    AD_CALL_ACTIONS = extra["ad_call_actions"]
    # режим «только план» пишет в ОТДЕЛЬНЫЕ файлы: боевой процесс и пробный прогон не должны делить состояние
    suffix = "" if args.execute else "_plan"
    LOG = STATS / f"gads_spend_guard_cpa_log{suffix}.csv"
    STATE = STATS / f"gads_spend_guard_state{suffix}.json"
    INTERV = STATS / f"gads_spend_guard_interventions{suffix}.csv"
    tg_explicit = "--telegram" in sys.argv

    cid = args.customer_id.replace("-", "").strip()
    targets = parse_map(args.target)
    base_arg = parse_map(args.base_budget)
    max_budget = parse_map(args.max_budget)
    restore_min = parse_hhmm(args.restore_at)
    flex_ids = extra["flex_ids"] if extra["flex_ids"] is not None else set(targets)
    hard_mult_by, total_limit_by, since_by = extra["hard_mult_by"], extra["total_limit_by"], extra["since_by"]
    zero_cap_by = extra["zero_cap_by"]
    default_target, unmanaged_ok = extra["default_target"], extra["unmanaged_ok"]
    plan_default_by_row = dict(extra["plan_by_row"])   # строка плана (None = по умолчанию) -> цена заявки

    if args.print_config:
        print(f"клиент: {args.client or '(без конфига)'} | аккаунт {cid} | файлы: {LOG.name}, {STATE.name}")
        print(f"режим: {'БОЕВОЙ' if args.execute else 'план'} | возобновление: {args.allow_reenable} | "
              f"запись бюджета: {args.allow_budget} | Telegram: {args.telegram} | пульс: {args.heartbeat_min:g} мин | "
              f"аванс {args.grace:g}, предел {args.abs_mult:g}× бюджета, дневной план {args.plan_daily or '—'}")
        if extra.get("plan"):
            print(f"план месяца ({extra['plan']['tab']}): заявок {extra['plan']['leads']:g}, CPA {extra['plan']['cpa']:g}, "
                  f"бюджет {extra['plan']['budget']:g}")
        print(f"{'ID':<12}{'имя':<30}{'цель':>7}{'бюджет':>10}{'потолок':>9}{'x бюджета':>11}   {'лимит всего'}")
        for r in cfg_rows or [(i, "", t, i in flex_ids, base_arg.get(i), max_budget.get(i), None, None, None)
                              for i, t in targets.items()]:
            cid_, nm, t, ctl, base, mx, hm, tl, since = r
            print(f"{cid_:<12}{nm:<30}{t:>7g}{(f'{base:g}' if ctl else 'без упр.'):>10}"
                  f"{(f'{mx:g}' if ctl else '—'):>9}{(f'{hm:g}' if hm else f'{args.abs_mult:g}'):>11}"
                  f"   {(f'{tl:g} {CUR} с {since}' if tl else '—')}")
        return
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    enums = client.enums.CampaignStatusEnum
    if not extra.get("currency"):   # валюта аккаунта, а не вшитое «€» (23.10: ExpertAgro в PLN получал сообщения в евро)
        try:
            code = next(iter(ga.search(customer_id=cid, query="SELECT customer.currency_code FROM customer"))).customer.currency_code
            CUR = CURRENCY_LABELS.get(code, code)
        except Exception as ex:
            print(f"  валюта аккаунта не прочитана ({type(ex).__name__}), подпись по умолчанию: {CUR}")
    m_ringostat, m_supabase, m_telegram, cfg = load_monitoring(args.monitoring_dir, args.monitoring_config)
    state = load_state()
    budget_state = state.setdefault("_budget", {})
    pending_resume = state.setdefault("_pending_resume", {})   # пауза сторожа по цене/«темпу», ждёт утреннего возобновления
    pause_history = state.setdefault("_pause_history", {})     # история пауз сторожа: [{date, reason}] по кампании (последние 10)
    resume_min = parse_hhmm(args.morning_resume_at)
    passport_path = (extra["client_dir"] / "Паспорт_кампаний.yaml") if extra.get("client_dir") else None
    passport_cache = {}

    def notify(text):
        # в режиме «только план» сообщения уходят, только если --telegram указан явно (проверка канала)
        if args.telegram and (args.execute or tg_explicit):
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

    # кампании, взятые под временную защиту как незнакомые (см. ниже), переживают перезапуск процесса
    adopted = state.setdefault("_adopted", {})
    for aid_, ainfo in adopted.items():
        if aid_ not in targets:
            targets[aid_] = float(ainfo["T"])
            zero_cap_by.setdefault(aid_, 1.0)
    sources = state.setdefault("_sources", {})
    seen_all = state.setdefault("_seen", {})   # последнее известное состояние кампании: бюджет, статус, стратегия, расписание
    unknown_warned = state.setdefault("_unknown_warned", {})

    calls_cache = {}
    auto_inited = False   # первое чтение tCPA после старта только выставляет цели молча, сообщения — о настоящих сменах
    last_hb = time.time()
    while True:
        now0 = datetime.now()
        today = date.today().isoformat()
        recovered = []
        # цели «по плану» перечитываются раз в сутки: в начале месяца лист «Цели2» меняется, перезапуск не нужен
        if (extra["plan_ids"] or extra["default_is_plan"]) and state.get("_plan_day") != today:
            state["_plan_day"] = today
            try:
                cache_ = {}
                for cid_p, row_p in extra["plan_ids"].items():
                    if row_p not in cache_:
                        cache_[row_p] = read_plan_cpa(extra["client_dir"], row_p)["cpa"]
                    new_t = cache_[row_p]
                    plan_default_by_row[row_p] = new_t
                    if cid_p in extra["auto_ids"]:
                        continue   # у `auto` цену выбирает блок ниже (tCPA кампании или план)
                    if cid_p in targets and abs(targets[cid_p] - new_t) > 1e-9:
                        notify(f"🎯 {cid_p}: цель заявки обновлена по плану месяца {targets[cid_p]:g} → {new_t:g} {CUR}")
                        print(f"{now0:%H:%M:%S} цель {cid_p} по плану: {targets[cid_p]:g} → {new_t:g}")
                        targets[cid_p] = new_t
                if extra["default_is_plan"]:
                    default_target = read_plan_cpa(extra["client_dir"], extra["default_plan_row"])["cpa"]
            except Exception as ex:
                print(f"{now0:%H:%M:%S} план месяца не прочитан: {type(ex).__name__}: {str(ex)[:100]} — цели прежние")
                notify("⚠️ План месяца («Цели2») не прочитан, цели заявки остались прежними. Проверь доступ к таблице.")

        def track_source(key, ok, label):
            """Источник заявок недоступен дольше source_alert_min минут → одно предупреждение; возврат → одно сообщение."""
            st_ = sources.setdefault(key, {"fail_since": None, "alerted": False})
            if ok:
                if st_["alerted"]:
                    notify(f"✅ {label}: снова доступен")
                    recovered.append(key)
                st_["fail_since"], st_["alerted"] = None, False
                return
            if not st_["fail_since"]:
                st_["fail_since"] = now0.isoformat(timespec="seconds")
            mins = (now0 - datetime.fromisoformat(st_["fail_since"])).total_seconds() / 60
            if mins >= extra["source_alert_min"] and not st_["alerted"]:
                st_["alerted"] = True
                notify(f"⚠️ {label} недоступен {mins:.0f} мин. Сторож считает заявки по последним известным данным: новые заявки "
                       f"не видны, возможна ложная пауза хорошей кампании. Проверь источник.")
        try:
            id_to_name = all_campaign_names(ga, cid)
        except Exception as ex:
            print(f"{now0:%H:%M:%S} ошибка списка кампаний: {type(ex).__name__}")
            id_to_name = {}
        # --- незнакомая включённая кампания (нет в списке и не в исключениях): предупреждение + минимальная защита
        try:
            for uid_, uinfo in list_enabled(client, ga, cid).items():
                if uid_ in targets or uid_ in unmanaged_ok:
                    continue
                if default_target:
                    targets[uid_] = default_target
                    zero_cap_by[uid_] = 1.0
                    adopted[uid_] = {"name": uinfo["name"], "T": default_target, "since": today, "notified": True}
                    msg = (f"🆕 {uinfo['name']} (id {uid_}): включена и не была под охраной. Бюджет {uinfo['budget']:g} {CUR}. Взята под "
                           f"минимальную защиту: пауза при расходе ≥ меньшего из «1 × бюджет» (только если бюджет ≥ 2,3 цены заявки) и «2 × {default_target:g} {CUR}» при нуле "
                           f"заявок за день, дальше обычное правило цены заявки. Если это осознанный тест, впишу в конфиг или в исключения.")
                    print(f"{now0:%H:%M:%S} {msg}")
                    notify(msg)
                    log_intervention([now0.isoformat(timespec="seconds"), uid_, uinfo["name"], "новая кампания под защиту", "",
                                      f"цель {default_target:g}, бюджет {uinfo['budget']:g}", ""])
                elif unknown_warned.get(uid_) != today:
                    unknown_warned[uid_] = today
                    msg = (f"🆕 {uinfo['name']} (id {uid_}): включена, бюджет {uinfo['budget']:g} {CUR}, под охраной нет. "
                           f"В guard_config.yaml нет `default_target`, защита не включена: впиши кампанию или добавь в исключения.")
                    print(f"{now0:%H:%M:%S} {msg}")
                    notify(msg)
        except Exception as ex:
            print(f"{now0:%H:%M:%S} проверка незнакомых кампаний: ошибка {type(ex).__name__}: {str(ex)[:100]}")
        try:
            calls_map = calls_by_day(cfg, m_ringostat, id_to_name)
        except Exception as ex:
            print(f"  Ringostat: ошибка {type(ex).__name__}: {str(ex)[:100]} — берём последнее известное")
            calls_map = None
        track_source("ringostat", calls_map is not None, "Ringostat (звонки)")
        if calls_map is not None:
            calls_cache = calls_map
        else:
            calls_map = calls_cache
        leads_by, unattributed, supa_ok = leads_today(cfg, m_ringostat, m_supabase, id_to_name)
        track_source("supabase", supa_ok, "Supabase (формы)")
        try:
            adcalls_now = ad_calls_today(ga, cid, list(targets))
            track_source("ads_calls", True, "Звонки из объявлений (Google Ads)")
        except Exception as ex:
            print(f"  Звонки из объявлений (Ads): ошибка {type(ex).__name__} — берём последнее известное")
            adcalls_now = {}
            track_source("ads_calls", False, "Звонки из объявлений (Google Ads)")
        # текущая стратегия ставок и расписание всех охраняемых кампаний: для обнаружения правок не сторожем
        try:
            settings_now, tcpa_now = read_settings(client, ga, cid, list(targets))
        except Exception as ex:
            print(f"  настройки кампаний не прочитаны: {type(ex).__name__}: {str(ex)[:100]}")
            settings_now, tcpa_now = {}, {}
        # --- цель заявки `target: auto` (правило пользователя 2026-11-04): tCPA кампании, если он выставлен в кабинете; иначе цель из плана
        for cid_a, row_a in extra["auto_ids"].items():
            if cid_a not in targets or cid_a not in tcpa_now:
                continue
            tc = tcpa_now[cid_a]
            new_t, src = (tc, "tCPA кампании") if tc else (plan_default_by_row.get(row_a) or plan_default_by_row.get(None), "план месяца")
            if new_t and abs(targets[cid_a] - new_t) > 1e-9:
                msg_a = f"🎯 {id_to_name.get(cid_a, cid_a)}: цель заявки {targets[cid_a]:g} → {new_t:g} {CUR} (источник: {src})"
                print(f"{now0:%H:%M:%S} {msg_a}" + ("" if auto_inited else " (старт, без сообщения)"))
                if auto_inited:
                    notify(msg_a)
                    log_intervention([now0.isoformat(timespec="seconds"), cid_a, id_to_name.get(cid_a, cid_a), "цель заявки сторожа",
                                      f"{targets[cid_a]:g}", f"{new_t:g} ({src})", ""])
                targets[cid_a] = new_t
        auto_inited = True
        try:
            schedules_now = read_schedule(ga, cid, list(targets))
        except Exception as ex:
            print(f"  расписание кампаний не прочитано: {type(ex).__name__}: {str(ex)[:100]}")
            schedules_now = {}

        morning_rows = []   # строки утреннего отчёта: (вид, кампания, пояснение)
        cur_vals = {}       # текущие значения кампаний для проверки согласованных изменений
        if passport_path and passport_path.exists():
            mt_ = passport_path.stat().st_mtime
            if mt_ != passport_cache.get("mtime"):
                passport_cache["mtime"], passport_cache["data"] = mt_, load_passport(passport_path)
                print(f"  паспорт кампаний прочитан: {len(passport_cache['data']['campaigns'])} кампаний, "
                      f"согласованных изменений {len(passport_cache['data']['agreed'])}")
        passport = passport_cache.get("data") or {"campaigns": {}, "agreed": []}
        for campaign_id, T in targets.items():
            now = datetime.now()
            try:
                s = read_state(ga, cid, campaign_id, since_by.get(campaign_id))
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
            for k, v in (("calls_max", 0), ("leads_max", 0), ("reenabled", 0), ("warned", False),
                         ("paused_by_guard", False), ("no_resume", False), ("flex_count", 0), ("samples", [])):
                st.setdefault(k, v)   # состояние за сегодня могло быть создано прежней версией скрипта
            name = s["name"]
            st["calls_max"] = max(st["calls_max"], calls_map.get((today, name), 0))
            st["leads_max"] = max(st["leads_max"], leads_by.get(name, 0))
            st["adcalls_max"] = max(st.get("adcalls_max", 0), int(round(adcalls_now.get(campaign_id, 0.0))))
            n = st["calls_max"] + st["leads_max"] + st["adcalls_max"]
            cost, budget = s["cost"], s["budget"]
            # предел считаем от САМОГО БОЛЬШОГО бюджета, который стоял сегодня (решение пользователя 2026-11-04): если бюджет
            # снизили посреди дня (15.10: 120 → 50), расход, накопленный при большем бюджете, не должен давать ложного «3× бюджета»
            st["budget_max"] = max(st.get("budget_max", 0), budget)
            budget_ref = st["budget_max"]
            allowance = (args.grace + n) * T
            share = cost / allowance if allowance else 0.0
            cpa_real = round(cost / n, 1) if n else ""
            status = s["status"]
            # --- «расход без заявок подряд» (решение 2026-11-04): расход с последней заявки, копится через дни
            dry_all = state.setdefault("_dry", {})
            dd = dry_all.get(campaign_id)
            if dd is None:
                dd = dry_all[campaign_id] = {"date": today, "carry": dry_replay(campaign_id, today), "cost": 0.0, "n": 0, "base": 0.0}
            if dd["date"] != today:   # новый день: вчерашний итог входит в счёт (день с заявкой обнуляет)
                dd["carry"] = 0.0 if dd["n"] > 0 else round(dd["carry"] + max(dd["cost"] - dd.get("base", 0.0), 0.0), 2)
                dd.update({"date": today, "cost": 0.0, "n": 0, "base": 0.0})
            dd["cost"], dd["n"] = max(dd["cost"], cost), max(dd["n"], n)
            dry_now = 0.0 if n > 0 else dd["carry"] + max(cost - dd.get("base", 0.0), 0.0)
            dry_limit = extra["dry_mult"] * T
            if extra["dry_mult"] and dd.get("shown") != today:
                dd["shown"] = today
                print(f"{now:%H:%M:%S} {name}: расход без заявок подряд до сегодня {dd['carry']:.1f} = {dd['carry'] / T:.1f}× цели {T:g} "
                      f"(пауза при {extra['dry_mult']:g}× = {dry_limit:.1f})")
            events = []
            inertia = ""
            paused_now = resumed_now = False

            # --- вмешательства не сторожем: бюджет, статус, стратегия ставок, расписание (решение пользователя 2026-11-04).
            # Сторож не гадает «почему»: замечает, запоминает новое значение, пересчитывает пределы от максимума бюджета дня
            # и сообщает в Telegram. Паузу из-за самого факта правки не ставит.
            seen_c = seen_all.setdefault(campaign_id, {})
            cur_state = {"budget": round(float(budget), 2), "status": int(status),
                         "bidding": settings_now.get(campaign_id), "schedule": schedules_now.get(campaign_id)}
            changes = []
            if seen_c:   # первое наблюдение только запоминаем
                for key_, label_ in (("budget", "бюджет"), ("status", "статус"), ("bidding", "стратегия ставок / цель"),
                                     ("schedule", "расписание показов")):
                    old_, new_ = seen_c.get(key_), cur_state.get(key_)
                    if old_ is None or new_ is None or old_ == new_:
                        continue
                    changes.append((label_, old_, new_))
            for key_, val_ in cur_state.items():
                if val_ is not None:
                    seen_c[key_] = val_
            if changes:
                who = who_changed(client, ga, cid, campaign_id)

                def human(label_, v_):
                    if label_ == "статус":
                        return "ВКЛ" if v_ == int(enums.ENABLED) else "ПАУЗА" if v_ == int(enums.PAUSED) else str(v_)
                    if label_ == "расписание показов":
                        return f"{len(str(v_).split('; ')) if v_ else 0} интервалов"
                    return str(v_)
                texts = []
                for label_, old_, new_ in changes:
                    texts.append(f"{label_} {human(label_, old_)} → {human(label_, new_)}")
                    log_intervention([now.isoformat(timespec="seconds"), campaign_id, name, label_, human(label_, old_),
                                      human(label_, new_), who])
                events.append("ВМЕШАТЕЛЬСТВО (не сторож): " + "; ".join(texts) + (f" [{who}]" if who else ""))
                if any(l_ == "статус" and n_ == int(enums.ENABLED) for l_, _o, n_ in changes):
                    dd["carry"], dd["base"] = 0.0, cost   # кампанию включили после паузы: счёт «без заявок подряд» начинается заново
                    dry_now = 0.0
                if campaign_id in pending_resume and any(l_ in ("бюджет", "стратегия ставок / цель", "расписание показов") for l_, _o, _n in changes):
                    pending_resume[campaign_id]["touched"] = True   # пока стояла пауза сторожа, кампанию правил человек: сам не включаем
                notify(f"🔔 {name}: изменено не сторожем: " + "; ".join(texts) + ". "
                       + (f"Последняя правка кампании в истории Ads: {who}. " if who else "История изменений Ads отстаёт на минуты, кто менял, проверю в сводке. ")
                       + f"Пределы дня считаются от максимального бюджета дня ({budget_ref:g} {CUR}). "
                       "Если правка намеренная, ничего делать не нужно, объяснишь потом одной строкой.")

            # --- темп: рост расхода за окно без новых заявок
            pace_hit = False
            samples = st.setdefault("samples", [])
            samples.append([now.isoformat(timespec="seconds"), cost, n])
            samples[:] = [x for x in samples if (now - datetime.fromisoformat(x[0])).total_seconds() <= 3600]
            # --- скачок заявок: прибавилось ≥ lead_jump_n за ~lead_jump_min минут (спам/дубли раздувают допустимый расход);
            # только предупреждение, правила не меняются; сразу после возврата источника не предупреждаем (догрузка за простой)
            if not recovered:
                refj = None
                for x in samples:
                    if (now - datetime.fromisoformat(x[0])).total_seconds() >= extra["lead_jump_min"] * 60:
                        refj = x
                last_jump = datetime.fromisoformat(st.get("jump_alert_at", "2000-01-01T00:00:00"))
                if refj and n - refj[2] >= extra["lead_jump_n"] and (now - last_jump).total_seconds() > 3600:
                    st["jump_alert_at"] = now.isoformat(timespec="seconds")
                    mins_j = (now - datetime.fromisoformat(refj[0])).total_seconds() / 60
                    events.append(f"СКАЧОК ЗАЯВОК: +{n - refj[2]} за {mins_j:.0f} мин ({refj[2]} → {n})")
                    notify(f"⚠️ {name}: заявок +{n - refj[2]} за {mins_j:.0f} мин ({refj[2]} → {n}). Допустимый расход вырос с "
                           f"{(args.grace + refj[2]) * T:.0f} до {allowance:.0f} {CUR}. Проверь, нет ли спама или дублей; "
                           f"правила сторожа не менялись.")
            ref = None
            for x in samples:   # самая свежая точка не моложе окна
                if (now - datetime.fromisoformat(x[0])).total_seconds() >= args.pace_min * 60:
                    ref = x
            # решение пользователя 2026-11-04: «темп» работает только пока заявок за день 0 (раньше — «в окне не прибавилось»).
            # Калибровка по логам ProfiMet+EkspertAgro (23 дня, 287 кампаний-дней): при пороге 40% и «заявок за день 0» —
            # 5 срабатываний, все на днях без заявок; при условии «в окне не прибавилось» — 7, из них 2 ложных (23.10, 26.10).
            # Когда заявка уже есть, дальше работает правило цены заявки.
            if ref and budget_ref and n == 0:
                # приводим рост к окну: после перезапуска/сбоя ближайшая «старая» точка может быть на 40+ минут раньше
                # (13.10: +20.8 € за 44 мин приняли за «+20.8 € за 30 мин» и поставили кампанию на паузу)
                age_min = max((now - datetime.fromisoformat(ref[0])).total_seconds() / 60, args.pace_min)
                if ((cost - ref[1]) * (args.pace_min / age_min) >= args.pace_share * budget_ref
                        and cost >= args.pace_min_allow_share * allowance):
                    pace_hit = True

            # --- пауза / возобновление по цене заявки
            if status == enums.ENABLED:
                if campaign_id in pending_resume and pending_resume[campaign_id].get("date") != today:
                    pending_resume.pop(campaign_id, None)   # кампанию включили (руками или утренним возобновлением)
                if st.get("paused_by_guard"):
                    events.append("ручное включение после паузы сторожа")
                    st["paused_by_guard"] = False
                reason = None
                hard_mult = hard_mult_by.get(campaign_id, args.abs_mult)
                total_lim = total_limit_by.get(campaign_id)
                zero_cap = zero_cap_by.get(campaign_id)
                if budget_ref and cost >= hard_mult * budget_ref:
                    reason = "жёсткий предел"
                    st["no_resume"] = True
                    events.append(f"ПАУЗА жёсткий предел: расход {cost:.2f} ≥ {hard_mult:g}× максимального бюджета дня {budget_ref:.2f} (заявок {n})")
                elif total_lim and s.get("total") is not None and s["total"] >= total_lim:
                    reason = "общий лимит"
                    st["no_resume"] = True
                    events.append(f"ПАУЗА общий лимит: с {since_by.get(campaign_id)} потрачено {s['total']:.2f} ≥ "
                                  f"{total_lim:g} {CUR} (заявок сегодня {n})")
                elif (zero_cap and n == 0 and budget_ref and cost >= zero_cap * budget_ref
                      and math.exp(-budget_ref / T) <= ZERO_CAP_MAX_FALSE):
                    # правило «N × бюджет при нуле заявок» только там, где бюджет ≥ ~2.3 цены заявки: иначе нулевой день у здоровой
                    # кампании обычное дело (вероятность без заявок на полном бюджете exp(−бюджет/цена) > 10%), расчёт 2026-11-04
                    reason = "расход без заявок"
                    events.append(f"ПАУЗА расход без заявок: {cost:.2f} ≥ {zero_cap:g}× максимального бюджета дня {budget_ref:.2f}, заявок 0")
                elif (extra["dry_mult"] and n == 0 and dd["carry"] > 0 and dry_now >= dry_limit
                      and not any(v_.get("fail_since") for v_ in sources.values())):
                    # расход без заявок подряд: нулевой день у кампании на цели обычен при малом бюджете, доказательство копится по дням
                    reason = "расход без заявок подряд"
                    events.append(f"ПАУЗА расход без заявок подряд: {dry_now:.2f} ≥ {extra['dry_mult']:g}× цели {T:g} = {dry_limit:.2f} "
                                  f"(до сегодня {dd['carry']:.2f} + сегодня {max(cost - dd.get('base', 0.0), 0.0):.2f}), заявок сегодня 0")
                elif cost >= allowance:
                    reason = "цена заявки"
                    events.append(f"ПАУЗА цена заявки: расход {cost:.2f} ≥ допустимого {allowance:.2f} "
                                  f"= ({args.grace:g}+{n})×{T:g}")
                elif pace_hit:
                    reason = "темп"
                    events.append(f"ПАУЗА темп: за {age_min:.0f} мин расход +{cost - ref[1]:.2f} "
                                  f"(≈ {(cost - ref[1]) * args.pace_min / age_min:.2f} за {args.pace_min:g} мин) "
                                  f"при {n} заявках (бюджет {budget_ref:.2f})")
                elif cost >= args.warn_share * allowance and not st["warned"]:
                    events.append(f"ПРЕДУПРЕЖДЕНИЕ: расход {cost:.2f} = {share:.0%} допустимого {allowance:.2f} (заявок {n})")
                    st["warned"] = True
                    notify(f"⚠️ {name}: расход {cost:.2f} {CUR} = {share:.0%} допустимого {allowance:.2f} {CUR} (заявок {n})")
                if reason:
                    if args.execute:
                        if reason == "расход без заявок подряд":
                            st["no_resume"] = True
                        pause(client, cid, campaign_id)
                        seen_c["status"] = int(enums.PAUSED)   # свою паузу вмешательством не считаем
                        st["paused_by_guard"] = True
                        st["paused_at"] = now.isoformat(timespec="seconds")
                        st["cost_at_pause"] = cost
                        st["n_at_pause"] = n
                        st["pause_reason"] = reason
                        paused_now = True
                        hist_ = pause_history.setdefault(campaign_id, [])
                        hist_.append({"date": today, "reason": reason})
                        del hist_[:-10]
                        if reason in ("цена заявки", "темп"):
                            pending_resume[campaign_id] = {"date": today, "reason": reason, "touched": False, "review_notified": False}
                        else:
                            pending_resume.pop(campaign_id, None)   # предел / лимит / расход без заявок: утром сам не включаем
                        notify(f"⛔ {name}: ПАУЗА ({reason}). Расход {cost:.2f} {CUR}, заявок {n}, "
                               f"допустимо {allowance:.2f} {CUR}, цель {T:g} {CUR}")
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
                        seen_c["status"] = int(enums.ENABLED)
                        st["paused_by_guard"] = False
                        st["reenabled"] += 1
                        st["warned"] = False
                        resumed_now = True
                        notify(f"✅ {name}: ВОЗОБНОВЛЕНА — поздние заявки (теперь {n}), расход {cost:.2f} {CUR}, "
                               f"допустимо {allowance:.2f} {CUR}")
                    else:
                        msg += " (dry-run или без --allow-reenable, не выполнено)"
                    events.append(msg)
            # иначе: на паузе по решению человека — не трогаем

            # --- утреннее возобновление после паузы сторожа (решение пользователя 2026-11-04)
            # Пауза по «цене заявки» или «темпу» у здоровой кампании ложная примерно в 13.5% дней (exp(−2)), поэтому утром следующего
            # дня включаем сами. Вторая такая пауза за 3 дня у здоровой кампании ≈ 1.8% (0.135²) — это сигнал, не случайность:
            # тогда не включаем, пишем «нужен разбор». Не включаем и если пока кампания стояла, её правил человек.
            pend = pending_resume.get(campaign_id)
            why_no, resumed_morning = None, False
            pp = passport["campaigns"].get(str(campaign_id)) or {}
            hold = pp.get("state") in HOLD_STATES
            cur_vals[str(campaign_id)] = {"budget": budget, "status": status}
            if (status != enums.ENABLED and not hold and pend and args.morning_resume and pend["date"] < today
                    and now.hour * 60 + now.minute >= resume_min):
                d_today = date.fromisoformat(today)
                recent = [h_ for h_ in pause_history.get(campaign_id, [])
                          if h_["reason"] in ("цена заявки", "темп") and 1 <= (d_today - date.fromisoformat(h_["date"])).days <= 3]
                if pend.get("touched"):
                    why_no = "пока кампания стояла на паузе, её изменил человек (бюджет / стратегия / расписание)"
                elif len(recent) >= 2:
                    why_no = (f"вторая пауза сторожа по цене/«темпу» за 3 дня ({', '.join(h_['date'] + ' ' + h_['reason'] for h_ in recent)}): "
                              f"две ложные подряд у здоровой кампании ≈ 1.8%")
                else:
                    why_no = None
                if why_no:
                    events.append("УТРЕННЕЕ ВОЗОБНОВЛЕНИЕ не выполнено: " + why_no)
                    if not pend.get("review_notified"):
                        pend["review_notified"] = True
                        notify(f"🔎 {name}: не включаю утром. {why_no[0].upper() + why_no[1:]}. Нужен разбор: включение — после вашего «да».")
                else:
                    msg = (f"УТРЕННЕЕ ВОЗОБНОВЛЕНИЕ: пауза сторожа {pend['date']} по причине «{pend['reason']}», "
                           f"новых правок кампании человеком нет, вторых пауз за 3 дня нет")
                    if args.execute:
                        enable(client, cid, campaign_id)
                        seen_c["status"] = int(enums.ENABLED)
                        pending_resume.pop(campaign_id, None)
                        resumed_now = resumed_morning = True
                        notify(f"🌅 {name}: ВКЛЮЧЕНА утром после паузы сторожа {pend['date']} («{pend['reason']}»). "
                               f"Если пауза была настоящей, правило сработает снова, и тогда утром не включим.")
                    else:
                        msg += " (dry-run, не выполнено)"
                    events.append(msg)

            # --- строка утреннего отчёта (включено / осталось на паузе и почему)
            if resumed_morning:
                morning_rows.append(("on", name, f"пауза сторожа {pend['date']} по причине «{pend['reason']}»"))
            elif status != enums.ENABLED and not resumed_now:
                last_h = (pause_history.get(campaign_id) or [None])[-1]
                if hold:
                    morning_rows.append(("off", name, "по паспорту: " + hold_text(pp)))
                elif why_no:
                    morning_rows.append(("off", name, why_no))
                elif last_h and 0 <= (date.fromisoformat(today) - date.fromisoformat(last_h["date"])).days <= 7                         and last_h["reason"] not in ("цена заявки", "темп"):
                    morning_rows.append(("off", name, f"пауза сторожа {last_h['date']} по причине «{last_h['reason']}»: такие паузы утром сам не снимаю"))
                elif pend and args.morning_resume and not args.execute:
                    morning_rows.append(("on", name, f"(режим плана, не выполнено) пауза сторожа {pend['date']} по причине «{pend['reason']}»"))
                elif pend and not args.morning_resume:
                    morning_rows.append(("off", name, "утреннее возобновление выключено"))
                else:
                    morning_rows.append(("off", name, "на паузе не по правилам сторожа (решение человека или давняя пауза), сам не включаю"))
            elif status == enums.ENABLED and not paused_now:
                morning_rows.append(("run", name, ""))
                hw_ = state.setdefault("_hold_enabled_warned", {})
                if hold and hw_.get(str(campaign_id)) != today:
                    hw_[str(campaign_id)] = today
                    notify(f"⚠️ {name}: кампания ВКЛЮЧЕНА, а в паспорте у неё состояние «{STATE_RU.get(pp.get('state'))}» "
                           f"({pp.get('why', 'причина не указана')}). Сторож охраняет её по обычным правилам. "
                           f"Если включение намеренное, обновлю паспорт.")

            # --- бюджет (только у кампаний с budget_control в конфиге; в режиме без конфига — у всех под охраной)
            if args.flex and campaign_id in flex_ids:
                try:
                    res, bud_now, shared = read_budget(ga, cid, campaign_id)
                    if res is None:
                        raise RuntimeError("бюджет не найден")
                    if shared:
                        events.append("бюджет общий для нескольких кампаний — управление пропущено")
                    else:
                        pb = budget_state.setdefault(campaign_id, {})
                        # база из конфига берётся один раз и при ИЗМЕНЕНИИ значения в конфиге; иначе каждый такт она перезаписывала
                        # бы базу, поднятую сторожем или вами, и утром бюджет откатывался (найдено 2026-11-04)
                        if campaign_id in base_arg:
                            if pb.get("cfg_base") != base_arg[campaign_id]:
                                pb["base"] = base_arg[campaign_id]
                                pb["floor"] = base_arg[campaign_id]
                            pb["cfg_base"] = base_arg[campaign_id]
                        pb.setdefault("floor", bud_now)
                        pb.setdefault("base", bud_now)
                        ceiling = max_budget.get(campaign_id, pb["base"])
                        # бюджет изменён не сторожем (люфт сторожа помечен flexed, свои правки базы сторож вносит в pb сам):
                        # в пределах max принимаем как новую базу, выше max — не откатываем и не принимаем, спрашиваем
                        if not pb.get("flexed") and abs(bud_now - pb["base"]) > 0.5:
                            if bud_now <= ceiling:
                                events.append(f"БАЗА {pb['base']:g} → {bud_now:g} {CUR}: бюджет изменён не сторожем, принят как новая база")
                                notify(f"💶 {name}: бюджет {pb['base']:g} → {bud_now:g} {CUR} изменён не сторожем, принят как новая база "
                                       f"(предел {ceiling:g}). Откатывать утром и вечером не буду.")
                                pb["base"] = bud_now
                                pb["floor"] = min(pb.get("floor", bud_now), bud_now)
                            elif pb.get("above_max_warned") != today:
                                pb["above_max_warned"] = today
                                notify(f"❓ {name}: бюджет {bud_now:g} {CUR} выше предела {ceiling:g}. Не откатываю и не принимаю как базу: "
                                       f"поднять предел или вернуть бюджет?")
                        can_write = args.execute and args.allow_budget

                        def apply_budget(value, why):
                            """Ставит бюджет (или только планирует). Возвращает True, если запись выполнена."""
                            value = int(round(value))
                            msg = f"БЮДЖЕТ {bud_now:g} → {value} {CUR}: {why}"
                            if can_write:
                                set_budget(client, cid, res, value)
                                seen_c["budget"] = round(float(value), 2)   # свою правку бюджета вмешательством не считаем
                                events.append(msg)
                                notify(f"💶 {name}: {msg}")
                                return True
                            events.append(msg + " (план, не выполнено)")
                            return False

                        # 1) утренний шаг: откат висящего люфта, базовый шаг вверх/вниз по истории
                        if pb.get("day_done") != today:
                            if pb.get("flexed") and bud_now != pb["base"]:
                                if apply_budget(pb["base"], "утро: возврат к базовому бюджету (откат люфта)"):
                                    bud_now = pb["base"]
                            if can_write:   # в режиме «только план» состояние не трогаем (иначе боевой запуск пропустит утро)
                                pb["flexed"] = False
                            cost_h, forms_h = ads_history(ga, cid, [campaign_id], days=12)
                            streak, last_bad = 0, False
                            days = [(date.today() - timedelta(days=i)).isoformat() for i in range(1, 12)]
                            hist = []
                            for d in days:
                                c = cost_h.get((campaign_id, d), 0.0)
                                nn = calls_map.get((d, name), 0) + int(round(forms_h.get((campaign_id, d), 0.0)))
                                hist.append((d, c, nn))
                            changed_on = pb.get("changed_on", "")
                            streak_days = []
                            skipped = []
                            for d, c, nn in hist:
                                if d < changed_on:
                                    break
                                # нерабочий день (выходной по расписанию, пауза, копеечный расход): не считаем и серию не рвём
                                if c < args.idle_share * pb["base"]:
                                    skipped.append(d)
                                    continue
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
                                    why = (f"{streak} дня подряд цена ≤ {T:g} {CUR} и расход ≥ {args.constrained_share:.0%} бюджета, "
                                           f"шаг +{step:g}%" + (" (большой запас по цене)" if big else ""))
                                else:
                                    events.append(f"рост бюджета не выполнен: потолок {ceiling:g} {CUR} или дневной план "
                                                  f"{args.plan_daily or 0:g} {CUR} (сумма базовых других кампаний)")
                            elif last_bad and pb["base"] > pb["floor"]:
                                new_base = max(pb["floor"], math.floor(pb["base"] / (1 + args.step_pct / 100)))
                                why = f"вчера расход {y[1]:.0f} {CUR} при {y[2]} заявках — выше допустимого"
                            if new_base is not None and new_base != pb["base"]:
                                if apply_budget(new_base, "базовый шаг: " + why):
                                    pb["base"] = new_base
                                    pb["changed_on"] = today
                                    bud_now = new_base
                            else:
                                events.append(f"базовый бюджет {pb['base']:g} {CUR} без изменений (подходящих дней подряд: "
                                              f"{streak} из {args.efficient_days}; нужно: цена ≤ цели и расход ≥ "
                                              f"{args.constrained_share:.0%} бюджета"
                                              + (f"; нерабочие дни пропущены: {', '.join(skipped)}" if skipped else "") + ")")
                            if can_write:   # утро «сделано» только после реальной записи, не после плана
                                pb["day_done"] = today

                        # 2) дневной люфт: эффективна и упирается в бюджет → поднять выше факта
                        enabled_now = (status == enums.ENABLED and not paused_now) or resumed_now
                        if (enabled_now and n >= args.flex_min_leads and cost / n <= args.flex_cpa_share * T
                                and cost >= args.flex_cost_share * bud_now and st["flex_count"] < args.flex_max_per_day
                                and bud_now < ceiling):
                            target = min(ceiling, math.ceil(max(cost * 1.3, bud_now * 1.25)))
                            if target > bud_now:
                                if apply_budget(target, f"люфт: заявок {n}, цена {cost / n:.1f} {CUR} ≤ {args.flex_cpa_share:.0%} "
                                                        f"цели, расход {cost:.1f} ≥ {args.flex_cost_share:.0%} бюджета"):
                                    pb["flexed"] = True
                                    st["flex_count"] += 1
                                    bud_now = target

                        # 3) вечерний возврат люфта
                        if (pb.get("flexed")
                                and now.hour * 60 + now.minute >= restore_min and bud_now != pb["base"]):
                            if apply_budget(pb["base"], "вечерний возврат к базовому"):
                                pb["flexed"] = False
                                bud_now = pb["base"]
                except Exception as ex:
                    events.append(f"бюджет: ошибка {type(ex).__name__}: {str(ex)[:120]}")

            event = "; ".join(events)
            print(f"{now:%H:%M:%S} {name}: статус {'ВКЛ' if status == enums.ENABLED else 'ПАУЗА'}, расход {cost:.2f}/"
                  f"бюджет {budget:.2f}, заявок {n} (звонки {st['calls_max']} + формы {st['leads_max']} + из объявлений {st['adcalls_max']}), допустимо "
                  f"{allowance:.2f} ({share:.0%}), цена заявки {cpa_real or '—'} {event} {inertia}")
            log_row([now.isoformat(timespec="seconds"), campaign_id, name, status, budget, round(cost, 2), T,
                     st["calls_max"] + st["adcalls_max"], st["leads_max"], n, round(allowance, 2), round(share, 3), cpa_real, event, inertia])

        if unattributed:
            print(f"  (форм без кампании/UTM сегодня: {unattributed} — не учтены ни в одной кампании)")
        # --- кампании, которые есть только в паспорте (не под охраной): показываем причину в отчёте
        for pid_, pinfo_ in passport["campaigns"].items():
            if pid_ not in targets and pinfo_.get("state") in HOLD_STATES:
                morning_rows.append(("off", pinfo_.get("name", pid_), "по паспорту (вне охраны): " + hold_text(pinfo_)))
        # --- согласованные изменения: сверка с кабинетом (сторож в паспорт НЕ пишет, только сообщает)
        plan_lines = []
        today_s = date.today().isoformat()
        seen_ag = state.setdefault("_agreed_seen", {})
        for ag in passport["agreed"]:
            if str(ag.get("status", "agreed")) != "agreed":
                continue
            cur_ = cur_vals.get(str(ag.get("campaign")))
            if cur_ is None:
                continue
            par_, to_ = ag.get("param"), ag.get("to")
            if par_ == "budget":
                done_ = abs(float(cur_["budget"]) - float(to_)) < 0.5
                now_txt = f"{cur_['budget']:g}"
            elif par_ == "status":
                done_ = cur_["status"] == getattr(enums, str(to_), None)
                now_txt = "ВКЛ" if cur_["status"] == enums.ENABLED else "ПАУЗА"
            else:
                continue
            label_ = f"{ag.get('id', '?')} {ag.get('campaign_name', ag.get('campaign'))}: {par_} → {to_}"
            late_ = bool(ag.get("deadline")) and str(ag["deadline"]) < today_s
            if done_:
                plan_lines.append(f"✅ {label_}: выполнено (в кабинете {now_txt})")
                if seen_ag.get(str(ag.get("id"))) != "applied":
                    seen_ag[str(ag.get("id"))] = "applied"
                    notify(f"✅ Согласованное изменение {label_} выполнено (в кабинете {now_txt}). Паспорт обновлю при записи в журнал.")
            else:
                plan_lines.append(f"{'⏳ просрочено' if late_ else '• ждёт'} {label_}: в кабинете {now_txt}, срок {ag.get('deadline', '—')}"
                                  + (" (apply: guard — автоприменение сторожем пока не включено)" if ag.get("apply") == "guard" else ""))
                if late_ and seen_ag.get(str(ag.get("id"))) != today_s:
                    seen_ag[str(ag.get("id"))] = today_s
                    notify(f"⏳ Согласовано, не сделано: {label_}. В кабинете {now_txt}, срок {ag.get('deadline')}.")
        # --- утренний отчёт один раз в день после morning_resume_at: что включено, что осталось на паузе и почему
        if (args.morning_resume and morning_rows and state.get("_morning_report") != date.today().isoformat()
                and datetime.now().hour * 60 + datetime.now().minute >= resume_min):
            on_ = [f"• {n_}: {w_}" for k_, n_, w_ in morning_rows if k_ == "on"]
            off_ = [f"• {n_}: {w_}" for k_, n_, w_ in morning_rows if k_ == "off"]
            run_ = [n_ for k_, n_, w_ in morning_rows if k_ == "run"]
            rep_ = [f"🌅 Утро {date.today():%d.%m}, {args.client or cid}: сторож проверил паузы."]
            rep_.append("Включены утром:\n" + "\n".join(on_) if on_ else "Утром ничего не включали.")
            rep_.append("Остаются на паузе:\n" + "\n".join(off_) if off_ else "На паузе кампаний из охраны нет.")
            rep_.append(f"Работают: {len(run_)}" + (f" ({', '.join(run_)})" if run_ else ""))
            if plan_lines:
                rep_.append("Согласованные изменения:" + chr(10) + chr(10).join(plan_lines))
            text_ = "\n".join(rep_)
            print(text_)
            if args.execute:
                notify(text_)
                state["_morning_report"] = date.today().isoformat()
        save_state(state)
        if args.heartbeat_min and time.time() - last_hb >= args.heartbeat_min * 60:
            last_hb = time.time()
            on_pause = [n_ for n_ in (id_to_name.get(i, i) for i in targets)
                        if state.get(next((i for i in targets if id_to_name.get(i) == n_), ""), {}).get("paused_by_guard")]
            notify(f"🟢 Сторож жив ({datetime.now():%H:%M}): кампаний {len(targets)}"
                   + (f" (из них под временной защитой как незнакомые: {len(adopted)})" if adopted else "")
                   + f", на паузе по нашему правилу {len(on_pause)}" + (f" ({', '.join(on_pause)})" if on_pause else "") +
                   f", форм без кампании {unattributed}. Тишина дольше интервала = процесс остановлен.")
        if not args.loop_min:
            break
        time.sleep(args.loop_min * 60)


if __name__ == "__main__":
    main()
