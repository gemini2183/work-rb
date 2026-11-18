#!/usr/bin/env python
# coding: utf-8
"""Цели счётчика Яндекс.Метрики: список и настройки (только чтение).

Зачем: ответить «что именно считает цель» (тип, условия, ценность, статус)
без разового кода. Записи в Метрику скрипт не делает вообще (только GET).

Что делает: GET management/v1/counter/{id}/goals, выводит таблицу целей:
id, имя, тип (action/url/form/step/call/conditional_call/cdp_*), статус,
ценность по умолчанию, conditions (type:url/field). Фильтры:
  --goal-id (повторяемый; для них печатается подробный блок),
  --name-regex (по имени), --type (по типу), --condition-regex (по url/field
  в conditions, в т.ч. в условиях шагов составной цели).
Без --run - план, в API не ходит, таблицу с токенами не открывает.
С --run - читает цели, печатает таблицу, пишет CSV
Клиенты/<--client-folder>/Статистика/metrika_goals_<counter>_<дата>.csv (utf-8-sig).

Токен: из таблицы агентства (_config.get_client_row, вкладка Metrika, столбец
token) по --token-client; в вывод не печатается.

Пример (запускать с PYTHONUTF8=1):
  python metrika_goals_read.py --counter-id 66145201 \\
      --token-client "Мокрый Нос - Груминг Франшиза" \\
      --client-folder "Франшиза Мокрый Нос Дзен" \\
      --goal-id 143150284 --goal-id 195677773 --run

Дата создания: 2026-11-18.
"""
import argparse
import csv
import re
import sys
from datetime import date

API_URL = "https://api-metrika.yandex.net/management/v1/counter/{cid}/goals"


def fmt_cond(c):
    """Одно условие -> 'type:url' (для шагов - вложенно)."""
    if not isinstance(c, dict):
        return str(c)
    val = c.get("url", c.get("field", ""))
    return f"{c.get('type', '')}:{val}"


def conds_of(goal):
    """Условия цели, включая условия шагов составной цели (step)."""
    out = [fmt_cond(c) for c in goal.get("conditions") or []]
    for st in goal.get("steps") or []:
        sub = "; ".join(fmt_cond(c) for c in st.get("conditions") or [])
        out.append(f"шаг[{st.get('name', '')}]: {sub}")
    return out


def fetch_goals(counter_id, token):
    import requests
    r = requests.get(API_URL.format(cid=counter_id),
                     headers={"Authorization": f"OAuth {token}"}, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"Ошибка {r.status_code}: {r.text[:500]}")
    return r.json().get("goals", [])


def select(goals, args):
    res = []
    ids = {str(g) for g in args.goal_id}
    for g in goals:
        if ids and str(g.get("id")) not in ids:
            continue
        if args.type and g.get("type") != args.type:
            continue
        if args.name_regex and not re.search(args.name_regex, g.get("name", ""), re.I):
            continue
        if args.condition_regex and not any(
                re.search(args.condition_regex, c, re.I) for c in conds_of(g)):
            continue
        res.append(g)
    return res


def row_of(g):
    return {
        "id": g.get("id"),
        "name": g.get("name", ""),
        "type": g.get("type", ""),
        "status": g.get("goal_status", g.get("status", "")),
        "default_price": g.get("default_price", ""),
        "is_retargeting": g.get("is_retargeting", ""),
        "conditions": " | ".join(conds_of(g)),
    }


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Цели счётчика Метрики (только чтение)")
    ap.add_argument("--counter-id", required=True)
    ap.add_argument("--token-client", default="",
                    help="строка таблицы агентства (вкладка Metrika) с token; нужна для --run")
    ap.add_argument("--client-folder", default="", help="папка клиента в Клиенты/ (CSV в Статистика/)")
    ap.add_argument("--goal-id", action="append", default=[], help="id цели, повторяемый; печатается подробно")
    ap.add_argument("--name-regex", default="", help="regex по имени цели")
    ap.add_argument("--type", default="", help="тип цели: action/url/form/step/call/conditional_call/cdp_*")
    ap.add_argument("--condition-regex", default="", help="regex по url/field в conditions")
    ap.add_argument("--run", action="store_true", help="выполнить чтение API (без флага - только план)")
    args = ap.parse_args()

    print("План (только чтение management API Метрики):")
    print(f"  GET {API_URL.format(cid=args.counter_id)}")
    print(f"  фильтры: goal-id={args.goal_id or '-'} name={args.name_regex or '-'} "
          f"type={args.type or '-'} condition={args.condition_regex or '-'}")
    out_name = f"metrika_goals_{args.counter_id}_{date.today().isoformat()}.csv"
    print(f"  файл: Клиенты/{args.client_folder or '<--client-folder>'}/Статистика/{out_name}")
    if not args.run:
        print("Сухой режим: запрос не выполнялся. Для выполнения добавьте --run.")
        return
    if not args.token_client:
        raise SystemExit("Для --run нужен --token-client (строка вкладки Metrika)")

    from _config import get_client_row, client_stats_dir
    token = str(get_client_row(args.token_client, tab="Metrika").get("token", "")).strip()
    if not token:
        raise SystemExit(f"У '{args.token_client}' пустой token")

    goals = fetch_goals(args.counter_id, token)
    sel = select(goals, args)
    print(f"Целей на счётчике: {len(goals)}; после фильтров: {len(sel)}")
    rows = [row_of(g) for g in sel]
    for r in rows:
        print(f"{r['id']}\t{r['type']}\t{r['status']}\t{r['default_price']}\t"
              f"{r['name']}\t{r['conditions']}")
    if args.goal_id:
        print("\nПодробно:")
        for g in sel:
            r = row_of(g)
            print(f"- id {r['id']}: {r['name']}")
            print(f"    тип: {r['type']}; статус: {r['status']}; ценность по умолчанию: {r['default_price']}")
            cs = conds_of(g)
            print(f"    условия: {'; '.join(cs) if cs else 'нет'}")
    if args.client_folder:
        path = client_stats_dir(args.client_folder) / out_name
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                               ["id", "name", "type", "status", "default_price",
                                "is_retargeting", "conditions"])
            w.writeheader()
            w.writerows(rows)
        print(f"Сохранено: {path} ({len(rows)} строк)")
    else:
        print("CSV не записан: --client-folder не задан")


if __name__ == "__main__":
    main()
