#!/usr/bin/env python
# coding: utf-8
"""Снапшот настроек кампаний Яндекс.Директа (тип, статус, стратегия/оплата)
для одного клиента в Статистика/клиента.

Нужен, чтобы отличать реальные проблемы в статистике (баг API, аномалия) от
ожидаемого поведения конкретной стратегии — например, при оплате за конверсию
(PAY_FOR_CONVERSION) расход по дням может быть неравномерным и подолгу нулевым,
это не баг. Логин/токен — из общей Google-таблицы (вкладка "Директ"), как и в
direct_stats.py.

Использование:
    python direct_campaigns.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin"
"""
import argparse
import json
import sys

import requests

from _config import get_client_row, client_stats_dir

CAMPAIGNS_URL = "https://api.direct.yandex.com/json/v5/campaigns"

CAMPAIGN_TYPE_FIELDS = [
    "TextCampaignFieldNames",
    "UnifiedCampaignFieldNames",
    "MobileAppCampaignFieldNames",
    "DynamicTextCampaignFieldNames",
    "CpmBannerCampaignFieldNames",
    "SmartCampaignFieldNames",
]


def fetch_campaigns(login, token):
    headers = {
        "Authorization": "Bearer " + token,
        "Client-Login": login,
        "Accept-Language": "ru",
    }
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "Type", "Status", "State"],
            **{f: ["BiddingStrategy"] for f in CAMPAIGN_TYPE_FIELDS},
        },
    }
    req = requests.post(CAMPAIGNS_URL, json.dumps(body), headers=headers, timeout=300)
    if req.status_code != 200:
        print(f"Ошибка {req.status_code}: {req.text[:500]}")
        sys.exit(1)
    return req.json()


def extract_strategy(campaign):
    for type_field in ("TextCampaign", "UnifiedCampaign", "MobileAppCampaign",
                        "DynamicTextCampaign", "CpmBannerCampaign", "SmartCampaign"):
        block = campaign.get(type_field)
        if block and "BiddingStrategy" in block:
            strategy = block["BiddingStrategy"]
            for platform in ("Search", "Network"):
                if platform in strategy and strategy[platform]:
                    return strategy[platform].get("BiddingStrategyType", "")
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Значение колонки 'client' на вкладке Директ")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "ЕГЭ Merlin"')
    args = ap.parse_args()

    row = get_client_row(args.client, tab="Директ")
    login = str(row.get("login", "")).strip()
    token = str(row.get("token", "")).strip()
    if not login or not token:
        print(f"У клиента '{args.client}' на вкладке 'Директ' пустой login/token")
        sys.exit(1)

    print(f"Клиент: {args.client_folder}")
    result = fetch_campaigns(login, token)

    campaigns = result.get("result", {}).get("Campaigns", [])
    rows = []
    for c in campaigns:
        rows.append({
            "Id": c.get("Id"),
            "Name": c.get("Name"),
            "Type": c.get("Type"),
            "Status": c.get("Status"),
            "State": c.get("State"),
            "BiddingStrategyType": extract_strategy(c),
        })

    import pandas as pd
    df = pd.DataFrame(rows)

    out_dir = client_stats_dir(args.client_folder)
    out_path = out_dir / "campaigns_settings.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} кампаний)")


if __name__ == "__main__":
    main()
