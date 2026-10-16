#!/usr/bin/env python
# coding: utf-8
"""Сводка «что изменилось без меня» — ТОЛЬКО ЧТЕНИЕ. Запускать в начале сессии по клиенту, до любых выводов.

Зачем: сторожа (`gads_spend_guard_cpa.py`) и пользователь меняют кампании между сессиями, а в вики это попадает с опозданием.
Скрипт собирает три вещи за последние N часов:
  1. события сторожа из `Статистика/gads_spend_guard_cpa_log.csv` (пауза, возобновление, бюджет, ручное включение, ошибки чтения);
  2. изменения кампаний и бюджетов из истории изменений Google Ads (`change_event`): кто (почта / клиент API или веб),
     что поменялось, статус было → стало; по остальным типам объектов (объявления, ассеты, ключи) — только счётчики;
  3. текущий статус и сегодняшний расход всех включённых кампаний;
  4. темп бюджета против плана месяца (таблица «Цели2 Адвайта»): план/факт расхода и заявок, нужный расход в день на остаток,
     упирается ли кампания в бюджет (потерянная доля показов по бюджету). Правило пользователя 2026-10-15: в каждой диагностике.
Ничего не пишет ни в кабинет, ни в вики. Что из сводки стратегически значимо — вносит Claude в Журнал_изменений/Решения.

Использование:
    python state_digest.py --customer-id 7552781705 --client-folder ProfiMet [--hours 48]
"""
import argparse
import calendar
import csv
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.ads.googleads.client import GoogleAdsClient

from _config import SERVICE_ACCOUNT_FILE, client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

TZ = ZoneInfo("Europe/Warsaw")
PLAN_SHEET_ID = "1Lbefo3nX1-VZ7OOmJI2zf8B6vDX8PiXIjMjqoa89T7c"  # «Цели2 Адвайта», лист «<Месяц> <гг>»
MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
             "Ноябрь", "Декабрь"]
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


def read_plan_row(folder, today):
    """План месяца клиента из Google-таблицы: analysis_config.yaml (plan.*) или строка Client == имя папки клиента."""
    import gspread
    from google.oauth2.service_account import Credentials
    sheet_id, client_name, budget_col = PLAN_SHEET_ID, folder, "AdwordsBudget"
    cfg_path = client_stats_dir(folder).parent / "analysis_config.yaml"
    if cfg_path.exists():
        try:
            import yaml
            plan = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("plan", {})
            sheet_id = plan.get("sheet_id", sheet_id)
            client_name = plan.get("client_name", client_name)
            budget_col = plan.get("budget_column", budget_col)
        except Exception:
            pass
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE),
                                                  scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    tab = f"{MONTHS_RU[today.month - 1]} {today.strftime('%y')}"
    rows = gspread.authorize(creds).open_by_key(sheet_id).worksheet(tab).get_all_records()
    num = lambda v: float(str(v).replace(",", ".").replace(" ", "") or 0)  # noqa: E731
    for r in rows:
        if str(r.get("Client", "")).strip() == client_name:
            return {"tab": tab, "client": client_name, "budget": num(r.get(budget_col)),
                    "leads": num(r.get("Conversions")), "cpa": num(r.get("CPA"))}
    return None


def budget_pacing(ga, cid, folder):
    today = datetime.now(TZ).date()
    dim = calendar.monthrange(today.year, today.month)[1]
    plan = read_plan_row(folder, today)
    if not plan or not plan["budget"]:
        print(f"  плана месяца для «{folder}» в таблице «Цели2 Адвайта» нет — темп не посчитать (проверить строку Client)")
        return
    first = today.replace(day=1)
    by_day = {}
    leads = 0.0
    for r in ga.search(customer_id=cid, query=(
            "SELECT segments.date, metrics.cost_micros, metrics.conversions FROM customer "
            f"WHERE segments.date BETWEEN '{first}' AND '{today}'")):
        by_day[r.segments.date] = by_day.get(r.segments.date, 0) + r.metrics.cost_micros / 1e6
        leads += r.metrics.conversions
    t = str(today)
    spent_today = by_day.get(t, 0.0)
    spent = sum(v for k, v in by_day.items() if k != t)          # расход по завершённым дням
    elapsed = today.day - 1                                       # завершённых дней в месяце
    remaining = dim - today.day + 1                               # дней осталось, считая сегодня
    plan_b, plan_l = plan["budget"], plan["leads"]
    expected = plan_b * elapsed / dim
    need = (plan_b - spent) / remaining if remaining else 0
    done_days = sorted(k for k in by_day if k != t)
    avg = lambda n: (sum(by_day[k] for k in done_days[-n:]) / len(done_days[-n:])) if done_days else 0  # noqa: E731
    print(f"  план месяца ({plan['tab']}, строка «{plan['client']}»): бюджет {plan_b:.0f}, заявок {plan_l:.0f}, "
          f"цена заявки {plan['cpa']:.0f}")
    print(f"  срез: расход по завершённым дням 1–{elapsed}: {spent:.0f}; сегодня на сейчас {spent_today:.0f}; "
          f"заявок в Ads (основные конверсии) за месяц {leads:.1f} (звонки Ringostat и формы вне Ads сюда не входят)")
    if elapsed > 0 and expected:
        pct = spent / expected * 100
        verdict = "ОТСТАЁМ" if pct < 90 else ("ПЕРЕРАСХОД" if pct > 110 else "в темпе")
        print(f"  расход: {spent:.0f} из {expected:.0f} по линейному плану на {elapsed} дн. ({pct:.0f}%) -> {verdict}; "
              f"недобор {expected - spent:.0f}" if expected > spent else f"опережение {spent - expected:.0f}")
    print(f"  среднее в день: последние 3 дня {avg(3):.0f}, 7 дней {avg(7):.0f}; "
          f"нужно в день на остаток ({remaining} дн. с сегодня), чтобы выйти на {plan_b:.0f}: {need:.0f}")
    if plan_l:
        left = plan_l - leads
        if left > 0:
            print(f"  заявки: {leads:.1f} из {plan_l:.0f}; нужная цена заявки на остаток = ({plan_b:.0f} - {spent:.0f}) / "
                  f"{left:.1f} = {(plan_b - spent) / left:.0f} (план {plan['cpa']:.0f})")
        else:
            print(f"  заявки: {leads:.1f} из {plan_l:.0f} - план по заявкам выполнен")
    seven = today - timedelta(days=7)
    # два запроса: бюджет кампании и доли показов в одном запросе API v23 даёт 500 Internal error
    budgets = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign_budget.amount_micros FROM campaign "
            "WHERE campaign.status = 'ENABLED' AND campaign.advertising_channel_type = 'SEARCH'")):
        budgets[r.campaign.id] = (r.campaign.name, r.campaign_budget.amount_micros / 1e6)
    print("  упирается ли в бюджет (7 дн., Search):")
    caps = 0.0
    for cid_, (name, bud) in budgets.items():
        rows = list(ga.search(customer_id=cid, query=(
            "SELECT metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share, "
            "metrics.search_impression_share, metrics.cost_micros FROM campaign "
            f"WHERE campaign.id = {cid_} AND segments.date BETWEEN '{seven}' AND '{today - timedelta(days=1)}'")))
        cost = sum(r.metrics.cost_micros for r in rows)
        if not cost:
            continue
        w = [r for r in rows if r.metrics.cost_micros]
        lost_b = sum(r.metrics.search_budget_lost_impression_share * r.metrics.cost_micros for r in w) / cost
        lost_r = sum(r.metrics.search_rank_lost_impression_share * r.metrics.cost_micros for r in w) / cost
        share = sum(r.metrics.search_impression_share * r.metrics.cost_micros for r in w) / cost
        caps += bud
        print(f"    {name}: дневной бюджет {bud:.0f}, доля показов {share:.0%}, потеряно по бюджету {lost_b:.0%}, "
              f"по рейтингу {lost_r:.0%} (средневзвешено по расходу)")
    if caps:
        print(f"    сумма дневных бюджетов Search: {caps:.0f}/день -> потолок на месяц ~{caps * 30.4:.0f} "
              f"(Google тратит до 2x в день, но не больше 30,4x дневного бюджета за месяц)")
    print("    Если «потеряно по бюджету» ~0, повышение бюджета расход не поднимет: тормозят ставки, рейтинг, охват.")


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
    print("\n[4] Темп бюджета против плана месяца:")
    try:
        budget_pacing(ga, cid, a.client_folder)
    except Exception as e:  # плана или таблицы может не быть - сводка не должна падать
        print(f"  не удалось посчитать темп бюджета: {e}")
    print("\nЭто чтение. Что значимо — внести в Журнал_изменений/Решения и в задачи.")


if __name__ == "__main__":
    main()
