#!/usr/bin/env python
# coding: utf-8
"""Тестовый цикл записи в Директ на АКТУАЛЬНЫХ типах: Единая перфоманс-кампания (ЕПК).

UnifiedCampaign -> UnifiedAdGroup -> ResponsiveAd (комбинаторное) -> ключ -> ставка -> минус-фразы,
затем чтение обратно. Адрес v501 (по документации Директа для ЕПК). Только поиск: сети выключены
(Network.SERVING_OFF). Стратегия поиска ручная (HIGHEST_POSITION), чтобы ставки применялись.

Без --execute — только план. --execute пишет и читает обратно; --delete (с --execute) удаляет
созданную кампанию в конце. Предыдущие direct_campaign_create / direct_test_cycle / direct_test_finish
создавали устаревший TEXT_CAMPAIGN через v5 — для новых кампаний не использовать.

Использование:
    python direct_epk_cycle.py --client "Груминг - Северная 3" --name "..." --href https://...
    python direct_epk_cycle.py ... --execute --delete
"""
import argparse
import json
import sys
from datetime import date

import requests

from _config import get_client_row

BASE = "https://api.direct.yandex.com/json/v501/"
MICRO = 1_000_000


class Api:
    def __init__(self, login, token):
        self.h = {"Authorization": "Bearer " + token, "Client-Login": login, "Accept-Language": "ru"}

    def call(self, service, method, params):
        r = requests.post(BASE + service, json={"method": method, "params": params}, headers=self.h, timeout=120)
        js = r.json()
        print(f"  {service}.{method} -> {json.dumps(js, ensure_ascii=False)[:1100]}")
        return js


def first_id(js, key):
    if "error" in js:
        return None
    res = js["result"][key][0]
    return None if res.get("Errors") else res.get("Id")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--name", default="Тестовая ЕПК для тестирования API")
    ap.add_argument("--href", required=True)
    ap.add_argument("--region", type=int, default=1)
    ap.add_argument("--titles", nargs="+", default=["Тест API, не включать", "Тест API, проверка"])
    ap.add_argument("--texts", nargs="+", default=["Тестовое объявление для проверки API. Не включать."])
    ap.add_argument("--keyword", default="тест апи груминг")
    ap.add_argument("--bid", type=int, default=30)
    ap.add_argument("--new-bid", type=int, default=35)
    ap.add_argument("--negative", default="тест-минус")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--delete", action="store_true")
    a = ap.parse_args()

    print(f"ЕПК «{a.name}», только поиск, ручная стратегия HIGHEST_POSITION, сети выключены, регион {a.region}")
    print(f"Объявление ResponsiveAd: заголовки {a.titles} / тексты {a.texts} -> {a.href}")
    print(f"Ключ «{a.keyword}»: {a.bid} ₽ -> {a.new_bid} ₽, на паузу; минус-фраза «{a.negative}»; удаление в конце: {a.delete}")
    if not a.execute:
        print("\nРежим плана, ничего не записано. Для записи добавьте --execute")
        return

    row = get_client_row(a.client, tab="Директ")
    api = Api(str(row["login"]).strip(), str(row["token"]).strip())

    print("\n1. Кампания (UnifiedCampaign)")
    cid = first_id(api.call("campaigns", "add", {"Campaigns": [{
        "Name": a.name, "StartDate": str(date.today()),
        "UnifiedCampaign": {"BiddingStrategy": {
            "Search": {"BiddingStrategyType": "HIGHEST_POSITION",
                       "PlacementTypes": {"SearchResults": "YES", "ProductGallery": "NO", "Maps": "NO",
                                          "SearchOrganizationList": "NO"}},
            "Network": {"BiddingStrategyType": "SERVING_OFF"}}}}]}), "AddResults")
    if not cid:
        sys.exit("Остановка: кампания не создана")

    print("\n2. Группа (UnifiedAdGroup)")
    gid = first_id(api.call("adgroups", "add", {"AdGroups": [{
        "Name": "Тест API", "CampaignId": cid, "RegionIds": [a.region],
        "UnifiedAdGroup": {"OfferRetargeting": "NO"}}]}), "AddResults")
    if not gid:
        sys.exit(f"Остановка: группа не создана (кампания {cid} осталась)")

    print("\n3. Объявление (ResponsiveAd)")
    ad = first_id(api.call("ads", "add", {"Ads": [{
        "AdGroupId": gid, "ResponsiveAd": {"Titles": a.titles, "Texts": a.texts, "Href": a.href}}]}), "AddResults")

    print("\n4. Ключ со ставкой, пауза, правка ставки")
    kw = first_id(api.call("keywords", "add", {"Keywords": [
        {"AdGroupId": gid, "Keyword": a.keyword, "Bid": a.bid * MICRO}]}), "AddResults")
    if kw:
        api.call("keywords", "suspend", {"SelectionCriteria": {"Ids": [kw]}})
        api.call("keywordbids", "set", {"KeywordBids": [{"KeywordId": kw, "SearchBid": a.new_bid * MICRO}]})

    print("\n5. Минус-фразы")
    api.call("campaigns", "update", {"Campaigns": [{"Id": cid, "NegativeKeywords": {"Items": [a.negative]}}]})
    api.call("adgroups", "update", {"AdGroups": [{"Id": gid, "NegativeKeywords": {"Items": [a.negative + "-группа"]}}]})

    print("\nЧтение обратно:")
    api.call("campaigns", "get", {"SelectionCriteria": {"Ids": [cid]},
                                  "FieldNames": ["Id", "Name", "Type", "Status", "State", "NegativeKeywords"],
                                  "UnifiedCampaignFieldNames": ["BiddingStrategy"]})
    api.call("adgroups", "get", {"SelectionCriteria": {"Ids": [gid]},
                                 "FieldNames": ["Id", "Name", "Type", "Status", "RegionIds", "NegativeKeywords"]})
    if ad:
        api.call("ads", "get", {"SelectionCriteria": {"Ids": [ad]},
                                "FieldNames": ["Id", "Type", "Subtype", "Status", "State"],
                                "ResponsiveAdFieldNames": ["Titles", "Texts", "Href"]})
    if kw:
        api.call("keywords", "get", {"SelectionCriteria": {"Ids": [kw]},
                                     "FieldNames": ["Id", "Keyword", "Bid", "State"]})
        api.call("keywordbids", "get", {"SelectionCriteria": {"KeywordIds": [kw]},
                                        "FieldNames": ["KeywordId"], "SearchFieldNames": ["Bid"]})
    print(f"\nIds: кампания {cid}, группа {gid}, объявление {ad}, ключ {kw}")

    if a.delete:
        print("\n6. Удаление кампании")
        api.call("campaigns", "delete", {"SelectionCriteria": {"Ids": [cid]}})
        js = api.call("campaigns", "get", {"SelectionCriteria": {}, "FieldNames": ["Id", "Name", "State"]})
        ids = [c["Id"] for c in js.get("result", {}).get("Campaigns", [])]
        print("  Удалённая кампания в списке:", cid in ids)


if __name__ == "__main__":
    main()
