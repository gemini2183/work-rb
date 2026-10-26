#!/usr/bin/env python
# coding: utf-8
"""Тестовый цикл записи в Яндекс.Директ: группа -> объявление -> ключ -> ставка, всё выключено.

Работает внутри уже созданной кампании (см. direct_campaign_create.py). Без --execute только
печатает план. С --execute пишет по шагам, объявление и ключ сразу ставит на паузу, затем
читает всё обратно. Ошибка любого шага останавливает цикл и печатается как есть.

Использование:
    python direct_test_cycle.py --client "Груминг - Северная 3" --campaign-id 715470053 --href https://...
    python direct_test_cycle.py ... --execute
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
        print(f"  {service}.{method} -> {json.dumps(js, ensure_ascii=False)[:700]}")
        return js


def first_id(js, key):
    """Id первого результата add/set или None, если есть ошибка."""
    if "error" in js:
        return None
    res = js["result"][key][0]
    return None if res.get("Errors") else res.get("Id")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--campaign-id", type=int, required=True)
    ap.add_argument("--href", required=True)
    ap.add_argument("--region", type=int, default=1)
    ap.add_argument("--group", default="Тест API")
    ap.add_argument("--title", default="Тест API, не включать")
    ap.add_argument("--text", default="Тестовое объявление для проверки API. Не включать.")
    ap.add_argument("--keyword", default="тест апи груминг")
    ap.add_argument("--bid", type=int, default=30, help="Ставка ключа, ₽")
    ap.add_argument("--new-bid", type=int, default=35, help="Ставка после правки, ₽")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()

    print(f"Кампания {a.campaign_id}, группа «{a.group}», регион {a.region}")
    print(f"Объявление: «{a.title}» ({len(a.title)}/35) / «{a.text}» ({len(a.text)}/81) -> {a.href}")
    print(f"Ключ «{a.keyword}», ставка {a.bid} ₽ -> {a.new_bid} ₽; объявление и ключ ставятся на паузу")
    if not a.execute:
        print("\nРежим плана, ничего не записано. Для записи добавьте --execute")
        return

    row = get_client_row(a.client, tab="Директ")
    api = Api(str(row["login"]).strip(), str(row["token"]).strip())

    print("\n1. Группа")
    gid = first_id(api.call("adgroups", "add", {"AdGroups": [
        {"Name": a.group, "CampaignId": a.campaign_id, "RegionIds": [a.region]}]}), "AddResults")
    if not gid:
        sys.exit("Остановка: группа не создана")

    print("\n2. Объявление и пауза")
    ad = first_id(api.call("ads", "add", {"Ads": [{"AdGroupId": gid, "TextAd": {
        "Title": a.title, "Text": a.text, "Href": a.href, "Mobile": "NO"}}]}), "AddResults")
    if not ad:
        sys.exit("Остановка: объявление не создано")
    api.call("ads", "suspend", {"SelectionCriteria": {"Ids": [ad]}})

    print("\n3. Ключ и пауза")
    kw_js = api.call("keywords", "add", {"Keywords": [
        {"AdGroupId": gid, "Keyword": a.keyword, "Bid": a.bid * MICRO}]})
    kw = first_id(kw_js, "AddResults")
    if not kw:
        print("  со ставкой не принял, пробую без ставки")
        kw = first_id(api.call("keywords", "add", {"Keywords": [{"AdGroupId": gid, "Keyword": a.keyword}]}), "AddResults")
    if not kw:
        sys.exit("Остановка: ключ не создан")
    api.call("keywords", "suspend", {"SelectionCriteria": {"Ids": [kw]}})

    print("\n4. Правка ставки")
    api.call("keywordbids", "set", {"KeywordBids": [{"KeywordId": kw, "SearchBid": a.new_bid * MICRO}]})

    print("\nЧтение обратно:")
    api.call("adgroups", "get", {"SelectionCriteria": {"Ids": [gid]},
                                 "FieldNames": ["Id", "Name", "CampaignId", "RegionIds", "Status", "ServingStatus"]})
    api.call("ads", "get", {"SelectionCriteria": {"Ids": [ad]}, "FieldNames": ["Id", "State", "Status"],
                            "TextAdFieldNames": ["Title", "Text", "Href"]})
    api.call("keywords", "get", {"SelectionCriteria": {"Ids": [kw]},
                                 "FieldNames": ["Id", "Keyword", "Bid", "State", "Status", "ServingStatus"]})
    api.call("campaigns", "get", {"SelectionCriteria": {"Ids": [a.campaign_id]},
                                  "FieldNames": ["Id", "Name", "Status", "State"]})
    print(f"\nIds: группа {gid}, объявление {ad}, ключ {kw}")


if __name__ == "__main__":
    main()
