#!/usr/bin/env python
# coding: utf-8
"""Добавить существующий триггер к тегу GTM (ЗАПИСЬ в черновик, 2026-10-27).

Зачем: тег «по согласию» на All Pages не срабатывает у нового посетителя, пока согласия нет, и не перезапускается после «принять».
Второй триггер на событие баннера (ProfiMet: `consentTypeSelected`, триггер 85) решает это; условие согласия тега не меняется.

Без --execute: проверка (живая и последняя версии, тег, триггеры, есть ли уже). С --execute: НОВАЯ рабочая область, правка тега,
версия контейнера. НЕ публикует: сначала `gtm_test_version.py --version N`, публикация — `gtm_publish_version.py` по «да».
Использование (из папки Скрипты):
    PYTHONUTF8=1 python gtm_tag_add_trigger.py --account 6003760261 --container 44158621 --tag "UTM - сохранить в браузере" --trigger 85
    ... --execute
"""
import argparse
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions"]


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--tag", required=True, help="точное имя тега")
    ap.add_argument("--trigger", required=True, help="id существующего триггера")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cont = f"accounts/{a.account}/containers/{a.container}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))

    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    tag = next((t for t in live.get("tag", []) if t["name"] == a.tag), None)
    trig = next((t for t in live.get("trigger", []) if t["triggerId"] == a.trigger), None)
    errors = []
    if not tag:
        errors.append(f"нет тега «{a.tag}»")
    elif a.trigger in tag.get("firingTriggerId", []):
        errors.append("триггер уже у тега")
    if not trig:
        errors.append(f"нет триггера {a.trigger}")
    if int(live["containerVersionId"]) != last:
        errors.append(f"живая версия не последняя ({live['containerVersionId']} против {last}): в области будут чужие правки")
    print(f"живая версия {live['containerVersionId']} «{live.get('name', '')}», последняя {last}")
    if tag:
        print(f"тег {tag['tagId']} «{tag['name']}», триггеры сейчас {tag.get('firingTriggerId')}, согласие {tag.get('consentSettings')}")
    if trig:
        print(f"триггер {trig['triggerId']} «{trig['name']}» тип {trig['type']}")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    print(f"Изменится: тег «{a.tag}» + триггер {a.trigger}. Остальное не трогаем.")
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return

    ws = call(s, "POST", cont + "/workspaces", json={"name": f"tag-{tag['tagId']}-add-trigger-{a.trigger}-2026-10-27"})
    wp = ws["path"]
    print("Рабочая область:", ws["name"], ws["workspaceId"])
    wtag = call(s, "GET", f"{wp}/tags/{tag['tagId']}")
    wtag["firingTriggerId"] = list(wtag.get("firingTriggerId", [])) + [a.trigger]
    call(s, "PUT", f"{wp}/tags/{tag['tagId']}", params={"fingerprint": wtag["fingerprint"]}, json=wtag)
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": f"{a.tag}: + триггер {a.trigger} 2026-10-27",
                     "notes": f"Тегу «{a.tag}» добавлен триггер {a.trigger} «{trig['name']}»; согласие тега не менялось. "
                              "Откат: опубликовать предыдущую версию."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {a.account} --container {a.container} "
          f"--version {live['containerVersionId']} --execute")


if __name__ == "__main__":
    main()
