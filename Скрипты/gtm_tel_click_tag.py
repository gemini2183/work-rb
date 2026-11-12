#!/usr/bin/env python
# coding: utf-8
"""Тег GTM «Клик по номеру - rngst и клик в Supabase» (EkspertAgro). ЗАПИСЬ в черновик GTM (2026-11-12).

Зачем: звонки на СТАТИЧЕСКИЕ пулы Ringostat (PMax) приходят без gclid, а `client_id` звонка не равен cookie `rngst` посетителя
(тест ProfiMet 12.11). На телефоне человек нажимает на номер `tel:`, звонок появляется через секунды. Тег записывает КАЖДОЕ нажатие
на `tel:` (время в мс, rngst.clientId, gclid/gbraid/wbraid из адреса или localStorage.rb_utm, utm, страница, номер из href, состояние
согласия) в таблицу Supabase; `tel_click_call_join.py` сопоставляет звонок с нажатием по окну в секунды. Клик по номеру НЕ конверсия:
в Ads идёт только пара «звонок ↔ найденный клик» (отдельный шаг по «да»).

Что делает тег:
  - триггер — существующий «Клики tel» (id 16; click, Click URL содержит `tel:`); сам триггер и тег 17 «GADS - click_num_web» НЕ правятся;
  - без условия согласия (как тег визитов ProfiMet; решение 2026-11-05); состояние ad_storage пишется в `consent`;
  - ничего не сохраняет на устройстве; запись через fetch keepalive (страница может уйти в набор номера);
  - пишет и нажатия без клика Google (gclid пустой): нужны для замера неоднозначности; адрес Supabase и публичный ключ берёт из
    живого тега «Supabase - Leads», ключи в код не пишутся.

Без --execute — только проверка и SQL для таблицы. С --execute: НОВАЯ рабочая область от последней версии, новый тег, версия. НЕ публикует
(публикация — `gtm_publish_version.py` после `gtm_tel_click_test.py` и явного «да» с номером версии).

    PYTHONUTF8=1 python gtm_tel_click_tag.py                # проверка
    PYTHONUTF8=1 python gtm_tel_click_tag.py --execute      # черновик + версия
"""
import argparse
import re
from pathlib import Path

import requests
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

import _runlog

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions"]
CLIENTS = {
    "EkspertAgro": dict(cfg="E:/PythonProjects/RedBird/monitoring scripts/monitoring/config/experagro.yaml",
                        account="6326663960", container="236673117", table="expertagro_tel_clicks",
                        sb_tag="Supabase - Leads", trigger_name="Клики tel", ws="tel-click-tag-2026-11-12"),
}
NEED_COLS = ["ts_ms", "rngst_client_id", "click_key", "gclid", "gbraid", "wbraid", "utm_source", "utm_medium", "utm_campaign",
             "utm_content", "page_url", "phone_href", "consent", "mark_source"]
TAG_NAME = "Клик по номеру - rngst и клик в Supabase"

SQL = """create table public.{t} (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  ts_ms bigint not null,
  rngst_client_id text not null default '',
  click_key text not null default '', gclid text not null default '', gbraid text not null default '', wbraid text not null default '',
  utm_source text not null default '', utm_medium text not null default '', utm_campaign text not null default '', utm_content text not null default '',
  page_url text not null default '', phone_href text not null default '', consent text not null default '', mark_source text not null default ''
);
create unique index {t}_uq on public.{t} (rngst_client_id, ts_ms);
alter table public.{t} enable row level security;
create policy "anon insert" on public.{t} for insert to anon with check (true);
-- чтение для anon НЕ открываем; читает скрипт с секретным ключом"""

TAG_HTML = r"""<script>
(function() {
  // Нажатие на tel: -> Supabase (__TABLE__). Ничего не сохраняет на устройстве. Согласие не требуется; его состояние пишется в consent.
  var SB_URL = '__URL__';
  var SB_KEY = '__KEY__';
  var href = '{{Click URL}}';
  function adGranted() {
    try {
      var e = window.google_tag_data.ics.entries.ad_storage;
      var v = (e.update !== undefined) ? e.update : e.default;
      return v === true || v === 'granted';
    } catch (x) { return false; }
  }
  function cid() {
    try {
      var c = document.cookie.match(/(?:^|; )rngst=([^;]*)/);
      if (!c) { return ''; }
      var o = JSON.parse(decodeURIComponent(c[1]));
      return (o && o.clientId) ? String(o.clientId) : '';
    } catch (e) { return ''; }
  }
  var q = new URLSearchParams(window.location.search);
  var src = 'url';
  var m = {
    gclid: q.get('gclid') || '', gbraid: q.get('gbraid') || '', wbraid: q.get('wbraid') || '',
    utm_source: q.get('utm_source') || '', utm_medium: q.get('utm_medium') || '',
    utm_campaign: q.get('utm_campaign') || '', utm_content: q.get('utm_content') || ''
  };
  if (!m.gclid && !m.gbraid && !m.wbraid) {
    try {
      var raw = localStorage.getItem('rb_utm');
      var o = raw ? JSON.parse(raw) : null;
      if (o && o._ts && (Date.now() - o._ts) < 30 * 24 * 3600 * 1000) {
        m.gclid = o.gclid || ''; m.gbraid = o.gbraid || ''; m.wbraid = o.wbraid || '';
        m.utm_source = o.utm_source || ''; m.utm_medium = o.utm_medium || '';
        m.utm_campaign = o.utm_campaign || ''; m.utm_content = o.utm_content || '';
        src = 'rb_utm';
      }
    } catch (e) {}
  }
  var body = JSON.stringify({
    ts_ms: Date.now(),
    rngst_client_id: cid(),
    click_key: m.gclid || m.gbraid || m.wbraid,
    gclid: m.gclid, gbraid: m.gbraid, wbraid: m.wbraid,
    utm_source: m.utm_source, utm_medium: m.utm_medium, utm_campaign: m.utm_campaign, utm_content: m.utm_content,
    page_url: String(window.location.href || '').substring(0, 300),
    phone_href: String(href || '').substring(0, 60),
    consent: adGranted() ? 'granted' : 'denied',
    mark_source: src
  });
  try {
    fetch(SB_URL + '/rest/v1/__TABLE__', {
      method: 'POST', keepalive: true,
      headers: { 'Content-Type': 'application/json', 'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY, 'Prefer': 'return=minimal' },
      body: body
    }).catch(function() {});
  } catch (e) {}
})();
</script>
"""


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def param(items, key):
    return next(p["value"] for p in items if p["key"] == key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="EkspertAgro", choices=list(CLIENTS))
    ap.add_argument("--execute", action="store_true")
    _runlog.add_arg(ap)
    a = ap.parse_args()
    _runlog.start(a)
    c = CLIENTS[a.client]
    cont = f"accounts/{c['account']}/containers/{c['container']}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))

    sb = yaml.safe_load(open(c["cfg"], encoding="utf-8"))["supabase"]
    hd = {"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]}
    r = requests.get(sb["url"] + "/rest/v1/", headers=hd, timeout=60)
    r.raise_for_status()
    defs = r.json().get("definitions", {})
    have = list(defs.get(c["table"], {}).get("properties", {}).keys())
    missing = [x for x in NEED_COLS if x not in have]

    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    sb_tag = next((t for t in live.get("tag", []) if t["name"] == c["sb_tag"]), None)
    trig = next((t for t in live.get("trigger", []) if t["name"] == c["trigger_name"]), None)
    errors = []
    if not have:
        errors.append(f"таблицы {c['table']} нет в Supabase (создать SQL ниже)")
    elif missing:
        errors.append(f"в таблице {c['table']} нет колонок {missing}")
    if not sb_tag:
        errors.append(f"нет тега «{c['sb_tag']}» — не откуда взять адрес и публичный ключ Supabase")
    else:
        h = param(sb_tag["parameter"], "html")
        if not (re.search(r"var supabaseUrl = '([^']+)'", h) and re.search(r"var publishableKey = '([^']+)'", h)):
            errors.append(f"в теге «{c['sb_tag']}» не нашёл supabaseUrl / publishableKey по образцу ProfiMet")
    if not trig:
        errors.append(f"нет триггера «{c['trigger_name']}»")
    if any(t["name"] == TAG_NAME for t in live.get("tag", [])):
        errors.append("тег клика по номеру уже есть в живой версии")
    print(f"живая версия {live.get('containerVersionId')}, последняя {last}; триггер «{c['trigger_name']}»: "
          f"{trig['triggerId'] if trig else '—'}; колонок в {c['table']}: {len(have)}")
    if int(live.get("containerVersionId")) != last:
        errors.append(f"живая версия не последняя ({live.get('containerVersionId')} против {last}): в область попадут чужие неопубликованные правки")
    if errors:
        print("SQL для таблицы (SQL Editor Supabase, создаёт пользователь):\n" + SQL.format(t=c["table"]))
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Добавится новый тег «{TAG_NAME}» на триггер {trig['triggerId']} (чужие объекты не правятся).")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    h117 = param(sb_tag["parameter"], "html")
    surl = re.search(r"var supabaseUrl = '([^']+)'", h117).group(1)
    skey = re.search(r"var publishableKey = '([^']+)'", h117).group(1)
    html = TAG_HTML.replace("__URL__", surl).replace("__KEY__", skey).replace("__TABLE__", c["table"])
    existing = [w for w in call(s, "GET", cont + "/workspaces").get("workspace", []) if w["name"] == c["ws"]]
    ws = existing[0] if existing else call(s, "POST", cont + "/workspaces", json={"name": c["ws"]})
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    new_tag = {"name": TAG_NAME, "type": "html", "firingTriggerId": [trig["triggerId"]], "tagFiringOption": "oncePerEvent",
               "consentSettings": {"consentStatus": "notSet"},
               "notes": "Каждое нажатие на tel: -> строка в " + c["table"] + " (время мс, rngst.clientId, клик Google, utm, номер из href), "
                        "чтобы сопоставить звонок статического пула с нажатием по окну в секунды. Без согласия, consent пишется. "
                        "Ничего не сохраняет на устройстве. Скрипт gtm_tel_click_tag.py. Триггер «Клики tel» и тег 17 не менялись.",
               "parameter": [{"type": "template", "key": "html", "value": html},
                             {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}]}
    created = call(s, "POST", f"{wp}/tags", json=new_tag)
    print("Новый тег:", created["tagId"], created["name"])
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Клик по номеру: rngst + клик → Supabase 2026-11-12",
                     "notes": f"База — версия {last}. Новый тег клика по номеру на триггер «{c['trigger_name']}». "
                              f"Откат: опубликовать версию {live.get('containerVersionId')}."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {c['account']} --container {c['container']} "
          f"--version {live.get('containerVersionId')} --execute")


if __name__ == "__main__":
    main()
