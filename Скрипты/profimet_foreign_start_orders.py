#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: заказы, которые попали в рекламный дашборд клиента, но НАЧАЛИСЬ с чужого источника — ТОЛЬКО ЧТЕНИЕ.

Зачем (запрос пользователя 2026-11-10): вкладка «Ads + FB» клиента считает платным каналом ВСЕ строки (Google Ads, YouTube, Facebook, «Нет метки», «Телефон»,
«Прочее»), цена продажи = расход ÷ все продажи вкладки. Если заказ начался с Allegro / OLX / Erli / Ceneo, SEO-сайта или другого проекта (EkspertAgro), он всё равно
попадает в знаменатель и занижает цену продажи рекламы. Скрипт находит такие заказы и называет, откуда они на самом деле пришли.

Что берём. Заказы: (а) из списков продаж дашборда клиента `Статистика/client_dashboard_sales_list_*.tsv` (в дашборде клиента они точно есть), (б) заказы схемы клиента
`profimet_sources_dashboard.client_scheme_orders` за период (в дашборде клиента они должны быть по нашему воспроизведению правила; в списках нет — помечено «по схеме»).
Старт заказа = самое раннее ВХОДЯЩЕЕ касание номера по полной выгрузке Ringostat (с 2023-08-31; пул) и по строкам CRM всех трёх сайтов; исходящие звонки менеджера
стартом не считаются. Если несколько касаний в пределах 3 минут от самого раннего — смотрим, нет ли среди них чужого.
Чужой старт: пул Ringostat Allegro / Allegro Tig / OLX / Erli / Ceneo («Маркетплейс»), пул SeoMocna или сайт szklarniaprofimet.pl («SEO»), строка листа Ekspertagro.pl («EkspertAgro»).

Запуск (из папки Скрипты): PYTHONUTF8=1 python profimet_foreign_start_orders.py [--from 2026-10-01] [--to 2026-11-10] [--cache pkl]
Результат: таблица в консоли и Клиенты/ProfiMet/Статистика/foreign_start_orders_<от>_<до>.csv (телефоны не пишем).
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

MARKET = ("allegro", "olx", "erli", "ceneo", "маркетплейс")


def pool_class(pool):
    p = str(pool).lower()
    if any(k in p for k in MARKET):
        return "Маркетплейс"
    if "seomocna" in p:
        return "SEO"
    return ""


def start_touch(ph, created, ringo, sheet):
    """Самое раннее входящее касание номера (Ringostat + CRM); возвращает (время, класс чужого или '', описание)."""
    ev = [(q.ts, pool_class(q.pool_name), f"Ringostat, пул «{q.pool_name or 'без пула'}»") for q in ringo[ringo["p9"].isin(ph) & (ringo["call_type"] == "in")].itertuples()]
    for q in sheet[sheet["p9"].isin(ph)].itertuples():
        cls = "EkspertAgro" if q.site == "Ekspertagro.pl" else ("SEO" if q.site == "szklarniaprofimet.pl" else "")
        ev.append((q.ts, cls, f"CRM {q.type}, {q.site}, {q.src or 'Нет метки'}"))
    ev = [e for e in ev if e[0] <= created + pd.Timedelta(minutes=3)]
    if not ev:
        return None, "", ""
    ev.sort(key=lambda e: e[0])
    near = [e for e in ev if e[0] - ev[0][0] <= pd.Timedelta(minutes=3)]
    pick = next((e for e in near if e[1]), ev[0])
    return pick[0], pick[1], pick[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-10-01")
    ap.add_argument("--to", dest="to", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    lists = sorted(d.client_stats_dir("ProfiMet").glob("client_dashboard_sales_list_*.tsv"))
    cl = d.read_client_list(lists) if lists else None
    cl_src = cl.set_index("key")["client_source"].to_dict() if cl is not None else {}
    cl_date = cl.set_index("key")["client_date"].to_dict() if cl is not None else {}
    sel, _ = d.client_scheme_orders(sheet, None, a.frm, a.to)
    scheme = sel.set_index("key")
    f0, t0 = a.frm, a.to
    keys = [k for k in cl_src if f0 <= str(cl_date[k])[:10] <= t0] + [k for k in scheme.index if k not in cl_src]
    first_rows = sheet[sheet["order"] != ""].sort_values("ts", kind="mergesort").groupby(sheet["order"].str[:8])
    rows = []
    for k in dict.fromkeys(keys):
        g = sheet[sheet["order"].str[:8] == k].sort_values("ts", kind="mergesort")
        if g.empty:
            continue
        ph = set(g["p9"]) - {""}
        created = g.iloc[0]["ts"]
        t, cls, what = start_touch(ph, created, ringo, sheet)
        src = cl_src.get(k) or scheme.loc[k, "rule"] if (k in cl_src or k in scheme.index) else ""
        rows.append({"Заказ": k, "В дашборде клиента": "да (список клиента)" if k in cl_src else "по схеме",
                     "Дата заказа": (cl_date.get(k) or f"{scheme.loc[k, 'est']:%Y-%m-%d}")[:10],
                     "Источник в дашборде клиента": src, "Чужой старт": cls, "Старт заказа": what,
                     "Дата старта": f"{t.tz_convert(d.W):%Y-%m-%d %H:%M}" if t is not None else "",
                     "Дней от старта до первой строки заказа": (created - t).days if t is not None else ""})
    out = pd.DataFrame(rows)
    bad = out[out["Чужой старт"] != ""].sort_values("Дата заказа")
    print(f"Ringostat с {ringo['ts'].min():%d.%m.%Y}, CRM до {sheet['ts'].max().tz_convert(d.W):%d.%m.%Y %H:%M}. Заказов в дашборде клиента {f0} — {t0}: {len(out)} "
          f"(из списков клиента {int(out['В дашборде клиента'].str.startswith('да').sum())}, по схеме {int((out['В дашборде клиента'] == 'по схеме').sum())}).")
    print(f"С чужим стартом: {len(bad)}; по классам: {bad['Чужой старт'].value_counts().to_dict()}; по источнику в дашборде клиента: {bad['Источник в дашборде клиента'].value_counts().to_dict()}\n")
    if len(bad):
        print(bad.to_string(index=False))
    path = d.client_stats_dir("ProfiMet") / f"foreign_start_orders_{a.frm}_{a.to}.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\nФайл (все заказы, не только с чужим стартом): {path}")


if __name__ == "__main__":
    main()
