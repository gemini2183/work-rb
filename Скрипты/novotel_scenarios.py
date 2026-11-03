"""
Novotel Тест_Сайта: сценарии «что изменить» на бюджет N ₽/мес по фактической цене обращения сегментов (без API, из выгрузок).

Цена обращения берётся из ФАКТА кампании (срезы Директа 12.01–30.06.2026), а не из прогноза Директа: цены прогноза в разы ниже факта.
Прогноз Директа (forecast_v4_*.json) используется только как потолок объёма: хватит ли трафика в сегменте на предлагаемые деньги.
Обращение = форма 498289834 + звонок 498298013. Эффекты сценариев независимо считаются от базы; общий итог — приближение (допущение
о независимости срезов). Запас --haircut применяется к числу обращений.

Запуск: PYTHONUTF8=1 python novotel_scenarios.py --budget 200000 --haircut 0.25
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from novotel_keyword_structure import clean, cls  # noqa: E402

ST = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"
CID = 705894438


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=200000)
    ap.add_argument("--haircut", type=float, default=0.25)
    ap.add_argument("--shift-share", type=float, default=0.30, help="доля бюджета общих ключей, переносимая в узкие")
    ap.add_argument("--below-share", type=float, default=0.25, help="целевая доля бюджета на показы ниже блока")
    a = ap.parse_args()
    B, hc = a.budget, a.haircut

    d = pd.read_csv(ST / "express_campaigns_daily.csv")
    d = d[d.CampaignId == CID].copy()
    d["leads"] = d.Conversions_498289834_AUTO.fillna(0) + d.Conversions_498298013_AUTO.fillna(0)
    d["we"] = pd.to_datetime(d.Date).dt.dayofweek >= 5
    cost0, leads0 = d.Cost.sum(), d.leads.sum()
    cpl0 = cost0 / leads0
    wk, we = d[~d.we], d[d.we]

    c = pd.read_csv(ST / "slice_criteria_705894438.csv")
    c["leads"] = c.Conversions_498289834_AUTO.fillna(0) + c.Conversions_498298013_AUTO.fillna(0)
    k = c[c.CriterionType == "KEYWORD"].copy()
    k["cls"] = k.Criterion.map(clean).map(cls)
    zero = (k.leads == 0) & (k.Clicks >= 24)
    ban = k.cls == "5 банкетный"
    removed = k[zero | ban]
    R = removed.Cost.sum()
    assert removed.leads.sum() == 0

    print(f"База: Тест_Сайта {cost0:,.0f} ₽, {leads0:.0f} обращений, {cpl0:,.0f} ₽/обращ; бюджет {B:,.0f}; запас {hc * 100:.0f}%")
    rows = []
    l0 = B / cpl0
    rows.append(("0. Как было (цена обращения кампании)", cpl0, l0))

    # 1. выходные
    cpl_wk = wk.Cost.sum() / wk.leads.sum()
    rows.append((f"1. Без выходных (сб+вс: {we.Cost.sum():,.0f} ₽ = {we.Cost.sum() / cost0 * 100:.1f}% расхода, {we.leads.sum():.0f} обращ.)", cpl_wk, B / cpl_wk))

    # 2. нулевые ключи и банкетные
    cpl_clean = (cost0 - R) / leads0
    rows.append((f"2. Без нулевых и банкетных ключей ({len(removed)} ключей, {R:,.0f} ₽ = {R / cost0 * 100:.1f}%)", cpl_clean, B / cpl_clean))

    # 3. общие -> узкие
    g = k.groupby("cls").agg(cost=("Cost", "sum"), leads=("leads", "sum"), clicks=("Clicks", "sum"))
    broad = g.loc["3 общие (зал/помещение для мероприятий)"]
    narrow = g.loc[["1 отель/бренд/сити", "2 конференц/переговорные/семинары"]].sum()
    cpl_b, cpl_n = broad.cost / broad.leads, narrow.cost / narrow.leads
    moved = B * (broad.cost / cost0) * a.shift_share
    gain3 = moved / cpl_n - moved / cpl_b
    n_cpc = narrow.cost / narrow.clicks
    need_clicks = (B * (narrow.cost / cost0) + moved) / n_cpc
    cap = json.load(open(ST / f"forecast_v4_{CID}_2026-11-03.json", encoding="utf-8"))
    pf = pd.DataFrame(cap["Phrases"])
    pf["cls"] = pf.Phrase.map(clean).map(cls)
    cap_narrow = pf[pf.cls.isin(["1 отель/бренд/сити", "2 конференц/переговорные/семинары"])].PremiumClicks.sum()
    rows.append((f"3. {a.shift_share * 100:.0f}% бюджета общих → узкие (перенос {moved:,.0f} ₽; ₽/обращ общие {cpl_b:,.0f}, узкие {cpl_n:,.0f}); "
                 f"нужно кликов {need_clicks:.0f}/мес при потолке прогноза {cap_narrow}", None, l0 + gain3))

    # 4. ниже блока
    slot = pd.read_csv(ST / "slice_slot_705894438.csv")
    slot["leads"] = slot.Conversions_498289834_AUTO.fillna(0) + slot.Conversions_498298013_AUTO.fillna(0)
    low, prem = slot[slot.Slot == "OTHER"].iloc[0], slot[slot.Slot == "PREMIUMBLOCK"].iloc[0]
    cpl_low, cpl_prem = low.Cost / low.leads, prem.Cost / prem.leads
    cur_share = low.Cost / slot.Cost.sum()
    moved4 = B * max(a.below_share - cur_share, 0)
    gain4 = moved4 / cpl_low - moved4 / cpl_prem
    cpc_low = low.Cost / low.Clicks
    need4 = B * a.below_share / cpc_low
    cap_low = cap["Common"]["FirstPlaceClicks"] + cap["Common"]["Clicks"]
    rows.append((f"4. Ниже блока с {cur_share * 100:.0f}% до {a.below_share * 100:.0f}% бюджета (перенос {moved4:,.0f} ₽; ₽/обращ ниже блока {cpl_low:,.0f}, "
                 f"спец {cpl_prem:,.0f}); нужно кликов {need4:.0f}/мес при потолке прогноза {cap_low}", None, l0 + gain4))

    # итог 1+2 вместе (независимость), +3, +4 прибавками
    cost_after = (cost0 - R) * (1 - we.Cost.sum() / cost0)
    leads_after = leads0 - we.leads.sum()
    cpl12 = cost_after / leads_after
    l12 = B / cpl12
    total = l12 + gain3 + gain4
    rows.append(("1+2 вместе (срезы независимы — допущение)", cpl12, l12))
    rows.append(("1+2+3+4 вместе", B / total, total))

    out = pd.DataFrame(rows, columns=["Сценарий", "₽/обращ", "Обращений на бюджет"])
    out["Прирост к базе"] = (out["Обращений на бюджет"] - l0).round(1)
    out[f"С запасом {hc * 100:.0f}%"] = (out["Обращений на бюджет"] * (1 - hc)).round(1)
    out["₽/обращ"] = out["₽/обращ"].round(0)
    out["Обращений на бюджет"] = out["Обращений на бюджет"].round(1)
    pd.set_option("display.width", 300)
    pd.set_option("display.max_colwidth", 170)
    print(out.to_string(index=False))
    print(f"\nОбъём трафика ниже блока по прогнозу Директа (100 ключей, Москва и область): {cap_low} кликов/мес "
          f"(первое место нижнего блока {cap['Common']['FirstPlaceClicks']} + остальные {cap['Common']['Clicks']}) против {cap['Common']['PremiumClicks']} в спецразмещении; "
          f"факт Тест_Сайта: {low.Clicks:.0f} кликов за период ({low.Clicks / low.Clicks.sum() if False else low.Clicks / slot.Clicks.sum() * 100:.0f}% всех кликов), цена клика {cpc_low:,.0f} ₽ против {prem.Cost / prem.Clicks:,.0f} ₽ в спецразмещении")


if __name__ == "__main__":
    main()
