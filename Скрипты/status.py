"""Статус направления/клиента/проекта из карточек `Клиенты/<Имя>/Направления/*.md`.

Только чтение кабинета, модель не нужна. Что делает:
  --all                         одна строка на каждое направление всех клиентов (карточки, без запросов в кабинет);
  --client X                    то же по клиенту X;
  --client X --direction Y      полная карточка + свежий автоматический блок + проверки.

Автоматический блок (между <!-- AUTO:start --> и <!-- AUTO:end -->) - кэш состояния кабинета Google Ads:
статус и бюджет кампаний, статус/ставка/показы/клики/расход групп. Старше --ttl-hours (по умолчанию 6)
или нет вовсе - запрашивается заново и записывается в карточку; --offline не ходит в кабинет.

Проверки (считает скрипт, не модель):
  - ожидание карточки (`expect.campaign_status`) против кабинета - строка «РАСХОЖДЕНИЕ»;
  - группа из карточки не найдена в кабинете;
  - файлы вики клиента, изменённые позже карточки, - «проверь, не устарела ли карточка».

Формат карточки: см. `Клиенты/Andverpersonalinjury/Направления/Motorcycle.md`.
Запуск из любой папки: python Скрипты/status.py --client Andverpersonalinjury --direction Motorcycle
"""
import argparse
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
AUTO_RE = re.compile(r"(<!-- AUTO:start -->)(.*?)(<!-- AUTO:end -->)", re.S)
WATCH = ["Журнал_изменений.md", "Решения.md", "Задачи.md", "Паспорт.md", "Эксперименты.md"]


def read_card(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path}: нет frontmatter")
    return yaml.safe_load(m.group(1)) or {}, m.group(2), text


def cards_of(client_dir):
    d = client_dir / "Направления"
    return sorted(d.glob("*.md")) if d.is_dir() else []


def one_line(meta, path):
    return (f"{meta.get('client', path.parent.parent.name)} / {meta.get('direction', path.stem)}: "
            f"{meta.get('status', '?')} | блокер: {meta.get('blocker', '-')} | дальше: {meta.get('next', '-')} "
            f"| карточка от {meta.get('updated', '?')}")


def fetched_at(body):
    m = AUTO_RE.search(body)
    if not m:
        return None
    t = re.search(r"fetched_at: (\S+)", m.group(2))
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.group(1))
    except ValueError:
        return None


def live_block(meta):
    """Запрашивает кабинет, возвращает (текст блока, список расхождений)."""
    os.chdir(HERE)  # secrets/google-ads.yaml лежит относительно папки Скрипты
    from google.ads.googleads.client import GoogleAdsClient
    from gads_stats import GOOGLE_ADS_YAML

    live = meta.get("live") or {}
    cid = str(live.get("customer_id", "")).replace("-", "")
    camp_ids = [str(x) for x in live.get("campaign_ids", [])]
    group_names = list(live.get("ad_groups", []))
    expect = (meta.get("expect") or {}).get("campaign_status")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    now = datetime.now(TZ)
    lines, issues = [], []

    ids = ", ".join(camp_ids)
    q = ("SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, "
         "campaign_budget.amount_micros, metrics.cost_micros, metrics.impressions, metrics.clicks "
         f"FROM campaign WHERE campaign.id IN ({ids}) AND segments.date DURING TODAY")
    seen = set()
    for r in ga.search(customer_id=cid, query=q):
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

    # последняя смена статуса кампаний (история изменений хранится 30 дней)
    since = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    until = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    qe = ("SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, "
          "change_event.changed_fields, change_event.campaign, change_event.old_resource, change_event.new_resource "
          f"FROM change_event WHERE change_event.change_resource_type = 'CAMPAIGN' "
          f"AND change_event.change_date_time >= '{since}' AND change_event.change_date_time <= '{until}' "
          "ORDER BY change_event.change_date_time DESC LIMIT 200")
    shown = 0
    for r in ga.search(customer_id=cid, query=qe):
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
        qg = ("SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros, campaign.id, "
              "segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks "
              f"FROM ad_group WHERE campaign.id IN ({ids}) AND ad_group.status != 'REMOVED' "
              "AND segments.date DURING LAST_7_DAYS")
        agg = {}
        today = now.strftime("%Y-%m-%d")
        for r in ga.search(customer_id=cid, query=qg):
            a = agg.setdefault(r.ad_group.id, {"name": r.ad_group.name, "status": r.ad_group.status,
                                               "bid": r.ad_group.cpc_bid_micros / 1e6, "camp": r.campaign.id,
                                               "cost": 0.0, "imp": 0, "clk": 0, "imp_today": 0})
            a["cost"] += r.metrics.cost_micros / 1e6
            a["imp"] += r.metrics.impressions
            a["clk"] += r.metrics.clicks
            if r.segments.date == today:
                a["imp_today"] += r.metrics.impressions
        for name in group_names:
            found = [a for a in agg.values() if a["name"] == name]
            if not found:
                lines.append(f"- Группа «{name}»: в кабинете за 7 дней строк нет (нет показов или группы нет)")
                issues.append(f"группа «{name}»: строк в кабинете за 7 дней нет")
            for a in found:
                st = E.AdGroupStatusEnum.AdGroupStatus.Name(a["status"])
                lines.append(f"- Группа «{a['name']}» (кампания {a['camp']}): **{st}**, ставка ${a['bid']:.0f}; "
                             f"за 7 дней показы {a['imp']}, клики {a['clk']}, расход {a['cost']:.2f}")
    block = (f"<!-- fetched_at: {now.isoformat(timespec='minutes')} -->\n"
             f"**Кабинет Google Ads на {now:%d.%m %H:%M} (Варшава)**, чтение `status.py`:\n" + "\n".join(lines))
    return block, issues


def write_block(path, text, block):
    st = path.stat()
    new = AUTO_RE.sub(lambda m: f"{m.group(1)}\n{block}\n{m.group(3)}", text, count=1)
    path.write_text(new, encoding="utf-8")
    os.utime(path, (st.st_atime, st.st_mtime))  # mtime карточки = последняя РУЧНАЯ правка, иначе проверка устаревания слепнет


def stale_sources(client_dir, card_path):
    t0 = card_path.stat().st_mtime
    files = [client_dir / n for n in WATCH]
    files += sorted(client_dir.glob("Хроника_*.md"))[-1:]
    return [f.name for f in files if f.exists() and f.stat().st_mtime > t0]


def show_direction(path, offline, ttl):
    meta, body, text = read_card(path)
    print(f"=== {meta.get('client')} / {meta.get('direction')} ===")
    print(f"Статус: {meta.get('status')}\nБлокер: {meta.get('blocker')}\nДальше: {meta.get('next')}\nКарточка от: {meta.get('updated')}")
    issues = []
    fa = fetched_at(body)
    fresh = fa is not None and (datetime.now(TZ) - (fa if fa.tzinfo else fa.replace(tzinfo=TZ))) < timedelta(hours=ttl)
    if meta.get("live") and not offline and not fresh:
        try:
            block, issues = live_block(meta)
            write_block(path, text, block)
            print("\n[кабинет прочитан и записан в карточку]")
        except Exception as e:  # лимит API (П-001), сеть, права - карточка остаётся как есть
            print(f"\n[кабинет прочитать не удалось: {type(e).__name__}: {str(e)[:300]}]")
            print("[в данных этого нет: статус кампании берётся из ручной части карточки с её датой]")
    elif meta.get("live") and fresh:
        print(f"\n[автоблок свежий: {fa:%d.%m %H:%M}, повторный запрос не нужен; --ttl-hours 0 заставит перечитать]")
    _, body, _ = read_card(path)
    m = AUTO_RE.search(body)
    if m:
        print("\n--- Кабинет (автоматически) ---" + m.group(2).rstrip())
    if issues:
        print("\n--- РАСХОЖДЕНИЯ ---")
        for i in issues:
            print("РАСХОЖДЕНИЕ: " + i)
    stale = stale_sources(path.parent.parent, path)
    if stale:
        print("\nПроверь, не устарела ли ручная часть: после последней правки карточки менялись файлы: " + ", ".join(stale))
    rest = AUTO_RE.sub("", body, count=1)
    print("\n--- Карточка (ручная часть) ---" + rest.rstrip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="по одной строке на каждое направление всех клиентов")
    ap.add_argument("--client")
    ap.add_argument("--direction")
    ap.add_argument("--offline", action="store_true", help="не ходить в кабинет")
    ap.add_argument("--ttl-hours", type=float, default=6)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if a.all or (a.client and not a.direction):
        dirs = sorted(d for d in CLIENTS.iterdir() if d.is_dir() and not d.name.startswith("_"))
        if a.client:
            dirs = [CLIENTS / a.client]
        n = 0
        for d in dirs:
            for p in cards_of(d):
                meta, _, _ = read_card(p)
                print(one_line(meta, p))
                n += 1
        if n == 0:
            print("карточек направлений нет (ищу Клиенты/<Имя>/Направления/*.md)")
        return
    if not (a.client and a.direction):
        ap.error("нужно --all, либо --client X, либо --client X --direction Y")
    cands = [p for p in cards_of(CLIENTS / a.client) if p.stem.lower() == a.direction.lower()]
    if not cands:
        names = ", ".join(p.stem for p in cards_of(CLIENTS / a.client)) or "карточек нет"
        sys.exit(f"карточки {a.direction} у клиента {a.client} нет. Есть: {names}")
    show_direction(cands[0], a.offline, a.ttl_hours)


if __name__ == "__main__":
    main()
