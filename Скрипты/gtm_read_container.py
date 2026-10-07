#!/usr/bin/env python
# coding: utf-8
"""Читает контейнер Google Tag Manager через Tag Manager API (ТОЛЬКО ЧТЕНИЕ).

Зачем: быстро ответить «какой тег что запускает» без браузера: найти тег по метке конверсии/событию/имени,
показать его параметры, режим срабатывания, условия согласия и триггеры. Работает с любым клиентом, у которого
сервисный аккаунт из Скрипты/secrets/rb_cloud_service.json добавлен в GTM (минимум «Читать»).

Доступ: Tag Manager API включён в проекте Google Cloud redbird-196813, сервисный аккаунт
rb-cloud-admin@redbird-196813.iam.gserviceaccount.com добавлен в аккаунт GTM клиента (Админ → Управление
пользователями). Подробности — Инфраструктура.md, запись 2026-10-07.

Использование:
    python gtm_read_container.py --list-accounts
    python gtm_read_container.py --account 6003760261 --list-containers
    python gtm_read_container.py --account 6003760261 --container 44158621 --summary
    python gtm_read_container.py --account 6003760261 --container 44158621 --find ByvXCNOawbIZEJ-F4JAB
    python gtm_read_container.py --account 6003760261 --container 44158621 --find click_tel --version 61
"""
import argparse
import json
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPE = "https://www.googleapis.com/auth/tagmanager.readonly"


def session():
    creds = service_account.Credentials.from_service_account_file(str(KEY), scopes=[SCOPE])
    return AuthorizedSession(creds)


def get(s, path):
    r = s.get(BASE + path)
    if r.status_code != 200:
        raise SystemExit(f"GTM API {r.status_code}: {r.text[:300]}")
    return r.json()


def short_params(items, limit=140):
    return {p.get("key"): str(p.get("value"))[:limit] for p in (items or [])}


def describe_trigger(t):
    return {
        "id": t["triggerId"], "name": t["name"], "type": t["type"],
        "filter": t.get("filter") or t.get("customEventFilter") or t.get("autoEventFilter"),
        "parameter": short_params(t.get("parameter")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-accounts", action="store_true")
    ap.add_argument("--account")
    ap.add_argument("--list-containers", action="store_true")
    ap.add_argument("--container", help="числовой id контейнера (не GTM-XXXX)")
    ap.add_argument("--version", default="live", help="live (по умолчанию) или id версии")
    ap.add_argument("--summary", action="store_true", help="список тегов и триггеров с типами")
    ap.add_argument("--find", help="подстрока (метка конверсии, имя события, имя тега) — показать подходящие теги")
    args = ap.parse_args()

    s = session()
    if args.list_accounts:
        for a in get(s, "accounts").get("account", []):
            print(a["accountId"], a["name"])
        return
    if not args.account:
        raise SystemExit("нужен --account")
    if args.list_containers:
        for c in get(s, f"accounts/{args.account}/containers").get("container", []):
            print(c["containerId"], c["publicId"], c["name"], c.get("usageContext"))
        return
    if not args.container:
        raise SystemExit("нужен --container")

    path = f"accounts/{args.account}/containers/{args.container}/versions"
    v = get(s, path + (":live" if args.version == "live" else f"/{args.version}"))
    tags, trig = v.get("tag", []), {t["triggerId"]: t for t in v.get("trigger", [])}
    print(f"Версия {v.get('containerVersionId')} ({v.get('name') or 'без имени'}): тегов {len(tags)}, триггеров {len(trig)}")

    if args.summary:
        for t in tags:
            print(f"  тег {t['tagId']:>4} {t['type']:<8} {t['name']}  <- триггеры {t.get('firingTriggerId')}")
        for t in trig.values():
            print(f"  триггер {t['triggerId']:>4} {t['type']:<14} {t['name']}")

    if args.find:
        needle = args.find.lower()
        hits = [t for t in tags if needle in json.dumps(t, ensure_ascii=False).lower()]
        print(f"Найдено тегов по «{args.find}»: {len(hits)}")
        for t in hits:
            print(f"\nТЕГ {t['tagId']} «{t['name']}» тип {t['type']} paused={t.get('paused')}")
            print("  параметры:", json.dumps(short_params(t.get("parameter")), ensure_ascii=False))
            print("  режим срабатывания:", t.get("tagFiringOption"), "| согласие:", t.get("consentSettings"))
            for tid in (t.get("firingTriggerId") or []) + (t.get("blockingTriggerId") or []):
                kind = "блокирующий" if tid in (t.get("blockingTriggerId") or []) else "запускающий"
                d = describe_trigger(trig[tid]) if tid in trig else {"id": tid, "name": "?"}
                print(f"  {kind} триггер:", json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    main()
