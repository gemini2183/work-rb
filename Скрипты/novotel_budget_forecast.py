"""
Novotel Moscow City: оценка объёма обращений при бюджете N ₽/мес по истории кампаний мероприятий (только чтение, без API).

Источники — Клиенты/Novotel_Moscow_City/Статистика/: express_campaigns_daily.csv (7 кампаний мероприятий янв–июн 2026),
slice_criteria_705894438.csv (условия показа Тест_Сайта). Заявка = формы + звонки по набору целей из
Аудит_мероприятий_2026-11-02.md (раздел 9); 94 обращения за период — верхняя граница (возможны дубли).

Что считает:
  1. История по месяцам: только поисковые кампании (РСЯ отдельно), цена клика, CTR, доля клик→обращение, цена обращения.
  2. Три сценария на бюджет --budget по цене обращения (как работало / без нулевых условий / лучшие условия) и тот же ряд
     с запасом --haircut (доля, на которую уменьшаем число обращений: шум выборки + дубли + оптимизм «лучших условий»).
  3. Проверка объёма: при какой цене клика бюджет упирается в имеющиеся показы (сколько показов нужно против месяцев,
     когда они были).
Текущий аукцион (ставки и цены по объёму трафика) отсюда НЕ виден: нужен KeywordBids.get/AuctionBids (токен клиента) или
«Прогноз бюджета» в интерфейсе Директа.

Запуск: PYTHONUTF8=1 python novotel_budget_forecast.py --budget 200000 --haircut 0.25
"""
import argparse
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ST = ROOT / "Клиенты" / "Novotel_Moscow_City" / "Статистика"
EVENT_IDS = [705894417, 705894429, 705894438, 705939577, 706976991, 708052907, 709510227]
RSYA_IDS = [705939577, 706976991]
FORMS = ["498289834", "495347102"]
CALLS = ["498298013", "495615844"]


def goal(df, gid):
    c = f"Conversions_{gid}_AUTO"
    return df[c].fillna(0) if c in df.columns else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=200000, help="бюджет на месяц, ₽")
    ap.add_argument("--auction-csv", default="auction_bids_2026-11-03.csv", help="файл direct_auction_bids.py в Статистика/")
    ap.add_argument("--haircut", type=float, default=0.25, help="доля, на которую уменьшаем число обращений")
    a = ap.parse_args()

    d = pd.read_csv(ST / "express_campaigns_daily.csv")
    d = d[d.CampaignId.isin(EVENT_IDS)].copy()
    d["leads"] = sum(goal(d, g) for g in FORMS + CALLS)
    d["net"] = d.CampaignId.isin(RSYA_IDS).map({True: "РСЯ", False: "Поиск"})

    def agg(g):
        t = g.agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"), imp=("Impressions", "sum"), leads=("leads", "sum"))
        t["CPC"] = (t.cost / t.clicks).round(0)
        t["CTR%"] = (t.clicks / t.imp * 100).round(2)
        t["клик→обращ%"] = (t.leads / t.clicks * 100).round(1)
        t["₽/обращ"] = (t.cost / t.leads.where(t.leads > 0)).round(0)
        t["cost"] = t.cost.round(0)
        return t

    print("== 1. История по месяцам, поиск (7 кампаний мероприятий, без РСЯ)")
    s = d[d.net == "Поиск"]
    hist = agg(s.groupby("Month"))
    print(hist.to_string())
    print("\n== то же, РСЯ")
    print(agg(d[d.net == "РСЯ"].groupby("Month")).to_string())
    tot = d.agg({"Cost": "sum", "leads": "sum", "Clicks": "sum"})
    cpl_all = tot.Cost / tot.leads
    print(f"\nИтого 7 кампаний: расход {tot.Cost:,.0f}, обращений {tot.leads:.0f} (верхняя граница), ₽/обращ {cpl_all:,.0f}; "
          f"в среднем расход {tot.Cost / d.Month.nunique():,.0f} ₽/мес")

    # шум выборки: пуассоновский 95% интервал для числа обращений
    n = tot.leads
    print(f"Шум выборки: {n:.0f} обращений → ±{1.96 / math.sqrt(n) * 100:.0f}% (95%, пуассон), до учёта дублей")

    print("\n== 2. Связь цены клика и цены обращения (Тест_Сайта по месяцам)")
    t = d[d.CampaignId == 705894438]
    ts = agg(t.groupby("Month"))
    print(ts[["cost", "clicks", "CPC", "leads", "клик→обращ%", "₽/обращ"]].to_string())
    ok = ts.dropna(subset=["₽/обращ"])
    print(f"корреляция CPC и ₽/обращ по {len(ok)} месяцам: {ok['CPC'].corr(ok['₽/обращ']):.2f}")

    halves = {"янв–мар": ["2026-01", "2026-02", "2026-03"], "апр–июн": ["2026-04", "2026-05", "2026-06"]}
    for lab, months in halves.items():
        h = s[s.Month.isin(months)]
        print(f"поиск, все кампании, {lab}: расход {h.Cost.sum():,.0f}, клики {h.Clicks.sum():.0f}, "
              f"CPC {h.Cost.sum() / h.Clicks.sum():,.0f}, обращений {h.leads.sum():.0f}, ₽/обращ {h.Cost.sum() / h.leads.sum():,.0f}")

    print("\n== 3. Резерв: условия показа без обращений (Тест_Сайта)")
    c = pd.read_csv(ST / "slice_criteria_705894438.csv")
    c["leads"] = c["Conversions_498289834_AUTO"].fillna(0) + c["Conversions_498298013_AUTO"].fillna(0)
    kw = c[c.CriterionType == "KEYWORD"]
    zero = kw[(kw.leads == 0) & (kw.Clicks >= 24)]
    total_cost, total_leads = c.Cost.sum(), c.leads.sum()
    with_leads = c[c.leads > 0]
    cpl_camp = total_cost / total_leads
    cpl_best = with_leads.Cost.sum() / total_leads
    waste = zero.Cost.sum()
    print(f"расход {total_cost:,.0f}, обращений {total_leads:.0f}, ₽/обращ {cpl_camp:,.0f}")
    print(f"ключей без обращений при ≥24 кликов: {len(zero)}, клики {zero.Clicks.sum():.0f}, расход {waste:,.0f} "
          f"({waste / total_cost * 100:.1f}%)")
    print(f"условий с обращениями: {len(with_leads)}, расход на них {with_leads.Cost.sum():,.0f}; "
          f"их расход / все обращения = {cpl_best:,.0f} ₽ (занижена выбором)")
    add_lo, add_hi = waste / cpl_camp, waste / cpl_best
    cpl_lo = total_cost / (total_leads + add_lo)
    cpl_hi = total_cost / (total_leads + add_hi)
    print(f"перенос расхода: +{add_lo:.0f}…+{add_hi:.0f} обращений → ₽/обращ {cpl_lo:,.0f}…{cpl_hi:,.0f}")
    r_lo, r_hi = cpl_lo / cpl_camp, cpl_hi / cpl_camp

    print(f"\n== 4. Сценарии на {a.budget:,.0f} ₽/мес; запас {a.haircut * 100:.0f}% на число обращений")
    rows = []
    for name, cpl in [("как работало (все 7 кампаний, весь период)", cpl_all),
                      ("без нулевых условий", cpl_all * r_lo),
                      ("лучшие условия (верх)", cpl_all * r_hi)]:
        leads = a.budget / cpl
        rows.append((name, round(cpl), round(leads, 1), round(leads * (1 - a.haircut), 1),
                     round(a.budget / (leads * (1 - a.haircut)))))
    print(pd.DataFrame(rows, columns=["сценарий", "₽/обращ", "обращений", "с запасом", "₽/обращ с запасом"]).to_string(index=False))

    print("\n== 5. Проверка объёма: цена клика → клики → нужные показы (поиск)")
    ctr = s.Clicks.sum() / s.Impressions.sum()
    cr = t.leads.sum() / t.Clicks.sum()
    monthly_imp = s.groupby("Month").Impressions.sum()
    print(f"CTR поиска за период {ctr * 100:.2f}%, клик→обращение Тест_Сайта {cr * 100:.1f}%")
    print("показы поиска по месяцам:", {k: int(v) for k, v in monthly_imp.items()})
    rows = []
    for cpc in (200, 300, 500, 750, 1000):
        cl = a.budget / cpc
        need = cl / ctr
        rows.append((cpc, round(cl), round(need), round(need / monthly_imp.max() * 100), round(cl * cr, 1),
                     round(cl * cr * (1 - a.haircut), 1)))
    print(pd.DataFrame(rows, columns=["CPC", "клики", "нужно показов", "% от лучшего месяца", "обращений", "с запасом"]).to_string(index=False))
    auction_section(a, s, t)


def auction_section(a, s, t):
    """Сценарий по таблице аукциона (direct_auction_bids.py): цена клика на ключах Тест_Сайта, взвешенная историческими кликами."""
    f = ST / a.auction_csv
    if not f.exists():
        return
    au = pd.read_csv(f)
    c = pd.read_csv(ST / "slice_criteria_705894438.csv")
    c = c[(c.CriterionType == "KEYWORD") & (c.Clicks > 0)][["CriterionId", "Clicks", "Cost"]]
    m = c.merge(au[au.CampaignId == 705894438], left_on="CriterionId", right_on="KeywordId")
    base = m.drop_duplicates("KeywordId")
    ctr = s.Clicks.sum() / s.Impressions.sum()
    jan_clicks = s[s.Month == "2026-01"].Clicks.sum()
    cr_lo = t[t.Month.isin(["2026-01", "2026-02", "2026-03"])].leads.sum() / t[t.Month.isin(["2026-01", "2026-02", "2026-03"])].Clicks.sum()
    cr_all = t.leads.sum() / t.Clicks.sum()
    print(f"\n== 6. Сценарий по таблице аукциона {f.name} (ключи Тест_Сайта с кликами в истории: {base.KeywordId.nunique()}, "
          f"факт цена клика на них {base.Cost.sum() / base.Clicks.sum():,.0f} ₽)")
    print("Объём трафика — шкала из KeywordBids (смысл значений >100 в документации не описан); цена — списываемая, на сегодня.")
    rows = []
    for tv in (80, 100, 120, 139):
        x = m[m.TrafficVolume == tv]
        w = x.Clicks.sum()
        bid = (x.Bid * x.Clicks).sum() / w
        price = (x.Price * x.Clicks).sum() / w
        for lab, p in (("по таблице", price), ("цена ×2 (проверка)", price * 2)):
            cl = a.budget / p
            rows.append((tv, lab, round(bid), round(p), round(cl), round(cl / ctr / s.groupby("Month").Impressions.sum().max() * 100),
                         round(cl * cr_lo * (1 - a.haircut), 1), round(cl * cr_all * (1 - a.haircut), 1)))
    print(pd.DataFrame(rows, columns=["объём", "вариант", "ставка", "CPC", "клики на бюджет", "% показов лучш.мес",
                                      f"обращ. CR {cr_lo * 100:.1f}%", f"обращ. CR {cr_all * 100:.1f}%"]).to_string(index=False))
    print(f"(обращения уже с запасом {a.haircut * 100:.0f}%; январь 2026: {jan_clicks:.0f} кликов на поиске — ориентир потолка спроса)")


if __name__ == "__main__":
    main()
