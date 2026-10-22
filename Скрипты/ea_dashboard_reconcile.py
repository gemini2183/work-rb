#!/usr/bin/env python
# coding: utf-8
"""Сверка клиентского дашборда «По источникам» EkspertAgro с нашими данными — ТОЛЬКО ЧТЕНИЕ.

Что сверяем (период задаётся `--from/--to`, даты включительно, Варшава):
  1. ЗВОНКИ: сколько звонков Google / Facebook даёт каждый способ подсчёта уникальности (все входящие; первый звонок номера
     за всю историю; единое множество по отслеживаемым источникам; флаг Ringostat `unique_call`; боевое правило 60 дней
     по клиентам ФБ/Мерчант/Теплицы; первый звонок номера внутри своего источника).
  2. ФОРМЫ: строки-формы листа таблицы по источнику (все и уникальные по номеру).
  3. ПРОДАЖИ: проданные и не отменённые заказы периода (по «Дата продажи») по способу создания (форма / звонок) и источнику
     первой строки; первое касание номера в таблице и в Ringostat до заказа; сколько заказов клиент мог записать
     на «Телефон» / «Нет метки», хотя первое касание рекламное.
Эталон — цифры со скрина дашборда клиента (`--client-google-calls` и т. д.), печатаются рядом.
Ключ Ringostat — из конфига мониторинга, в вывод не попадает.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ea_dashboard_reconcile.py --from 2026-10-01 --to 2026-10-20 [--csv путь]
"""
import argparse

import pandas as pd

from ea_ringostat_vs_sheet import SHEET_ID, fetch_ringostat, last9, prod_unique
from ea_sales_orders_check import load as load_sheet
from ringostat_sales_attribution import MONITORING_CONFIG, categorize_source

TZ = "Europe/Warsaw"
CLIENT = {"Google Ads": {"calls": 31}, "Facebook": {"calls": 22}}  # со скрина 01–20.10


def cat_of(df):
    kws = ["google", "dspl", "kms", "performance_max"]
    c = [categorize_source(s, m, kws) for s, m in zip(df["utm_source"], df["utm_medium"])]
    c = pd.Series(c, index=df.index)
    c[df["utm_campaign"].isin(["(organic)", "Google Карты Бизнес"])] = "No Source"
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-10-01")
    ap.add_argument("--to", dest="d1", default="2026-10-20")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()
    t0 = pd.Timestamp(args.d0, tz=TZ)
    t1 = pd.Timestamp(args.d1, tz=TZ) + pd.Timedelta(days=1)

    # ---------------- звонки
    ringo = fetch_ringostat("2025-12-01")
    ringo["category"] = cat_of(ringo)
    ringo = ringo.sort_values("ts", kind="mergesort").reset_index(drop=True)
    tracked = ringo[ringo["category"] != "Other"]
    seen, flag = set(), {}
    for i, p in zip(tracked.index, tracked["p9"]):
        flag[i] = p not in seen
        seen.add(p)
    ringo["our_unique"] = pd.Series(flag).reindex(ringo.index).fillna(False).astype(bool)
    # первый звонок номера в своей категории за всю историю
    ringo["first_in_cat"] = ~ringo.duplicated(["category", "p9"], keep="first")
    ringo = prod_unique(ringo)
    w = ringo[(ringo["ts"] >= t0) & (ringo["ts"] < t1)]
    print(f"== 1. ЗВОНКИ {args.d0} … {args.d1} (Ringostat аккаунта EkspertAgro) ==")
    print("Клиент на скрине: Google 31, Facebook 22, всего 53\n")
    rows = []
    for name, mask in [("все входящие", w["p9"].notna()),
                       ("первый звонок номера за всю историю (единое множество)", w["our_unique"]),
                       ("первый звонок номера в своей категории", w["first_in_cat"]),
                       ("флаг Ringostat unique_call=1", w["unique_call"] == 1),
                       ("боевое правило 60 дн (клиент+номер)", w["prod_unique"])]:
        s = w[mask]
        rows.append({"способ": name, "Google": int((s["category"] == "Google Ads").sum()),
                     "Facebook": int((s["category"] == "Facebook").sum()),
                     "другое": int((~s["category"].isin(["Google Ads", "Facebook"])).sum()), "всего": len(s)})
    print(pd.DataFrame(rows).to_string(index=False))
    # по боевому правилу клиент определяется по utm: ФБ = facebook cpc; остальное — Google
    pu = w[w["prod_unique"]]
    print("\nБоевое правило по клиентам (ФБ / Мерчант / Теплицы):", pu["client"].value_counts().to_dict())

    # ---------------- формы и продажи из таблицы
    df = load_sheet(SHEET_ID, "Ekspertagro.pl")
    df["p9"] = df["phone"].map(last9)
    df = df.sort_values("ts", kind="mergesort").reset_index(drop=True)
    ws = df[(df["ts"] >= t0) & (df["ts"] < t1)]
    forms = ws[ws["type"] == "форма"]
    print(f"\n== 2. ФОРМЫ таблицы {args.d0} … {args.d1} ==")
    print("Клиент: конверсии минус звонки = Google 25, Facebook 22, Нет метки 2, всего 49 (по GA4, если как у ProfiMet)")
    fr = []
    for src, g in forms.groupby("src"):
        fr.append({"источник": src, "строк-форм": len(g), "уникальных номеров": g["p9"].nunique(),
                   "с заказом": int((g["order"] != "").sum())})
    print(pd.DataFrame(fr).to_string(index=False))

    # ---------------- продажи
    o = df[df["order"] != ""]
    g = o.groupby("order")
    orders = pd.DataFrame({
        "created": g["ts"].min(), "first_type": g["type"].first(), "first_src": g["src"].first(),
        "first_campaign": g["utm_campaign"].first(), "p9": g["p9"].first(),
        "rows": g.size(), "srcs": g["src"].apply(lambda s: ",".join(sorted(set(s)))),
        "sale": g["sale_date_dt"].max(), "cancel": g["cancel_date_dt"].max(),
    })
    sale_day = orders["sale"].dt.tz_convert(None).dt.normalize()
    in_p = (sale_day >= pd.Timestamp(args.d0)) & (sale_day <= pd.Timestamp(args.d1))
    sold = orders[in_p].copy()
    print(f"\n== 3. ПРОДАЖИ: заказы с датой продажи {args.d0} … {args.d1} ==")
    print("Клиент на скрине: всего 35 (Google 4, Facebook 9, Нет метки 10, Телефон 12, Прочее 0)")
    print(f"Наши: продано {len(sold)}, из них позже отменено {int(sold['cancel'].notna().sum())}, "
          f"не отменено {int(sold['cancel'].isna().sum())}")
    ok = sold[sold["cancel"].isna()].copy()
    print("\nНе отменённые: способ создания × источник первой строки")
    print(pd.crosstab(ok["first_type"], ok["first_src"], margins=True))

    # первое касание номера ДО заказа: в таблице и в Ringostat (вся история)
    first_touch = df[df["p9"] != ""].groupby("p9").head(1).set_index("p9")
    ok["table_first_src"] = ok["p9"].map(first_touch["src"])
    ok["table_first_ts"] = ok["p9"].map(first_touch["ts"])
    rfirst = ringo[ringo["category"] != "Other"].groupby("p9").head(1).set_index("p9")
    ok["ringo_first_cat"] = ok["p9"].map(rfirst["category"]).fillna("нет звонков")
    ok["ringo_first_ts"] = ok["p9"].map(rfirst["ts"])
    ok["touch_age_days"] = (ok["created"] - ok[["table_first_ts", "ringo_first_ts"]].min(axis=1)).dt.days
    print("\nПервое касание номера в Ringostat (вся история) × источник первой строки заказа:")
    print(pd.crosstab(ok["first_src"], ok["ringo_first_cat"], margins=True))
    print("\nПервое касание номера в ТАБЛИЦЕ (вся история) × источник первой строки заказа:")
    print(pd.crosstab(ok["first_src"], ok["table_first_src"], margins=True))
    ok["touch_before_order_days"] = (ok["created"] - ok["table_first_ts"]).dt.days
    print("\nВозраст первого касания таблицы до заказа (дней): ", ok["touch_before_order_days"].describe().round(1).to_dict())
    older = ok[(ok["touch_before_order_days"] > 0) & (ok["table_first_src"] != ok["first_src"])]
    print(f"Заказов, где первое касание таблицы раньше заказа и источник иной: {len(older)}")
    if args.csv:
        ok.to_csv(args.csv, encoding="utf-8-sig")
        print("Сохранено:", args.csv)


if __name__ == "__main__":
    main()
