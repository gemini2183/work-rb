#!/usr/bin/env python
# coding: utf-8
"""ExpertAgro (GTM-5FBCZLMC): починка записи заявок в Supabase `expertagro_leads`. ЗАПИСЬ в черновик GTM.

Что чинит (причины — Клиенты/EkspertAgro/Хроника_2026-10.md, запись «16.10 (поздно вечером)»):
  1. Переменная «Phone - Enhanced Conversions» брала ПЕРВОЕ поле tel на странице (скрытое поле корзины, пустое) →
     теперь берёт самое длинное число среди всех полей tel; меньше 9 цифр (только префикс «48») → пусто.
  2. UTM читались только из адреса текущей страницы → новый тег «UTM - сохранить в браузере» (как у ProfiMet v62,
     localStorage `rb_utm` на 30 дней, при согласии ad_storage) + тег «Supabase - Leads» берёт метки из адреса, иначе из `rb_utm`.
  3. Пачки одинаковых отправок → повтор в течение 5 секунд игнорируется.

Без --execute: только проверка (читает живую версию, показывает, что изменится). С --execute: создаёт НОВУЮ рабочую
область, правит переменную и тег, создаёт тег сохранения UTM, делает версию контейнера. НЕ публикует (публикация —
отдельный флаг --publish, только после проверки тестовой заявкой и «да» пользователя).
Откат до публикации не нужен (живая версия не меняется); после публикации — опубликовать предыдущую версию (печатается «живая версия до»).

    python gtm_ekspertagro_supabase_fix.py                # проверка
    python gtm_ekspertagro_supabase_fix.py --execute      # черновик + версия
    python gtm_ekspertagro_supabase_fix.py --publish-version <ID>   # опубликовать созданную версию
"""
import argparse
import re
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]
ACCOUNT, CONTAINER = "6326663960", "236673117"
WORKSPACE = "supabase-phone-utm-2026-10-16"
ALL_PAGES_TRIGGER = "2147479553"   # тот же, что у тега Ringostat Script (все страницы)
PHONE_VAR = "Phone - Enhanced Conversions"
SB_TAG = "Supabase - Leads"
UTM_TAG = "UTM - сохранить в браузере"

PHONE_JS = r"""function() {
  // Самое длинное число среди ВСЕХ полей tel: набрано только в отправляемой форме (раньше брали первое поле страницы —
  // скрытое поле корзины, всегда пустое). Меньше 9 цифр (только префикс 48) — считаем, что номера нет.
  var fields = document.querySelectorAll('input[type="tel"]');
  var best = '';
  for (var i = 0; i < fields.length; i++) {
    var d = (fields[i].value || '').replace(/\D/g, '');
    if (d.length > best.length) { best = d; }
  }
  if (best.length === 10 && best.charAt(0) === '0') { best = '48' + best.substring(1); }
  if (best.length === 9) { best = '48' + best; }
  if (best.length < 11) { return undefined; }
  return '+' + best;
}"""

UTM_HTML = """<script>
(function() {
  try {
    var KEY = 'rb_utm';
    var q = new URLSearchParams(window.location.search);
    var keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'gad_source', 'gad_campaignid'];
    var found = {}, has = false;
    keys.forEach(function(k) {
      var v = q.get(k);
      if (v) { found[k] = v; has = true; }
    });
    if (has) {
      found._ts = Date.now();
      localStorage.setItem(KEY, JSON.stringify(found));
    }
  } catch (e) {}
})();
</script>
"""

OLD_PAYLOAD = """  var payload = JSON.stringify({
    phone: {{Phone - Enhanced Conversions}} || '',
    utm_source: {{utm_source}} || '',
    utm_medium: {{utm_medium}} || '',
    utm_campaign: {{utm_campaign}} || ''
  });
"""
NEW_PAYLOAD = """  // Защита от пачек: повторная отправка в течение 5 секунд игнорируется (09.10 пришло 5 пустых строк подряд).
  if (window.__rbLeadTs && (Date.now() - window.__rbLeadTs) < 5000) { return; }
  window.__rbLeadTs = Date.now();

  // UTM из адреса страницы, а если их там нет (человек походил по сайту) - из браузера, куда их сохранил тег
  // «UTM - сохранить в браузере» (30 дней, только при согласии ad_storage).
  var stored = {};
  try {
    var raw = localStorage.getItem('rb_utm');
    if (raw) {
      var o = JSON.parse(raw);
      if (o && o._ts && (Date.now() - o._ts) < 30 * 24 * 3600 * 1000) { stored = o; }
    }
  } catch (e) {}

  var payload = JSON.stringify({
    phone: {{Phone - Enhanced Conversions}} || '',
    utm_source: {{utm_source}} || stored.utm_source || '',
    utm_medium: {{utm_medium}} || stored.utm_medium || '',
    utm_campaign: {{utm_campaign}} || stored.utm_campaign || ''
  });
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--publish-version", help="ID версии контейнера для публикации (после проверки!)")
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{ACCOUNT}/containers/{CONTAINER}"

    if a.publish_version:
        res = call(s, "POST", f"{cont}/versions/{a.publish_version}:publish")
        print("Опубликована версия", res.get("containerVersion", {}).get("containerVersionId"))
        return

    live = call(s, "GET", cont + "/versions:live")
    print(f"Живая версия до: {live.get('containerVersionId')} «{live.get('name', '')}»")
    var = next((v for v in live["variable"] if v["name"] == PHONE_VAR), None)
    tag = next((t for t in live["tag"] if t["name"] == SB_TAG), None)
    errors = []
    if not var:
        errors.append(f"нет переменной «{PHONE_VAR}»")
    if not tag:
        errors.append(f"нет тега «{SB_TAG}»")
    elif OLD_PAYLOAD not in param(tag["parameter"], "html"):
        errors.append("текст тега Supabase не совпадает с ожидаемым (кто-то менял) — остановка")
    if any(t["name"] == UTM_TAG for t in live["tag"]):
        errors.append(f"тег «{UTM_TAG}» уже есть")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Изменится: переменная «{PHONE_VAR}» (код), тег «{SB_TAG}» (метки из браузера, защита от пачек); "
          f"будет создан тег «{UTM_TAG}» (все страницы, согласие ad_storage).")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    ws = call(s, "POST", cont + "/workspaces", json={"name": WORKSPACE})
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])

    wvar = call(s, "GET", f"{wp}/variables/{var['variableId']}")
    set_param(wvar["parameter"], "javascript", PHONE_JS)
    call(s, "PUT", f"{wp}/variables/{var['variableId']}", params={"fingerprint": wvar["fingerprint"]}, json=wvar)
    print("Переменная обновлена")

    wtag = call(s, "GET", f"{wp}/tags/{tag['tagId']}")
    html = param(wtag["parameter"], "html")
    set_param(wtag["parameter"], "html", html.replace(OLD_PAYLOAD, NEW_PAYLOAD))
    call(s, "PUT", f"{wp}/tags/{tag['tagId']}", params={"fingerprint": wtag["fingerprint"]}, json=wtag)
    print("Тег Supabase обновлён")

    new_tag = {
        "name": UTM_TAG, "type": "html",
        "parameter": [{"type": "template", "key": "html", "value": UTM_HTML},
                      {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}],
        "firingTriggerId": [ALL_PAGES_TRIGGER], "tagFiringOption": "oncePerEvent",
        "consentSettings": {"consentStatus": "needed",
                            "consentType": {"type": "list", "list": [{"type": "template", "value": "ad_storage"}]}},
    }
    created = call(s, "POST", f"{wp}/tags", json=new_tag)
    print("Тег сохранения UTM создан, id", created.get("tagId"))

    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Supabase: телефон и UTM 2026-10-16",
                     "notes": "Телефон: самое длинное число среди полей tel. UTM: сохранение в localStorage. Защита от пачек 5 с. Не опубликовано."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))


if __name__ == "__main__":
    main()
