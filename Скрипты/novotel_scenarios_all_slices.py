"""
Novotel Тест_Сайта: сценарии на бюджет N ₽/мес по ВСЕМ найденным срезам (без API, из выгрузок в Статистика/).

Рычаги (каждый = убрать сегмент с его расходом и обращениями), цена обращения по факту кампании 12.01-30.06.2026:
  1. выходные (сб+вс), из express_campaigns_daily.csv
  2. ключи без обращений и банкетные, как в novotel_scenarios.py (>=24 кликов и 0 обращений, либо банкетный класс)
  3. возраст 18-24 и 55+, из slice_age
  4. доход «прочий», из slice_income
  5. время: оставить только Пн-Пт 9:00-17:59, из Метрики (расход окна оценён по доле визитов, допущение: цена клика одна во все часы);
     пересекается с рычагом 1 (выходные уже вне окна), поэтому 1 и 5 вместе не берутся
Обращение = форма 498289834 + звонок 498298013. Срезы пересекаются, общий итог считается по допущению независимости срезов
(доли расхода и обращений перемножаются). Реальный итог ниже: возраст и доход, например, частично про одних и тех же людей.
Запас --haircut уменьшает число обращений при том же бюджете, цена обращения = бюджет / (обращений с запасом).

Запуск: PYTHONUTF8=1 python Скрипты/novotel_scenarios_all_slices.py --budget 200000 --haircut 0.25
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from novotel_keyword_structure import clean, cls  # noqa: E402

ST = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"
CID = 705894438


def leads_of(df):
    return df.Conversions_498289834_AUTO.fillna(0) + df.Conversions_498298013_AUTO.fillna(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=200000)
    ap.add_argument("--haircut", type=float, default=0.25)
    a = ap.parse_args()
    B, hc = a.budget, a.haircut

    d = pd.read_csv(ST / "express_campaigns_daily.csv")
    d = d[d.CampaignId == CID].copy()
    d["leads"] = leads_of(d)
    cost0, leads0 = d.Cost.sum(), d.leads.sum()
    we = d[pd.to_datetime(d.Date).dt.dayofweek >= 5]

    c = pd.read_csv(ST / "slice_criteria_705894438.csv")
    c["leads"] = leads_of(c)
    k = c[c.CriterionType == "KEYWORD"].copy()
    k["cls"] = k.Criterion.map(clean).map(cls)
    rem = k[((k.leads == 0) & (k.Clicks >= 24)) | (k.cls == "5 банкетный")]
    assert rem.leads.sum() == 0

    age = pd.read_csv(ST / "slice_age_705894438.csv")
    age["leads"] = leads_of(age)
    age_out = age[age.Age.isin(["AGE_18_24", "AGE_55_"])] if "AGE_55_" in set(age.Age) else age[age.Age.str.contains("18_24|55")]
    inc = pd.read_csv(ST / "slice_income_705894438.csv")
    inc["leads"] = leads_of(inc)
    inc_out = inc[inc.IncomeGrade == "OTHER"]

    h = pd.read_csv(ST / "metrika_105965383_dow_hour_705894438.csv", encoding="utf-8-sig")
    inwin = h[(~h.dow.isin(["Saturday", "Sunday"])) & (h.h.between(9, 17))]
    vis_keep, leads_keep_h = inwin.visits.sum() / h.visits.sum(), inwin.leads.sum() / h.leads.sum()

    # (название, доля расхода, которая остаётся, доля обращений, которая остаётся)
    levers = {
        "1": ("Убрать выходные (сб и вс)", 1 - we.Cost.sum() / cost0, 1 - we.leads.sum() / leads0),
        "2": ("Убрать ключи без обращений и банкетные", 1 - rem.Cost.sum() / cost0, 1.0),
        "3": ("Убрать возраст 18-24 и 55+", 1 - age_out.Cost.sum() / cost0, 1 - age_out.leads.sum() / leads0),
        "4": ("Убрать доход «прочий»", 1 - inc_out.Cost.sum() / cost0, 1 - inc_out.leads.sum() / leads0),
        "5": ("Оставить только Пн-Пт 9:00-17:59 (расход по визитам)", vis_keep, leads_keep_h),
    }

    def result(keys):
        kc = lk = 1.0
        for key in keys:
            kc *= levers[key][1]
            lk *= levers[key][2]
        cpl = cost0 * kc / (leads0 * lk)
        n = B / cpl
        return cpl, n, n * (1 - hc), B / (n * (1 - hc))

    print(f"База: {cost0:,.0f} ₽, {leads0:.0f} обращений, {cost0 / leads0:,.0f} ₽/обращ; бюджет {B:,.0f}; запас {hc * 100:.0f}%")
    for key, (name, kc, lk) in levers.items():
        print(f"  рычаг {key}: {name}; уходит {100 * (1 - kc):.1f}% расхода и {100 * (1 - lk):.1f}% обращений")
    rows = [("0. Ничего не меняем", [])]
    rows += [(f"{key}. {levers[key][0]}", [key]) for key in levers]
    rows += [
        ("Вместе 1+2", ["1", "2"]),
        ("Вместе 1+2+3", ["1", "2", "3"]),
        ("Вместе 1+2+3+4", ["1", "2", "3", "4"]),
        ("Вместе 5+2 (время вместо выходных)", ["5", "2"]),
        ("Вместе 5+2+3 (время вместо выходных)", ["5", "2", "3"]),
        ("Вместе 5+2+3+4 (время вместо выходных)", ["5", "2", "3", "4"]),
    ]
    out = []
    for name, keys in rows:
        cpl, n, n_hc, cpl_hc = result(keys)
        out.append((name, round(cpl), round(n, 1), round(n_hc, 1), round(cpl_hc)))
    df = pd.DataFrame(out, columns=["Сценарий", "₽/обращ", "Обращений на бюджет", "С запасом", "₽/обращ с запасом"])
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 90)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
