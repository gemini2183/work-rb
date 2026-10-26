#!/usr/bin/env python
# coding: utf-8
"""Создание пустой текстовой кампании в Яндекс.Директе (без групп, объявлений и ключей).

По умолчанию только читает: показывает существующие кампании кабинета и тело запроса,
ничего не пишет. Запись — только с --execute; после неё кампании читаются обратно.
Кампания без объявлений показываться не может. Логин/токен — с вкладки "Директ".

Использование:
    python direct_campaign_create.py --client "Груминг - Северная 3" --name "Тестовая кампания для тестирования API"
    python direct_campaign_create.py --client "Груминг - Северная 3" --name "..." --execute
"""
import argparse
import json
import sys
from datetime import date

import requests

from _config import get_client_row

URL = "https://api.direct.yandex.com/json/v5/campaigns"


def call(login, token, method, params):
    headers = {"Authorization": "Bearer " + token, "Client-Login": login, "Accept-Language": "ru"}
    r = requests.post(URL, json={"method": method, "params": params}, headers=headers, timeout=120)
    return r.json()


def list_campaigns(login, token):
    js = call(login, token, "get", {
        "SelectionCriteria": {},
        "FieldNames": ["Id", "Name", "Type", "Status", "State", "StartDate"],
    })
    if "error" in js:
        print("Ошибка чтения:", json.dumps(js["error"], ensure_ascii=False))
        sys.exit(1)
    return js["result"].get("Campaigns", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Значение колонки 'client' на вкладке Директ")
    ap.add_argument("--name", required=True)
    ap.add_argument("--weekly-limit-rub", type=int, default=300, help="Недельный лимит стратегии, ₽ (минимум 300)")
    ap.add_argument("--execute", action="store_true", help="Без флага — только план")
    args = ap.parse_args()

    row = get_client_row(args.client, tab="Директ")
    login, token = str(row.get("login", "")).strip(), str(row.get("token", "")).strip()
    if not login or not token:
        print("Пустой login/token на вкладке 'Директ'")
        sys.exit(1)

    print(f"Кабинет: {args.client} (login={login})\n\nДо:")
    before = list_campaigns(login, token)
    for c in before:
        print(f"  {c['Id']} | {c['Name']} | {c['Type']} | {c['Status']}/{c['State']}")
    if not before:
        print("  (кампаний нет)")

    campaign = {
        "Name": args.name,
        "StartDate": str(date.today()),
        "TextCampaign": {
            "BiddingStrategy": {
                "Search": {
                    "BiddingStrategyType": "WB_MAXIMUM_CLICKS",
                    "WbMaximumClicks": {"WeeklySpendLimit": args.weekly_limit_rub * 1_000_000},
                },
                "Network": {"BiddingStrategyType": "SERVING_OFF"},
            },
        },
    }
    print("\nПлан (campaigns.add):")
    print(json.dumps(campaign, ensure_ascii=False, indent=2))
    if not args.execute:
        print("\nРежим плана, ничего не записано. Для записи добавьте --execute")
        return

    js = call(login, token, "add", {"Campaigns": [campaign]})
    print("\nОтвет API:", json.dumps(js, ensure_ascii=False))
    if "error" in js:
        sys.exit(1)

    print("\nПосле (чтение обратно):")
    for c in list_campaigns(login, token):
        print(f"  {c['Id']} | {c['Name']} | {c['Type']} | {c['Status']}/{c['State']} | старт {c.get('StartDate')}")


if __name__ == "__main__":
    main()
