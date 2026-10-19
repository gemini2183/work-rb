#!/usr/bin/env python
# coding: utf-8
"""Опубликовать версию контейнера GTM и прочитать результат обратно. ЗАПИСЬ в боевой контейнер — только по явному «опубликуй».

Один универсальный инструмент публикации для любых клиентов, контейнеров и версий (правка переменных/тегов делается другими
скриптами и только создаёт черновик версии). Без --execute показывает, что будет опубликовано: имя версии, число тегов /
переменных / триггеров, какая версия сейчас живая. С --execute публикует и читает живую версию обратно.

    python gtm_publish_version.py --account 6003760261 --container 44158621 --version 63              # план
    python gtm_publish_version.py --account 6003760261 --container 44158621 --version 63 --execute     # публикация

Откат — тот же скрипт с номером прежней версии (в плане печатается «сейчас живая: N»).
"""
import argparse
import io
import sys
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]


def call(s, method, path):
    r = s.request(method, BASE + path)
    if r.status_code >= 300:
        raise SystemExit(f"GTM API {r.status_code}: {r.text[:500]}")
    return r.json()


def summary(v):
    return (f"версия {v.get('containerVersionId')} «{v.get('name', '')}»: тегов {len(v.get('tag', []))}, "
            f"переменных {len(v.get('variable', []))}, триггеров {len(v.get('trigger', []))}")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--execute", action="store_true", help="без флага — только план")
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{a.account}/containers/{a.container}"
    live_before = call(s, "GET", f"{cont}/versions:live")
    target = call(s, "GET", f"{cont}/versions/{a.version}")
    print("сейчас живая:", summary(live_before))
    print("будет опубликована:", summary(target))
    if str(live_before.get("containerVersionId")) == str(a.version):
        print("эта версия уже живая — ничего не делаю")
        return
    if not a.execute:
        print("ПЛАН: ничего не записано. Для публикации добавить --execute.")
        return
    call(s, "POST", f"{cont}/versions/{a.version}:publish")
    live_after = call(s, "GET", f"{cont}/versions:live")
    print("после публикации живая:", summary(live_after))
    print("ОК" if str(live_after.get("containerVersionId")) == str(a.version) else "ВНИМАНИЕ: живая версия не совпала")
    print(f"откат: --version {live_before.get('containerVersionId')} --execute")


if __name__ == "__main__":
    main()
