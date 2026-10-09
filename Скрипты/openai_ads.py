#!/usr/bin/env python
# coding: utf-8
"""Чтение статистики и смена ставок в OpenAI Ads (реклама в ChatGPT) через Ads API.

Подкоманды:
    groups   — группы кампании: статус и ставка;
    insights — показы/клики/расход/CTR/CPC по группам (или кампании) за период;
    set-bid  — смена fixed_bid у групп кампании.
    set-maxclicks — перевод групп на maximize_clicks (без ставки; формат взят у групп dog bite).

БЕЗОПАСНОСТЬ: set-bid по умолчанию только показывает план «было → станет» и ничего
не пишет. Реальная запись — только с флагом --execute, после неё группы читаются
обратно и печатается фактическое состояние. Другие записи (создание, активация,
бюджеты) сюда сознательно не входят.

Ключ: переменная окружения OPENAI_ADS_API_KEY; если процесс её не видит (VS Code не
перезапускали после setx) — читается из пользовательской области Windows. Значение
ключа нигде не печатается. HTTP — через curl: Python urllib получает 403 (блок по
User-Agent).

Использование:
    python openai_ads.py groups   --campaign cmpn_...
    python openai_ads.py insights --campaign cmpn_... --since 2026-10-07 --until 2026-10-08
    python openai_ads.py insights --campaign cmpn_... --since 2026-10-07 --until 2026-10-08 --granularity hourly --level campaign
    python openai_ads.py set-bid  --campaign cmpn_... --bid 7              # план
    python openai_ads.py set-bid  --campaign cmpn_... --bid 7 --execute    # запись
"""
import argparse
import json
import os
import subprocess
import sys

BASE = "https://api.ads.openai.com/v1"
KEY_ENV = "OPENAI_ADS_API_KEY"


def get_key():
    key = os.environ.get(KEY_ENV)
    if not key and sys.platform == "win32":
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"[Environment]::GetEnvironmentVariable('{KEY_ENV}','User')"],
            capture_output=True, text=True)
        key = out.stdout.strip()
    if not key:
        sys.exit(f"Нет ключа: задайте переменную {KEY_ENV} (setx) и перезапустите VS Code")
    return key


def call(method, path, params=None, body=None):
    cmd = ["curl", "-sS", "-X", method, "-w", "\n%{http_code}",
           "-H", f"Authorization: Bearer {get_key()}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    url = BASE + path
    if params:
        cmd.append("-G")
        for k, v in params:
            cmd += ["--data-urlencode", f"{k}={v}"]
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    text, _, code = res.stdout.rpartition("\n")
    if not code.startswith("2"):
        sys.exit(f"HTTP {code} {method} {path}: {text[:500]}")
    return json.loads(text)


def list_groups(campaign):
    return call("GET", "/ad_groups", [("campaign_id", campaign)])["data"]


def bid_text(g):
    b = g.get("bidding_config") or {}
    return f"{b.get('strategy')} ${(b.get('max_bid_micros') or 0) / 1e6:g}"


def cmd_groups(a):
    for g in list_groups(a.campaign):
        print(f"{g['id']}  {g['name']}  {g['status']}  {bid_text(g)}")


def cmd_insights(a):
    level = a.level
    fields = ["campaign.name", "impressions", "clicks", "spend", "ctr", "cpc"]
    if a.granularity != "none":  # при none поле времени API не принимает
        fields.insert(0, "metadata.readable_time")
    if level == "ad_group":
        fields[1:1] = ["ad_group.id", "ad_group.name"]
    params = [("time_granularity", a.granularity), ("aggregation_level", level)]
    params += [("fields[]", f) for f in fields]
    params.append(("time_ranges[]", json.dumps(
        {"type": "date_range", "since": a.since, "until": a.until})))
    params.append(("filters[]", json.dumps(
        {"field": "campaign.id", "operator": "IN", "value": [a.campaign]})))
    rows = call("GET", "/ad_account/insights", params)["data"]
    tot = {"impressions": 0, "clicks": 0, "spend": 0.0}
    for r in rows:
        name = r.get("ad_group_name") or r.get("campaign_name")
        print(f"{r.get('readable_time') or ''}  {name}  показы {r['impressions']}  клики {r['clicks']}  "
              f"расход ${r['spend']:.2f}  CTR {r['ctr']}  CPC ${r['cpc']:.2f}")
        for k in tot:
            tot[k] += r[k]
    print(f"ИТОГО строк {len(rows)}: показы {tot['impressions']}, клики {tot['clicks']}, расход ${tot['spend']:.2f}")


def cmd_set_bid(a):
    micros = int(round(a.bid * 1_000_000))
    groups = list_groups(a.campaign)
    if a.groups:
        wanted = set(a.groups)
        groups = [g for g in groups if g["id"] in wanted]
    if not groups:
        sys.exit("Группы не найдены")
    print("Объект | Действие | Было → Станет")
    for g in groups:
        print(f"{g['name']} ({g['id']}) | fixed_bid | {bid_text(g)} → fixed_bid ${a.bid:g}")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    for g in groups:
        call("POST", f"/ad_groups/{g['id']}", body={"bidding_config": {
            "strategy": "fixed_bid", "billing_event_type": "click", "max_bid_micros": micros}})
    print("\nПрочитано обратно из аккаунта:")
    after = {g["id"]: g for g in list_groups(a.campaign)}
    for g in groups:
        print(f"{after[g['id']]['name']}  {after[g['id']]['status']}  {bid_text(after[g['id']])}")


def cmd_set_maxclicks(a):
    groups = list_groups(a.campaign)
    if a.groups:
        wanted = set(a.groups)
        groups = [g for g in groups if g["id"] in wanted]
    if not groups:
        sys.exit("Группы не найдены")
    print("Объект | Действие | Было → Станет")
    for g in groups:
        print(f"{g['name']} ({g['id']}) | тип ставки | {bid_text(g)} → maximize_clicks (без ставки)")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    for g in groups:
        call("POST", f"/ad_groups/{g['id']}", body={"bidding_config": {
            "strategy": "maximize_clicks", "billing_event_type": "click"}})
    print("\nПрочитано обратно из аккаунта:")
    after = {g["id"]: g for g in list_groups(a.campaign)}
    for g in groups:
        print(f"{after[g['id']]['name']}  {after[g['id']]['status']}  {bid_text(after[g['id']])}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("groups"); g.add_argument("--campaign", required=True); g.set_defaults(f=cmd_groups)
    i = sub.add_parser("insights"); i.add_argument("--campaign", required=True)
    i.add_argument("--since", required=True); i.add_argument("--until", required=True)
    i.add_argument("--level", default="ad_group", choices=["campaign", "ad_group", "ad"])
    i.add_argument("--granularity", default="none", choices=["none", "daily", "hourly", "monthly"])
    i.set_defaults(f=cmd_insights)
    s = sub.add_parser("set-bid"); s.add_argument("--campaign", required=True)
    s.add_argument("--bid", required=True, type=float, help="ставка в долларах")
    s.add_argument("--groups", nargs="*", help="ID групп; по умолчанию все группы кампании")
    s.add_argument("--execute", action="store_true"); s.set_defaults(f=cmd_set_bid)
    m = sub.add_parser("set-maxclicks"); m.add_argument("--campaign", required=True)
    m.add_argument("--groups", nargs="*", help="ID групп; по умолчанию все группы кампании")
    m.add_argument("--execute", action="store_true"); m.set_defaults(f=cmd_set_maxclicks)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
