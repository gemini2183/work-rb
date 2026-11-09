"""ProfiMet: продажи периода, у которых заказ оформлен РАНЬШЕ периода («перетёкшие» продажи). Только чтение.

Зачем: дашборд клиента относит заказ к периоду по «Дате заказа» (колонка выгрузки CRM, проверено 09.11.2026 на списке клиента за 01–08.11).
Заказ, созданный в октябре и проданный в ноябре, у клиента остаётся октябрьским и в ноябрьскую цену продажи не попадает, хотя расход ноября
работал в том числе на него. Скрипт находит такие продажи по выгрузке CRM, чтобы предъявить клиенту / учесть в оценке месяца.

Что считается: заказы по схеме клиента (`profimet_sources_dashboard.client_scheme_orders`: есть форма или первое обращение за 60 дн не «Телефон»/SEO,
не отменён), у которых дата продажи в [--from, --to], а дата заказа раньше --from. Источник — по правилу клиента (форма → её источник, иначе «Телефон»)
и по первому обращению номера за 60 дней (наше правило). Количество штук в выгрузке CRM нет: считаем по 1 на заказ (у клиента 2 штуки = 2 продажи).

Запуск: python profimet_sales_from_earlier_orders.py --from 2026-11-01 --to 2026-11-08
Результат: таблица в консоли и Клиенты/ProfiMet/Статистика/sales_from_earlier_orders_<от>_<до>.csv (телефоны не пишем).
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import profimet_sources_dashboard as d  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default=date.today().replace(day=1).isoformat())
    ap.add_argument("--to", dest="to", default=(date.today() - timedelta(days=1)).isoformat())
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    f, t = pd.Timestamp(a.frm).date(), pd.Timestamp(a.to).date()

    sheet = d.load_sheet(d.SHEET_ID)
    sel, _ = d.client_scheme_orders(sheet, None, None, None)  # все заказы схемы клиента, без фильтра по периоду
    sel = sel.copy()
    sel["sale_day"] = pd.to_datetime(sel["sale"]).dt.date
    sel["order_day"] = sel["est"].dt.date
    x = sel[(sel["sale_day"] >= f) & (sel["sale_day"] <= t) & (sel["order_day"] < f)].sort_values("sale_day")
    out = pd.DataFrame({
        "Заказ": x["key"], "Дата заказа": x["order_day"], "Дата продажи": x["sale_day"],
        "Дней от заказа до продажи": [(s - o).days for s, o in zip(x["sale_day"], x["order_day"])],
        "Источник по схеме клиента": x["rule"], "Первое обращение за 60 дней (наше правило)": x["first60"].replace("", "нет в выгрузке CRM"),
        "Рекламное касание": ["да" if v else "нет" for v in x["ad_touch"]], "Повторная покупка": ["да" if v else "нет" for v in x["repeat"]],
        "Месяц, в который заказ засчитан у клиента": [o.strftime("%Y-%m") for o in x["order_day"]],
    })
    out_dir = d.client_stats_dir("ProfiMet")
    path = out_dir / f"sales_from_earlier_orders_{a.frm}_{a.to}.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")

    all_sales = sel[(sel["sale_day"] >= f) & (sel["sale_day"] <= t)]
    print(f"Период продаж {a.frm} — {a.to}: продаж по схеме клиента {len(all_sales)} (штук по 1 на заказ), из них заказ оформлен раньше периода: {len(out)}")
    if len(out):
        print(out.to_string(index=False))
        print("\nПо источнику схемы клиента:", out["Источник по схеме клиента"].value_counts().to_dict())
        print("С рекламным касанием:", int((out["Рекламное касание"] == "да").sum()), "из", len(out))
    print(f"\nФайл: {path}")


if __name__ == "__main__":
    main()
