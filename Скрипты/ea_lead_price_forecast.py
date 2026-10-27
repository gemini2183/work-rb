#!/usr/bin/env python
# coding: utf-8
"""EkspertAgro: цена заявки по кампаниям и прогноз освоения бюджета — ТОЛЬКО ЧТЕНИЕ (Google Ads API + выгрузка CRM клиента).

Заявка (лид) — уникальный номер, ПЕРВОЕ касание которого за всю историю выгрузки — Google Ads (звонок или форма); кампания лида —
по `utm_campaign` первой строки номера (как в `ea_lead_to_sale_trend.py`). Общая метка PMax «Google CPC General - pm» к кампании
не привязывается и печатается отдельной строкой (расход у неё всегда 0, поэтому цена заявки по ней не считается).
Считает только будни пн–пт (окно показа 08–18, суббота и воскресенье не включены).

Печатает:
  1) по кампаниям за два окна (--split — граница, по умолчанию 2026-10-14, перестройка аккаунта): расход, лиды, цена заявки €,
     продажи лидов (не созрели в последних неделях);
  2) по будням последних --days дней: расход и лиды ВСЕХ кампаний и только включённых сейчас + скользящая цена за 5 будней;
  3) прогноз до конца месяца: средний расход в будни включённых кампаний за --avg-days последних будней, сколько будней
     осталось, ожидаемый расход и заявки против плана месяца (--plan-budget, --plan-leads), недобор.
Ограничения: лиды последних дней появляются в выгрузке CRM с лагом (последняя строка выводится); у кампании мало лидов — цена
заявки шумит; прогноз линейный (средний будний день), без учёта сезона и ручных правок.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python ea_lead_price_forecast.py [--customer-id 8826134558] [--split 2026-10-14] [--days 20] [--avg-days 7]
                                     [--plan-budget 10800] [--plan-leads 98] [--rate 4.3691] [--month-end 2026-10-31]
"""
import argparse

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from ea_sales_by_campaign import GOOGLE_ADS_YAML, SHEET_ID, resolve
from ea_sales_orders_check import load as load_sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", default="8826134558")
    ap.add_argument("--worksheet", default="Ekspertagro.pl")
    ap.add_argument("--split", default="2026-10-14")
    ap.add_argument("--from", dest="date_from", default="2026-09-01")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--avg-days", type=int, default=7, help="сколько последних законченных будней брать в средний расход")
    ap.add_argument("--plan-budget", type=float, default=10800.0)
    ap.add_argument("--plan-leads", type=float, default=98.0)
    ap.add_argument("--rate", type=float, default=4.3691, help="zł за 1 EUR")
    ap.add_argument("--month-end", default="2026-10-31")
    a = ap.parse_args()
    eur = lambda zl: zl / a.rate  # noqa: E731
    today = pd.Timestamp.now().normalize()

    ga = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).get_service("GoogleAdsService")
    names, status = {}, {}
    for b in ga.search_stream(customer_id=a.customer_id, query="SELECT campaign.id, campaign.name, campaign.status FROM campaign"):
        for r in b.results:
            names[str(r.campaign.id)] = r.campaign.name
            status[r.campaign.name] = {2: "ENABLED", 3: "PAUSED", 4: "REMOVED"}.get(int(r.campaign.status), "?")
    by_name = {n.strip().lower().rstrip("_"): n for n in names.values()}
    q = (f"SELECT segments.date, campaign.name, metrics.cost_micros FROM campaign "
         f"WHERE segments.date >= '{a.date_from}' AND segments.date <= '{today:%Y-%m-%d}'")
    S = pd.DataFrame([(pd.Timestamp(r.segments.date), r.campaign.name, r.metrics.cost_micros / 1e6)
                      for b in ga.search_stream(customer_id=a.customer_id, query=q) for r in b.results],
                     columns=["date", "camp", "cost"])
    S = S[S["cost"] > 0]

    df = load_sheet(SHEET_ID, a.worksheet)
    df["ph"] = df["phone"].astype(str).str.replace(r"\D", "", regex=True).str[-9:]
    df = df[(df["ph"].str.len() == 9) & df["ts"].notna()].sort_values("ts")
    df["net"] = df["sale_date_dt"].notna() & df["cancel_date_dt"].isna()
    first = df.groupby("ph").first()
    L = first[["ts", "src", "utm_campaign"]].copy()
    L["sale"] = df.groupby("ph")["net"].any()
    L["camp"] = [resolve(u, names, by_name) if s == "Google Ads" else "" for u, s in zip(L["utm_campaign"], L["src"])]
    G = L[(L["src"] == "Google Ads") & (L["ts"] >= pd.Timestamp(a.date_from, tz="UTC"))].copy()
    G["date"] = G["ts"].dt.tz_localize(None).dt.normalize()
    last_row = df["ts"].max()
    print(f"Выгрузка CRM: последняя строка {last_row:%Y-%m-%d %H:%M}; лидов Google с {a.date_from}: {len(G)}; "
          f"курс {a.rate} zł/€; только будни пн–пт")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 300)

    wd = lambda X: X[X["date"].dt.dayofweek < 5]  # noqa: E731
    S_all, G_all = S, G
    S, G = wd(S), wd(G)
    split = pd.Timestamp(a.split)

    def block(sp, ld, title):
        t = pd.DataFrame({"расход_zl": sp.groupby("camp")["cost"].sum(), "лиды": ld.groupby("camp").size(),
                          "продажи": ld.groupby("camp")["sale"].sum()}).fillna(0)
        t["цена_заявки_EUR"] = (eur(t["расход_zl"]) / t["лиды"]).replace(float("inf"), float("nan")).round(1)
        t["расход_zl"] = t["расход_zl"].round(0)
        t["статус"] = [status.get(c, "") for c in t.index]
        tot = pd.DataFrame({"расход_zl": [round(sp["cost"].sum())], "лиды": [len(ld)], "продажи": [ld["sale"].sum()]},
                           index=["ВСЕГО"])
        tot["цена_заявки_EUR"] = round(eur(sp["cost"].sum()) / max(len(ld), 1), 1)
        print(f"\n=== {title} ===")
        print(pd.concat([t.sort_values("расход_zl", ascending=False), tot]).to_string())

    block(S[S["date"] < split], G[G["date"] < split], f"1. Будни {a.date_from} .. {(split - pd.Timedelta(days=1)):%Y-%m-%d}")
    block(S[S["date"] >= split], G[G["date"] >= split], f"1. Будни {a.split} .. сегодня (после перестройки)")

    on = [c for c, s in status.items() if s == "ENABLED"]
    print(f"\nВключены сейчас: {', '.join(on)}")
    d = pd.DataFrame({"расход_все": S.groupby("date")["cost"].sum(), "лиды_все": G.groupby("date").size(),
                      "расход_вкл": S[S["camp"].isin(on)].groupby("date")["cost"].sum(),
                      "лиды_вкл": G[G["camp"].isin(on)].groupby("date").size()}).fillna(0)
    d = d[d.index >= today - pd.Timedelta(days=a.days)]
    roll = lambda c, n: (d[c].rolling(5, min_periods=5).sum() / d[n].rolling(5, min_periods=5).sum() / a.rate)  # noqa: E731
    d["цена_5б_все_EUR"] = roll("расход_все", "лиды_все").round(1)
    d["цена_5б_вкл_EUR"] = roll("расход_вкл", "лиды_вкл").round(1)
    for c in ("расход_все", "расход_вкл"):
        d[c] = d[c].round(0)
    print("\n=== 2. Будни по дням (цена за 5 будней подряд; сегодняшний день не закончен) ===")
    print(d.to_string())

    done = d[d.index < today].tail(a.avg_days)
    cost_day = done["расход_вкл"].mean()
    lead_day = done["лиды_вкл"].mean()
    left = [x for x in pd.date_range(today, a.month_end) if x.dayofweek < 5]
    m1 = pd.Timestamp(today.year, today.month, 1)
    spent = S_all[S_all["date"] >= m1]["cost"].sum()
    print(f"\n=== 3. Прогноз до {a.month_end} (по {len(done)} последним законченным будням включённых кампаний) ===")
    print(f"средний будний день: расход {cost_day:.0f} zł, лидов {lead_day:.2f} (цена {eur(cost_day) / max(lead_day, 1e-9):.1f} €)")
    print(f"осталось будней с сегодняшним: {len(left)} ({', '.join(x.strftime('%d.%m') for x in left)})")
    add_cost, add_leads = cost_day * len(left), lead_day * len(left)
    month_leads = len(G_all[G_all["date"] >= m1])
    print(f"расход месяца: уже {spent:.0f} (все дни) + прогноз {add_cost:.0f} = {spent + add_cost:.0f} zł против плана {a.plan_budget:.0f}; "
          f"недобор {a.plan_budget - spent - add_cost:.0f} zł ({(spent + add_cost) / a.plan_budget * 100:.0f}% плана)")
    print(f"лиды месяца (CRM, все дни): уже {month_leads} + прогноз {add_leads:.0f} = {month_leads + add_leads:.0f} против плана {a.plan_leads:.0f}")
    print(f"чтобы выйти на план расхода, нужно {(a.plan_budget - spent) / len(left):.0f} zł в будний день (сейчас {cost_day:.0f})")
    print("Ограничение: прогноз — только будни окна показа 08–18; суббота и воскресенье не включены.")


if __name__ == "__main__":
    main()
