#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: ОТЧЁТ О НЕСТЫКОВКАХ «выгрузка CRM ↔ дашборд клиента, вкладка Ads + FB» — ТОЛЬКО ЧТЕНИЕ (2026-11-05).

Зачем. Клиент считает цену продажи по вкладке «Ads + FB» как расход ÷ ВСЕ продажи вкладки (Google Ads, YouTube, Facebook, «Нет метки»,
«Телефон», «Прочее»: всё это для него платный канал). Поэтому важно:
  • заказ, проданный по CRM и относящийся к рекламе, но отсутствующий в списке вкладки, — потерянная продажа (занижает число продаж, цена продажи растёт);
  • заказ, у которого CRM знает рекламный источник (форма Google Ads / Facebook, рекламный звонок), а у клиента «Нет метки»/«Телефон», —
    атрибуция не дошла (общий итог не меняется, но Google Ads / Facebook по строкам занижены);
  • заказ в списке клиента, которого у нас нет проданным, — наоборот.
Список продаж клиента (TSV из вкладки «Ads + FB», колонки Дата, Заказ, Телефон, Товар, Кол-во, Источник, UTM, Площадка, Автор) присылается за период;
период берётся из имени файла `..._ГГГГ-ММ-ДД_ГГГГ-ММ-ДД...tsv`. Сравнение — только внутри этого периода (иначе лишние «только у нас»).

Правила отбора заказов клиента — `profimet_sources_dashboard.client_scheme_orders` (воспроизведено на 01–20.10: 74 из 75 дат; 02–04.11: 15 из 16).
Результат: печать по категориям + CSV `Клиенты/ProfiMet/Статистика/client_discrepancies_<с>_<по>.csv`. Ничего не пишет в кабинеты и таблицы.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python profimet_client_discrepancy_report.py --client-list ПУТЬ1.tsv [ПУТЬ2.tsv ...] [--cache pkl]
"""
import argparse
import pickle
import re
import sys
from pathlib import Path

import pandas as pd

from _config import client_stats_dir
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_sources_dashboard import SITE, client_scheme_orders, read_client_list

AD = {"Google Ads", "Facebook"}


def period_of(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", Path(path).name)
    if not m:
        sys.exit(f"В имени файла {path} нет периода ГГГГ-ММ-ДД_ГГГГ-ММ-ДД")
    return m.group(1), m.group(2)


def crm_view(sheet, key):
    """Как заказ выглядит в CRM: сайты, число строк, первая строка, есть ли форма, есть ли строка с рекламным источником, дата продажи/отмены."""
    g = sheet[sheet["order"].str[:8] == key].sort_values("ts", kind="mergesort")
    if g.empty:
        return {"crm_rows": 0, "crm_sites": "", "crm_first": "", "crm_first_src": "", "crm_has_form": "", "crm_ad_src": "", "crm_sale": "", "crm_cancel": ""}
    f = g.iloc[0]
    ad = [s for s in g["src"] if s in AD]
    return {"crm_rows": len(g), "crm_sites": ", ".join(sorted(set(g["site"]))),
            "crm_first": f"{f['ts'].tz_convert('Europe/Warsaw'):%d.%m %H:%M} {f['type']}", "crm_first_src": f["src"] or "Нет метки",
            "crm_has_form": "да" if (g["type"] == "форма").any() else "нет", "crm_ad_src": ad[0] if ad else "",
            "crm_sale": min([d for d in g["sale_date"] if d] or [""]), "crm_cancel": max([d for d in g["cancel_date"] if d] or [""])}


def analyse(sheet, cl, d0, d1):
    sel, diff = client_scheme_orders(sheet, cl, d0, d1)
    rows = []
    cin = cl[(cl["client_date"].str[:10] >= d0) & (cl["client_date"].str[:10] <= d1)]
    ck = cin.set_index("key")
    for r in cin.itertuples():  # заказы клиента: источник против CRM
        v = crm_view(sheet, r.key)
        so = sel[sel["key"] == r.key]
        if so.empty:
            kind = "В списке клиента, у нас не продан в период" if not v["crm_sale"] or v["crm_cancel"] else "В списке клиента, у нас вне схемы клиента"
            rows.append({"Категория": kind, "Заказ": r.key, "Дата у клиента": r.client_date, "Источник у клиента": r.client_source, "Наш источник по схеме": "", **v,
                         "Пояснение": "в выгрузке CRM нет даты продажи или заказ отменён (возможна задержка выгрузки)" if (not v["crm_sale"] or v["crm_cancel"]) else "правило отбора не совпало, проверить вручную"})
            continue
        o = so.iloc[0]
        ad_crm = v["crm_ad_src"] or (o["first60"] if o["first60"] in AD else "")
        if r.client_source in ("Нет метки", "Телефон") and ad_crm in AD:
            kind = "Источник не дошёл: в CRM реклама, у клиента без метки"
            why = (f"в CRM у заказа есть строка с источником {ad_crm}" if v["crm_ad_src"] else f"первое обращение номера за 60 дн — {ad_crm}") + f"; у клиента «{r.client_source}»"
            rows.append({"Категория": kind, "Заказ": r.key, "Дата у клиента": r.client_date, "Источник у клиента": r.client_source, "Наш источник по схеме": o["rule"], **v, "Пояснение": why})
        elif o["rule"] != r.client_source:
            rows.append({"Категория": "Источник у клиента другой (не реклама в CRM)", "Заказ": r.key, "Дата у клиента": r.client_date, "Источник у клиента": r.client_source,
                         "Наш источник по схеме": o["rule"], **v, "Пояснение": "правило клиента даёт другой источник (вероятно, ручной выбор менеджера)"})
    for r in sel[~sel["key"].isin(ck.index)].itertuples():  # наши заказы, которых нет в списке клиента
        v = crm_view(sheet, r.key)
        ad = r.first60 in AD or r.ad_touch
        rows.append({"Категория": "Продан в CRM, нет в дашборде клиента" + (" (рекламное касание)" if ad else ""), "Заказ": r.key, "Дата у клиента": "",
                     "Источник у клиента": "", "Наш источник по схеме": r.rule, **v,
                     "Пояснение": "по схеме клиента заказ должен быть на вкладке; " + ("повторная покупка" if r.repeat else "причина не найдена")})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-list", nargs="+", required=True)
    ap.add_argument("--cache", default=None, help="pickle (sheet, ringo) как у profimet_sources_dashboard.py")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sheet = pickle.load(open(a.cache, "rb"))[0] if a.cache and Path(a.cache).exists() else load_sheet(SHEET_ID)
    out = []
    for p in a.client_list:
        d0, d1 = period_of(p)
        cl = read_client_list([p])
        df = analyse(sheet, cl, d0, d1)
        df.insert(0, "Период списка клиента", f"{d0} … {d1}")
        out.append(df)
        print(f"\n=== {d0} … {d1}: заказов в списке клиента {len(cl)}, штук {int(cl['qty'].sum())}; нестыковок {len(df)} ===")
        if len(df):
            print(df["Категория"].value_counts().to_string())
    res = pd.concat(out, ignore_index=True)
    f = client_stats_dir("ProfiMet") / f"client_discrepancies_{res['Период списка клиента'].iloc[0][:10]}_{res['Период списка клиента'].iloc[-1][-10:]}.csv"
    res.to_csv(f, index=False, encoding="utf-8-sig")
    print("\nCSV:", f)


if __name__ == "__main__":
    main()
