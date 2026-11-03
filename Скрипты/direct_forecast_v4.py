#!/usr/bin/env python
# coding: utf-8
"""«Прогноз бюджета» Директа через API Live 4 (CreateNewForecast → GetForecastList → GetForecast → DeleteForecastReport).

Только чтение: прогноз формируется на сервере Яндекса, в кабинет ничего не пишется. Отчёт удаляется после чтения
(лимит 5 отчётов на пользователя, иначе ошибка 31). Прогноз — верхняя оценка по статистике прошлого месяца, РСЯ не
учитывает. Токен — из файла (.secrets/, вне git), в вывод не попадает.

ВНИМАНИЕ: в ответе Min/Max/PremiumMin/PremiumMax — СТАВКИ (проверено на Novotel: PremiumMin == ставка P13/P14), а не цены клика;
реальная цена — AuctionBids.Price. Клики (Clicks/FirstPlaceClicks/PremiumClicks) — потолок объёма за месяц.

Фразы — ключи кампании с кликами в истории (slice_criteria_<id>.csv), по убыванию кликов, до 100.
Запуск:
    PYTHONUTF8=1 python direct_forecast_v4.py --token-file ../.secrets/novotel_direct.token --client-folder Novotel_Moscow_City \
        --campaign-id 705894438 --geo 1 [--top 100]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path
from time import sleep

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_express_audit import read_token, VAULT_ROOT  # noqa: E402

LIVE = "https://api.direct.yandex.com/live/v4/json/"


def live(token, method, param=None):
    body = {"method": method, "token": token, "locale": "ru"}
    if param is not None:
        body["param"] = param
    r = requests.post(LIVE, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=120)
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--geo", default="1", help="ID регионов через запятую (1 — Москва и область, 213 — Москва)")
    ap.add_argument("--top", type=int, default=100)
    a = ap.parse_args()
    token = read_token(a.token_file)
    st = VAULT_ROOT / "Клиенты" / a.client_folder / "Статистика"
    c = pd.read_csv(st / f"slice_criteria_{a.campaign_id}.csv")
    c = c[(c.CriterionType == "KEYWORD") & (c.Clicks > 0)].sort_values("Clicks", ascending=False)
    phrases = list(dict.fromkeys(c.Criterion.tolist()))[: a.top]
    print(f"фраз для прогноза: {len(phrases)} (по убыванию кликов в истории)")

    d = live(token, "CreateNewForecast", {"Phrases": phrases, "GeoID": [int(x) for x in a.geo.split(",")],
                                          "Currency": "RUB", "AuctionBids": "Yes"})
    if "error_code" in d or "data" not in d:
        sys.exit(f"CreateNewForecast: {d.get('error_code')} {d.get('error_str')} {d.get('error_detail')}")
    rid = d["data"]
    print("отчёт:", rid)
    try:
        for _ in range(30):
            sleep(5)
            lst = live(token, "GetForecastList")
            row = next((x for x in lst.get("data", []) if x["ForecastID"] == rid), None)
            if row and row.get("StatusForecast") == "Done":
                break
        else:
            sys.exit("прогноз не готов за 150 с")
        res = live(token, "GetForecast", rid)
        if "data" not in res:
            sys.exit(f"GetForecast: {res.get('error_code')} {res.get('error_str')}")
        out = st / f"forecast_v4_{a.campaign_id}_{date.today().isoformat()}.json"
        out.write_text(json.dumps(res["data"], ensure_ascii=False, indent=1), encoding="utf-8")
        print("сохранено:", out)
        data = res["data"]
        print("ключи верхнего уровня:", list(data.keys()))
        common = data.get("Common") or {}
        print("Common:", json.dumps(common, ensure_ascii=False)[:600])
    finally:
        live(token, "DeleteForecastReport", rid)


if __name__ == "__main__":
    main()
