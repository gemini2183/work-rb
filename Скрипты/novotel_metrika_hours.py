"""
Novotel: визиты и обращения по часам и дням недели из Метрики (только чтение).

Срез по рекламе кампании: UTM-метка кампании оканчивается на ID Директа. Обращение = визиты с целью «УМ: Все формы» (498289834) + визиты с целью
«УМ: Звонок Calltouch» (498298013) счётчика 105965383 (один на визит, как в Директе). Час — час начала визита в часовом поясе счётчика.
Расход по часам Директ в отчётах не отдаёт: расход окна оценивается как доля визитов × расход кампании (допущение: цена клика одинакова
во все часы). Токен клиента — из файла (.secrets/), в вывод не попадает.
Запуск: PYTHONUTF8=1 python novotel_metrika_hours.py --token-file ../.secrets/novotel_direct.token --campaign-id 705894438 --cost 440098
"""
import argparse
from pathlib import Path

import pandas as pd
import requests

ST = Path(__file__).resolve().parent.parent / "Клиенты" / "Novotel_Moscow_City" / "Статистика"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--counter", default="105965383")
    ap.add_argument("--campaign-id", default="705894438")
    ap.add_argument("--date1", default="2026-01-12")
    ap.add_argument("--date2", default="2026-06-30")
    ap.add_argument("--cost", type=float, required=True, help="расход кампании за период, ₽ (Директ)")
    ap.add_argument("--budget", type=float, default=200000)
    ap.add_argument("--haircut", type=float, default=0.25)
    ap.add_argument("--from-h", type=int, default=9)
    ap.add_argument("--to-h", type=int, default=17, help="последний час окна включительно")
    a = ap.parse_args()
    h = {"Authorization": "OAuth " + Path(a.token_file).read_text().strip()}
    tz = requests.get(f"https://api-metrika.yandex.net/management/v1/counter/{a.counter}", headers=h, timeout=60).json()["counter"].get("time_zone_name")
    r = requests.get("https://api-metrika.yandex.net/stat/v1/data", headers=h, timeout=120, params=dict(
        ids=a.counter, date1=a.date1, date2=a.date2, accuracy="full", limit=1000,
        filters=f"ym:s:UTMCampaign=~'{a.campaign_id}$'",
        metrics="ym:s:visits,ym:s:goal498289834visits,ym:s:goal498298013visits",
        dimensions="ym:s:dayOfWeek,ym:s:hour")).json()
    d = pd.DataFrame([[x["dimensions"][0]["name"], int(x["dimensions"][1]["name"][:2])] + x["metrics"] for x in r["data"]],
                     columns=["dow", "h", "visits", "forms", "calls"])
    d["leads"] = d.forms + d.calls
    d.to_csv(ST / f"metrika_{a.counter}_dow_hour_{a.campaign_id}.csv", index=False, encoding="utf-8-sig")
    wk = ~d.dow.isin(["Saturday", "Sunday"])
    inw = d.h.between(a.from_h, a.to_h)
    print(f"Часовой пояс счётчика: {tz}. Визитов {d.visits.sum():.0f}, форм {d.forms.sum():.0f}, звонков {d.calls.sum():.0f}")
    rows = []
    for name, m in ((f"Пн–Пт {a.from_h}:00–{a.to_h}:59", wk & inw), ("Пн–Пт остальные часы", wk & ~inw), ("Сб–Вс весь день", ~wk)):
        x = d[m]
        rows.append((name, x.visits.sum(), round(x.visits.sum() / d.visits.sum() * 100), x.leads.sum(), round(x.leads.sum() / x.visits.sum() * 100, 1),
                     round(a.cost * x.visits.sum() / d.visits.sum())))
    print(pd.DataFrame(rows, columns=["Окно", "Визитов", "% визитов", "Обращений", "Обращений на 100 визитов", "Оценка расхода, ₽"]).to_string(index=False))
    keep = d[wk & inw]
    cost_k, l_k = a.cost * keep.visits.sum() / d.visits.sum(), keep.leads.sum()
    cpl = cost_k / l_k
    lb = a.budget / cpl
    print(f"\nТолько Пн–Пт {a.from_h}:00–{a.to_h}:59: цена обращения {cpl:,.0f} ₽ (вся кампания по Метрике {a.cost / d.leads.sum():,.0f} ₽); "
          f"на {a.budget:,.0f} ₽: {lb:.1f} обращений, с запасом {a.haircut * 100:.0f}% — {lb * (1 - a.haircut):.1f} обращений по {cpl / (1 - a.haircut):,.0f} ₽")
    print("по часам (визитов / обращений):", {int(k): (int(v), int(l)) for k, v, l in d.groupby("h")[["visits", "leads"]].sum().reset_index().values})


if __name__ == "__main__":
    main()
