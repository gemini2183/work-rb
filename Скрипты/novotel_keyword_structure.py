"""
Novotel: структура ключей кампании по широте/специфичности и результат каждого класса (только чтение, без API).

Источник — Клиенты/Novotel_Moscow_City/Статистика/slice_criteria_<id>.csv (direct_campaign_slices.py). Заявка = формы 498289834 +
звонки 498298013 (счётчик 105965383). Фраза очищается от минус-слов (слова с «-»). Классы (приоритет сверху вниз):
  1 отель/бренд/сити (отел|гостини|новотел|сити)  2 конференц/переговорные/семинары/тренинг/бизнес/корпоратив
  3 общие (зал/помещение для мероприятий)         4 с числом человек                5 банкетный
Классификация по подстрокам — грубая, примеры по классам печатаются для проверки глазами.
Запуск: PYTHONUTF8=1 python novotel_keyword_structure.py --campaign-id 705894438
"""
import argparse
import re
from pathlib import Path

import pandas as pd

ST = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"


def clean(s):
    return " ".join(w for w in str(s).replace('"', "").split() if not w.startswith("-"))


def cls(p):
    p = p.lower()
    if re.search(r"отел|гостини|новотел|novotel|сити|accor", p):
        return "1 отель/бренд/сити"
    if re.search(r"банкет", p):
        return "5 банкетный"
    if re.search(r"конференц|переговор|семинар|тренинг|совещ|бизнес|корпоратив", p):
        return "2 конференц/переговорные/семинары"
    if re.search(r"\d+\s*(чел|человек|персон)|на \d+", p):
        return "4 с числом человек"
    return "3 общие (зал/помещение для мероприятий)"


def summ(g, total_cost):
    t = g.agg(ключей=("CriterionId", "nunique"), клики=("Clicks", "sum"), расход=("Cost", "sum"), обращ=("leads", "sum"))
    t["доля расхода%"] = (t.расход / total_cost * 100).round(1)
    t["CPC"] = (t.расход / t.клики).round(0)
    t["₽/обращ"] = (t.расход / t.обращ.where(t.обращ > 0)).round(0)
    t["расход"] = t.расход.round(0)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", default="705894438")
    a = ap.parse_args()
    c = pd.read_csv(ST / f"slice_criteria_{a.campaign_id}.csv")
    c["leads"] = c.Conversions_498289834_AUTO.fillna(0) + c.Conversions_498298013_AUTO.fillna(0)
    total = c.Cost.sum()
    k = c[c.CriterionType == "KEYWORD"].copy()
    k["phrase"] = k.Criterion.map(clean)
    k["cls"] = k.phrase.map(cls)
    k["words"] = k.phrase.str.split().str.len().clip(upper=5)
    print(f"Кампания {a.campaign_id}: расход {total:,.0f}, обращений {c.leads.sum():.0f}, ₽/обращ {total / c.leads.sum():,.0f}")
    print("\n== по классам ключей"); print(summ(k.groupby("cls"), total).to_string())
    au = c[c.CriterionType == "AUTOTARGETING"]
    print(f"автотаргетинг: условий {len(au)}, расход {au.Cost.sum():,.0f} ({au.Cost.sum() / total * 100:.1f}%), "
          f"клики {au.Clicks.sum():.0f}, обращений {au.leads.sum():.0f}, ₽/обращ {au.Cost.sum() / max(au.leads.sum(), 1):,.0f}")
    print("\n== по числу слов во фразе (5 = 5 и больше)"); print(summ(k.groupby("words"), total).to_string())
    c["theme"] = c.AdGroupName.str.replace(r"_(Москва|Регионы)$", "", regex=True)
    th = c.groupby("theme").agg(клики=("Clicks", "sum"), расход=("Cost", "sum"), обращ=("leads", "sum"))
    th["₽/обращ"] = (th.расход / th.обращ.where(th.обращ > 0)).round(0)
    print("\n== темы групп (топ-12 по расходу)"); print(th.sort_values("расход", ascending=False).head(12).round(0).to_string())
    print("\n== примеры (топ-4 по расходу в классе)")
    for name, g in k.groupby("cls"):
        print(name); print(g.sort_values("Cost", ascending=False).head(4)[["phrase", "Clicks", "Cost", "leads"]].round(0).to_string(index=False))


if __name__ == "__main__":
    main()
