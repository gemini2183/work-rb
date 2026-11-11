"""Статус по двум осям: клиент/направление × канал. Только чтение кабинетов, модель не нужна.

Источники:
  Клиенты/<Имя>/Каналы.yaml                 какие каналы подключены (customer_id и т.п.)
  Клиенты/<Имя>/Направления/<Имя>.md        карточка направления: шапка (status/blocker/next/updated), блоки каналов
                                            в frontmatter (`channels:`), ручная таблица, автоблок кэша кабинета
  Клиенты/<Имя>/Статистика/channel_snapshot_<канал>.json   снимок аккаунта клиента в канале (пишет скрипт)

Запросы:
  --all                                  все клиенты: снимки аккаунтов + строки направлений
  --all --channel google_ads             все клиенты, только Google Ads
  --client X                             клиент: снимки аккаунтов (с перечнем включённых кампаний) + направления
  --client X --channel google_ads        клиент, только этот канал
  --client X --direction Y               полная карточка направления, автоблоки всех её каналов
  --client X --direction Y --channel C   то же, но читается и печатается только канал C
Флаги: --offline (только кэш, без обращений к кабинетам), --ttl-hours N (по умолчанию 6; 0 - перечитать).

Что считает сам скрипт (не модель): расхождение «ожидание карточки против кабинета», группа/кампания не найдена,
темп расхода против линейного плана месяца, кампании на паузе с расходом сегодня, файлы клиента новее ручной части
карточки. Канал без читателя печатается как «читатель не подключён».
Подключены читатели: google_ads. Не подключены: openai_ads, lsa (в карточках заведены как заготовки).
"""
import argparse
import calendar
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

HERE = Path(__file__).resolve().parent
VAULT = HERE.parent
CLIENTS = VAULT / "Клиенты"
TZ = ZoneInfo("Europe/Warsaw")
AUTO_RE = re.compile(r"<!-- AUTO:start -->(.*?)<!-- AUTO:end -->", re.S)
CH_RE = re.compile(r"<!-- CH:(\S+) fetched_at=(\S+) -->\n(.*?)\n<!-- /CH -->", re.S)
WATCH = ["Журнал_изменений.md", "Решения.md", "Задачи.md", "Паспорт.md", "Эксперименты.md"]
_CLIENT = {}


# ---------- общие ----------

def now():
    return datetime.now(TZ)


def parse_dt(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=TZ)
    except (TypeError, ValueError):
        return None


def is_fresh(dt, ttl):
    return dt is not None and ttl > 0 and (now() - dt) < timedelta(hours=ttl)


def client_dirs(client=None):
    if client:
        return [CLIENTS / client]
    return sorted(d for d in CLIENTS.iterdir() if d.is_dir() and not d.name.startswith("_"))


def read_channels(cdir):
    p = cdir / "Каналы.yaml"
    if not p.exists():
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("channels") or {}


def read_card(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path}: нет frontmatter")
    return yaml.safe_load(m.group(1)) or {}, m.group(2), text


def cards_of(cdir):
    d = cdir / "Направления"
    return sorted(d.glob("*.md")) if d.is_dir() else []


def google_client():
    if "ga" not in _CLIENT:
        os.chdir(HERE)  # secrets/google-ads.yaml лежит относительно папки Скрипты
        from google.ads.googleads.client import GoogleAdsClient
        from gads_stats import GOOGLE_ADS_YAML
        c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
        _CLIENT["client"], _CLIENT["ga"] = c, c.get_service("GoogleAdsService")
    return _CLIENT["client"], _CLIENT["ga"]


# ---------- Google Ads: снимок аккаунта клиента ----------

def snapshot_google_ads(cdir, cfg):
    client, ga = google_client()
    E = client.enums
    cid = str(cfg["customer_id"]).replace("-", "")
    today = now().date()
    first = today.replace(day=1)
    dim = calendar.monthrange(today.year, today.month)[1]
    cur = next(iter(ga.search(customer_id=cid, query="SELECT customer.currency_code FROM customer LIMIT 1"))).customer.currency_code
    camps = {}
    for r in ga.search(customer_id=cid, query=("SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros "
                                               "FROM campaign WHERE campaign.status != 'REMOVED'")):
        camps[r.campaign.id] = {"name": r.campaign.name, "status": E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status),
                                "budget": r.campaign_budget.amount_micros / 1e6}
    rows, today_cost = [], {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT segments.date, campaign.id, campaign.shopping_setting.merchant_id, metrics.cost_micros "
            f"FROM campaign WHERE segments.date BETWEEN '{first}' AND '{today}'")):
        cost = r.metrics.cost_micros / 1e6
        rows.append((r.segments.date, bool(r.campaign.shopping_setting.merchant_id), cost))
        if r.segments.date == str(today):
            today_cost[r.campaign.id] = today_cost.get(r.campaign.id, 0.0) + cost
    snap = {"channel": "google_ads", "fetched_at": now().isoformat(timespec="minutes"), "currency": cur,
            "enabled": [{"name": v["name"], "budget": v["budget"]} for v in camps.values() if v["status"] == "ENABLED"],
            "paused": sum(1 for v in camps.values() if v["status"] == "PAUSED"),
            "spent_today": round(sum(today_cost.values()), 2),
            "paused_with_spend": [camps[i]["name"] for i, c in today_cost.items() if c > 0 and i in camps and camps[i]["status"] == "PAUSED"],
            "projects": []}
    # план месяца - как в state_digest (Цели2 Адвайта), по проектам из analysis_config.yaml
    try:
        import state_digest as SD
        sheet_id, budget_col, projects = SD.plan_projects(cfg.get("plan_folder") or cdir.name)
        tab, plan_rows = SD.read_plan_rows(sheet_id, budget_col, today)
        by_name = {r["client"]: r for r in plan_rows}
        elapsed = today.day - 1
        for p in projects:
            plan = by_name.get(p["client_name"])
            if not plan or not plan["budget"]:
                snap["projects"].append({"name": p["client_name"], "note": "строки плана в таблице нет или бюджет 0"})
                continue
            spent = sum(c for d, feed, c in rows if d != str(today) and (p["merchant_feed"] is None or p["merchant_feed"] == feed))
            expected = plan["budget"] * elapsed / dim
            pct = spent / expected * 100 if elapsed > 0 and expected else None
            verdict = None if pct is None else ("ОТСТАЁМ" if pct < 90 else ("ПЕРЕРАСХОД" if pct > 110 else "в темпе"))
            snap["projects"].append({"name": p["client_name"], "tab": tab, "plan_budget": plan["budget"], "spent_done": round(spent, 2),
                                     "expected": round(expected, 2), "pct": None if pct is None else round(pct), "verdict": verdict,
                                     "days_done": elapsed})
    except Exception as e:
        snap["projects"] = [{"name": cdir.name, "note": f"план не прочитан ({type(e).__name__}: {str(e)[:100]})"}]
    return snap


def render_snapshot(name, snap, detail=False, stale=False):
    cur = snap.get("currency", "")
    flag = " [КЭШ УСТАРЕЛ, обновить не удалось]" if stale else ""
    at = parse_dt(snap["fetched_at"])
    parts = [f"включено {len(snap['enabled'])}, на паузе {snap['paused']}", f"сегодня {snap['spent_today']:.0f} {cur}"]
    for p in snap["projects"]:
        if "note" in p:
            parts.append(f"{p['name']}: {p['note']}")
        elif p["pct"] is None:
            parts.append(f"{p['name']}: план {p['plan_budget']:.0f}, завершённых дней нет")
        else:
            parts.append(f"{p['name']}: потрачено {p['spent_done']:.0f} при линейном плане на сегодня {p['expected']:.0f} "
                         f"({p['pct']}%) → {p['verdict']}; план месяца {p['plan_budget']:.0f}")
    lines = [f"{name} / google_ads: " + "; ".join(parts) + f" | снимок {at:%d.%m %H:%M}{flag}"]
    if snap["paused_with_spend"]:
        lines.append("  ВНИМАНИЕ: на паузе, но с расходом сегодня: " + ", ".join(snap["paused_with_spend"]))
    if detail:
        for c in snap["enabled"]:
            lines.append(f"  - включена: {c['name']} (бюджет {c['budget']:.0f}/день)")
    return "\n".join(lines)


def get_snapshot(cdir, channel, cfg, offline, ttl):
    path = cdir / "Статистика" / f"channel_snapshot_{channel}.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if cached and (offline or is_fresh(parse_dt(cached["fetched_at"]), ttl)):
        return cached, False
    if offline:
        return None, False
    try:
        snap = snapshot_google_ads(cdir, cfg)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        return snap, False
    except Exception as e:  # лимит API (П-001), сеть, права - остаётся кэш с пометкой
        print(f"  [{cdir.name}/{channel}: кабинет прочитать не удалось: {type(e).__name__}: {str(e)[:200]}]")
        return cached, True


SNAPSHOT_READERS = {"google_ads"}


# ---------- Google Ads: блок направления ----------

def direction_google_ads(cfg):
    client, ga = google_client()
    E = client.enums
    cid = str(cfg["customer_id"]).replace("-", "")
    camp_ids = [str(x) for x in cfg.get("campaign_ids", [])]
    group_names = list(cfg.get("ad_groups", []))
    expect = (cfg.get("expect") or {}).get("campaign_status")
    lines, issues = [], []
    ids = ", ".join(camp_ids)
    seen = set()
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, campaign_budget.amount_micros, "
            f"metrics.cost_micros, metrics.impressions, metrics.clicks FROM campaign WHERE campaign.id IN ({ids}) AND segments.date DURING TODAY")):
        st = E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status)
        strat = E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(r.campaign.bidding_strategy_type)
        seen.add(str(r.campaign.id))
        lines.append(f"- Кампания `{r.campaign.id}` {r.campaign.name}: **{st}**, бюджет {r.campaign_budget.amount_micros / 1e6:.0f}/день, "
                     f"стратегия {strat}; сегодня (по поясу аккаунта) расход {r.metrics.cost_micros / 1e6:.2f}, "
                     f"показы {r.metrics.impressions}, клики {r.metrics.clicks}")
        if expect and st != expect:
            issues.append(f"кампания {r.campaign.id}: в карточке ожидается {expect}, в кабинете {st}")
    for c in camp_ids:
        if c not in seen:
            lines.append(f"- Кампания `{c}`: в кабинете не найдена или нет строки за сегодня")
            issues.append(f"кампания {c} не найдена в кабинете")
    since = (now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    until = (now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    shown = 0
    for r in ga.search(customer_id=cid, query=(
            "SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, change_event.changed_fields, "
            "change_event.campaign, change_event.old_resource, change_event.new_resource FROM change_event "
            f"WHERE change_event.change_resource_type = 'CAMPAIGN' AND change_event.change_date_time >= '{since}' "
            f"AND change_event.change_date_time <= '{until}' ORDER BY change_event.change_date_time DESC LIMIT 200")):
        ev = r.change_event
        if ev.campaign.split("/")[-1] not in camp_ids or "status" not in list(ev.changed_fields.paths):
            continue
        old = E.CampaignStatusEnum.CampaignStatus.Name(ev.old_resource.campaign.status)
        new = E.CampaignStatusEnum.CampaignStatus.Name(ev.new_resource.campaign.status)
        lines.append(f"- Смена статуса {ev.change_date_time[:19]}: {old} → {new} ({ev.user_email or '-'}, "
                     f"{E.ChangeClientTypeEnum.ChangeClientType.Name(ev.client_type)})")
        shown += 1
        if shown >= 3:
            break
    if shown == 0:
        lines.append("- Смен статуса кампании за 7 дней в истории кабинета нет")
    if group_names:
        agg, today = {}, str(now().date())
        for r in ga.search(customer_id=cid, query=(
                "SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros, campaign.id, segments.date, "
                f"metrics.cost_micros, metrics.impressions, metrics.clicks FROM ad_group WHERE campaign.id IN ({ids}) "
                "AND ad_group.status != 'REMOVED' AND segments.date DURING LAST_7_DAYS")):
            a = agg.setdefault(r.ad_group.id, {"name": r.ad_group.name, "status": r.ad_group.status, "bid": r.ad_group.cpc_bid_micros / 1e6,
                                               "camp": r.campaign.id, "cost": 0.0, "imp": 0, "clk": 0})
            a["cost"] += r.metrics.cost_micros / 1e6
            a["imp"] += r.metrics.impressions
            a["clk"] += r.metrics.clicks
        for name in group_names:
            found = [a for a in agg.values() if a["name"] == name]
            if not found:
                lines.append(f"- Группа «{name}»: в кабинете за 7 дней строк нет (нет показов или группы нет)")
                issues.append(f"группа «{name}»: строк в кабинете за 7 дней нет")
            for a in found:
                st = E.AdGroupStatusEnum.AdGroupStatus.Name(a["status"])
                lines.append(f"- Группа «{a['name']}» (кампания {a['camp']}): **{st}**, ставка ${a['bid']:.0f}; "
                             f"за 7 дней показы {a['imp']}, клики {a['clk']}, расход {a['cost']:.2f}")
    return "\n".join(lines), issues


DIRECTION_READERS = {"google_ads": direction_google_ads}


# ---------- карточка направления ----------

def read_auto(body):
    m = AUTO_RE.search(body)
    return {ch: (at, txt) for ch, at, txt in CH_RE.findall(m.group(1))} if m else {}


def write_auto(path, text, blocks):
    st = path.stat()
    inner = "\n".join(f"<!-- CH:{ch} fetched_at={at} -->\n{txt}\n<!-- /CH -->" for ch, (at, txt) in blocks.items())
    new = AUTO_RE.sub(lambda m: f"<!-- AUTO:start -->\n{inner}\n<!-- AUTO:end -->", text, count=1)
    path.write_text(new, encoding="utf-8")
    os.utime(path, (st.st_atime, st.st_mtime))  # mtime карточки = последняя РУЧНАЯ правка, иначе проверка устаревания слепнет


def stale_sources(cdir, card_path):
    t0 = card_path.stat().st_mtime
    files = [cdir / n for n in WATCH] + sorted(cdir.glob("Хроника_*.md"))[-1:]
    return [f.name for f in files if f.exists() and f.stat().st_mtime > t0]


def show_direction(path, only_channel, offline, ttl):
    meta, body, text = read_card(path)
    cdir = path.parent.parent
    chans = meta.get("channels") or {}
    base = read_channels(cdir)
    print(f"=== {meta.get('client')} / {meta.get('direction')}" + (f" / {only_channel}" if only_channel else "") + " ===")
    print(f"Статус: {meta.get('status')}\nБлокер: {meta.get('blocker')}\nДальше: {meta.get('next')}\nКарточка от: {meta.get('updated')}")
    blocks, issues, dirty = read_auto(body), [], False
    if only_channel and only_channel not in chans:
        print(f"\nКанал {only_channel} в карточке не заведён. Заведены: {', '.join(chans) or 'нет'}")
    for ch, cfg in chans.items():
        if only_channel and ch != only_channel:
            continue
        cfg = {**(base.get(ch) or {}), **(cfg or {})}  # customer_id берётся из Каналы.yaml клиента, если в карточке не задан
        if ch not in DIRECTION_READERS:
            print(f"\n--- {ch} ---\nчитатель канала не подключён: статус только из ручной части карточки (с её датой)")
            continue
        at = parse_dt(blocks.get(ch, (None, ""))[0])
        if offline or is_fresh(at, ttl):
            note = f"[{ch}: кэш от {at:%d.%m %H:%M}]" if at else f"[{ch}: кэша нет, режим offline]"
            print("\n" + note)
        else:
            try:
                txt, iss = DIRECTION_READERS[ch](cfg)
                blocks[ch] = (now().isoformat(timespec="minutes"), f"**Кабинет {ch} на {now():%d.%m %H:%M} (Варшава)**, чтение `status.py`:\n{txt}")
                issues += [f"[{ch}] {i}" for i in iss]
                dirty = True
                print(f"\n[{ch}: кабинет прочитан и записан в карточку]")
            except Exception as e:  # лимит API (П-001), сеть, права - остаётся прежний блок
                print(f"\n[{ch}: кабинет прочитать не удалось: {type(e).__name__}: {str(e)[:300]}]\n"
                      f"[в данных этого нет: статус берётся из ручной части карточки с её датой]")
        if ch in blocks:
            print(f"--- {ch} (автоматически, кэш) ---\n" + blocks[ch][1])
    if dirty:
        write_auto(path, text, blocks)
    if issues:
        print("\n--- РАСХОЖДЕНИЯ ---")
        for i in issues:
            print("РАСХОЖДЕНИЕ: " + i)
    stale = stale_sources(cdir, path)
    if stale:
        print("\nПроверь, не устарела ли ручная часть: после последней правки карточки менялись файлы: " + ", ".join(stale))
    _, body, _ = read_card(path)
    print("\n--- Карточка (ручная часть) ---" + AUTO_RE.sub("", body, count=1).rstrip())


def direction_line(meta, path, only_channel=None):
    chans = ", ".join(meta.get("channels") or {}) or "-"
    return (f"{meta.get('client', path.parent.parent.name)} / {meta.get('direction', path.stem)} [каналы: {chans}]: "
            f"{meta.get('status', '?')} | блокер: {meta.get('blocker', '-')} | дальше: {meta.get('next', '-')} | карточка от {meta.get('updated', '?')}")


# ---------- точка входа ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--client")
    ap.add_argument("--direction")
    ap.add_argument("--channel")
    ap.add_argument("--offline", action="store_true", help="только кэш, без обращений к кабинетам")
    ap.add_argument("--ttl-hours", type=float, default=6)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.direction:
        if not a.client:
            ap.error("--direction требует --client")
        cands = [p for p in cards_of(CLIENTS / a.client) if p.stem.lower() == a.direction.lower()]
        if not cands:
            sys.exit(f"карточки {a.direction} у клиента {a.client} нет. Есть: {', '.join(p.stem for p in cards_of(CLIENTS / a.client)) or 'карточек нет'}")
        return show_direction(cands[0], a.channel, a.offline, a.ttl_hours)
    if not (a.all or a.client):
        ap.error("нужно --all, либо --client X, либо --client X --direction Y")
    detail = bool(a.client)
    print("=== Аккаунты в каналах ===")
    shown = 0
    for cdir in client_dirs(a.client):
        for ch, cfg in read_channels(cdir).items():
            if a.channel and ch != a.channel:
                continue
            if ch not in SNAPSHOT_READERS:
                print(f"{cdir.name} / {ch}: читатель канала не подключён")
                continue
            snap, stale = get_snapshot(cdir, ch, cfg, a.offline, a.ttl_hours)
            print(render_snapshot(cdir.name, snap, detail, stale) if snap else f"{cdir.name} / {ch}: снимка нет (режим offline или чтение не удалось)")
            shown += 1
    if not shown:
        print("подключённых каналов нет (ищу Клиенты/<Имя>/Каналы.yaml)")
    print("\n=== Направления ===")
    n = 0
    for cdir in client_dirs(a.client):
        for p in cards_of(cdir):
            meta, _, _ = read_card(p)
            if a.channel and a.channel not in (meta.get("channels") or {}):
                continue
            print(direction_line(meta, p))
            n += 1
    if not n:
        print("карточек направлений нет")


if __name__ == "__main__":
    main()
