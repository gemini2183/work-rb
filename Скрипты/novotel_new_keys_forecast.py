"""
Novotel: прогноз спроса и цены клика по НОВЫМ темам ключей (услуги сайта novotel-events.ru), которых нет в кампании Тест_Сайта.

Темы взяты со страницы сайта (залы, форматы, кейтеринг, видеоконференции, проживание, корпоративы) 03.11.2026; фразы — гипотезы для теста,
не проверены на конверсию. Прогноз — «Прогноз бюджета» Директа (Live 4, direct_forecast_v4.py): показы и клики за прошлый месяц, цена
клика в спецразмещении, регион Москва и область. Фразы, совпадающие по набору слов с ключами Тест_Сайта (без минус-слов), помечаются «есть».
Запуск: PYTHONUTF8=1 python novotel_new_keys_forecast.py --token-file ../.secrets/novotel_direct.token
"""
import argparse
import json
import sys
from pathlib import Path
from time import sleep

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_express_audit import read_token  # noqa: E402
from direct_forecast_v4 import live  # noqa: E402

ST = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"

CAND = {
    "Москва-Сити / отель": ["конференц зал москва сити", "аренда конференц зала в москва сити", "аренда зала в москва сити",
        "переговорная в москва сити", "конференц залы в отеле москва", "конференц зал в гостинице москва",
        "отель для конференций москва", "проведение конференции в отеле москва", "отель с залами для мероприятий москва"],
    "Видеоконференции и вебинары": ["аренда зала для вебинара москва", "студия для вебинаров москва", "организация видеоконференций москва",
        "аренда зала для видеоконференции", "трансляция конференции москва", "аренда оборудования для видеоконференций"],
    "Форматы встреч": ["аренда зала для презентации москва", "помещение для мастер класса москва", "аренда зала для тренинга москва",
        "аренда зала для семинара москва", "зал для бизнес встречи москва", "зал для делового завтрака москва",
        "приватный зал для переговоров москва", "vip зал для переговоров москва", "аренда переговорной на час москва"],
    "Новый год и корпоративы": ["новогодний корпоратив москва сити", "корпоратив в отеле москва", "новогодний корпоратив в отеле москва",
        "зал для корпоратива на 100 человек москва", "аренда зала для фуршета москва", "фуршет для корпоратива москва"],
    "Вместимость": ["конференц зал на 300 человек москва", "конференц зал на 100 человек москва", "конференц зал на 50 человек москва",
        "зал на 200 человек москва", "зал на 300 человек москва", "зал для конференции на 150 человек"],
    "Кейтеринг и под ключ": ["кофе брейк для конференции москва", "кофе брейк в отеле москва", "организация конференции в москве под ключ",
        "организация корпоративных мероприятий москва", "конференция с обедом и кофе брейком москва", "кейтеринг для конференции москва"],
    "Проживание участников": ["конференция с проживанием москва", "отель для проведения конференции с проживанием", "бизнес отель москва с конференц залами"],
    "Рядом (метро, выставки)": ["конференц зал у метро деловой центр", "конференц зал рядом с экспоцентром", "конференц зал в районе москва сити"],
    "Английские запросы": ["conference hall moscow", "meeting room moscow city", "event venue moscow", "conference venue moscow"],
}


def norm(s):
    return " ".join(sorted(w.lower() for w in str(s).replace('"', "").split() if not w.startswith("-")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--campaign-id", default="705894438")
    a = ap.parse_args()
    token = read_token(a.token_file)
    have = {norm(x) for x in pd.read_csv(ST / f"slice_criteria_{a.campaign_id}.csv").Criterion}
    rows = [(t, p) for t, ps in CAND.items() for p in ps]
    d = live(token, "CreateNewForecast", {"Phrases": [p for _, p in rows], "GeoID": [1], "Currency": "RUB", "AuctionBids": "No"})
    if "data" not in d:
        sys.exit(f"CreateNewForecast: {d.get('error_code')} {d.get('error_str')} {d.get('error_detail')}")
    rid = d["data"]
    try:
        for _ in range(40):
            sleep(5)
            row = next((x for x in live(token, "GetForecastList").get("data", []) if x["ForecastID"] == rid), None)
            if row and row.get("StatusForecast") == "Done":
                break
        res = live(token, "GetForecast", rid)["data"]
    finally:
        live(token, "DeleteForecastReport", rid)
    by = {p["Phrase"]: p for p in res["Phrases"]}
    out = []
    for t, p in rows:
        r = by.get(p, {})
        out.append(dict(тема=t, фраза=p, есть_в_кампании=norm(p) in have, показы=r.get("Shows"), клики_спец=r.get("PremiumClicks"),
                        цена_клика_спец=r.get("PremiumMin"), цена_клика_первое_место_спец=r.get("PremiumMax")))
    df = pd.DataFrame(out)
    df.to_csv(ST / "new_keys_forecast_2026-11-03.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 55)
    pd.set_option("display.max_rows", 200)
    print(df.to_string(index=False))
    n = df[~df.есть_в_кампании]
    g = n.groupby("тема").agg(фраз=("фраза", "count"), показы=("показы", "sum"), клики=("клики_спец", "sum"))
    g["цена_ср"] = (n.assign(c=n.клики_спец * n.цена_клика_спец).groupby("тема").c.sum() / g.клики).round(0)
    print("\n== новые темы (без уже имеющихся фраз)")
    print(g.sort_values("клики", ascending=False).to_string())
    print("итого новых фраз", len(n), "показы", n.показы.sum(), "клики в спецразмещении", n.клики_спец.sum())


if __name__ == "__main__":
    main()
