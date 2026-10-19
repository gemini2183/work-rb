#!/usr/bin/env python
# coding: utf-8
"""Заменить JS-переменную телефона в контейнере GTM на «самое длинное число среди полей tel». ЗАПИСЬ в черновик.

Зачем: переменная брала телефон из зашитых ID полей (ProfiMet: `input_1496239478607`, `input_1531306540094` — после пересборки
форм Tilda 31.08.2026 их нет, номер в Supabase перестал приходить) или из ПЕРВОГО поля tel страницы (ExpertAgro — скрытое поле
корзины). Новая переменная не зависит от ID: берёт самое длинное число среди всех `input[type=tel]` (+ доп. селекторы вроде
виджета Ringostat); меньше 9 цифр (только префикс «48») — пусто. Тот же код, что в gtm_ekspertagro_supabase_fix.py.

Без --execute: проверка. С --execute: новая рабочая область, правка переменной, версия (НЕ публикует).
--publish-version <ID> публикует версию (после проверки!).

    python gtm_phone_variable_fix.py --account 6003760261 --container 44158621 --extra-selector "#rngst_phone_input"
    python gtm_phone_variable_fix.py --account ... --container ... --extra-selector ... --execute
    python gtm_phone_variable_fix.py --account ... --container ... --publish-version 63
"""
import argparse
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]

JS_TEMPLATE = r"""function() {
  // Самое длинное число среди ВСЕХ полей телефона: набрано только в отправляемой форме. Не зависит от ID полей
  // (формы Tilda пересобирают — зашитые ID ломаются). Меньше 9 цифр (только префикс 48) — считаем, что номера нет.
  var fields = document.querySelectorAll('__SELECTOR__');
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


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--variable", default="Phone - Enhanced Conversions")
    ap.add_argument("--extra-selector", default="", help='доп. селекторы через запятую, напр. "#rngst_phone_input"')
    ap.add_argument("--workspace", default="phone-variable-2026-10-16")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--publish-version")
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{a.account}/containers/{a.container}"

    if a.publish_version:
        res = call(s, "POST", f"{cont}/versions/{a.publish_version}:publish")
        print("Опубликована версия", res.get("containerVersion", {}).get("containerVersionId"))
        return

    live = call(s, "GET", cont + "/versions:live")
    print(f"Живая версия до: {live.get('containerVersionId')} «{live.get('name', '')}»")
    var = next((v for v in live["variable"] if v["name"] == a.variable), None)
    if not var or var["type"] != "jsm":
        raise SystemExit(f"ОСТАНОВКА: нет JS-переменной «{a.variable}»")
    selector = 'input[type="tel"]' + (", " + a.extra_selector if a.extra_selector else "")
    code = JS_TEMPLATE.replace("__SELECTOR__", selector.replace("'", "\\'"))
    print(f"Изменится: переменная «{a.variable}» (id {var['variableId']}), селектор: {selector}")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    ws = call(s, "POST", cont + "/workspaces", json={"name": a.workspace})
    wp = ws["path"]
    wvar = call(s, "GET", f"{wp}/variables/{var['variableId']}")
    for p in wvar["parameter"]:
        if p["key"] == "javascript":
            p["value"] = code
    call(s, "PUT", f"{wp}/variables/{var['variableId']}", params={"fingerprint": wvar["fingerprint"]}, json=wvar)
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": "Телефон: самое длинное число среди полей tel 2026-10-16",
                     "notes": "Переменная телефона больше не зависит от ID полей Tilda. Не опубликовано."})
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    print("Версия создана (НЕ опубликована):", ver.get("containerVersion", {}).get("containerVersionId"), ver.get("compilerError", ""))


if __name__ == "__main__":
    main()
