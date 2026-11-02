"""
Novotel Moscow City: разбор одной архивной кампании по уже сохранённым выгрузкам (только чтение, без API).

Источники — Клиенты/Novotel_Moscow_City/Статистика/: express_campaigns_daily.csv, express_queries.csv,
express_raw_q_goals.csv, keywords_full.csv. Заявка = формы + звонки по набору целей из Аудит_мероприятий_2026-11-02.md (раздел 9):
  формы  498289834 (счётчик 105965383), 495347102 (97147563)
  звонки 498298013 (105965383),         495615844 (97147563)
«Квал MICE» (511709344) и «90 секунд» (498184341) показываются отдельно, заявками не считаются.

Срезы по условиям показа, гео, устройствам, позициям, объявлениям читаются из slice_*_<id>.csv, которые кладёт
direct_campaign_slices.py (цели в них — только 498289834 / 498298013 счётчика 105965383, поэтому для кампаний с
подключённым сайтом отеля заявки 495347102 / 495615844 в срезах не видны). Запросы Директ отдаёт только за 180 дней.

Запуск: PYTHONUTF8=1 python novotel_campaign_audit.py --campaign-id 705894438
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ST = ROOT / "Клиенты" / "Novotel_Moscow_City" / "Статистика"
FORMS = ["498289834", "495347102"]
CALLS = ["498298013", "495615844"]
OTHER = {"511709344": "qual", "498184341": "sec90"}


def goal(df, gid):
    c = f"Conversions_{gid}_AUTO"
    return df[c].fillna(0) if c in df.columns else 0


def add_goals(df):
    df["forms"] = sum(goal(df, g) for g in FORMS)
    df["calls"] = sum(goal(df, g) for g in CALLS)
    df["leads"] = df["forms"] + df["calls"]
    df["qual"] = goal(df, "511709344")
    df["sec90"] = goal(df, "498184341")
    return df


def cpl(cost, leads):
    return round(cost / leads) if leads else None


def table(g, label):
    t = g.agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"), imp=("Impressions", "sum"),
              forms=("forms", "sum"), calls=("calls", "sum"), leads=("leads", "sum"),
              qual=("qual", "sum"), sec90=("sec90", "sum")).reset_index()
    t["CTR%"] = (t["clicks"] / t["imp"] * 100).round(1)
    t["CPC"] = (t["cost"] / t["clicks"]).round(0)
    t["₽/заявку"] = [cpl(c, l) for c, l in zip(t["cost"], t["leads"])]
    t["cost"] = t["cost"].round(0)
    print(f"\n== {label}")
    print(t.to_string(index=False))


def slice_leads(df):
    for g in ("498289834", "498298013", "511709344", "498184341"):
        col = [c for c in df.columns if c.startswith("Conversions_" + g)]
        df[g] = df[col[0]].fillna(0) if col else 0
    df["leads"] = df["498289834"] + df["498298013"]
    return df


def sl_table(df, by, label):
    t = df.groupby(by).agg(imp=("Impressions", "sum"), clicks=("Clicks", "sum"), cost=("Cost", "sum"),
                           forms=("498289834", "sum"), calls=("498298013", "sum"), leads=("leads", "sum"),
                           qual=("511709344", "sum"), sec90=("498184341", "sum")).reset_index()
    t["share%"] = (t["cost"] / t["cost"].sum() * 100).round(1)
    t["CPC"] = (t["cost"] / t["clicks"].where(t["clicks"] > 0)).round(0)
    t["₽/заявку"] = (t["cost"] / t["leads"].where(t["leads"] > 0)).round(0)
    print(f"\n== {label}")
    print(t.sort_values("cost", ascending=False).round(0).to_string(index=False))
    return t


def slices(cid):
    f = lambda n: ST / f"slice_{n}_{cid}.csv"
    if not f("criteria").exists():
        print("\nСрезов нет (запустить direct_campaign_slices.py)")
        return
    sl_table(slice_leads(pd.read_csv(f("device"))), "Device", "Устройства")
    sl_table(slice_leads(pd.read_csv(f("slot"))), "Slot", "Позиция показа (Slot)")
    c = slice_leads(pd.read_csv(f("criteria")))
    sl_table(c, "CriterionType", "Условия показа: ключи против автотаргетинга")
    n = c[c["Cost"] > 0]
    print(f"Условий с расходом {len(n)}; с заявками {int((n['leads'] > 0).sum())}; расход на условия с заявками "
          f"{n.loc[n['leads'] > 0, 'Cost'].sum():.0f} ₽ из {n['Cost'].sum():.0f} ₽")
    gg = slice_leads(pd.read_csv(f("geo")))
    gg["Регион"] = gg["LocationOfPresenceName"].where(gg["LocationOfPresenceName"] == "Москва", "все остальные")
    sl_table(gg, "Регион", "Гео (где находился пользователь): Москва против остальных")
    print(f"Регионов с расходом {int((gg['Cost'] > 0).sum())}, с заявками {int((gg['leads'] > 0).sum())}")
    ad = slice_leads(pd.read_csv(f("ad")))
    print(f"\n== Объявления: всего {len(ad)}, с расходом {int((ad['Cost'] > 0).sum())}, с заявками {int((ad['leads'] > 0).sum())}")
    ads = pd.read_csv(ST / "express_ads.csv")
    ads = ads[ads["CampaignId"] == cid][["Id", "TextAd"]]
    ad = ad.merge(ads, left_on="AdId", right_on="Id", how="left")
    import ast

    def txt(x):
        try:
            d = ast.literal_eval(x)
            return f"{d.get('Title')} | {d.get('Text')}"
        except Exception:
            return ""
    ad["Текст"] = ad["TextAd"].map(txt).str.slice(0, 110)
    print(ad.sort_values("Cost", ascending=False)[["AdId", "Clicks", "Cost", "leads", "498184341", "Текст"]].head(10).round(0).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    cid = int(a.campaign_id)

    d = pd.read_csv(ST / "express_campaigns_daily.csv", encoding="utf-8-sig")
    d = add_goals(d[d["CampaignId"] == cid].copy())
    d["Date"] = pd.to_datetime(d["Date"])
    print(f"Кампания {cid}: {d['CampaignName'].iloc[0]}")
    print(f"Дни в выгрузке: {d['Date'].min().date()} .. {d['Date'].max().date()} ({len(d)} дней с показами)")
    tot = d[["Cost", "Clicks", "Impressions", "forms", "calls", "leads", "qual", "sec90"]].sum()
    print(f"Итого: расход {tot['Cost']:.0f} ₽, клики {tot['Clicks']:.0f}, показы {tot['Impressions']:.0f}, формы {tot['forms']:.0f}, "
          f"звонки {tot['calls']:.0f}, заявок {tot['leads']:.0f}, ₽/заявку {cpl(tot['Cost'], tot['leads'])}, Квал {tot['qual']:.0f}, 90с {tot['sec90']:.0f}")

    table(d.groupby("Month"), "По месяцам")
    d["weekday"] = d["Date"].dt.dayofweek.map(dict(enumerate(["пн", "вт", "ср", "чт", "пт", "сб", "вс"])))
    order = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    t = d.groupby("weekday").agg(days=("Date", "nunique"), cost=("Cost", "sum"), clicks=("Clicks", "sum"),
                                 leads=("leads", "sum")).reindex(order).reset_index()
    t["₽/заявку"] = [cpl(c, l) for c, l in zip(t["cost"], t["leads"])]
    t["cost"] = t["cost"].round(0)
    print("\n== По дням недели (все дни с показами, не чистое окно)")
    print(t.to_string(index=False))

    # Запросы
    q = pd.read_csv(ST / "express_queries.csv", encoding="utf-8-sig")
    q = add_goals(q[q["CampaignId"] == cid].copy())
    if q.empty:
        print("\nЗапросов по кампании в выгрузке нет")
    else:
        print(f"\n== Поисковые запросы: даты {q['Date'].min()} .. {q['Date'].max()}, строк {len(q)}, "
              f"расход в выгрузке {q['Cost'].sum():.0f} ₽ из {tot['Cost']:.0f} ₽ по кампании "
              f"({q['Cost'].sum() / tot['Cost'] * 100:.0f}%)")
        g = q.groupby("Query").agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"), imp=("Impressions", "sum"),
                                   leads=("leads", "sum"), forms=("forms", "sum"), calls=("calls", "sum"),
                                   sec90=("sec90", "sum"), qual=("qual", "sum")).reset_index()
        print(f"Уникальных запросов {len(g)}; с заявками {int((g['leads'] > 0).sum())}; "
              f"расход на запросы с заявками {g.loc[g['leads'] > 0, 'cost'].sum():.0f} ₽; "
              f"без заявок {g.loc[g['leads'] == 0, 'cost'].sum():.0f} ₽")
        print("\n-- запросы с заявками")
        print(g[g["leads"] > 0].sort_values("leads", ascending=False).round(0).to_string(index=False))
        print(f"\n-- топ-{a.top} запросов по расходу БЕЗ заявок")
        print(g[g["leads"] == 0].sort_values("cost", ascending=False).head(a.top).round(0).to_string(index=False))
        print("\n-- бренд / небренд")
        b = q.groupby("Brand").agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"), leads=("leads", "sum")).reset_index()
        b["₽/заявку"] = [cpl(c, l) for c, l in zip(b["cost"], b["leads"])]
        print(b.round(0).to_string(index=False))
        print("\n-- по сегменту (поле Segment выгрузки)")
        s = q.groupby("Segment").agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"), leads=("leads", "sum")).reset_index()
        s["₽/заявку"] = [cpl(c, l) for c, l in zip(s["cost"], s["leads"])]
        print(s.sort_values("cost", ascending=False).round(0).to_string(index=False))

    # Структура
    k = pd.read_csv(ST / "keywords_full.csv", encoding="utf-8-sig")
    k = k[k["CampaignId"] == cid]
    print(f"\n== Структура: групп {k['AdGroupId'].nunique()}, ключей {len(k)} "
          f"(включено {int((k['Состояние ключа'] == 'ON').sum())}), автотаргетинг-ключей {int(k['Ключевое слово'].eq('---autotargeting').sum())}")
    slices(cid)


if __name__ == "__main__":
    main()
