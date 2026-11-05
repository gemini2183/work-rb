#!/usr/bin/env python
# coding: utf-8
"""Удалить тег GTM (и его «осиротевшие» триггеры) через новую версию контейнера (2026-11-05). Без --execute — только проверка.

Зачем: убрать старый тег, который больше не нужен (ProfiMet: «visitsToServer», слал визиты на ringostat-webhook.onrender.com).
Что делает: ищет тег по имени/id в ЖИВОЙ версии; показывает его триггеры и кто ещё ими пользуется; триггер удаляется только если его не использует
ни один другой тег. Переменные не трогает. С --execute: НОВАЯ рабочая область → удаление тега и осиротевших триггеров → версия (НЕ публикует).
Публикация — `gtm_publish_version.py`; откат — публикация прежней живой версии (скрипт печатает её номер). Содержимое тега перед удалением
сохраняется в `Скрипты/_gtm_deleted/<имя>_v<версия>.json`.

    PYTHONUTF8=1 python gtm_delete_tag.py --account 6003760261 --container 44158621 --tag visitsToServer
    ... --execute
"""
import argparse
import json
import re
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

HERE = Path(__file__).resolve().parent
KEY = HERE / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions"]


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:600]}")
    return r.json() if r.text else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--tag", required=True, help="имя или id тега")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cont = f"accounts/{a.account}/containers/{a.container}"
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    live = call(s, "GET", cont + "/versions:live")
    heads = call(s, "GET", cont + "/version_headers").get("containerVersionHeader", [])
    last = max(int(h["containerVersionId"]) for h in heads)
    tag = next((t for t in live["tag"] if t["name"] == a.tag or t["tagId"] == a.tag), None)
    if not tag:
        raise SystemExit(f"тег «{a.tag}» не найден в живой версии {live.get('containerVersionId')}")
    errors = []
    if int(live["containerVersionId"]) != last:
        errors.append(f"живая версия {live['containerVersionId']} не последняя ({last}): в область попадут чужие неопубликованные правки")
    fire = tag.get("firingTriggerId", [])
    block = tag.get("blockingTriggerId", [])
    others = [t for t in live["tag"] if t["tagId"] != tag["tagId"]]
    orphan = []
    for tid in fire + block:
        users = [t["name"] for t in others if tid in t.get("firingTriggerId", []) or tid in t.get("blockingTriggerId", [])]
        name = next((x["name"] for x in live.get("trigger", []) if x["triggerId"] == tid), "?")
        print(f"триггер {tid} «{name}»: другие теги — {users or 'нет'}")
        if not users and not tid.startswith("2147"):  # встроенные (All Pages и т. п.) не удаляем
            orphan.append(tid)
    html = next((p["value"] for p in tag["parameter"] if p["key"] == "html"), "")
    print(f"тег {tag['tagId']} «{tag['name']}» ({tag['type']}), живая версия {live['containerVersionId']}; "
          f"будут удалены тег и триггеры {orphan or 'нет'}; текст тега {len(html)} знаков")
    if errors:
        raise SystemExit("ОСТАНОВКА: " + "; ".join(errors))
    if not a.execute:
        print("Проверка пройдена. Ничего не изменено (нужен --execute).")
        return
    bk = HERE / "_gtm_deleted"
    bk.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", tag["name"])
    saved = {"tag": tag, "triggers": [x for x in live.get("trigger", []) if x["triggerId"] in orphan]}
    (bk / f"{safe}_v{live['containerVersionId']}.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    ws = call(s, "POST", cont + "/workspaces", json={"name": f"delete-{safe}"[:60]})
    wp = ws["path"]
    call(s, "DELETE", f"{wp}/tags/{tag['tagId']}")
    for tid in orphan:
        call(s, "DELETE", f"{wp}/triggers/{tid}")
    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": f"Удалён тег «{tag['name']}»",
                     "notes": f"База — версия {live['containerVersionId']}. Удалены тег {tag['tagId']} и триггеры {orphan}. "
                              f"Копия в Скрипты/_gtm_deleted. Откат: опубликовать версию {live['containerVersionId']}."})
    cv = ver.get("containerVersion", {})
    print("Версия создана (НЕ опубликована):", cv.get("containerVersionId"), ver.get("compilerError", ""))
    print("Откат после публикации:", f"gtm_publish_version.py --account {a.account} --container {a.container} --version {live['containerVersionId']} --execute")


if __name__ == "__main__":
    main()
