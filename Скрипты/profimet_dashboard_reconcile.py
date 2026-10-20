#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: сверка таблицы продаж CRM с дашбордом клиента за 01.10 – утро 16.10.2026. ТОЛЬКО ЧТЕНИЕ.

Дашборд на 16.10 (Хроника_2026-10.md, «16.10 — дашборд клиента»): «Продажи» по метке — 57 заказов (58 единиц товара),
из них Google Ads 12, «Телефон» 31, «Нет метки» 14; «Новые обращения» — 112, продажа у 47, из них первое касание Google 30.
Скрипт считает то же по таблице: проданные заказы по дате продажи и по дате первой строки заказа (≈ создание), источник
первой строки заказа и тип (звонок/форма), первое обращение номера, «новые номера» (первое обращение в таблице в периоде) и
строки со статусом «Продажа». Даты периода зашиты в START/CUT — менять под новый снимок дашборда.

Использование:
    PYTHONIOENCODING=utf-8 python profimet_dashboard_reconcile.py [кеш.pkl от profimet_sales_vs_ringostat.py]
Без аргумента читает таблицу заново. Запускать без -I.
"""
import pickle, sys
import pandas as pd

from profimet_sales_vs_ringostat import SHEET_ID, load_sheet

pd.set_option("display.width", 220)
sheet = pickle.load(open(sys.argv[1], "rb"))[0] if len(sys.argv) > 1 else load_sheet(SHEET_ID)
AD = {"Google Ads", "Facebook"}
s = sheet[sheet["site"] == "mocnaszklarnia.pl"].copy()
W = "Europe/Warsaw"
s["tw"] = s["ts"].dt.tz_convert(W)
START = pd.Timestamp("2026-10-01", tz=W)
CUT = pd.Timestamp("2026-10-16 08:00", tz=W)  # «до утра 16.10»
by_phone = {p: g for p, g in s.groupby("p9")}

# ---- заказы: проданные (есть «Дата продажи»), по каждому — строки заказа и первое обращение номера
rows = []
for order, grp in s[s["order"] != ""].groupby("order"):
    sd = [d for d in grp["sale_date"] if d]
    if not sd:
        continue
    grp = grp.sort_values("ts", kind="mergesort")
    t0 = grp.iloc[0]["ts"]
    t = pd.concat([by_phone[p] for p in set(grp["p9"]) if p in by_phone])
    out = {"order": order, "sale_date": min(sd), "cancel": any(grp["cancel_date"] != ""), "t0": t0.tz_convert(W),
           "first_row_src": grp.iloc[0]["src"] or "Нет метки", "first_row_type": grp.iloc[0]["type"],
           "n_rows": len(grp), "p9": grp.iloc[0]["p9"]}
    for w in (30, 60):
        tt = t[(t["ts"] >= t0 - pd.Timedelta(days=w)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        out[f"first_touch_{w}"] = tt.iloc[0]["src"] or "Нет метки"
        out[f"first_touch_ts_{w}"] = tt.iloc[0]["tw"]
    rows.append(out)
d = pd.DataFrame(rows)
d["sd"] = pd.to_datetime(d["sale_date"])


def show(name, g):
    print(f"\n--- {name}: проданных заказов {len(g)} (из них потом отменено: {int(g['cancel'].sum())}) ---")
    print(" источник первой строки заказа:", g["first_row_src"].value_counts().to_dict())
    print(" источник первого обращения (окно 30):", g["first_touch_30"].value_counts().to_dict())
    print(" источник первого обращения (окно 60):", g["first_touch_60"].value_counts().to_dict())
    print(" тип первой строки заказа:", g["first_row_type"].value_counts().to_dict())


print("ТАБЛИЦА, mocnaszklarnia.pl. Сравнение с дашбордом клиента на 16.10: 57 заказов (58 ед.), по метке Google 12 заказов (13 ед.), Телефон 31, Нет метки 14")
show("дата продажи 01.10–15.10", d[(d["sd"] >= "2026-10-01") & (d["sd"] <= "2026-10-15")])
show("дата продажи 01.10–16.10", d[(d["sd"] >= "2026-10-01") & (d["sd"] <= "2026-10-16")])
show("первая строка заказа 01.10 – утро 16.10 (≈ дата создания заказа)", d[(d["t0"] >= START) & (d["t0"] < CUT)])
show("дата продажи 01.10–19.10 (то, что я считал раньше)", d[(d["sd"] >= "2026-10-01")])

# ---- «Новые обращения»: номера, чьё ПЕРВОЕ обращение в таблице пришлось на 01.10 – утро 16.10
first = s.sort_values("ts", kind="mergesort").groupby("p9").head(1)
new = first[(first["tw"] >= START) & (first["tw"] < CUT)]
print(f"\n=== Новые номера (первое обращение в таблице с 01.08.2025 пришлось на 01.10 – утро 16.10): {len(new)} (в дашборде «обращений за период» 112) ===")
print(" источник первого обращения:", new["src"].replace("", "Нет метки").value_counts().to_dict(), "; тип:", new["type"].value_counts().to_dict())
sold = d[["p9", "order", "sale_date", "t0"]].drop_duplicates("p9")
j = new.merge(sold, on="p9", how="left", suffixes=("", "_o"))
j_sold = j[j["order_o"].notna() if "order_o" in j else j["order"].notna()]
print(" из них дошли до проданного заказа (любой датой до 19.10):", len(j_sold), "; по источнику первого обращения:", j_sold["src"].replace("", "Нет метки").value_counts().to_dict())

# ---- по обращениям (строкам таблицы) в этот период
r = s[(s["tw"] >= START) & (s["tw"] < CUT)]
print(f"\n=== Строк-обращений в таблице 01.10 – утро 16.10: {len(r)}; по источнику:", r["src"].replace("", "Нет метки").value_counts().to_dict())
print(" статус на момент обращения:", r["status"].value_counts().to_dict())
print(" строк со статусом «Продажа»:", int((r["status"] == "Продажа").sum()), "; уникальных номеров среди них:", r[r["status"] == "Продажа"]["p9"].nunique())
sr = r[r["status"] == "Продажа"]
print(" строки «Продажа» по источнику:", sr["src"].replace("", "Нет метки").value_counts().to_dict(), "; уникальных заказов:", sr["order"].nunique())
