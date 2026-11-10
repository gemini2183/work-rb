#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: заказы периода с источником «Телефон» / «Нет метки» (режим «как у клиента») и ВСЕ их прежние касания по номеру — ТОЛЬКО ЧТЕНИЕ.

Зачем (запрос пользователя 2026-11-10): в клиентском дашборде заказ менеджера без формы получает источник «Телефон», звонок без метки — «Нет метки».
Наша проверка по выгрузке CRM (лист с 01.08.2025, часть звонков отфильтрована) может не видеть прежние касания номера. Здесь для каждого такого заказа
берётся ПОЛНАЯ выгрузка Ringostat аккаунта (с 2023-08-31, входящие, исходящие и без метки — `profimet_season_audit.fetch_ringostat_full`) плюс все строки CRM
по всем трём сайтам, и печатается хронология номера. «Прежнее касание» = раньше первой строки заказа в CRM по времени.

Заказы периода — как у клиента: `profimet_sources_dashboard.client_scheme_orders`, период по «Дате заказа».

Запуск (из папки Скрипты): PYTHONUTF8=1 python profimet_phone_orders_earlier_touches.py --from 2026-11-01 --to 2026-11-10 [--cache путь.pkl] [--sources Телефон,Нет\\ метки]
Результат: хронология в консоли и Клиенты/ProfiMet/Статистика/phone_orders_earlier_touches_<от>_<до>.csv (телефоны не пишем).
"""
import argparse
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import profimet_sources_dashboard as d  # noqa: E402
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet  # noqa: E402
from profimet_season_audit import fetch_ringostat_full  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default=date.today().replace(day=1).isoformat())
    ap.add_argument("--to", dest="to", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--sources", default="Телефон,Нет метки", help="какие источники клиентской схемы проверять (через запятую)")
    ap.add_argument("--basis", choices=["our", "client"], default="our",
                    help="our — продажи по дате продажи, источник = первое касание номера в CRM (строка «Телефон» нашего дашборда); client — заказы схемы клиента по дате заказа")
    ap.add_argument("--cache", default=None, help="pickle (sheet, ringo_full)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    want = [s.strip() for s in a.sources.split(",")]
    if a.basis == "our":
        # наш режим: продажа периода (по дате продажи), источник = источник первого касания номера в CRM за 60 дней («Телефон» = звонок без метки)
        S0 = d.sales_with_source(sheet)
        S0 = S0[(S0["sale_date"] >= pd.Timestamp(a.frm).date()) & (S0["sale_date"] <= pd.Timestamp(a.to).date())]
        S = S0[S0["src2"].isin(want)]
        first = sheet[(sheet["site"] == d.SITE) & (sheet["order"] != "")].sort_values("ts", kind="mergesort").groupby("order")["ts"].first()
        x = pd.DataFrame({"key": S["order"].str[:8], "rule": S["src2"], "est": pd.to_datetime(S["touch_date"]), "sale": S["sale_date"].astype(str),
                          "created": [first[o] for o in S["order"]]}).sort_values("sale")
        n_all = f"продаж периода {len(S0)}"
    else:
        sel, _ = d.client_scheme_orders(sheet, None, a.frm, a.to)
        x = sel[sel["rule"].isin(want)].sort_values("est")
        n_all = f"заказов схемы клиента {len(sel)}"
    print(f"Ringostat: {len(ringo)} звонков с {ringo['ts'].min():%d.%m.%Y}; CRM до {sheet['ts'].max().tz_convert(d.W):%d.%m.%Y %H:%M}. "
          f"Режим «{a.basis}», {a.frm} — {a.to}: {n_all}, проверяем {len(x)} ({a.sources}).")
    rows = []
    for r in x.itertuples():
        ph = set(sheet.loc[sheet["order"].str[:8] == r.key, "p9"]) - {""}
        rg, cr = ringo[ringo["p9"].isin(ph)], sheet[sheet["p9"].isin(ph)]
        ev = [(q.ts, "Ringostat", f"{q.call_type}/{q.disposition}/{q.billsec}с", q.category, f"{q.utm_source}|{q.utm_medium}|{q.utm_campaign}") for q in rg.itertuples()]
        ev += [(q.ts, "CRM", f"{q.type}/{q.site}", q.src or "Нет метки", f"{q.utm_source}|{q.utm_medium}|{q.utm_campaign}|заказ {q.order[:8] or '-'}") for q in cr.itertuples()]
        ev.sort(key=lambda e: e[0])
        earlier = [e for e in ev if e[0] < r.created - pd.Timedelta(minutes=3)]
        print(f"\n=== {r.key} | у клиента «{r.rule}» | заказ {r.est:%d.%m} | первая строка CRM {r.created.tz_convert(d.W):%d.%m %H:%M} | прежних касаний: {len(earlier)} "
              f"(Ringostat всего {len(rg)}, CRM {len(cr)})")
        for e in ev:
            tag = "  ← до заказа" if e in earlier else ""
            print(f"  {e[0].tz_convert(d.W):%Y-%m-%d %H:%M} {e[1]:9} {e[2]:36} {e[3]:12} {e[4]}{tag}")
        ad = [e for e in earlier if e[3] in d.AD_SRC or e[3] == "Google Ads"]
        rows.append({"Заказ": r.key, "Источник у клиента": r.rule, "Дата заказа": f"{r.est:%Y-%m-%d}", "Дата продажи": r.sale,
                     "Прежних строк (звонок виден в Ringostat и в CRM — две строки)": len(earlier), "Из них рекламных": len(ad),
                     "Самое раннее касание": f"{earlier[0][0].tz_convert(d.W):%Y-%m-%d} {earlier[0][1]} {earlier[0][3]}" if earlier else "",
                     "Дней от раннего до заказа": (r.created - earlier[0][0]).days if earlier else ""})
    out = pd.DataFrame(rows)
    path = d.client_stats_dir("ProfiMet") / f"phone_orders_earlier_touches_{a.basis}_{a.frm}_{a.to}.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print("\n", out.to_string(index=False), f"\n\nФайл: {path}")


if __name__ == "__main__":
    main()
