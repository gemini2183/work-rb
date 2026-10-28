#!/usr/bin/env python
# coding: utf-8
"""Снимает минус-слова из общего списка минус-слов (shared set) Google Ads — по имени списка.

ЗАПИСЬ в аккаунт: без --execute — validate_only (Google проверяет, ничего не удаляет). Перед записью показывает,
к каким кампаниям подключён список (радиус действия) и что именно будет снято. С --execute: снимок «до» в Статистика/
клиента (откат — `gads_shared_negatives_add.py` с этим же текстом и типом), удаление, чтение обратно.
Только после согласования таблицы плана (CLAUDE.md, протокол записи в кабинет).

    python gads_shared_negatives_remove.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --list-name "gen / init" --text lyft --match BROAD [--execute]
"""
import argparse
import re
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_shared_negatives_add import find_list, read_attachments, read_members
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

SAFE_FILE = re.compile(r"[^\w-]+")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--list-name", required=True, help="Точное имя общего списка минус-слов")
    ap.add_argument("--text", required=True, nargs="+", help="Текст(ы) минус-слов к снятию")
    ap.add_argument("--match", required=True, choices=["EXACT", "PHRASE", "BROAD"])
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType

    sset = find_list(ga, cid, args.list_name)
    before = read_members(client, ga, cid, sset.id)
    attached = read_attachments(ga, cid, sset.id)
    print(f"Список «{sset.name}» (id {sset.id}): {len(before)} фраз; подключён к: "
          + "; ".join(f"{n} [{'ENABLED' if s == 2 else 'не включена'}]" for n, s in attached))

    want = {t.strip().lower() for t in args.text}
    q = ("SELECT shared_criterion.resource_name, shared_criterion.keyword.text, shared_criterion.keyword.match_type "
         f"FROM shared_criterion WHERE shared_set.id = {sset.id}")
    found = [(r.shared_criterion.resource_name, r.shared_criterion.keyword.text)
             for b in ga.search_stream(customer_id=cid, query=q) for r in b.results
             if r.shared_criterion.keyword.text.lower() in want
             and mt.Name(r.shared_criterion.keyword.match_type) == args.match]
    missing = want - {t.lower() for _, t in found}
    if missing:
        print(f"В списке нет ({args.match}): {', '.join(sorted(missing))}")
    if not found:
        return
    print("Объект | Действие | Было → Станет")
    for _, t in found:
        print(f"{sset.name} | минус {args.match} «{t}» | есть → снять")

    if args.execute:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        snap = client_stats_dir(args.client_folder) / f"shared_negatives_{SAFE_FILE.sub('_', sset.name)}_before_remove_{stamp}.csv"
        before.to_csv(snap, index=False, encoding="utf-8-sig")
        print(f"Снимок «до»: {snap}")

    req = client.get_type("MutateSharedCriteriaRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for rn, _ in found:
        op = client.get_type("SharedCriterionOperation")
        op.remove = rn
        req.operations.append(op)
    client.get_service("SharedCriterionService").mutate_shared_criteria(request=req)
    print("ВЫПОЛНЕНО (снято)" if args.execute else "validate_only: ОК, ничего не изменено")

    if args.execute:
        after = read_members(client, ga, cid, sset.id)
        left = [t for t in after[after.match == args.match].text.str.lower() if t in want]
        print(f"После (чтение обратно): в списке {len(after)} фраз (было {len(before)}); "
              f"из снимаемых осталось {len(left)}")


if __name__ == "__main__":
    main()
