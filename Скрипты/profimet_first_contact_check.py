#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: правило клиента «продажа — первому обращению». ТОЛЬКО ЧТЕНИЕ.

Для каждого проданного заказа сайта mocnaszklarnia.pl берёт самое первое обращение того же номера (звонок или форма)
в окне 30 / 60 дн и без окна (в таблице данные с 01.08.2025) и показывает: чьё это обращение, за сколько дней до заказа,
какой у него был статус заказа на тот момент («нет заказа», предзаказ, продажа, отмена) и тег причины. Отдельно считает
случаи, когда первое обращение не реклама, а реклама пришла позже (так Google теряет продажу по правилу клиента).

Использование:
    PYTHONIOENCODING=utf-8 python profimet_first_contact_check.py [кеш.pkl от profimet_sales_vs_ringostat.py] > вывод.txt
Без аргумента читает таблицу заново (сервисный аккаунт, роль «Читатель»). Запускать без -I.
"""
import pickle, sys
import pandas as pd

from profimet_sales_vs_ringostat import SHEET_ID, load_sheet

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 220)
sheet = pickle.load(open(sys.argv[1], "rb"))[0] if len(sys.argv) > 1 else load_sheet(SHEET_ID)
AD = {"Google Ads", "Facebook"}
s = sheet[sheet["site"] == "mocnaszklarnia.pl"]
by_phone = {p: g for p, g in s.groupby("p9")}


def run(window_days):
    win = pd.Timedelta(days=window_days)
    rows = []
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd:
            continue
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        t = pd.concat([by_phone[p] for p in set(grp["p9"]) if p in by_phone])
        t = t[(t["ts"] >= t0 - win) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        ft = t.iloc[0]
        ad_later = t[t["src"].isin(AD)]
        rows.append({
            "order": order, "m": min(sd)[:7], "first_src": ft["src"] or "Нет метки", "first_type": ft["type"],
            "first_status": ft["status"], "first_reason": ft["reason"], "first_order": ft["order"],
            "has_ad": not ad_later.empty, "first_ad_src": "" if ad_later.empty else ad_later.iloc[0]["src"],
            "credited_first_row": grp.iloc[0]["src"] or "Нет метки",
            "gap_days": (t0 - ft["ts"]).total_seconds() / 86400, "n_touch": len(t),
        })
    return pd.DataFrame(rows)


for w in (30, 60):
    d = run(w)
    lost = d[(~d["first_src"].isin(AD)) & d["has_ad"]]
    print(f"\n######## окно {w} дн ########")
    for lab, m in (("всё", d["m"] > ""), ("сен+окт 2026", d["m"].isin(["2026-09", "2026-10"])), ("окт 2026", d["m"] == "2026-10")):
        g = d[m]
        l = lost[lost["m"].isin(g["m"].unique())] if lab != "всё" else lost
        if lab == "сен+окт 2026":
            l = lost[lost["m"].isin(["2026-09", "2026-10"])]
        if lab == "окт 2026":
            l = lost[lost["m"] == "2026-10"]
        print(f"{lab}: заказов {len(g)} | первое обращение: " + str(g["first_src"].value_counts().to_dict()) +
              f" | реклама пришла позже первого неРекламного: {len(l)} ({round(100*len(l)/max(len(g),1),1)}%), позже-реклама: {l['first_ad_src'].value_counts().to_dict()}")
    if w == 60:
        print("\nПервое обращение НЕ реклама, а реклама позже — что это за первое обращение (всё время):")
        print(" тип:", lost["first_type"].value_counts().to_dict())
        print(" источник:", lost["first_src"].value_counts().to_dict())
        print(" статус заказа на момент обращения:", lost["first_status"].value_counts().to_dict())
        print(" причина/тег:", lost["first_reason"].replace("", "(пусто)").value_counts().head(12).to_dict())
        print(" первое обращение уже с этим заказом:", int((lost["first_order"] != "").sum()), "из", len(lost), "(остальное — звонок без заказа)")

print("\n######## БЕЗ ограничения окна: самое первое обращение номера в таблице (с 01.08.2025) до заказа ########")
d = run(3650)
bins = [(-1, 1, "в тот же день (<1 дн)"), (1, 30, "1–30 дн"), (30, 60, "31–60 дн"), (60, 100, "61–100 дн"), (100, 180, "101–180 дн"), (180, 4000, ">180 дн")]
for lab, m in (("всё время", d["m"] > ""), ("сен+окт 2026", d["m"].isin(["2026-09", "2026-10"]))):
    g = d[m]
    print(f"\n{lab}: заказов {len(g)}; первое обращение до заказа:")
    for lo, hi, name in bins:
        x = g[(g["gap_days"] > lo) & (g["gap_days"] <= hi)] if lo >= 0 else g[g["gap_days"] <= hi]
        print(f"  {name}: {len(x)} ({round(100*len(x)/len(g),1)}%)")
old = d[d["gap_days"] > 60]
print(f"\nПервое обращение старше 60 дн до заказа: {len(old)} из {len(d)} (за всю историю таблицы, с учётом что история начинается с 01.08.2025 — старые обращения до этой даты не видны)")
print(" источник этого первого обращения:", old["first_src"].value_counts().to_dict())
print(" тип:", old["first_type"].value_counts().to_dict())
print(" статус заказа на момент того обращения:", old["first_status"].value_counts().to_dict())
print(" тег причины:", old["first_reason"].replace("", "(пусто)").value_counts().head(10).to_dict())
d60 = run(60)
m = d.merge(d60[["order", "first_src"]], on="order", suffixes=("_all", "_60"))
chg = m[m["first_src_all"] != m["first_src_60"]]
print(f"\nЕсли не ограничивать окно, источник первого обращения меняется у {len(chg)} из {len(m)} заказов; из них становится Google Ads: {int((chg['first_src_all']=='Google Ads').sum())}, Facebook: {int((chg['first_src_all']=='Facebook').sum())}, перестаёт быть Google Ads: {int(((chg['first_src_60']=='Google Ads')).sum())}")
print("  переходы (окно 60 → без окна):", chg.groupby(["first_src_60", "first_src_all"]).size().sort_values(ascending=False).head(10).to_dict())
