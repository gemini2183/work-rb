#!/usr/bin/env python
# coding: utf-8
"""Тег GTM «Supabase - Leads»: добавить в отправку `gclid`, `utm_content`, `page_url`. ЗАПИСЬ в черновик GTM (2026-10-27).

Клиенты: ProfiMet (GTM-TKGN4NT, таблица profimet_leads), ExpertAgro (GTM-5FBCZLMC, таблица expertagro_leads).
ПЕРЕД публикацией в таблице Supabase должны существовать колонки gclid, utm_content, page_url (иначе Supabase отклонит запись
и заявки перестанут сохраняться). Скрипт сам читает таблицу и останавливается, если колонок нет.
`gclid` и `utm_content` берутся из адреса страницы, а если их там нет — из `localStorage.rb_utm` (его пишет тег «UTM - сохранить
в браузере», 30 дней, при согласии ad_storage); `page_url` — адрес страницы в момент отправки (первые 1000 знаков).

Без --execute: только проверка (живая версия, последняя версия, текст тега, колонки). С --execute: создаёт НОВУЮ рабочую
область, правит тег, делает версию контейнера. НЕ публикует: публикация — `gtm_publish_version.py`, после теста и «да».
Использование (из папки Скрипты):
    PYTHONUTF8=1 python gtm_supabase_leads_columns.py --client ProfiMet            # проверка
    PYTHONUTF8=1 python gtm_supabase_leads_columns.py --client ProfiMet --execute  # черновик + версия
"""
import argparse
from pathlib import Path

import requests
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions"]
MON_CFG = "E:/PythonProjects/RedBird/monitoring scripts/monitoring/config/"
CLIENTS = {
    "ProfiMet": dict(account="6003760261", container="44158621", table="profimet_leads", cfg="profimet.yaml"),
    "ExpertAgro": dict(account="6326663960", container="236673117", table="expertagro_leads", cfg="experagro.yaml"),
}
SB_TAG = "Supabase - Leads"
NEW_COLS = ["gclid", "utm_content", "page_url"]
OLD = """    utm_campaign: {{utm_campaign}} || stored.utm_campaign || ''
  });"""
NEW = """    utm_campaign: {{utm_campaign}} || stored.utm_campaign || '',
    utm_content: q.get('utm_content') || stored.utm_content || '',
    gclid: q.get('gclid') || stored.gclid || '',
    page_url: String(window.location.href || '').substring(0, 1000)
  });"""
OLD_Q = "  var payload = JSON.stringify({"
NEW_Q = "  var q = new URLSearchParams(window.location.search);\n  var payload = JSON.stringify({"


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def param(items, key):
    return next(p["value"] for p in items if p["key"] == key)


def set_param(items, key, value):
    for p in items:
        if p["key"] == key:
            p["value"] = value
            return
    items.append({"type": "template", "key": key, "value": value})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, choices=list(CLIENTS))
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    c = CLIENTS[a.client]
    cont = f"accounts/{c['account']}/containers/{c['container']}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))

    # колонки Supabase (ключ читается из конфига мониторинга, не печатается)
    sb = yaml.safe_load(open(MON_CFG + c["cfg"], encoding="utf-8"))["supabase"]
    r = requests.get(f"{sb['url']}/rest/v1/{c['table']}", timeout=60, params={"select": "*", "limit": 1},
                     headers={"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]})
    r.raise_for_status()
    have = list(r.json()[0].keys()) if r.json() else []
    missing = [x for x in NEW_COLS if x not in have]

    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    tag = next((t for t in live["tag"] if t["name"] == SB_TAG), None)
    errors = []
    if missing:
        errors.append(f"в таблице {c['table']} нет колонок {missing}")
    if not tag:
        errors.append(f"нет тега «{SB_TAG}»")
    else:
        html = param(tag["parameter"], "html")
        if OLD not in html or OLD_Q not in html:
            errors.append("текст тега не совпадает с ожидаемым (кто-то менял) — остановка")
        if "page_url" in html:
            errors.append("тег уже отправляет page_url")
    print(f"{a.client}: живая версия {live.get('containerVersionId')} «{live.get('name', '')}», последняя версия {last}, "
          f"колонки таблицы: {have}")
    if int(live.get("containerVersionId")) != last:
        errors.append(f"живая версия не последняя ({live.get('containerVersionId')} против {last}): в рабочей области будут чужие неопубликованные правки")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Изменится тег «{SB_TAG}»: + {', '.join(NEW_COLS)}. Остальное не трогаем.")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    ws = call(s, "POST", cont + "/workspaces", json={"name": "supabase-gclid-content-pageurl-2026-10-27"})
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    wtag = call(s, "GET", f"{wp}/tags/{tag['tagId']}")
    html = param(wtag["parameter"], "html").replace(OLD, NEW).replace(OLD_Q, NEW_Q, 1)
    set_param(wtag["parameter"], "html", html)
    call(s, "PUT", f"{wp}/tags/{tag['tagId']}", params={"fingerprint": wtag["fingerprint"]}, json=wtag)
    print("Тег Supabase обновлён")
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Supabase: gclid, utm_content, page_url 2026-10-27",
                     "notes": "В отправку в Supabase добавлены gclid, utm_content (адрес страницы или localStorage rb_utm) и page_url. "
                              "Колонки в таблице созданы заранее. Откат: опубликовать предыдущую версию."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {c['account']} --container {c['container']} "
          f"--version {live.get('containerVersionId')} --execute")


if __name__ == "__main__":
    main()
