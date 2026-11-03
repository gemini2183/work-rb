"""Novotel: микроцель «90 секунд» против заявок по условиям показа кампании (только чтение CSV).

Берёт срез по условиям показа (`direct_campaign_slices.py` -> slice_criteria_<ID>.csv) и считает:
сколько конверсий микроцели и заявок, доля микроцели, на каких условиях микроцель срабатывала без единой заявки
(их расход и доля расхода), частота микроцели на клик там, где заявки есть и где их нет, корреляция по условиям.
Заявка = форма 498289834 + звонок 498298013; микроцель = 498184341.

Запуск: PYTHONUTF8=1 python Скрипты/novotel_micro_goal_check.py [--campaign-id 705894438]
"""
import argparse
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"


def num(x):
    return float(x) if x else 0.0


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return cov / math.sqrt(va * vb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", default="705894438")
    args = ap.parse_args()
    path = ROOT / f"slice_criteria_{args.campaign_id}.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    micro = [num(r["Conversions_498184341_AUTO"]) for r in rows]
    leads = [num(r["Conversions_498289834_AUTO"]) + num(r["Conversions_498298013_AUTO"]) for r in rows]
    clicks = [num(r["Clicks"]) for r in rows]
    cost = [num(r["Cost"]) for r in rows]
    total_cost = sum(cost)

    print(f"Условий показа с расходом: {len(rows)}; расход {total_cost:,.0f} ₽; клики {sum(clicks):.0f}")
    print(f"Микроцель «90 секунд»: {sum(micro):.0f}; заявок (форма + звонок): {sum(leads):.0f}")

    only_micro = [i for i in range(len(rows)) if micro[i] > 0 and leads[i] == 0]
    print(f"Условий, где микроцель была, а заявок не было: {len(only_micro)}; "
          f"микроцелей {sum(micro[i] for i in only_micro):.0f}; "
          f"расход {sum(cost[i] for i in only_micro):,.0f} ₽ ({sum(cost[i] for i in only_micro) / total_cost * 100:.1f}%)")

    with_leads = [i for i in range(len(rows)) if leads[i] > 0]
    no_leads = [i for i in range(len(rows)) if leads[i] == 0]
    print(f"Микроцелей на клик там, где заявки есть: {sum(micro[i] for i in with_leads) / sum(clicks[i] for i in with_leads):.3f}; "
          f"где заявок нет: {sum(micro[i] for i in no_leads) / sum(clicks[i] for i in no_leads):.3f}")
    print(f"Корреляция микроцель/заявки по условиям: {corr(micro, leads):.2f} "
          f"(на объём кликов она частично опирается, это не доказательство связи)")


if __name__ == "__main__":
    main()
