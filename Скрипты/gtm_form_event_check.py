#!/usr/bin/env python
# coding: utf-8
"""Ловит ли контейнер GTM событие отправки формы Tilda (ТОЛЬКО ЧТЕНИЕ).

Tilda после успешной отправки пушит в dataLayer событие `submit_<id формы>`. Скрипт берёт id форм страницы,
строит это имя и проверяет его регулярными выражениями триггеров типа «Пользовательское событие», на которых
стоят теги GA4 с именем события form_submit (или другим из --tag-event). Для каждой формы печатает ЛОВИТСЯ / НЕ ЛОВИТСЯ
и какие триггеры совпали. Ничего не пишет в GTM.

Ограничения: имя события выводится по правилу Tilda (подтверждено живой отправкой на испанской странице Landver),
а не наблюдается; регэкспы проверяются питоновским `re.search` (у GTM — JS, для простых выражений совпадает);
триггеры других типов (клик, видимость, форма) не разбираются — помечаются «не разобран».

Использование (из папки Скрипты):
    python gtm_form_event_check.py --account 6353362488 --container 261134482 --form-id ldv-moto-form
    python gtm_form_event_check.py --account 6353362488 --container 261134482 --form-id vb-b2s-form --form-id ldv-form-el --version 17
Код возврата 1 — есть форма, которую контейнер не ловит.
"""
import argparse
import re
import sys

from gtm_read_container import get, session


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True, help="числовой id контейнера")
    ap.add_argument("--form-id", action="append", required=True, help="id формы на странице (повторять для нескольких)")
    ap.add_argument("--version", default="live")
    ap.add_argument("--tag-event", default="form_submit", help="имя события GA4 в теге, которое должна запускать отправка формы")
    args = ap.parse_args()

    s = session()
    path = f"accounts/{args.account}/containers/{args.container}/versions"
    v = get(s, path + (":live" if args.version == "live" else f"/{args.version}"))
    trig = {t["triggerId"]: t for t in v.get("trigger", [])}
    tags = []
    for t in v.get("tag", []):
        params = {p.get("key"): p.get("value") for p in t.get("parameter", [])}
        if t.get("type") == "gaawe" and params.get("eventName") == args.tag_event and not t.get("paused"):
            tags.append(t)
    print(f"Версия {v.get('containerVersionId')} «{v.get('name') or 'без имени'}»: тегов GA4 с событием {args.tag_event}: {len(tags)}")
    for t in tags:
        print(f"  тег {t['tagId']} «{t['name']}» <- триггеры {t.get('firingTriggerId')}")

    bad = 0
    for fid in args.form_id:
        event = f"submit_{fid}"
        matched, unparsed = [], []
        for t in tags:
            for tid in t.get("firingTriggerId") or []:
                tr = trig.get(tid)
                if not tr:
                    continue
                if tr.get("type") != "customEvent":
                    unparsed.append(f"{tid} «{tr['name']}» ({tr['type']})")
                    continue
                for f in tr.get("customEventFilter") or []:
                    ps = {p["key"]: p.get("value") for p in f.get("parameter", [])}
                    arg1 = ps.get("arg1", "")
                    ftype = f.get("type")
                    if ftype == "matchRegex":
                        ok = re.search(arg1, event) is not None
                    elif ftype == "equals":
                        ok = event == arg1
                    elif ftype == "contains":
                        ok = arg1 in event
                    elif ftype == "startsWith":
                        ok = event.startswith(arg1)
                    else:
                        unparsed.append(f"{tid} «{tr['name']}» (условие {ftype})")
                        continue
                    if ok:
                        matched.append(f"{tid} «{tr['name']}» ({ftype} {arg1})")
        if matched:
            print(f"ЛОВИТСЯ      форма {fid}: событие {event}  <- " + "; ".join(sorted(set(matched))))
        else:
            bad += 1
            print(f"НЕ ЛОВИТСЯ   форма {fid}: событие {event} не подходит ни под один триггер тегов {args.tag_event}")
        if unparsed:
            print("  не разобраны: " + "; ".join(sorted(set(unparsed))))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
