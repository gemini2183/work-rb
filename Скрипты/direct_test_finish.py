#!/usr/bin/env python
# coding: utf-8
"""Второй тестовый цикл записи в Директ: ручная стратегия, правка ставки, минус-фразы, удаление.

Продолжает direct_test_cycle.py на той же тестовой кампании. Без --execute только план.
--execute: стратегия -> ставка -> минус-фразы (кампания и группа), чтение обратно.
--delete (вместе с --execute): после этого удаляет кампанию и читает список кампаний.

Использование:
    python direct_test_finish.py --client "Груминг - Северная 3" --campaign-id 715470053 \
        --adgroup-id 5815187673 --keyword-id 58314507299 --execute [--delete]
"""
import argparse
import json
import sys

import requests

from _config import get_client_row

BASE = "https://api.direct.yandex.com/json/v5/"
MICRO = 1_000_000


class Api:
    def __init__(self, login, token):
        self.h = {"Authorization": "Bearer " + token, "Client-Login": login, "Accept-Language": "ru"}

    def call(self, service, method, params):
        r = requests.post(BASE + service, json={"method": method, "params": params}, headers=self.h, timeout=120)
        js = r.json()
        print(f"  {service}.{method} -> {json.dumps(js, ensure_ascii=False)[:900]}")
        return js


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--campaign-id", type=int, required=True)
    ap.add_argument("--adgroup-id", type=int, required=True)
    ap.add_argument("--keyword-id", type=int, required=True)
    ap.add_argument("--new-bid", type=int, default=35, help="Ставка после смены стратегии, ₽")
    ap.add_argument("--negative", default="тест-минус")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--delete", action="store_true", help="Удалить кампанию (только вместе с --execute)")
    a = ap.parse_args()

    print(f"Кампания {a.campaign_id}: стратегия поиска -> HIGHEST_POSITION (ручные ставки), сети выключены;")
    print(f"ставка ключа {a.keyword_id} -> {a.new_bid} ₽; минус-фраза «{a.negative}» на кампанию и группу {a.adgroup_id}")
    print("Удаление кампании: " + ("ДА" if a.delete else "нет"))
    if not a.execute:
        print("\nРежим плана, ничего не записано. Для записи добавьте --execute")
        return

    row = get_client_row(a.client, tab="Директ")
    api = Api(str(row["login"]).strip(), str(row["token"]).strip())

    print("\n1. Ручная стратегия")
    api.call("campaigns", "update", {"Campaigns": [{"Id": a.campaign_id, "TextCampaign": {"BiddingStrategy": {
        "Search": {"BiddingStrategyType": "HIGHEST_POSITION"},
        "Network": {"BiddingStrategyType": "SERVING_OFF"}}}}]})

    print("\n2. Правка ставки")
    api.call("keywordbids", "set", {"KeywordBids": [{"KeywordId": a.keyword_id, "SearchBid": a.new_bid * MICRO}]})

    print("\n3. Минус-фразы")
    api.call("campaigns", "update", {"Campaigns": [{"Id": a.campaign_id, "NegativeKeywords": {"Items": [a.negative]}}]})
    api.call("adgroups", "update", {"AdGroups": [{"Id": a.adgroup_id, "NegativeKeywords": {"Items": [a.negative + "-группа"]}}]})

    print("\nЧтение обратно:")
    api.call("campaigns", "get", {"SelectionCriteria": {"Ids": [a.campaign_id]},
                                  "FieldNames": ["Id", "Name", "Status", "State", "NegativeKeywords"],
                                  "TextCampaignFieldNames": ["BiddingStrategy"]})
    api.call("adgroups", "get", {"SelectionCriteria": {"Ids": [a.adgroup_id]},
                                 "FieldNames": ["Id", "Name", "NegativeKeywords"]})
    api.call("keywords", "get", {"SelectionCriteria": {"Ids": [a.keyword_id]},
                                 "FieldNames": ["Id", "Keyword", "Bid", "State"]})
    api.call("keywordbids", "get", {"SelectionCriteria": {"KeywordIds": [a.keyword_id]},
                                    "FieldNames": ["KeywordId"], "SearchFieldNames": ["Bid"]})

    if a.delete:
        print("\n4. Удаление кампании")
        api.call("campaigns", "delete", {"SelectionCriteria": {"Ids": [a.campaign_id]}})
        print("\nСписок кампаний после удаления:")
        js = api.call("campaigns", "get", {"SelectionCriteria": {}, "FieldNames": ["Id", "Name", "State"]})
        ids = [c["Id"] for c in js.get("result", {}).get("Campaigns", [])]
        print("  Удалённая кампания в списке:", a.campaign_id in ids)


if __name__ == "__main__":
    main()
