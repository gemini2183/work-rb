#!/usr/bin/env python
# coding: utf-8
"""Тег «по согласию» перезапускается после выбора в баннере (ЗАПИСЬ в черновик GTM, 2026-10-27).

Проблема: GTM решает, какие теги запускать на событии, в его начале. Тег баннера выдаёт согласие внутри того же события
(`consentTypeSelected`), поэтому тег с условием согласия, повешенный на то же событие, всё равно блокируется (проверено на ProfiMet,
версия 90: `rb_utm` пуст). Решение: новый тег на событие баннера кладёт в dataLayer следующее событие `rb_consent_selected`;
оно обрабатывается после выдачи согласия; целевой тег вешается на него (условие согласия тега остаётся). Новый триггер и новый
тег — отдельные объекты, старые не правятся (кроме набора триггеров целевого тега).

Без --execute: проверка. С --execute: НОВАЯ рабочая область, версия. НЕ публикует (`gtm_test_version.py --version N`, затем
`gtm_publish_version.py` по «да»).
    PYTHONUTF8=1 python gtm_consent_retrigger.py --account 6003760261 --container 44158621 --tag-id 147 --banner-trigger 85 [--execute]
"""
import argparse
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions"]
EVENT = "rb_consent_selected"
HTML = "<script>\n  window.dataLayer = window.dataLayer || [];\n  window.dataLayer.push({event: '%s'});\n</script>" % EVENT


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--tag-id", required=True, help="целевой тег с условием согласия")
    ap.add_argument("--banner-trigger", required=True, help="id триггера события баннера (consentTypeSelected)")
    ap.add_argument("--own-draft", type=int, help="номер неопубликованной версии, которая новее живой, но своя (не чужая правка)")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cont = f"accounts/{a.account}/containers/{a.container}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))

    live = call(s, "GET", cont + "/versions:live")
    last = max(int(h["containerVersionId"]) for h in call(s, "GET", cont + "/version_headers").get("containerVersionHeader", []))
    tag = next((t for t in live.get("tag", []) if t["tagId"] == a.tag_id), None)
    banner = next((t for t in live.get("trigger", []) if t["triggerId"] == a.banner_trigger), None)
    errors = []
    if not tag:
        errors.append(f"нет тега {a.tag_id}")
    if not banner:
        errors.append(f"нет триггера {a.banner_trigger}")
    if any(t["name"].startswith("rb_consent_selected") for t in live.get("trigger", [])):
        errors.append("триггер rb_consent_selected уже есть")
    if int(live["containerVersionId"]) != last and last != a.own_draft:
        errors.append(f"живая версия не последняя ({live['containerVersionId']} против {last})")
    print(f"живая версия {live['containerVersionId']}, последняя {last}")
    if tag:
        print(f"целевой тег {tag['tagId']} «{tag['name']}», триггеры {tag.get('firingTriggerId')}, согласие {tag.get('consentSettings', {}).get('consentType')}")
    if banner:
        print(f"триггер баннера {banner['triggerId']} «{banner['name']}» {banner['type']}")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Будет создано: триггер «{EVENT}» (customEvent), тег «Баннер - следующее событие {EVENT}» на триггере {a.banner_trigger}; "
          f"тегу {a.tag_id} добавляется триггер «{EVENT}». Остальное не трогаем.")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    ws = call(s, "POST", cont + "/workspaces", json={"name": f"consent-retrigger-{a.tag_id}-2026-10-27"})
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    trig = call(s, "POST", wp + "/triggers", json={
        "name": EVENT, "type": "customEvent",
        "customEventFilter": [{"type": "equals", "parameter": [
            {"type": "template", "key": "arg0", "value": "{{_event}}"},
            {"type": "template", "key": "arg1", "value": EVENT}]}]})
    new_tag = call(s, "POST", wp + "/tags", json={
        "name": f"Баннер - следующее событие {EVENT}", "type": "html",
        "notes": "После выбора в баннере кладёт в dataLayer следующее событие: теги с условием согласия (UTM - сохранить в браузере) "
                 "запускаются уже после выдачи согласия. Решение 2026-10-27.",
        "parameter": [{"type": "template", "key": "html", "value": HTML},
                      {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}],
        "firingTriggerId": [a.banner_trigger], "tagFiringOption": "oncePerEvent"})
    print("Создано: триггер", trig["triggerId"], "тег", new_tag["tagId"])
    wtag = call(s, "GET", f"{wp}/tags/{a.tag_id}")
    wtag["firingTriggerId"] = list(wtag.get("firingTriggerId", [])) + [trig["triggerId"]]
    call(s, "PUT", f"{wp}/tags/{a.tag_id}", params={"fingerprint": wtag["fingerprint"]}, json=wtag)
    ver = call(s, "POST", f"{wp}:create_version", json={
        "name": f"Тег {a.tag_id}: перезапуск после выбора в баннере 2026-10-27",
        "notes": f"Новый тег на событии баннера кладёт {EVENT}; тегу {a.tag_id} добавлен триггер {EVENT}. Условие согласия не менялось. "
                 "Откат: опубликовать предыдущую версию."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {a.account} --container {a.container} "
          f"--version {live['containerVersionId']} --execute")


if __name__ == "__main__":
    main()
