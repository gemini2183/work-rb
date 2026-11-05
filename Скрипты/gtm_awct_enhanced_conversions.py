#!/usr/bin/env python
# coding: utf-8
"""Включить ручную передачу телефона (расширенные конверсии, Enhanced Conversions) в тегах конверсий Google Ads контейнера GTM.
ЗАПИСЬ в черновик контейнера — только с --execute. Не публикует (публикация — gtm_publish_version.py).

Зачем (LuxeBrokers, 2026-11-04): диагностика Google Ads показывала покрытие 0% по двум основным конверсиям с тегом на сайте;
в тегах awct не было данных пользователя. Автоматический метод Google не находит поля на формах Tilda.

Что делает с --execute (новая рабочая область, версия создаётся, живая версия не меняется):
  1. JS-переменная «Phone - Enhanced Conversions»: телефон из полей формы (`input[name="Phone"]`, `input[type="tel"]`), самое длинное число;
     10 цифр → добавляет 1 (США); меньше 11 цифр → пусто; при пустом поле берёт номер, запомненный при вводе (window.__rbPhoneEc).
  2. Custom HTML-тег «EC - cache phone»: при вводе в поле телефона запоминает номер (Tilda может очистить форму до срабатывания тега конверсии).
  3. Переменная «User-Provided Data» (тип awec, ручной режим): phone = переменная из п. 1.
  4. Теги конверсий из --tags: enableEnhancedConversion = true, пользовательские данные = переменная из п. 3.
Остальные объекты не трогаются.

    python gtm_awct_enhanced_conversions.py --account 6240500366 --container 190366786 --tags 58 65            # план
    python gtm_awct_enhanced_conversions.py --account ... --container ... --tags 58 65 --execute              # черновик
"""
import argparse
import io
import sys
import time
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]

VAR_JS = "Phone - Enhanced Conversions"
VAR_AWEC = "User-Provided Data (phone)"
TAG_CACHE = "EC - cache phone"

JS_CODE = r"""function() {
  // Телефон для расширенных конверсий. Самое длинное число среди полей телефона; Tilda может очистить форму к моменту
  // срабатывания тега, поэтому есть запасной вариант — номер, запомненный тегом «EC - cache phone» при вводе.
  var els = document.querySelectorAll('input[name="Phone"], input[type="tel"]');
  var best = '';
  for (var i = 0; i < els.length; i++) {
    var d = (els[i].value || '').replace(/\D/g, '');
    if (d.length > best.length) { best = d; }
  }
  if (best.length < 10 && window.__rbPhoneEc) { best = window.__rbPhoneEc; }
  if (best.length === 10) { best = '1' + best; }
  if (best.length < 11) { return undefined; }
  return '+' + best;
}"""

CACHE_HTML = r"""<script>
(function () {
  if (window.__rbPhoneEcBound) { return; }
  window.__rbPhoneEcBound = true;
  document.addEventListener('input', function (e) {
    var t = e.target;
    if (!t || t.tagName !== 'INPUT') { return; }
    if (t.type !== 'tel' && t.name !== 'Phone') { return; }
    var d = (t.value || '').replace(/\D/g, '');
    if (d.length >= 10) { window.__rbPhoneEc = d; }
  }, true);
})();
</script>"""


def call(s, method, path, **kw):
    """Квота Tag Manager API мала (запись — единицы в минуту): при 429 ждём и повторяем."""
    for wait in (0, 20, 40, 60, 90):
        time.sleep(wait)
        r = s.request(method, BASE + path, **kw)
        if r.status_code != 429:
            break
        print(f"   429 (квота), жду… {method} {path.split('/')[-1]}")
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def set_param(params, key, ptype, value):
    for p in params:
        if p["key"] == key:
            p["type"], p["value"] = ptype, value
            return
    params.append({"type": ptype, "key": key, "value": value})


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--tags", nargs="+", required=True, help="id тегов awct (конверсии Google Ads)")
    ap.add_argument("--workspace", default="ec-phone-2026-11-04")
    ap.add_argument("--phone-keys", nargs="+", default=["phone"],
                    help="имя(ена) параметра телефона в переменной awec (ручной режим); несколько — для подбора ключа, по умолчанию phone")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{a.account}/containers/{a.container}"

    live = call(s, "GET", cont + "/versions:live")
    print(f"Живая версия до: {live.get('containerVersionId')} «{live.get('name', '')}»")
    names = {v["name"] for v in live.get("variable", [])} | {t["name"] for t in live.get("tag", [])}
    for n in (VAR_JS, VAR_AWEC, TAG_CACHE):
        if n in names:
            raise SystemExit(f"ОСТАНОВКА: объект «{n}» уже есть в контейнере")
    tags = {t["tagId"]: t for t in live["tag"]}
    for tid in a.tags:
        t = tags.get(tid)
        if not t or t["type"] != "awct":
            raise SystemExit(f"ОСТАНОВКА: тег {tid} не найден или не awct")
        print(f"Изменится тег {tid} «{t['name']}»: enableEnhancedConversion -> true, данные -> {{{{{VAR_AWEC}}}}}")
    print(f"Будут созданы: JS-переменная «{VAR_JS}», переменная awec «{VAR_AWEC}», Custom HTML «{TAG_CACHE}» (все страницы)")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    ws = call(s, "POST", cont + "/workspaces", json={"name": a.workspace})
    wp = ws["path"]
    v1 = call(s, "POST", wp + "/variables", json={"name": VAR_JS, "type": "jsm",
              "parameter": [{"type": "template", "key": "javascript", "value": JS_CODE}]})
    v2 = call(s, "POST", wp + "/variables", json={"name": VAR_AWEC, "type": "awec", "parameter": [
        {"type": "template", "key": "mode", "value": "MANUAL"},
        *[{"type": "template", "key": k, "value": "{{" + VAR_JS + "}}"} for k in a.phone_keys],
        {"type": "boolean", "key": "enableElementBlocking", "value": "false"}]})
    t0 = call(s, "POST", wp + "/tags", json={"name": TAG_CACHE, "type": "html", "firingTriggerId": ["2147479553"],
              "parameter": [{"type": "template", "key": "html", "value": CACHE_HTML},
                            {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}]})
    print("создано:", v1["variableId"], v2["variableId"], t0["tagId"])
    for tid in a.tags:
        wt = call(s, "GET", f"{wp}/tags/{tid}")
        set_param(wt["parameter"], "enableEnhancedConversion", "boolean", "true")
        set_param(wt["parameter"], "cssProvidedEnhancedConversionValue", "template", "{{" + VAR_AWEC + "}}")
        call(s, "PUT", f"{wp}/tags/{tid}", params={"fingerprint": wt["fingerprint"]}, json=wt)
        back = call(s, "GET", f"{wp}/tags/{tid}")
        print(f"тег {tid} после записи:", [(p['key'], p['value']) for p in back['parameter'] if 'nhanced' in p['key'] or 'css' in p['key']])
    ver = call(s, "POST", f"{wp}:create_version", json={
        "name": "Расширенные конверсии: телефон в тегах конверсий 2026-11-04",
        "notes": "Ручная передача телефона (awec manual) в теги 58 и 65 + кэш номера при вводе. Не опубликовано."})
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    print("Версия создана (НЕ опубликована):", ver.get("containerVersion", {}).get("containerVersionId"), ver.get("compilerError", ""))


if __name__ == "__main__":
    main()
