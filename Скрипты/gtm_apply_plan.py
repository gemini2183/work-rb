#!/usr/bin/env python
# coding: utf-8
"""Применить пакет изменений к контейнеру Google Tag Manager по JSON-плану. ЗАПИСЬ.

Без --execute: только проверка (читает контейнер, проверяет план, ничего не создаёт).
С --execute: создаёт НОВУЮ рабочую область, в ней — встроенные переменные, переменные, триггеры, теги,
правит указанные существующие теги, создаёт версию контейнера. С --publish — публикует версию.
Живая версия до публикации остаётся прежней: откат — публикация предыдущей версии
(номер печатается в начале как «живая версия до»).

Нужен сервисный аккаунт из Скрипты/secrets/rb_cloud_service.json с правом «Публикация» в контейнере.

План (JSON):
  account, container, workspace_name, version_name, version_notes
  built_in_variables: ["elementId", "clickElement", ...]          (type из API)
  variables: [{name, type, parameter}]                              (формат ресурса GTM API v2)
  triggers:  [{name, type, filter|customEventFilter|autoEventFilter, parameter}]
  tags:      [{name, type, parameter, firingTriggerNames: [...], firingTriggerIds: [...]}]
  update_tags: [{name, set_event_parameters: {имя: значение}, set_consent: ["analytics_storage"],
                 set_parameters: [{type, key, value}] (заменить по ключу с точным типом), set_fields: {поле: значение} (setupTag, tagFiringOption; добавлено 2026-10-27)}]
               (для тегов gaawe: добавить параметры события; set_consent — заменить требуемые типы согласия; set_html — новый код HTML-тега)
  update_variables: [{name, set_parameter: {ключ: значение}}]      (например, javascript у JS-переменной; добавлено 2026-10-24)
  update_triggers:  [{name, set_parameter: {ключ: значение}, set_filter_arg1: "значение"}]
               (set_parameter — например elementSelector у триггера видимости; set_filter_arg1 — условие первого фильтра, например CSS-селектор клика)
  folders:   ["имя папки"]; у variables / triggers / tags ключ "folder": "имя папки" кладёт объект в папку (папка создаётся, если её нет;
               добавлено 2026-10-28)
  update_tags: set_blocking_triggers: ["имя триггера"] — добавить тегу исключающие триггеры (имена резолвятся в id; добавлено 2026-10-28)
  Имена триггеров резолвятся в id (созданные в этом пакете + существующие).

    python gtm_apply_plan.py --plan "Клиенты/Andverpersonalinjury/Трекинг/gtm_plan_2026-10-15.json"
    python gtm_apply_plan.py --plan ... --execute --publish
"""
import argparse
import json
import sys
import time
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parent.parent
KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]


def call(s, method, path, **kw):
    for attempt in range(6):  # лимит API: запросов в минуту на пользователя — ждём и повторяем
        r = s.request(method, BASE + path, **kw)
        if r.status_code != 429:
            break
        print(f"  лимит запросов, пауза 30 с (попытка {attempt + 1})")
        time.sleep(30)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:500]}")
    return r.json() if r.text else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="продолжить в уже заполненной рабочей области (пропустить созданное по имени)")
    a = ap.parse_args()
    p = Path(a.plan)
    plan = json.loads((p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8"))
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{plan['account']}/containers/{plan['container']}"

    live = call(s, "GET", cont + "/versions:live")
    print(f"Живая версия до: {live.get('containerVersionId')} «{live.get('name', '')}», "
          f"тегов {len(live.get('tag', []))}, триггеров {len(live.get('trigger', []))}")
    existing_tags = {t["name"]: t for t in live.get("tag", [])}
    existing_trg = {t["name"]: t["triggerId"] for t in live.get("trigger", [])}
    existing_var = {v["name"] for v in live.get("variable", [])}
    live_var_ids = {v["name"]: v["variableId"] for v in live.get("variable", [])}

    errors = []
    for u in plan.get("update_variables", []):
        if u["name"] not in live_var_ids:
            errors.append(f"нет переменной «{u['name']}» для правки")
    for u in plan.get("update_triggers", []):
        if u["name"] not in existing_trg:
            errors.append(f"нет триггера «{u['name']}» для правки")
    for t in plan.get("tags", []):
        if t["name"] in existing_tags:
            errors.append(f"тег «{t['name']}» уже есть")
    for v in plan.get("variables", []):
        if v["name"] in existing_var:
            errors.append(f"переменная «{v['name']}» уже есть")
    for u in plan.get("update_tags", []):
        if u["name"] not in existing_tags:
            errors.append(f"нет тега «{u['name']}» для правки")
    new_trg_names = {t["name"] for t in plan.get("triggers", [])}
    for t in plan.get("tags", []):
        for n in t.get("firingTriggerNames", []):
            if n not in new_trg_names and n not in existing_trg:
                errors.append(f"тег «{t['name']}»: триггер «{n}» не найден")
    print(f"\nПлан: переменных {len(plan.get('variables', []))}, триггеров {len(plan.get('triggers', []))}, "
          f"новых тегов {len(plan.get('tags', []))}, правок тегов {len(plan.get('update_tags', []))}")
    for t in plan.get("tags", []):
        print("  + тег", t["name"], "<-", t.get("firingTriggerNames") or t.get("firingTriggerIds"))
    for u in plan.get("update_tags", []):
        print("  ~ тег", u["name"], "параметры:", list(u.get("set_event_parameters", {})), [x["key"] for x in u.get("set_parameters", [])],
              "поля:", list(u.get("set_fields", {})), "исключающие триггеры:", u.get("set_blocking_triggers", []), "html:", bool(u.get("set_html")),
              "согласие:", u.get("set_consent", "без изменений"))
    for u in plan.get("update_variables", []):
        print("  ~ переменная", u["name"], "поля:", list(u.get("set_parameter", {})))
    for u in plan.get("update_triggers", []):
        print("  ~ триггер", u["name"], "поля:", list(u.get("set_parameter", {})))
    if errors:
        print("\nОСТАНОВКА:")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)
    if not a.execute:
        print("\nПроверка пройдена. Ничего не изменено (нужен --execute).")
        return

    same = [w for w in call(s, "GET", cont + "/workspaces").get("workspace", []) if w["name"] == plan["workspace_name"]]
    if same:
        ws = same[0]
        if call(s, "GET", ws["path"] + "/status").get("workspaceChange") and not a.resume:
            raise SystemExit(f"Рабочая область «{ws['name']}» уже содержит изменения — разберите вручную или смените workspace_name")
        print("Использую пустую существующую рабочую область")
    else:
        ws = call(s, "POST", cont + "/workspaces", json={"name": plan["workspace_name"]})
    wp = ws["path"]
    print("\nРабочая область:", ws["name"], ws["workspaceId"])
    if plan.get("built_in_variables"):
        q = "&".join(f"type={t}" for t in plan["built_in_variables"])
        call(s, "POST", f"{wp}/built_in_variables?{q}")
        print("Встроенные переменные включены:", plan["built_in_variables"])
    folder_ids = {f["name"]: f["folderId"] for f in call(s, "GET", f"{wp}/folders").get("folder", [])}
    for fname in plan.get("folders", []):
        if fname not in folder_ids:
            folder_ids[fname] = call(s, "POST", f"{wp}/folders", json={"name": fname})["folderId"]
            print("  папка", fname, folder_ids[fname])

    def with_folder(obj, drop=()):
        body = {k: v for k, v in obj.items() if k not in ("folder",) + tuple(drop)}
        if obj.get("folder"):
            body["parentFolderId"] = folder_ids[obj["folder"]]
        return body

    have_v = {v["name"] for v in call(s, "GET", f"{wp}/variables").get("variable", [])}
    have_t = {t["name"]: t["triggerId"] for t in call(s, "GET", f"{wp}/triggers").get("trigger", [])}
    have_g = {t["name"] for t in call(s, "GET", f"{wp}/tags").get("tag", [])}
    for v in plan.get("variables", []):
        if v["name"] in have_v:
            continue
        call(s, "POST", f"{wp}/variables", json=with_folder(v))
        print("  переменная", v["name"])
    trg_ids = dict(existing_trg)
    for t in plan.get("triggers", []):
        if t["name"] in have_t:
            trg_ids[t["name"]] = have_t[t["name"]]
            continue
        r = call(s, "POST", f"{wp}/triggers", json=with_folder(t))
        trg_ids[t["name"]] = r["triggerId"]
        print("  триггер", t["name"], r["triggerId"])
    for t in plan.get("tags", []):
        if t["name"] in have_g:
            continue
        body = with_folder(t, drop=("firingTriggerNames", "firingTriggerIds"))
        body["firingTriggerId"] = [trg_ids[n] for n in t.get("firingTriggerNames", [])] + list(t.get("firingTriggerIds", []))
        r = call(s, "POST", f"{wp}/tags", json=body)
        print("  тег", t["name"], r["tagId"])
    for u in plan.get("update_tags", []):
        tag = call(s, "GET", f"{wp}/tags/{existing_tags[u['name']]['tagId']}")
        if u.get("set_event_parameters"):
            params = [x for x in tag.get("parameter", []) if x.get("key") != "eventSettingsTable"]
            rows = [{"type": "map", "map": [{"type": "template", "key": "parameter", "value": k},
                                             {"type": "template", "key": "parameterValue", "value": v}]}
                    for k, v in u["set_event_parameters"].items()]
            params.append({"type": "list", "key": "eventSettingsTable", "list": rows})
            tag["parameter"] = params
        for np_ in u.get("set_parameters", []):  # заменить/добавить параметры по ключу с точным типом (boolean, template, ...)
            tag["parameter"] = [x for x in tag.get("parameter", []) if x.get("key") != np_["key"]] + [np_]
        if u.get("set_blocking_triggers"):
            tag["blockingTriggerId"] = sorted(set(tag.get("blockingTriggerId", [])) | {trg_ids[n] for n in u["set_blocking_triggers"]})
        tag.update(u.get("set_fields", {}))  # верхний уровень тега: setupTag, tagFiringOption, ...
        if u.get("set_html"):  # заменить код пользовательского HTML-тега
            for x in tag.get("parameter", []):
                if x.get("key") == "html":
                    x["value"] = u["set_html"]
        if u.get("set_consent"):
            tag["consentSettings"] = {"consentStatus": "needed", "consentType": {
                "type": "list", "list": [{"type": "template", "value": c} for c in u["set_consent"]]}}
        call(s, "PUT", f"{wp}/tags/{tag['tagId']}?fingerprint={tag['fingerprint']}", json=tag)
        print("  правка тега", u["name"])
    for kind, key, ids in (("variables", "update_variables", live_var_ids), ("triggers", "update_triggers", existing_trg)):
        for u in plan.get(key, []):
            obj = call(s, "GET", f"{wp}/{kind}/{ids[u['name']]}")
            for k, v in u.get("set_parameter", {}).items():
                for x in obj.get("parameter", []):
                    if x.get("key") == k:
                        x["value"] = v
                        break
                else:
                    raise SystemExit(f"{kind[:-1]} «{u['name']}»: нет поля «{k}»")
            if u.get("set_filter_arg1"):  # значение условия триггера (arg1 первого фильтра), например CSS-селектор клика
                for x in obj["filter"][0]["parameter"]:
                    if x.get("key") == "arg1":
                        x["value"] = u["set_filter_arg1"]
            call(s, "PUT", f"{wp}/{kind}/{ids[u['name']]}?fingerprint={obj['fingerprint']}", json=obj)
            print("  правка", "переменной" if kind == "variables" else "триггера", u["name"])

    ver = call(s, "POST", f"{wp}:create_version",
               json={"name": plan.get("version_name", plan["workspace_name"]), "notes": plan.get("version_notes", "")})
    if ver.get("compilerError"):
        raise SystemExit("compilerError: " + json.dumps(ver, ensure_ascii=False)[:600])
    cv = ver["containerVersion"]
    print(f"\nВерсия создана: {cv['containerVersionId']}, тегов {len(cv.get('tag', []))}, "
          f"триггеров {len(cv.get('trigger', []))}")
    if not a.publish:
        print("Не опубликовано (нужен --publish). Живая версия прежняя.")
        return
    call(s, "POST", cont + f"/versions/{cv['containerVersionId']}:publish")
    now = call(s, "GET", cont + "/versions:live")
    print(f"ОПУБЛИКОВАНО. Живая версия сейчас: {now['containerVersionId']} «{now.get('name', '')}», "
          f"тегов {len(now.get('tag', []))}")
    print("Откат: опубликовать версию", live.get("containerVersionId"))


if __name__ == "__main__":
    main()
