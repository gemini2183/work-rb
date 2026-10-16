#!/usr/bin/env python
# coding: utf-8
"""Решение по группам объявлений Search-кампании одним правилом — ТОЛЬКО ЧТЕНИЕ, ничего не пишет в кабинет.

Зачем: не решать «по ощущению». Каждая группа оценивается одинаково: по небрендовым запросам (search_term_view, бренд
отсечён регуляркой), заявки = форма + звонок из объявления + GA4 Ringostat_calls, байесовская оценка коэффициента
конверсии с общим априорным по кампании, вероятность того, что цена заявки группы ≤ цели T. Два окна: всё окно и свежие
14 дней (чтобы отличить устойчивое от разового, см. База_знаний/Паттерны/Google-Ads-Search-байесовский-анализ-срезов-и-рычагов.md).

Правило (параметры в аргументах):
  кликов в окне < --min-clicks                       → МАЛО ДАННЫХ: оставить, tCPA = T, стоп-лосс (пауза, если расход ≥ 3×T без заявок)
  p_все ≥ 0.30                                       → ОСТАВИТЬ, tCPA = T
  p_все < 0.10 И p_свежие < 0.20                     → ПАУЗА (оба окна плохие)
  иначе                                              → НАБЛЮДЕНИЕ: tCPA = T, стоп-лосс как выше
  p — вероятность, что цена заявки группы ≤ T; цена заявки = цена клика / коэффициент конверсии.

Использование:
    python gads_group_decision.py --customer-id 7552781705 --client-folder ProfiMet --campaign-id 19158580966 \
        --since 2026-09-15 --until 2026-10-15 --target-cpl 18
"""
import argparse
import re
import sys
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from scipy.stats import beta

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

LEAD_ACTIONS = ("form_submit_gtm", "Звонки по объявлениям")


def is_lead(action):
    return action in LEAD_ACTIONS or action.endswith("Ringostat_calls")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--target-cpl", type=float, default=18.0, help="целевая цена заявки T, €")
    ap.add_argument("--brand-regex", default=r"profi|mocna ?szklarnia|mocnaszklarnia|mocne szklarnie|profimed|profinamiot")
    ap.add_argument("--recent-days", type=int, default=14)
    ap.add_argument("--prior-clicks", type=float, default=150.0, help="вес априорного, в кликах")
    ap.add_argument("--min-clicks", type=int, default=20)
    ap.add_argument("--tcpa-floor", type=float, default=0.55, help="нижняя граница предлагаемого tCPA, доля от T")
    ap.add_argument("--tcpa-cap", type=float, default=1.25, help="верхняя граница предлагаемого tCPA, доля от T")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    brand = re.compile(a.brand_regex, re.I)
    cut = (date.fromisoformat(a.until) - timedelta(days=a.recent_days - 1)).isoformat()

    rows = []
    for r in ga.search(customer_id=cid, query=f"""SELECT ad_group.id, ad_group.name, search_term_view.search_term,
            segments.date, metrics.cost_micros, metrics.clicks FROM search_term_view
            WHERE campaign.id = {a.campaign_id} AND segments.date BETWEEN '{a.since}' AND '{a.until}'"""):
        rows.append(dict(id=r.ad_group.id, g=r.ad_group.name, t=r.search_term_view.search_term, d=r.segments.date,
                         cost=r.metrics.cost_micros / 1e6, clk=r.metrics.clicks, leads=0.0))
    cv = {}
    for r in ga.search(customer_id=cid, query=f"""SELECT ad_group.id, search_term_view.search_term, segments.date,
            segments.conversion_action_name, metrics.all_conversions FROM search_term_view
            WHERE campaign.id = {a.campaign_id} AND segments.date BETWEEN '{a.since}' AND '{a.until}'
            AND metrics.all_conversions > 0"""):
        if is_lead(r.segments.conversion_action_name):
            k = (r.ad_group.id, r.search_term_view.search_term, r.segments.date)
            cv[k] = cv.get(k, 0) + r.metrics.all_conversions
    d = pd.DataFrame(rows)
    d["leads"] = [cv.get((i, t, dd), 0.0) for i, t, dd in zip(d.id, d.t, d.d)]
    brand_mask = d.t.map(lambda s: bool(brand.search(s)))
    nb = d[~brand_mask].copy()
    print(f"Кампания {a.campaign_id}, окно {a.since}..{a.until}, свежие {cut}..{a.until}, T = {a.target_cpl:g} €.")
    print(f"Бренд исключён регуляркой: {brand_mask.sum()} строк, {d[brand_mask].cost.sum():.0f} € из {d.cost.sum():.0f} €.")
    print("Оценка по запросам, видимым в search_term_view (≈ 70% расхода; скрытые запросы редких формулировок не входят).")

    clk_all, lead_all = nb.clk.sum(), nb.leads.sum()
    p0 = max(lead_all, 0.5) / max(clk_all, 1)
    a0, b0 = p0 * a.prior_clicks, (1 - p0) * a.prior_clicks
    print(f"Небрендовый коэффициент конверсии кампании: {100 * p0:.2f}% ({lead_all:.1f} заявок / {clk_all} кликов); "
          f"цена заявки кампании ≈ {nb.cost.sum() / max(lead_all, 0.5):.0f} €")

    def prob(clicks, leads, cpc):
        if clicks <= 0 or cpc <= 0:
            return None
        need = cpc / a.target_cpl          # нужный коэффициент конверсии, чтобы цена заявки ≤ T
        return float(beta.sf(need, a0 + leads, b0 + clicks - leads))

    out = []
    for (gid, name), g in nb.groupby(["id", "g"]):
        gr = g[g.d >= cut]
        c_all, l_all, cost_all = int(g.clk.sum()), g.leads.sum(), g.cost.sum()
        c_r, l_r, cost_r = int(gr.clk.sum()), gr.leads.sum(), gr.cost.sum()
        cpc_all = cost_all / c_all if c_all else 0
        cpc_r = cost_r / c_r if c_r else cpc_all
        p_all, p_r = prob(c_all, l_all, cpc_all), prob(c_r, l_r, cpc_r)
        if c_all < a.min_clicks:
            dec = "МАЛО ДАННЫХ: оставить, tCPA=T, стоп-лосс"
        elif p_all is not None and p_all >= 0.30:
            dec = "ОСТАВИТЬ, tCPA=T"
        elif p_all is not None and p_all < 0.10 and (p_r is None or p_r < 0.20):
            dec = "ПАУЗА"
        else:
            dec = "НАБЛЮДЕНИЕ: tCPA=T, стоп-лосс"
        # предлагаемый tCPA группы: T·T/факт, факт = худшая из цен заявки (весь период / свежие дни), с зажимом
        price_all = cost_all / l_all if l_all > 0 else None
        price_r = cost_r / l_r if l_r > 0 else None
        known = [x for x in (price_all, price_r) if x is not None]
        eff = max(known) if known else None
        floor_v, cap_v = a.tcpa_floor * a.target_cpl, a.tcpa_cap * a.target_cpl
        tcpa = floor_v if eff is None else min(cap_v, max(floor_v, a.target_cpl * a.target_cpl / eff))
        trend = "" if (price_all is None or price_r is None) else ("хуже" if price_r > price_all * 1.15 else
                                                                 "лучше" if price_r < price_all * 0.85 else "ровно")
        out.append(dict(группа=name, расход=round(cost_all), клики=c_all, заявки=round(l_all, 1),
                        цена_клика=round(cpc_all, 2), цена_заявки=round(cost_all / l_all) if l_all else None,
                        цена_свежие=round(price_r) if price_r else None, тенденция=trend,
                        tCPA_предлагаемый=round(tcpa, 1),
                        p_все=None if p_all is None else round(p_all, 2),
                        кликов_свежие=c_r, заявок_свежие=round(l_r, 1),
                        p_свежие=None if p_r is None else round(p_r, 2), решение=dec))
    res = pd.DataFrame(out).sort_values("расход", ascending=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print()
    print(res.to_string(index=False))
    path = client_stats_dir(a.client_folder) / f"gads_group_decision_{a.campaign_id}_{a.until}.csv"
    res.to_csv(path, index=False, encoding="utf-8-sig")
    print("\nФайл:", path)
    print(f"Стоп-лосс для «наблюдения» и «мало данных»: пауза группы, если после включения расход ≥ {3 * a.target_cpl:g} € без заявок.")


if __name__ == "__main__":
    main()
