#!/usr/bin/env python
# coding: utf-8
"""Сверка всех чисел из документа «Novotel Moscow City: первичный осмотр кабинета Директа» с сырыми выгрузками.

Читает только сохранённые CSV из Клиенты/Novotel_Moscow_City/Статистика/ (токен и API не нужны).
Каждое число документа задано в списке CHECKS как (описание, значение в документе, функция расчёта, допуск)
и пересчитывается из данных. Расхождение помечается DIFF. Запуск:
    python novotel_express_numbers_check.py
"""
import sys
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"
camp = pd.read_csv(D / "express_campaigns_daily.csv")
g569 = pd.read_csv(D / "express_goal_569197311_daily.csv")[["Date", "CampaignId", "Conversions_569197311_AUTO"]]
camp = camp.merge(g569, on=["Date", "CampaignId"], how="left")
q = pd.read_csv(D / "express_q569_brand_campaigns.csv")

G = {"forms_all": "Conversions_498289834_AUTO", "forms_any": "Conversions_495735955_AUTO",
     "forms_hall": "Conversions_495347102_AUTO", "calls_ev": "Conversions_498298013_AUTO",
     "calls_hotel": "Conversions_495615844_AUTO", "mice": "Conversions_511709344_AUTO",
     "sec90": "Conversions_498184341_AUTO", "buy_accor": "Conversions_347409254_AUTO",
     "buy": "Conversions_569197311_AUTO"}
for v in G.values():
    camp[v] = camp[v].fillna(0)


def S(df, col):
    return float(df[col].sum())


def window(ids, d1=None, d2=None):
    s = camp[camp.CampaignId.isin(ids)]
    if d1:
        s = s[(s.Date >= d1) & (s.Date <= d2)]
    return s


def forms(s):
    return S(s, G["forms_all"]) + S(s, G["forms_any"]) + S(s, G["forms_hall"])


def calls(s):
    return S(s, G["calls_ev"]) + S(s, G["calls_hotel"])


EV = {"705894417": "страница залов сайта отеля", "705894438": "Тест_Сайта", "705894429": "Ключи_бренд (залы)",
      "705939577": "РСЯ Сайт", "706976991": "РСЯ LAL", "708052907": "Тест_Сем-фида", "709510227": "Эффективные ключи"}
EV_IDS = [int(k) for k in EV]
FEED, KEY = 710991462, 710989906
BR2 = [FEED, KEY]

rows = []


def chk(name, doc, calc, tol=0.0):
    ok = abs(float(doc) - float(calc)) <= tol
    rows.append((name, doc, round(float(calc), 3), "OK" if ok else "DIFF"))


# --- общий расход
tot = S(camp, "Cost")
chk("Общий расход, млн ₽ (1,47)", 1.47, tot / 1e6, 0.005)
chk("Расход в месяц, тыс. ₽ (147; за 10 мес)", 147, tot / 10 / 1e3, 1)

# --- кампании мероприятий
ev = window(EV_IDS)
chk("Расход мероприятий, ₽ (846 330)", 846330, S(ev, "Cost"), 1)
chk("Клики мероприятий (5 087)", 5087, S(ev, "Clicks"), 0)
chk("Формы всего (30)", 30, forms(ev))
chk("Звонки всего (65)", 65, calls(ev))
chk("Квал MICE всего (21)", 21, S(ev, G["mice"]))
chk("Обращений всего (95)", 95, forms(ev) + calls(ev))
chk("Цена обращения средняя, ₽ (8 909)", 8909, S(ev, "Cost") / (forms(ev) + calls(ev)), 1)
chk("Цена формы, ₽ (≈28 тыс.)", 28000, S(ev, "Cost") / forms(ev), 500)
chk("Цена звонка, ₽ (≈13 тыс.)", 13000, S(ev, "Cost") / calls(ev), 500)
chk("Цена Квал MICE, ₽ (40,3 тыс.)", 40300, S(ev, "Cost") / S(ev, G["mice"]), 100)

DOC_EV = {  # id: (расход, клики, формы, звонки, mice, цена обращения)
    705894417: (84878, 473, 2, 10, 0, 7073), 705894438: (440098, 1192, 20, 31, 13, 8629),
    705894429: (100236, 357, 2, 12, 2, 7160), 705939577: (22685, 2422, 0, 5, 0, 4537),
    706976991: (1094, 214, 0, 0, 0, None), 708052907: (71509, 292, 5, 4, 5, 7945),
    709510227: (125831, 137, 1, 3, 1, 31458)}
for cid, (c, k, f, cl, m, p) in DOC_EV.items():
    s = window([cid])
    chk(f"{EV[str(cid)]}: расход", c, S(s, "Cost"), 1)
    chk(f"{EV[str(cid)]}: клики", k, S(s, "Clicks"))
    chk(f"{EV[str(cid)]}: формы", f, forms(s))
    chk(f"{EV[str(cid)]}: звонки", cl, calls(s))
    chk(f"{EV[str(cid)]}: MICE", m, S(s, G["mice"]))
    if p:
        chk(f"{EV[str(cid)]}: цена обращения", p, S(s, "Cost") / (forms(s) + calls(s)), 1)

# --- пара 12.01-06.02
a = window([705894417], "2026-01-12", "2026-02-06")
b = window([705894438], "2026-01-12", "2026-02-06")
chk("Пара залов: расход A, тыс. (84,9)", 84.9, S(a, "Cost") / 1e3, 0.05)
chk("Пара залов: расход B, тыс. (85,5)", 85.5, S(b, "Cost") / 1e3, 0.05)
chk("Пара залов: показы A (9 178)", 9178, S(a, "Impressions"))
chk("Пара залов: показы B (9 579)", 9579, S(b, "Impressions"))
chk("Пара залов: клики A (473)", 473, S(a, "Clicks"))
chk("Пара залов: клики B (419)", 419, S(b, "Clicks"))
chk("Пара залов: звонки A (10)", 10, calls(a))
chk("Пара залов: звонки B (11)", 11, calls(b))
chk("Пара залов: формы A (2)", 2, forms(a))
chk("Пара залов: формы B (4)", 4, forms(b))
chk("Пара залов: цена A (≈7 100)", 7100, S(a, "Cost") / (forms(a) + calls(a)), 50)
chk("Пара залов: цена B (≈5 700)", 5700, S(b, "Cost") / (forms(b) + calls(b)), 50)

# --- пара бренда 23.06-03.08
k = window([KEY], "2026-06-23", "2026-08-03")
x = window([710991132], "2026-06-23", "2026-08-03")
chk("Пара бренда: расход сайт отеля, тыс. (55,8)", 55.8, S(k, "Cost") / 1e3, 0.05)
chk("Пара бренда: расход accor, тыс. (55,7)", 55.7, S(x, "Cost") / 1e3, 0.05)
chk("Пара бренда: клики сайт отеля (662)", 662, S(k, "Clicks"))
chk("Пара бренда: клики accor (381)", 381, S(x, "Clicks"))
chk("Пара бренда: цена клика сайт отеля (84)", 84, S(k, "Cost") / S(k, "Clicks"), 0.5)
chk("Пара бренда: цена клика accor (146)", 146, S(x, "Cost") / S(x, "Clicks"), 0.5)
chk("Пара бренда: покупки сайт отеля (39)", 39, S(k, G["buy"]))
chk("Пара бренда: покупки accor (17)", 17, S(x, G["buy_accor"]))
chk("Пара бренда: цена покупки сайт отеля (1 430)", 1430, S(k, "Cost") / S(k, G["buy"]), 1)
chk("Пара бренда: цена покупки accor (3 279)", 3279, S(x, "Cost") / S(x, G["buy_accor"]), 1)
chk("Пара бренда: во сколько раз больше покупок (2,3)", 2.3, S(k, G["buy"]) / S(x, G["buy_accor"]), 0.05)

# --- удалённая кампания
dl = window([710989238])
chk("Удалённая: расход, тыс. (104)", 104, S(dl, "Cost") / 1e3, 0.5)
chk("Удалённая: покупки accor (54)", 54, S(dl, G["buy_accor"]))
chk("Удалённая: покупки сайт отеля (5)", 5, S(dl, G["buy"]))

# --- помесячные таблицы двух кампаний
camp["Month"] = camp["Date"].astype(str).str[:7]
DOC_M = {FEED: {"2026-06": (8166, 157, 52, 4, 2041), "2026-07": (34093, 393, 87, 33, 1033),
                "2026-08": (32898, 324, 102, 24, 1371), "2026-09": (63499, 445, 143, 32, 1984),
                "2026-10": (55540, 523, 106, 31, 1792)},
         KEY: {"2026-06": (9567, 177, 54, 6, 1595), "2026-07": (40889, 446, 92, 28, 1460),
               "2026-08": (51217, 389, 132, 28, 1829), "2026-09": (70890, 415, 171, 17, 4170),
               "2026-10": (61966, 615, 101, 23, 2694)}}
for cid, ms in DOC_M.items():
    nm = "фид" if cid == FEED else "ключи"
    for mth, (c, kl, cpc, buy, cpa) in ms.items():
        s = camp[(camp.CampaignId == cid) & (camp.Month == mth) & (camp.Date >= "2026-06-23")]
        chk(f"{nm} {mth}: расход", c, S(s, "Cost"), 1)
        chk(f"{nm} {mth}: клики", kl, S(s, "Clicks"))
        chk(f"{nm} {mth}: цена клика", cpc, S(s, "Cost") / S(s, "Clicks"), 0.5)
        chk(f"{nm} {mth}: покупки", buy, S(s, G["buy"]))
        chk(f"{nm} {mth}: цена покупки", cpa, S(s, "Cost") / S(s, G["buy"]), 1)
    s = camp[(camp.CampaignId == cid) & (camp.Date >= "2026-06-23")]
    tot_row = (194195, 1842, 105, 124, 1566) if cid == FEED else (234529, 2042, 115, 102, 2299)
    chk(f"{nm} всего: расход", tot_row[0], S(s, "Cost"), 1)
    chk(f"{nm} всего: клики", tot_row[1], S(s, "Clicks"))
    chk(f"{nm} всего: цена клика", tot_row[2], S(s, "Cost") / S(s, "Clicks"), 0.5)
    chk(f"{nm} всего: покупки", tot_row[3], S(s, G["buy"]))
    chk(f"{nm} всего: цена покупки", tot_row[4], S(s, "Cost") / S(s, G["buy"]), 1)


def cvr(cid, mth):
    s = camp[(camp.CampaignId == cid) & (camp.Month == mth)]
    return 100 * S(s, G["buy"]) / S(s, "Clicks")


chk("Ключи: доля кликов с покупкой июль (6,3%)", 6.3, cvr(KEY, "2026-07"), 0.05)
chk("Ключи: доля кликов с покупкой сентябрь (4,1%)", 4.1, cvr(KEY, "2026-09"), 0.05)
chk("Фид: доля кликов с покупкой июль (8,4%)", 8.4, cvr(FEED, "2026-07"), 0.05)
chk("Фид: доля кликов с покупкой сентябрь (7,2%)", 7.2, cvr(FEED, "2026-09"), 0.05)

# --- звонки на сайте отеля у двух кампаний
c2 = camp[camp.CampaignId.isin(BR2) & (camp.Date >= "2026-06-23")]
for mth, v in {"2026-06": 6, "2026-07": 30, "2026-08": 3, "2026-09": 0, "2026-10": 0}.items():
    chk(f"Звонки Calltouch (сайт отеля) {mth}", v, S(c2[c2.Month == mth], G["calls_hotel"]))
chk("Последний звонок ключи (01.08)", 20260801, int(c2[(c2.CampaignId == KEY) & (c2[G["calls_hotel"]] > 0)].Date.max().replace("-", "")))
chk("Последний звонок фид (03.08)", 20260803, int(c2[(c2.CampaignId == FEED) & (c2[G["calls_hotel"]] > 0)].Date.max().replace("-", "")))
for mth, v in {"2026-09": 415 + 445, "2026-10": 615 + 523}.items():
    chk(f"Клики двух кампаний {mth}", v, S(c2[c2.Month == mth], "Clicks"))
chk("Покупки июль, две кампании (61)", 61, S(c2[c2.Month == "2026-07"], G["buy"]))
chk("Цена покупки июль, две кампании (1 229)", 1229, S(c2[c2.Month == "2026-07"], "Cost") / S(c2[c2.Month == "2026-07"], G["buy"]), 1)

# --- запросы: бренд / небренд, две кампании, 23.06-25.10
qq = q[q.CampaignId.isin(BR2)].copy()
qq["Month"] = qq["Date"].astype(str).str[:7]
qq["brand"] = qq["Query"].astype(str).str.lower().str.contains("novotel|новотел|новотэл")
nb, br = qq[~qq.brand], qq[qq.brand]
cost_all = S(c2, "Cost")
chk("Запросы: покрытие расхода, % (99,8)", 99.8, 100 * S(qq, "Cost") / cost_all, 0.05)
chk("Небренд: расход, тыс. (59,1)", 59.1, S(nb, "Cost") / 1e3, 0.05)
chk("Небренд: доля расхода, % (13,8)", 13.8, 100 * S(nb, "Cost") / S(qq, "Cost"), 0.05)
chk("Небренд: покупки (9)", 9, S(nb, "conv"))
chk("Все покупки по запросам (225)", 225, S(qq, "conv"))
chk("Небренд: доля покупок, % (4)", 4, 100 * S(nb, "conv") / S(qq, "conv"), 0.5)
chk("Небренд: цена покупки (6 566)", 6566, S(nb, "Cost") / S(nb, "conv"), 1)
chk("Бренд: цена покупки (1 708)", 1708, S(br, "Cost") / S(br, "conv"), 1)
o = qq[qq.Month == "2026-10"]
chk("Небренд октябрь, тыс. (22,0)", 22.0, S(o[~o.brand], "Cost") / 1e3, 0.05)
chk("Небренд октябрь, доля месяца, % (19)", 19, 100 * S(o[~o.brand], "Cost") / S(o, "Cost"), 0.5)
chk("Небренд в ключевой кампании, тыс. (57,4)", 57.4, S(nb[nb.CampaignId == KEY], "Cost") / 1e3, 0.05)
chk("Небренд в фидовой кампании, тыс. (1,7)", 1.7, S(nb[nb.CampaignId == FEED], "Cost") / 1e3, 0.05)
so = qq[qq.Month.isin(["2026-09", "2026-10"])]
chk("Сент-окт: цена покупки, всего (2 440)", 2440, S(so, "Cost") / S(so, "conv"), 1)
chk("Сент-окт: цена покупки, только бренд (2 226)", 2226, S(so[so.brand], "Cost") / S(so[so.brand], "conv"), 1)
chk("Сент-окт: снижение цены, % (9)", 9, 100 * (1 - (S(so[so.brand], "Cost") / S(so[so.brand], "conv")) / (S(so, "Cost") / S(so, "conv"))), 0.5)
chk("Сент-окт: покупок всего (103)", 103, S(so, "conv"))
chk("Сент-окт: покупок в небренде (6)", 6, S(so[~so.brand], "conv"))
chk("Сент-окт: потеря покупок, % (6)", 6, 100 * S(so[~so.brand], "conv") / S(so, "conv"), 0.5)
sm = qq[qq.Month.isin(["2026-07", "2026-08"]) & qq.brand]
sb = so[so.brand]
cpc_s, cpc_a = S(sm, "Cost") / S(sm, "Clicks"), S(sb, "Cost") / S(sb, "Clicks")
cv_s, cv_a = S(sm, "conv") / S(sm, "Clicks"), S(sb, "conv") / S(sb, "Clicks")
chk("Бренд июль-авг: цена клика (105)", 105, cpc_s, 0.5)
chk("Бренд сент-окт: цена клика (136)", 136, cpc_a, 0.5)
chk("Бренд июль-авг: доля кликов с покупкой, % (8,4)", 8.4, 100 * cv_s, 0.05)
chk("Бренд сент-окт: доля кликов с покупкой, % (6,1)", 6.1, 100 * cv_a, 0.05)
chk("Бренд июль-авг: цена покупки (1 248)", 1248, cpc_s / cv_s, 1)
chk("Сценарий: клик как летом (≈1 730)", 1730, cpc_s / cv_a, 5)
chk("Сценарий: доля как летом (≈1 610)", 1610, cpc_a / cv_s, 5)
chk("Сценарий: оба как летом (≈1 250)", 1250, cpc_s / cv_s, 5)
imp = qq[qq.brand].groupby("Month").Impressions.sum()
chk("Показы бренда, мин. тыс. июль-окт (2,1)", 2.1, imp.loc["2026-07":"2026-10"].min() / 1e3, 0.05)
chk("Показы бренда, макс. тыс. июль-окт (2,8)", 2.8, imp.loc["2026-07":"2026-10"].max() / 1e3, 0.05)

# --- диапазоны из раздела «Вывод» и прочие числа текста
def price(cid, mths):
    s = camp[(camp.CampaignId == cid) & (camp.Month.isin(mths))]
    return S(s, "Cost") / S(s, G["buy"])


summer = [price(FEED, ["2026-07"]), price(FEED, ["2026-08"]), price(KEY, ["2026-07"]), price(KEY, ["2026-08"])]
chk("Вывод: лето, нижняя граница, тыс. (1,0)", 1.0, min(summer) / 1e3, 0.05)
chk("Вывод: лето, верхняя граница, тыс. (1,8)", 1.8, max(summer) / 1e3, 0.05)
octo = [price(FEED, ["2026-10"]), price(KEY, ["2026-10"])]
chk("Вывод: октябрь, нижняя граница, тыс. (1,8)", 1.8, min(octo) / 1e3, 0.05)
chk("Вывод: октябрь, верхняя граница, тыс. (2,7)", 2.7, max(octo) / 1e3, 0.05)
chk("Вывод: оптимистичная оценка, нижняя, тыс. (1,2)", 1.2, (cpc_s / cv_s) / 1e3, 0.05)
chk("Вывод: оптимистичная оценка, верхняя, тыс. (1,7)", 1.7, (cpc_s / cv_a) / 1e3, 0.05)
for mth, v in {"2026-08": 52, "2026-09": 49, "2026-10": 54}.items():
    chk(f"Покупки двух кампаний {mth} (49–54 в месяц)", v, S(c2[c2.Month == mth], G["buy"]))
chk("Кампания «ключи»: цена покупки июль, тыс. (1,5)", 1.5, price(KEY, ["2026-07"]) / 1e3, 0.05)
chk("Кампания «ключи»: цена покупки сентябрь, тыс. (4,2)", 4.2, price(KEY, ["2026-09"]) / 1e3, 0.05)
chk("Кампания «фид»: цена покупки июль, тыс. (1,0)", 1.0, price(FEED, ["2026-07"]) / 1e3, 0.05)
chk("Кампания «фид»: цена покупки сентябрь, тыс. (2,0)", 2.0, price(FEED, ["2026-09"]) / 1e3, 0.05)
chk("Цена клика ключи июль→сентябрь (92→171): июль", 92, S(camp[(camp.CampaignId == KEY) & (camp.Month == "2026-07")], "Cost") / S(camp[(camp.CampaignId == KEY) & (camp.Month == "2026-07")], "Clicks"), 0.5)
chk("Цена клика фид июль (87)", 87, S(camp[(camp.CampaignId == FEED) & (camp.Month == "2026-07")], "Cost") / S(camp[(camp.CampaignId == FEED) & (camp.Month == "2026-07")], "Clicks"), 0.5)
chk("Срок: доля месяцев в данных (10 мес.: январь–октябрь)", 10, camp.Month.nunique())


# --- Вордстат (снят вручную, CSV в Статистика/)
ws = pd.read_csv(D / "express_wordstat_2026-10-26.csv").set_index("region")["queries"]
WS_RU, WS_MSK, WS_ALL = float(ws["Россия"]), float(ws["Москва и область"]), float(ws["Всего (мир)"])
WS_OUT = WS_RU - WS_MSK
chk("Вордстат: Москва и область, доля России, % (38,7)", 38.7, 100 * WS_MSK / WS_RU, 0.05)
chk("Вордстат: Россия вне Москвы и области (3 217)", 3217, WS_OUT)
chk("Вордстат: Россия вне Москвы и области, доля, % (61,3)", 61.3, 100 * WS_OUT / WS_RU, 0.05)
chk("Вордстат: вне Москвы и области к Москве и области, раз (1,6)", 1.6, WS_OUT / WS_MSK, 0.05)
chk("Вордстат: остальной Центр (628)", 628, float(ws["Центр"]) - WS_MSK)
chk("Вордстат: за пределами России (269)", 269, WS_ALL - WS_RU)
other = WS_OUT - (float(ws["Центр"]) - WS_MSK) - float(ws["Поволжье"]) - float(ws["Северо-Запад"]) - float(ws["Урал"]) - float(ws["Юг"]) - float(ws["Сибирь"]) - float(ws["Дальний Восток"]) - float(ws["Северный Кавказ"])
chk("Вордстат: прочие регионы России в таблице (26)", 26, other)
imp_sep_oct = imp.loc["2026-09":"2026-10"]
chk("Показы бренда сентябрь, тыс. (2,3)", 2.3, imp_sep_oct.loc["2026-09"] / 1e3, 0.05)
chk("Показы бренда октябрь, тыс. (2,5)", 2.5, imp_sep_oct.loc["2026-10"] / 1e3, 0.05)
chk("Показы бренда (сент–окт) к Вордстату Москвы и области, раз (1,1–1,2)", 1.15, float(imp_sep_oct.mean()) / WS_MSK, 0.06)

# --- лето/осень цены по двум кампаниям: из сводки
chk("Цена покупки фид, октябрь (1 792)", 1792, S(camp[(camp.CampaignId == FEED) & (camp.Month == "2026-10")], "Cost") / S(camp[(camp.CampaignId == FEED) & (camp.Month == "2026-10")], G["buy"]), 1)

df = pd.DataFrame(rows, columns=["Проверка", "В документе", "Расчёт скриптом", "Итог"])
pd.set_option("display.width", 250, "display.max_rows", 500, "display.max_colwidth", 70)
print(df.to_string(index=False))
bad = df[df["Итог"] == "DIFF"]
print(f"\nПроверено: {len(df)}; совпало: {len(df) - len(bad)}; расхождений: {len(bad)}")
if len(bad):
    print("\nРАСХОЖДЕНИЯ:")
    print(bad.to_string(index=False))
sys.exit(1 if len(bad) else 0)
