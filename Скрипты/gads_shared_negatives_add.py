#!/usr/bin/env python
# coding: utf-8
"""Добавляет минус-слова в общий список минус-слов (shared set) Google Ads — по имени списка.

ЗАПИСЬ в аккаунт: без --execute — validate_only (Google проверяет, ничего не создаёт). Уже существующие в списке
(тот же текст и тип) пропускает. Перед записью показывает, к каким кампаниям подключён список (радиус действия),
проверяет лимиты Google (80 знаков, 10 слов, 5000 на список). С --execute: снимок «до» в Статистика/ клиента,
запись, чтение обратно. Только после согласования таблицы плана (CLAUDE.md, протокол записи в кабинет).

CSV с колонкой текста (по умолчанию `text`); тип совпадения один на запуск (--match).

    python gads_shared_negatives_add.py --customer-id 882-613-4558 --client-folder "EkspertAgro/Мерчант" \
        --list-name "Shop - запросы без размера 2" --csv new_exact.csv --column term --match EXACT [--execute]
"""
import argparse
import re
from datetime import datetime

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

LIST_LIMIT = 5000
MAX_CHARS = 80
MAX_WORDS = 10
SAFE_FILE = re.compile(r"[^\w-]+")
# Google отклоняет такие символы в тексте минус-слова (напр. запятую в «3x4,5m»)
INVALID_CHARS = set(",!@%^()={};~`<>?\\|")


def find_list(ga, cid, name):
    q = ("SELECT shared_set.id, shared_set.name, shared_set.resource_name, shared_set.member_count "
         "FROM shared_set WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND shared_set.status = 'ENABLED'")
    found = [r.shared_set for b in ga.search_stream(customer_id=cid, query=q) for r in b.results
             if r.shared_set.name == name]
    if len(found) != 1:
        raise SystemExit(f"Список «{name}» найден {len(found)} раз(а), ожидался один")
    return found[0]


def read_members(client, ga, cid, set_id):
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType
    q = ("SELECT shared_criterion.keyword.text, shared_criterion.keyword.match_type "
         f"FROM shared_criterion WHERE shared_set.id = {set_id}")
    return pd.DataFrame([
        {"text": r.shared_criterion.keyword.text, "match": mt.Name(r.shared_criterion.keyword.match_type)}
        for b in ga.search_stream(customer_id=cid, query=q) for r in b.results
    ], columns=["text", "match"])


def read_attachments(ga, cid, set_id):
    q = ("SELECT campaign.name, campaign.status FROM campaign_shared_set "
         f"WHERE shared_set.id = {set_id} AND campaign_shared_set.status = 'ENABLED'")
    return [(r.campaign.name, int(r.campaign.status)) for b in ga.search_stream(customer_id=cid, query=q) for r in b.results]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "EkspertAgro/Мерчант"')
    ap.add_argument("--list-name", required=True, help="Точное имя общего списка минус-слов")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--column", default="text")
    ap.add_argument("--match", required=True, choices=["EXACT", "PHRASE", "BROAD"])
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    texts = [str(t).strip().lower() for t in pd.read_csv(args.csv, encoding="utf-8-sig")[args.column].dropna()]
    texts = list(dict.fromkeys(t for t in texts if t))

    sset = find_list(ga, cid, args.list_name)
    before = read_members(client, ga, cid, sset.id)
    have = set(zip(before.text.str.lower(), before.match))
    attached = read_attachments(ga, cid, sset.id)
    print(f"Список «{sset.name}» (id {sset.id}): {len(before)} фраз; подключён к: "
          + "; ".join(f"{n} [{'ENABLED' if s == 2 else 'не включена'}]" for n, s in attached))

    new = [t for t in texts if (t, args.match) not in have]
    too_long = [t for t in new if len(t) > MAX_CHARS or len(t.split()) > MAX_WORDS or INVALID_CHARS & set(t)]
    new = [t for t in new if t not in too_long]
    print(f"Во входном файле {len(texts)}; уже в списке {len(texts) - len(new) - len(too_long)}; "
          f"не проходят правила Google (длина/слова/символы) {len(too_long)}; к добавлению {len(new)} ({args.match})")
    if len(before) + len(new) > LIST_LIMIT:
        raise SystemExit(f"Превышен лимит списка: {len(before)} + {len(new)} > {LIST_LIMIT}")
    if not new:
        return
    print("Объект | Действие | Было → Станет")
    for t in new[:15]:
        print(f"{sset.name} | минус {args.match} «{t}» | нет → добавить")
    if len(new) > 15:
        print(f"… и ещё {len(new) - 15}")

    if args.execute:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        safe = SAFE_FILE.sub("_", sset.name)
        snap = client_stats_dir(args.client_folder) / f"shared_negatives_{safe}_before_{stamp}.csv"
        before.to_csv(snap, index=False, encoding="utf-8-sig")
        print(f"Снимок «до»: {snap}")

    req = client.get_type("MutateSharedCriteriaRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for t in new:
        op = client.get_type("SharedCriterionOperation")
        op.create.shared_set = sset.resource_name
        op.create.keyword.text = t
        op.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, args.match)
        req.operations.append(op)
    client.get_service("SharedCriterionService").mutate_shared_criteria(request=req)
    print("ВЫПОЛНЕНО (добавлено)" if args.execute else "validate_only: ОК, ничего не изменено")

    if args.execute:
        after = read_members(client, ga, cid, sset.id)
        have2 = set(zip(after.text.str.lower(), after.match))
        print(f"После (чтение обратно): в списке {len(after)} фраз (было {len(before)}); "
              f"из добавляемых на месте {sum((t, args.match) in have2 for t in new)} из {len(new)}")


if __name__ == "__main__":
    main()
