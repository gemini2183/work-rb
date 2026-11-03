#!/usr/bin/env python
# coding: utf-8
"""Текущий аукцион Директа по ключам кампании (только чтение): ставка и цена клика по объёму трафика.

KeywordBids.get с AuctionBids: для каждого ключа таблица «объём трафика → ставка → списываемая цена». Метод может вернуть
null для автотаргетинга, групп со статусом «мало показов» и кампаний без показов на поиске. Результат — long-CSV
Клиенты/<папка>/Статистика/auction_bids_<дата>.csv и сводка: какая ставка/цена нужна для 25/50/75/100% объёма.

Токен — только из файла (--token-file), в vault он не попадает (.secrets/ в .gitignore).

Запуск:
    PYTHONUTF8=1 python direct_auction_bids.py --login porg-juupcxo3 --token-file ../.secrets/novotel_direct.token \
        --client-folder Novotel_Moscow_City --campaign-ids 705894438 [--probe]
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_express_audit import Direct, read_token, VAULT_ROOT  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-ids", required=True, help="через запятую, до 10")
    ap.add_argument("--probe", action="store_true", help="только проверить доступ и статусы кампаний")
    a = ap.parse_args()
    api = Direct(a.login, read_token(a.token_file))
    ids = [int(x) for x in a.campaign_ids.split(",")]

    camps, err = api.get_all("campaigns", {
        "SelectionCriteria": {"Ids": ids, "States": ["ON", "OFF", "SUSPENDED", "ENDED", "CONVERTED", "ARCHIVED"]},
        "FieldNames": ["Id", "Name", "State", "Status"]}, "Campaigns")
    if err:
        sys.exit(f"Campaigns.get: {err}")
    for c in camps:
        print(f"{c['Id']}  {c['State']:9s} {c['Status']:9s} {c['Name']}")
    if a.probe:
        return

    rows, nulls, total = [], 0, 0
    items, err = api.get_all("keywordbids", {
        "SelectionCriteria": {"CampaignIds": ids},
        "FieldNames": ["KeywordId", "AdGroupId", "CampaignId", "ServingStatus"],
        "SearchFieldNames": ["Bid", "AuctionBids"]}, "KeywordBids")
    if err:
        sys.exit(f"KeywordBids.get: {err}")
    for it in items:
        total += 1
        s = it.get("Search") or {}
        ab = (s.get("AuctionBids") or {}).get("AuctionBidItems") or []
        if not ab:
            nulls += 1
        for x in ab:
            rows.append({"CampaignId": it["CampaignId"], "AdGroupId": it["AdGroupId"], "KeywordId": it["KeywordId"],
                         "ServingStatus": it.get("ServingStatus"), "CurrentBid": (s.get("Bid") or 0) / 1e6,
                         "TrafficVolume": x["TrafficVolume"], "Bid": x["Bid"] / 1e6, "Price": x["Price"] / 1e6})
    print(f"\nключей получено {total}, без таблицы аукциона (null) {nulls}, строк таблицы {len(rows)}")
    if not rows:
        return
    df = pd.DataFrame(rows)
    out = VAULT_ROOT / "Клиенты" / a.client_folder / "Статистика" / f"auction_bids_{date.today().isoformat()}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print("сохранено:", out)
    piv = df.groupby("TrafficVolume").agg(keywords=("KeywordId", "nunique"), bid_median=("Bid", "median"),
                                          price_median=("Price", "median"), price_p25=("Price", lambda s: s.quantile(.25)),
                                          price_p75=("Price", lambda s: s.quantile(.75))).round(0)
    print("\nпо объёму трафика (медиана и квартили по ключам), ₽:")
    print(piv.to_string())


if __name__ == "__main__":
    main()
