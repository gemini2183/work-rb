#!/usr/bin/env python
# coding: utf-8
"""Офлайн-выгрузка уникальных звонков Ringostat в Google Ads по gclid через Data Manager API (ProfiMet).

Зачем: оптимизировать автоставки по уникальным звонкам (без повторов) и не терять звонки без согласия на cookie
(через GA4 доходило ~64%, gclid есть у ~78% уникальных звонков Google Ads: он лежит в метке `utm_content`
как `gclid_<значение>`). Решение пользователя 2026-10-09.

Режимы (все по умолчанию БЕЗ записи):
  --create-action            создать конверсию «Ringostat — уникальный звонок (офлайн, gclid)»: загрузка кликов, категория
                             «телефонный лид», один звонок на клик, окно 90 дней, ВТОРИЧНАЯ (не основная), чтобы не менять
                             ставки кампаний, пока не заведена пользовательская цель. Основной её делает отдельный шаг.
  --upload                   выгрузить уникальные звонки Google Ads с gclid за период (по умолчанию 90 дней назад → сейчас).
Без --execute ничего не пишется (для --upload — проверка Data Manager API `validateOnly`). Токен — secrets/datamanager_token.json (скрипт datamanager_auth.py). Выгруженное записывается в
реестр `Статистика/offline_unique_calls_uploaded.csv` (id звонка Ringostat = order_id), повторно не отправляется.

Использование:
    python gads_offline_unique_calls.py --customer-id 7552781705 --client-folder ProfiMet --create-action [--execute]
    python gads_offline_unique_calls.py --customer-id 7552781705 --client-folder ProfiMet --upload [--days 90] [--execute]
"""
import argparse
import csv
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from ringostat_stats_profimet import AUTH_KEY

ACTION_NAME = "Ringostat — уникальный звонок (офлайн, gclid)"
TZ = ZoneInfo("Europe/Warsaw")
FIELDS = "calldate,caller,disposition,billsec,duration,call_type,uniqueid,utm_source,utm_medium,utm_campaign,utm_content,pool_name,unique_call"
LEDGER_NAME = "offline_unique_calls_uploaded.csv"
GCLID_RE = re.compile(r"gclid[_=]([A-Za-z0-9_\-]{20,})")


def find_action(client, ga, cid):
    q = ("SELECT conversion_action.resource_name, conversion_action.id, conversion_action.status, conversion_action.primary_for_goal "
         f"FROM conversion_action WHERE conversion_action.name = '{ACTION_NAME}' AND conversion_action.status != 'REMOVED'")
    for r in ga.search(customer_id=cid, query=q):
        return r.conversion_action
    return None


def create_action(client, ga, cid, execute):
    E = client.enums
    existing = find_action(client, ga, cid)
    if existing:
        print("Конверсия уже есть:", existing.resource_name, "| основная:", existing.primary_for_goal)
        return
    op = client.get_type("ConversionActionOperation")
    a = op.create
    a.name = ACTION_NAME
    a.type_ = E.ConversionActionTypeEnum.UPLOAD_CLICKS
    a.category = E.ConversionActionCategoryEnum.PHONE_CALL_LEAD
    a.status = E.ConversionActionStatusEnum.ENABLED
    a.counting_type = E.ConversionActionCountingTypeEnum.ONE_PER_CLICK
    a.click_through_lookback_window_days = 90
    a.primary_for_goal = False
    req = client.get_type("MutateConversionActionsRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not execute
    try:
        resp = client.get_service("ConversionActionService").mutate_conversion_actions(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:5]:
            print("  -", err.message)
        raise SystemExit(1)
    if not execute:
        print("Проверка создания конверсии пройдена. НИЧЕГО не создано (validate_only).")
        return
    print("Создана:", resp.results[0].resource_name)
    got = find_action(client, ga, cid)
    print("Прочитано обратно:", got.resource_name, "| статус", E.ConversionActionStatusEnum.ConversionActionStatus.Name(got.status),
          "| основная:", got.primary_for_goal)


def fetch_calls(date_from, date_to):
    r = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": f"{date_from} 00:00:00", "to": f"{date_to} 23:59:59", "fields": FIELDS},
        headers={"Content-Type": "application/json; charset=utf-8", "Auth-key": AUTH_KEY},
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    return df


def load_ledger(path):
    if not path.exists():
        return set()
    with open(path, encoding="utf-8-sig") as f:
        return {row["uniqueid"] for row in csv.DictReader(f)}


DM_URL = "https://datamanager.googleapis.com/v1/events:ingest"
ACTION_ID = None  # числовой id конверсии, определяется по имени
LOGIN_ACCOUNT = "3023486398"  # менеджерский аккаунт (login_customer_id из secrets/google-ads.yaml)
BATCH = 2000


def dm_headers():
    t = json.load(open(Path(__file__).resolve().parent / "secrets" / "datamanager_token.json", encoding="utf-8"))
    tok = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": t["client_id"], "client_secret": t["client_secret"],
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}).json()
    return {"Authorization": "Bearer " + tok["access_token"], "Content-Type": "application/json"}


def send_batch(headers, cid, action_id, events, execute):
    """Отправляет пачку. Data Manager отвергает ВСЮ пачку при ошибке формата — плохие события выбрасываем и повторяем."""
    bad = {}
    work = list(enumerate(events))
    while work:
        body = {"destinations": [{"operatingAccount": {"accountType": "GOOGLE_ADS", "accountId": cid},
                                  "loginAccount": {"accountType": "GOOGLE_ADS", "accountId": LOGIN_ACCOUNT},
                                  "productDestinationId": str(action_id)}],
                "events": [e for _, e in work], "validateOnly": not execute}
        r = requests.post(DM_URL, headers=headers, json=body)
        if r.status_code == 200:
            return r.json().get("requestId", ""), bad, [i for i, _ in work]
        try:
            details = r.json()["error"].get("details", [])
            idx = [int(m) for d in details for v in d.get("fieldViolations", [])
                   for m in re.findall(r"events\[(\d+)\]", v.get("field", ""))]
            msg = r.json()["error"]["message"]
        except Exception:
            raise SystemExit(f"ОШИБКА Data Manager API {r.status_code}: {r.text[:300]}")
        if not idx:
            raise SystemExit(f"ОШИБКА Data Manager API {r.status_code}: {msg[:300]}")
        drop = {work[k][0] for k in set(idx) if k < len(work)}
        for orig in drop:
            bad[orig] = msg[:120]
        work = [(o, e) for o, e in work if o not in drop]
    return "", bad, []


def upload(client, ga, cid, folder, days, execute):
    action = find_action(client, ga, cid)
    if not action:
        raise SystemExit("конверсия не создана: сначала --create-action --execute")
    action_id = action.id
    date_to = datetime.now(TZ)
    date_from = date_to - timedelta(days=days)
    df = fetch_calls(date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d"))
    print("звонков Ringostat за период:", len(df))
    for c in ("utm_source", "utm_medium", "utm_content", "utm_campaign", "pool_name"):
        df[c] = df[c].fillna("")
    df["unique_call"] = df["unique_call"].astype(int)
    g = df[(df.utm_source == "google") & (df.utm_medium == "cpc") & (df.unique_call == 1)].copy()
    g["gclid"] = g.utm_content.map(lambda s: (GCLID_RE.search(s).group(1) if GCLID_RE.search(s) else None))
    with_gclid = g[g.gclid.notna()].copy()
    print(f"уникальных Google CPC: {len(g)}; с gclid: {len(with_gclid)}; без gclid: {len(g) - len(with_gclid)}")
    ledger_path = client_stats_dir(folder) / LEDGER_NAME
    done = load_ledger(ledger_path)
    todo = with_gclid[~with_gclid.uniqueid.astype(str).isin(done)].copy()
    print("уже выгружено ранее:", len(with_gclid) - len(todo), "| к выгрузке:", len(todo))
    if todo.empty:
        return
    todo["start"] = pd.to_datetime(todo.calldate, utc=True).dt.tz_convert(TZ)
    todo = todo[todo.start < datetime.now(TZ) - timedelta(minutes=10)]
    print("по кампаниям (utm_campaign):", todo.utm_campaign.value_counts().head(8).to_dict())

    rows = list(todo.itertuples())
    events = [{"adIdentifiers": {"gclid": r.gclid}, "eventTimestamp": r.start.isoformat(),
               "transactionId": str(r.uniqueid), "eventSource": "PHONE"} for r in rows]
    headers = dm_headers()
    sent_rows, failed_rows, request_ids = [], [], []
    for i in range(0, len(events), BATCH):
        chunk_rows, chunk_ev = rows[i:i + BATCH], events[i:i + BATCH]
        rid, bad, ok_idx = send_batch(headers, cid, action_id, chunk_ev, execute)
        request_ids.append(rid)
        failed_rows += [(chunk_rows[k], msg) for k, msg in bad.items()]
        sent_rows += [(chunk_rows[k], rid) for k in ok_idx]
    print(f"{'отправлено' if execute else 'проверка пройдена'}: принято {len(sent_rows)}, отвергнуто при проверке формата {len(failed_rows)}")
    for r, msg in failed_rows[:8]:
        print("  отвергнуто:", r.uniqueid, r.utm_campaign, msg)
    if not execute:
        print("НИЧЕГО не выгружено (validateOnly).")
        return
    new = not ledger_path.exists()
    with open(ledger_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["uniqueid", "uploaded_at", "call_time", "utm_campaign", "pool_name", "gclid_prefix", "result"])
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        for r, rid in sent_rows:
            w.writerow([r.uniqueid, now, r.start.isoformat(), r.utm_campaign, r.pool_name, r.gclid[:12], "отправлено " + rid])
        for r, msg in failed_rows:
            w.writerow([r.uniqueid, now, r.start.isoformat(), r.utm_campaign, r.pool_name, r.gclid[:12], "отвергнуто: " + msg])
    print("Реестр:", ledger_path, "| requestId:", request_ids[:3])
    print("Обработка событий в Google идёт асинхронно: конверсии появятся в отчётах через несколько часов.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--create-action", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — только проверка")
    ap.add_argument("--loop-min", type=int, default=0, help="повторять --upload каждые N минут, пока процесс открыт (0 = один раз)")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    if args.create_action:
        create_action(client, ga, cid, args.execute)
    if args.upload:
        while True:
            print(datetime.now(TZ).strftime("[%Y-%m-%d %H:%M:%S]"), "запуск выгрузки", flush=True)
            upload(client, ga, cid, args.client_folder, args.days, args.execute)
            if not args.loop_min:
                break
            import time
            time.sleep(args.loop_min * 60)


if __name__ == "__main__":
    main()
