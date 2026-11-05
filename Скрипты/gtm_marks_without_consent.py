#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: метки заявок в Supabase при любом выборе в cookie-баннере. ЗАПИСЬ в черновик GTM (2026-11-05).

Что делает (без --execute — только проверка, ничего не пишет):
  1. Тег «Supabase - Leads» (117): для каждой метки порядок «адрес страницы → localStorage.rb_utm → cookie TILDAUTM (только utm_*)»;
     добавлены `fbclid`, `gbraid`, `wbraid` (колонки в profimet_leads созданы заранее). `gclid` — из адреса, из rb_utm или из
     `gclid_<значение>` внутри utm_content, НО НЕ из TILDAUTM: Tilda пишет значения в нижнем регистре (проверено на живом сайте:
     TESTCLID → testclid), а gclid чувствителен к регистру.
  2. Тег «UTM - сохранить в браузере» (147): в rb_utm добавлены fbclid, gbraid, wbraid (при согласии ad_storage, как раньше).
  3. НОВЫЙ тег «Метки - перенос по ссылкам без согласия»: пока ad_storage не дано, при клике по внутренней ссылке дописывает в неё
     метки из адреса текущей страницы (в localStorage/cookie ничего не пишет). Состояние согласия читается в момент клика.
Создаёт новую рабочую область от ПОСЛЕДНЕЙ версии контейнера, правит теги, делает версию. НЕ публикует: публикация —
`gtm_publish_version.py` после теста (`gtm_test_version.py`, `gtm_consent_audit.py`) и «да». Откат — публикация прежней живой версии
(скрипт печатает её номер).

    PYTHONUTF8=1 python gtm_marks_without_consent.py            # проверка
    PYTHONUTF8=1 python gtm_marks_without_consent.py --execute  # черновик + версия
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
ACCOUNT, CONTAINER, TABLE = "6003760261", "44158621", "profimet_leads"
NEW_COLS = ["fbclid", "gbraid", "wbraid", "gclid", "utm_content", "page_url"]
SB_TAG, SAVE_TAG, CARRY_TAG = "Supabase - Leads", "UTM - сохранить в браузере", "Метки - перенос по ссылкам без согласия"
ALL_PAGES = "2147479553"

SB_HTML = r"""<script>
(function() {
  var supabaseUrl = '__URL__';
  var publishableKey = '__KEY__';

  // Порядок для каждой метки: адрес страницы -> localStorage rb_utm (30 дней, только при согласии ad_storage) ->
  // cookie TILDAUTM (её Tilda ставит сама, без согласия; в ней только utm_*, значения в нижнем регистре).
  var q = new URLSearchParams(window.location.search);
  var stored = {};
  try {
    var raw = localStorage.getItem('rb_utm');
    if (raw) {
      var o = JSON.parse(raw);
      if (o && o._ts && (Date.now() - o._ts) < 30 * 24 * 3600 * 1000) { stored = o; }
    }
  } catch (e) {}

  var tilda = {};
  try {
    var m = document.cookie.match(/(?:^|; )TILDAUTM=([^;]*)/);
    if (m) {
      decodeURIComponent(m[1]).split('|||').forEach(function(p) {
        var i = p.indexOf('=');
        if (i > 0) {
          var v = p.slice(i + 1);
          try { v = decodeURIComponent(v); } catch (e2) {}
          tilda[p.slice(0, i)] = v;
        }
      });
    }
  } catch (e) {}

  // src запоминает, откуда взята каждая метка: url (адрес), rb_utm (localStorage), tildautm (cookie Tilda, возможно старый клик).
  var src = {};
  function pick(k) {
    var v = q.get(k);
    if (v) { src[k] = 'url'; return v; }
    v = stored[k];
    if (v) { src[k] = 'rb_utm'; return v; }
    v = (k.indexOf('utm_') === 0) ? tilda[k] : '';
    if (v) { src[k] = 'tildautm'; return v; }
    return '';
  }
  var vals = {};
  ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'fbclid', 'gbraid', 'wbraid'].forEach(function(k) { vals[k] = pick(k); });
  // gclid: адрес, rb_utm, затем gclid_<значение> внутри utm_content из адреса/rb_utm. Из TILDAUTM не берём (регистр).
  var gclid = q.get('gclid') || '';
  if (gclid) { src.gclid = 'url'; }
  if (!gclid && stored.gclid) { gclid = stored.gclid; src.gclid = 'rb_utm'; }
  if (!gclid) {
    var gm = /gclid_([^|\s]+)/.exec(q.get('utm_content') || stored.utm_content || '');
    if (gm) { gclid = gm[1]; src.gclid = q.get('utm_content') ? 'url' : 'rb_utm'; }
  }
  // mark_source: откуда главная метка заявки (источник трафика, иначе gclid и т.д.)
  var markSource = src.utm_source || src.gclid || src.fbclid || src.gbraid || src.wbraid || '';

  var payload = JSON.stringify({
    phone: {{Phone - Enhanced Conversions}} || '',
    utm_source: vals.utm_source,
    utm_medium: vals.utm_medium,
    utm_campaign: vals.utm_campaign,
    utm_content: vals.utm_content,
    gclid: gclid,
    fbclid: vals.fbclid,
    gbraid: vals.gbraid,
    wbraid: vals.wbraid,
    mark_source: markSource,
    page_url: String(window.location.href || '').substring(0, 1000)
  });

  var xhr = new XMLHttpRequest();
  xhr.open('POST', supabaseUrl + '/rest/v1/profimet_leads');
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('apikey', publishableKey);
  xhr.setRequestHeader('Authorization', 'Bearer ' + publishableKey);
  xhr.setRequestHeader('Prefer', 'return=minimal');
  xhr.send(payload);
})();
</script>
"""

CARRY_HTML = r"""<script>
(function() {
  // Пока ad_storage не дано: при клике по внутренней ссылке дописываем в неё метки из адреса текущей страницы.
  // Ничего не сохраняем (ни localStorage, ни cookie). Согласие читается в момент клика.
  if (window.__rbMarksCarry) { return; }
  window.__rbMarksCarry = true;
  var KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'fbclid', 'gbraid', 'wbraid'];

  function adGranted() {
    try {
      var e = window.google_tag_data.ics.entries.ad_storage;
      var v = (e.update !== undefined) ? e.update : e.default;
      return v === true || v === 'granted';
    } catch (x) { return false; }
  }

  function decorate(ev) {
    try {
      if (adGranted()) { return; }
      var q = new URLSearchParams(window.location.search);
      var marks = {}, n = 0;
      KEYS.forEach(function(k) { var v = q.get(k); if (v) { marks[k] = v; n++; } });
      if (!n) { return; }
      var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
      if (!a) { return; }
      var h = a.getAttribute('href');
      if (!h || /^(tel:|mailto:|javascript:|#)/i.test(h)) { return; }
      var u = new URL(a.href, window.location.href);
      if (u.origin !== window.location.origin) { return; }
      if (u.pathname === window.location.pathname && u.search === window.location.search) { return; }
      var changed = false;
      Object.keys(marks).forEach(function(k) {
        if (!u.searchParams.has(k)) { u.searchParams.set(k, marks[k]); changed = true; }
      });
      if (changed) { a.href = u.toString(); }
    } catch (x) {}
  }

  ['mousedown', 'touchstart', 'click'].forEach(function(t) {
    document.addEventListener(t, decorate, true);
  });
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


def set_param(items, key, value):
    for p in items:
        if p["key"] == key:
            p["value"] = value
            return
    items.append({"type": "template", "key": key, "value": value})


def add_mark_source(a):
    cont = f"accounts/{ACCOUNT}/containers/{CONTAINER}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    sb = yaml.safe_load(open(MON_CFG, encoding="utf-8"))["supabase"]
    hd = {"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]}
    r = requests.get(f"{sb['url']}/rest/v1/{TABLE}", timeout=60, params={"select": "*", "limit": 1}, headers=hd)
    r.raise_for_status()
    have = list(r.json()[0].keys()) if r.json() else []
    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    lastv = call(s, "GET", cont + f"/versions/{last}")
    tag = next((t for t in lastv["tag"] if t["name"] == SB_TAG), None)
    errors = []
    if "mark_source" not in have:
        errors.append(f"в таблице {TABLE} нет колонки mark_source (иначе Supabase отклонит запись)")
    html = param(tag["parameter"], "html") if tag else ""
    if "TILDAUTM" not in html:
        errors.append(f"в тег 117 версии {last} не внесён шаг 1 (TILDAUTM) — сначала обычный запуск")
    if "mark_source" in html:
        errors.append(f"версия {last} уже отправляет mark_source")
    print(f"живая {live.get('containerVersionId')}, последняя {last}, колонки: {have}")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    if not a.execute:
        print(f"Проверка пройдена: на базе версии {last} в тег 117 добавится mark_source. Ничего не изменено (нужен --execute).")
        return
    surl = re.search(r"var supabaseUrl = '([^']+)'", html).group(1)
    skey = re.search(r"var publishableKey = '([^']+)'", html).group(1)
    new117 = SB_HTML.replace("__URL__", surl).replace("__KEY__", skey)
    ws = call(s, "POST", cont + "/workspaces", json={"name": "marks-mark-source-2026-11-05"})
    wp = ws["path"]
    wt = call(s, "GET", f"{wp}/tags/{tag['tagId']}")
    set_param(wt["parameter"], "html", new117)
    call(s, "PUT", f"{wp}/tags/{tag['tagId']}", params={"fingerprint": wt["fingerprint"]}, json=wt)
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Метки без согласия + mark_source 2026-11-05",
                     "notes": f"База — версия {last}. В тег 117 добавлено поле mark_source (url / rb_utm / tildautm). "
                              f"Откат: опубликовать версию {live.get('containerVersionId')}."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--add-mark-source", action="store_true",
                    help="второй шаг: в тег 117 последней (ещё не опубликованной) версии добавить mark_source; колонка mark_source должна быть в таблице")
    a = ap.parse_args()
    if a.add_mark_source:
        return add_mark_source(a)
    cont = f"accounts/{ACCOUNT}/containers/{CONTAINER}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))

    sb = yaml.safe_load(open(MON_CFG, encoding="utf-8"))["supabase"]
    r = requests.get(f"{sb['url']}/rest/v1/{TABLE}", timeout=60, params={"select": "*", "limit": 1},
                     headers={"apikey": sb["secret_key"], "Authorization": "Bearer " + sb["secret_key"]})
    r.raise_for_status()
    have = list(r.json()[0].keys()) if r.json() else []
    missing = [x for x in NEW_COLS if x not in have]

    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    sb_tag = next((t for t in live["tag"] if t["name"] == SB_TAG), None)
    save_tag = next((t for t in live["tag"] if t["name"] == SAVE_TAG), None)
    errors = []
    if missing:
        errors.append(f"в таблице {TABLE} нет колонок {missing}")
    if not sb_tag or not save_tag:
        errors.append("нет тега 117 или 147")
    else:
        h117, h147 = param(sb_tag["parameter"], "html"), param(save_tag["parameter"], "html")
        if "page_url" not in h117 or "TILDAUTM" in h117 or "{{Phone - Enhanced Conversions}}" not in h117:
            errors.append("текст тега 117 не совпадает с ожидаемым (кто-то менял) — остановка")
        if "var keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid'];" not in h147:
            errors.append("текст тега 147 не совпадает с ожидаемым — остановка")
    if any(t["name"] == CARRY_TAG for t in live["tag"]):
        errors.append("тег переноса уже есть в живой версии")
    print(f"живая версия {live.get('containerVersionId')}, последняя {last}, колонки: {have}")
    if int(live.get("containerVersionId")) != last:
        errors.append(f"живая версия не последняя ({live.get('containerVersionId')} против {last}): в область попадут чужие неопубликованные правки")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Изменятся: тег 117 «{SB_TAG}», тег 147 «{SAVE_TAG}» (+fbclid/gbraid/wbraid); новый тег «{CARRY_TAG}» (All Pages).")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    surl = re.search(r"var supabaseUrl = '([^']+)'", h117).group(1)
    skey = re.search(r"var publishableKey = '([^']+)'", h117).group(1)
    new117 = SB_HTML.replace("__URL__", surl).replace("__KEY__", skey)
    new147 = h147.replace("['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid'];",
                          "['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'fbclid', 'gbraid', 'wbraid'];")

    ws = call(s, "POST", cont + "/workspaces", json={"name": "marks-without-consent-2026-11-05"})
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    for tag, html in ((sb_tag, new117), (save_tag, new147)):
        wt = call(s, "GET", f"{wp}/tags/{tag['tagId']}")
        set_param(wt["parameter"], "html", html)
        call(s, "PUT", f"{wp}/tags/{tag['tagId']}", params={"fingerprint": wt["fingerprint"]}, json=wt)
        print("Тег обновлён:", tag["tagId"])
    new_tag = {"name": CARRY_TAG, "type": "html", "firingTriggerId": [ALL_PAGES], "tagFiringOption": "oncePerEvent",
               "consentSettings": {"consentStatus": "notSet"},
               "notes": "Пока ad_storage не дано: при клике по внутренней ссылке дописывает в неё метки из адреса текущей страницы "
                        "(ничего не сохраняет). Нужен, чтобы метки доехали до страницы с формой без cookie. 2026-11-05.",
               "parameter": [{"type": "template", "key": "html", "value": CARRY_HTML},
                             {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}]}
    created = call(s, "POST", f"{wp}/tags", json=new_tag)
    print("Новый тег:", created["tagId"], created["name"])
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Метки без согласия: TILDAUTM, fbclid/gbraid/wbraid, перенос по ссылкам 2026-11-05",
                     "notes": "Тег 117: метки адрес -> rb_utm -> TILDAUTM (utm_*), + fbclid/gbraid/wbraid. Тег 147: + fbclid/gbraid/wbraid. "
                              "Новый тег переноса меток по внутренним ссылкам без ad_storage. Откат: опубликовать версию "
                              + str(live.get("containerVersionId")) + "."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {ACCOUNT} --container {CONTAINER} "
          f"--version {live.get('containerVersionId')} --execute")


if __name__ == "__main__":
    main()
