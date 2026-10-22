#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: сверка списка продаж клиентского дашборда с нашими заказами по номеру заказа — ТОЛЬКО ЧТЕНИЕ.

Вход: список «Продажи» клиентского дашборда (все источники сразу, текст с колонкой «Автор»), `--client-list` (TSV). Наши заказы — лист
`mocnaszklarnia.pl` таблицы продаж клиента (`profimet_sales_vs_ringostat.load_sheet`), правило нашего дашборда «заявки → продажи»:
проданный заказ без отмены, источник — первое обращение номера за 60 дн до заказа (`profimet_sales_trend.sales_table`).
Номер заказа клиента = первые 8 символов нашего (у форм — первые 8 цифр 10-значного номера). Не нашлось по номеру — ищется по телефону и дате (±1 день).
Печатает: состав списка клиента (строки / заказы / количество), как каждый его заказ выглядит у нас, наши заказы, которых нет у клиента, и причины.
Использование (из папки Скрипты): PYTHONUTF8=1 python profimet_client_list_reconcile.py --client-list ПУТЬ.tsv [--from 2026-10-01] [--to 2026-10-20]
"""
import argparse
import re

import pandas as pd

from profimet_sales_trend import SITE, WINDOW
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet

SRC_OK = {"Google Ads", "Facebook"}


def our_orders(sheet):
    s = sheet[sheet["site"] == SITE]
    by_phone = {p: g for p, g in s.groupby("p9") if p}
    rows = []
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        parts = [by_phone[p] for p in set(grp["p9"]) if p in by_phone]
        t = pd.concat(parts) if parts else grp
        win = t[(t["ts"] >= t0 - pd.Timedelta(days=WINDOW)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        first = win.iloc[0] if not win.empty else grp.iloc[0]
        rows.append({"order": order, "key": order[:8], "op9": grp.iloc[0]["p9"], "created": t0,
                     "sale": pd.Timestamp(min(sd)).date() if sd else None, "cancelled": bool(any(grp["cancel_date"] != "")),
                     "first_row_type": grp.iloc[0]["type"], "first_row_src": grp.iloc[0]["src"] or "Нет метки",
                     "touch_src": first["src"] or "Нет метки", "touch_type": first["type"], "touch_ts": first["ts"],
                     "rows": len(grp)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-list", required=True)
    ap.add_argument("--from", dest="d0", default="2026-10-01")
    ap.add_argument("--to", dest="d1", default="2026-10-20")
    a = ap.parse_args()
    d0, d1 = pd.Timestamp(a.d0).date(), pd.Timestamp(a.d1).date()

    C = pd.read_csv(a.client_list, sep="\t", dtype=str)
    C["qty"] = C["Кол-во"].astype(int)
    C["p9"] = C["Телефон"].map(lambda x: re.sub(r"\D", "", x)[-9:])
    C["ts"] = pd.to_datetime(C["Дата"])
    print(f"== Список клиента {a.d0}…{a.d1} ==")
    print(f"строк (это и есть его «Продажи»): {len(C)}; разных заказов: {C['Заказ'].nunique()}; сумма «Кол-во»: {C['qty'].sum()}")
    print("по метке (строк):", C["Источник"].value_counts().to_dict())
    print("по метке (ЕДИНИЦЫ = сумма «Кол-во»; именно это число стоит в «Продажи» дашборда):", C.groupby("Источник")["qty"].sum().to_dict())
    cc = C.groupby("Заказ").agg(label=("Источник", "first"), lines=("Заказ", "size"), p9=("p9", "first"), ts=("ts", "first"),
                                author=("Автор", "first"), platform=("Площадка", "first")).reset_index()
    cc["by"] = cc["author"].map(lambda x: "сайт/скрипт" if str(x).startswith("script") else "менеджер")

    sheet = load_sheet(SHEET_ID)
    O = our_orders(sheet)
    sold = O[O["sale"].notna()].copy()
    ours = sold[(sold["sale"] >= d0) & (sold["sale"] <= d1) & ~sold["cancelled"]].copy()
    ours["kind"] = ours["touch_src"].where(ours["touch_src"].isin(["Google Ads", "Facebook", "Нет метки", "Телефон"]), "Прочее")
    print(f"\n== Наши данные: проданных без отмены с датой продажи {a.d0}…{a.d1}: {len(ours)} ==")
    print("по источнику первого обращения за 60 дн:", ours["kind"].value_counts().to_dict())
    print(f"из них не «Телефон» (это и есть наши «продажи» в дашборде): {int((ours['kind'] != 'Телефон').sum())}; «Телефон»: {int((ours['kind'] == 'Телефон').sum())}")

    # сопоставление: по ключу, затем по телефону и дате
    allO = O.copy()
    m = cc.merge(allO, left_on="Заказ", right_on="key", how="left")
    miss = m["order"].isna()
    for i in m[miss].index:
        cand = allO[(allO["op9"] == m.loc[i, "p9"]) & ((allO["created"].dt.tz_convert(None) - m.loc[i, "ts"]).abs() <= pd.Timedelta(days=1.2))]
        if len(cand):
            for col in allO.columns:
                m.loc[i, col] = cand.iloc[0][col]
            m.loc[i, "match"] = "по телефону и дате"
    m["match"] = m["match"].fillna(m["order"].notna().map({True: "по номеру", False: "не найден"}))
    m.loc[m["order"].isna(), "match"] = "не найден"
    print(f"\n== Как заказы клиента выглядят у нас ==")
    print("сопоставлено:", m["match"].value_counts().to_dict())
    print("\nНе найдены у нас:"); print(m[m["match"] == "не найден"][["Заказ", "label", "platform", "author"]].to_string(index=False))

    def status(r):
        if pd.isna(r["order"]):
            return "нет у нас"
        if r["cancelled"]:
            return "у нас отменён"
        if pd.isna(r["sale"]):
            return "у нас не продан"
        return "продан"
    m["у_нас"] = m.apply(status, axis=1)
    f = m[m["match"] != "не найден"]
    print("\nМетка клиента × состояние заказа у нас:"); print(pd.crosstab(m["label"], m["у_нас"], margins=True).to_string())
    pr = f[f["у_нас"] == "продан"]
    print("\nМетка клиента × источник первого обращения у нас (только проданные у нас):"); print(pd.crosstab(pr["label"], pr["touch_src"], margins=True).to_string())
    print("\nМетка клиента × кто создал заказ:"); print(pd.crosstab(m["label"], m["by"], margins=True).to_string())

    inc = set(f["order"])
    in_client = ours["order"].isin(inc)
    print(f"\n== Наши {len(ours)} проданных: сколько есть в списке клиента ==")
    print(pd.crosstab(ours["kind"], in_client.map({True: "есть у клиента", False: "нет у клиента"}), margins=True).to_string())
    x = ours[~in_client & (ours["kind"] != "Телефон")]
    print(f"\nНаши НЕ «Телефон», которых нет в списке клиента ({len(x)}):")
    print(x[["order", "created", "sale", "kind", "first_row_type", "first_row_src", "touch_type"]].assign(created=lambda d: d["created"].dt.tz_convert("Europe/Warsaw").dt.strftime("%d.%m %H:%M")).to_string(index=False))
    y = f[(f["у_нас"] == "продан") & ~f["order"].isin(ours["order"])]
    print(f"\nЗаказы клиента, найденные у нас, но не входящие в наши «проданные без отмены за период» ({len(y)}):")
    print(y[["Заказ", "label", "sale", "cancelled"]].to_string(index=False) if len(y) else "нет")
    z = f[f["у_нас"].isin(["у нас отменён", "у нас не продан"])]
    print(f"\nЗаказы клиента, у нас отменённые или не проданные ({len(z)}):"); print(z[["Заказ", "label", "у_нас", "sale"]].to_string(index=False) if len(z) else "нет")


if __name__ == "__main__":
    main()
