#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: тег «Визит: rngst + клик → Supabase» (таблица profimet_visits). ЗАПИСЬ в черновик GTM (2026-11-05).

Зачем: звонки статических пулов Ringostat (pmax, demand_gen, YouTube, ретаргет) приходят без gclid. При визите Ringostat ставит cookie
`rngst` = {"clientId": "<uuid>"}; тот же uuid лежит в поле `client_id` звонка в API Ringostat (формат совпадает; равенство значений
проверяется по первым реальным звонкам — `visit_call_join.py`). Тег записывает пару «clientId + клик Google» в Supabase, позже звонок
сопоставляется с визитом по client_id и берётся gclid для офлайн-конверсии.

Что делает тег:
  - срабатывает на All Pages БЕЗ условия согласия (как тег 117 «Supabase - Leads»; решение пользователя 2026-11-05: метки без согласия);
    состояние ad_storage в момент отправки пишет в колонку `consent` (granted / denied) — по ней потом считается доля визитов без согласия;
  - клик берёт из адреса страницы (gclid / gbraid / wbraid), запасной вариант — localStorage.rb_utm (пишется только при согласии);
    из TILDAUTM gclid НЕ берём (Tilda переводит значения в нижний регистр, а gclid чувствителен к регистру);
  - визиты без клика Google не пишет; ничего не сохраняет на устройстве (ни cookie, ни localStorage);
  - ждёт cookie `rngst` до 5 с (скрипт Ringostat ставит её асинхронно); не дождался — не пишет;
  - дубликаты (тот же clientId + клик) отсекает уникальный индекс в таблице (ответ 409, это нормально).

Без --execute — только проверка. С --execute: новая рабочая область от последней версии контейнера, новый тег, версия. НЕ публикует:
публикация — `gtm_publish_version.py` после теста (`gtm_visit_tag_test.py`, `gtm_consent_audit.py`) и «да».

    PYTHONUTF8=1 python gtm_visit_tag.py            # проверка
    PYTHONUTF8=1 python gtm_visit_tag.py --execute  # черновик + версия
"""
import argparse
import re
from pathlib import Path

import requests
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions"]
MON_CFG = "E:/PythonProjects/RedBird/monitoring scripts/monitoring/config/profimet.yaml"
ACCOUNT, CONTAINER, TABLE = "6003760261", "44158621", "profimet_visits"
NEED_COLS = ["rngst_client_id", "click_key", "gclid", "gbraid", "wbraid", "utm_source", "utm_medium", "utm_campaign", "utm_content",
             "page_url", "consent", "mark_source"]
SB_TAG, VISIT_TAG = "Supabase - Leads", "Визит - rngst и клик в Supabase"
ALL_PAGES = "2147479553"

VISIT_HTML = r"""<script>
(function() {
  // Визит с кликом Google -> Supabase (profimet_visits). Ничего не сохраняет на устройстве. Согласие не требуется; его состояние пишется в consent.
  if (window.__rbVisitTag) { return; }
  window.__rbVisitTag = true;
  var SB_URL = '__URL__';
  var SB_KEY = '__KEY__';

  function adGranted() {
    try {
      var e = window.google_tag_data.ics.entries.ad_storage;
      var v = (e.update !== undefined) ? e.update : e.default;
      return v === true || v === 'granted';
    } catch (x) { return false; }
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
  var click = m.gclid || m.gbraid || m.wbraid;
  if (!click) { return; }

  function readClientId() {
    try {
      var c = document.cookie.match(/(?:^|; )rngst=([^;]*)/);
      if (!c) { return ''; }
      var o = JSON.parse(decodeURIComponent(c[1]));
      return (o && o.clientId) ? String(o.clientId) : '';
    } catch (e) { return ''; }
  }

  function send(cid) {
    var body = JSON.stringify({
      rngst_client_id: cid,
      click_key: click,
      gclid: m.gclid, gbraid: m.gbraid, wbraid: m.wbraid,
      utm_source: m.utm_source, utm_medium: m.utm_medium, utm_campaign: m.utm_campaign, utm_content: m.utm_content,
      page_url: String(window.location.href || '').substring(0, 300),
      consent: adGranted() ? 'granted' : 'denied',
      mark_source: src
    });
    try {
      fetch(SB_URL + '/rest/v1/profimet_visits', {
        method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'apikey': SB_KEY, 'Authorization': 'Bearer ' + SB_KEY, 'Prefer': 'return=minimal' },
        body: body
      }).catch(function() {});
    } catch (e) {}
  }

  var tries = 0;
  (function wait() {
    var cid = readClientId();
    if (cid) { send(cid); return; }
    if (++tries < 10) { setTimeout(wait, 500); }
  })();
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
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cont = f"accounts/{ACCOUNT}/containers/{CONTAINER}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))

    sb = yaml.safe_load(open(MON_CFG, encoding="utf-8"))["supabase"]
    hd = {"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]}
    r = requests.get(sb["url"] + "/rest/v1/", headers=hd, timeout=60)
    r.raise_for_status()
    have = list(r.json().get("definitions", {}).get(TABLE, {}).get("properties", {}).keys())
    missing = [c for c in NEED_COLS if c not in have]

    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    sb_tag = next((t for t in live["tag"] if t["name"] == SB_TAG), None)
    errors = []
    if missing:
        errors.append(f"в таблице {TABLE} нет колонок {missing} (иначе Supabase отклонит запись)")
    if not sb_tag:
        errors.append(f"нет тега «{SB_TAG}» — не откуда взять адрес и публичный ключ Supabase")
    if any(t["name"] == VISIT_TAG for t in live["tag"]):
        errors.append("тег визитов уже есть в живой версии")
    print(f"живая версия {live.get('containerVersionId')}, последняя {last}, колонки {TABLE}: {len(have)}")
    if int(live.get("containerVersionId")) != last:
        errors.append(f"живая версия не последняя ({live.get('containerVersionId')} против {last}): в область попадут чужие неопубликованные правки")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Добавится новый тег «{VISIT_TAG}» (All Pages, без условия согласия). Остальное не трогаем.")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    h117 = param(sb_tag["parameter"], "html")
    surl = re.search(r"var supabaseUrl = '([^']+)'", h117).group(1)
    skey = re.search(r"var publishableKey = '([^']+)'", h117).group(1)
    html = VISIT_HTML.replace("__URL__", surl).replace("__KEY__", skey)

    WS_NAME = "visit-tag-rngst-2026-11-05"
    existing = [w for w in call(s, "GET", cont + "/workspaces").get("workspace", []) if w["name"] == WS_NAME]
    ws = existing[0] if existing else call(s, "POST", cont + "/workspaces", json={"name": WS_NAME})  # пустую область после сбоя используем повторно
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    new_tag = {"name": VISIT_TAG, "type": "html", "firingTriggerId": [ALL_PAGES], "tagFiringOption": "oncePerEvent",
               "consentSettings": {"consentStatus": "notSet"},
               "notes": "Пара «clientId из cookie rngst (Ringostat) + gclid/gbraid/wbraid» в profimet_visits, чтобы сопоставить звонок "
                        "статического пула с кликом Google. Без условия согласия (решение пользователя 2026-11-05); consent пишется в колонку. "
                        "Ничего не сохраняет на устройстве. Скрипт gtm_visit_tag.py.",
               "parameter": [{"type": "template", "key": "html", "value": html},
                             {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}]}
    created = call(s, "POST", f"{wp}/tags", json=new_tag)
    print("Новый тег:", created["tagId"], created["name"])
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Визиты: rngst + клик → Supabase 2026-11-05",
                     "notes": f"База — версия {last}. Новый тег визитов (All Pages, без согласия, consent пишется в таблицу). "
                              f"Откат: опубликовать версию {live.get('containerVersionId')}."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {ACCOUNT} --container {CONTAINER} "
          f"--version {live.get('containerVersionId')} --execute")


if __name__ == "__main__":
    main()
