#!/usr/bin/env python
# coding: utf-8
"""План новой группы Search «<Тема> - Exact» для gads_campaign_rework.py из файлов плана (ТОЛЬКО формирует JSON, в кабинет не пишет).

Берёт: RSA-yaml (final_url, path1, headlines_pin1/_pin2, headlines, description_pin1, descriptions), CSV точных ключей
(колонки keyword, group) и ставку. Пишет `<out-dir>/topic_group_<slug>_plan_<дата>.json` — по одному файлу на группу,
потому что `gads_campaign_rework.py` создаёт одну новую группу за запуск. Группа создаётся на ПАУЗЕ, ключи EXACT.
Групповые минусы и быстрые ссылки к группе добавляются отдельно после создания: `gads_adgroup_negatives.py`, `gads_sitelinks.py`.

    python gads_topic_groups_plan.py --client-folder Andverpersonalinjury --campaign "search / car+truck injuries / s / lp - tilda" \
        --rsa Креативы/rsa_6themes_2026-10-28.yaml --keywords Статистика/exact_plan_6themes_2026-10-28.csv \
        --groups "Wrongful Death - Exact" "Brain Injury - Exact" "Rideshare - Exact" --bid 100 --out-dir Кампании/Search
    python gads_campaign_rework.py --plan Клиенты/Andverpersonalinjury/Кампании/Search/topic_group_<...>_plan_<дата>.json  [--execute]
"""
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--customer-id", default="2136216123")
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--rsa", required=True, help="yaml с текстами, путь от папки клиента")
    ap.add_argument("--keywords", required=True, help="csv с колонками keyword, group, путь от папки клиента")
    ap.add_argument("--groups", nargs="+", required=True)
    ap.add_argument("--bid", type=float, required=True, help="ставка группы, $")
    ap.add_argument("--out-dir", required=True, help="папка для планов, путь от папки клиента")
    args = ap.parse_args()

    base = ROOT / "Клиенты" / args.client_folder
    rsa = yaml.safe_load((base / args.rsa).read_text(encoding="utf-8"))
    with open(base / args.keywords, encoding="utf-8-sig", newline="") as f:
        kws = list(csv.DictReader(f))

    for g in args.groups:
        r = rsa[g]
        keys = list(dict.fromkeys(k["keyword"].strip().lower() for k in kws if k["group"] == g))
        heads = ([{"text": t, "pin": "HEADLINE_1"} for t in r["headlines_pin1"]]
                 + [{"text": t, "pin": "HEADLINE_2"} for t in r["headlines_pin2"]]
                 + [{"text": t} for t in r["headlines"]])
        descs = [{"text": r["description_pin1"], "pin": "DESCRIPTION_1"}] + [{"text": t} for t in r["descriptions"]]
        assert len(heads) <= 15 and len(descs) <= 4, g
        plan = {
            "_comment": f"Новая группа «{g}» на паузе, ключи EXACT, ставка ${args.bid:g}. Сформировано gads_topic_groups_plan.py {date.today()} из {args.rsa} и {args.keywords}",
            "customer_id": args.customer_id,
            "campaign": args.campaign,
            "new_group": {"name": g, "status": "PAUSED", "cpc_bid_micros": int(args.bid * 1_000_000),
                          "keywords": keys, "match": "EXACT"},
            "rsa": {"final_url": r["final_url"], "path1": r.get("path1", ""), "path2": r.get("path2", ""),
                    "ad_groups": [], "also_new_group": True, "headlines": heads, "descriptions": descs},
        }
        out = base / args.out_dir / f"topic_group_{slug(g)}_plan_{date.today()}.json"
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{g}: ключей {len(keys)}, заголовков {len(heads)}, описаний {len(descs)} -> {out}")


if __name__ == "__main__":
    main()
