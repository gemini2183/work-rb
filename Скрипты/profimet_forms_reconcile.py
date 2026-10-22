#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: сверка форм сайта — CRM (лист mocnaszklarnia.pl) против GA4 `form_submit` — ТОЛЬКО ЧТЕНИЕ (2026-10-21).

1) Помесячно и по каналам: формы CRM (без тестовых номеров) против событий и сеансов GA4 form_submit.
2) Сопоставление «одна форма CRM ↔ одно событие GA4» по минуте (допуск `--tol-min`, время GA4 = Europe/Warsaw, CRM = UTC).
   Минутный срез GA4 (dateHourMinute) хранится ~60 дней, поэтому сопоставление идёт с `--match-from` (по умолчанию 22.08.2026);
   раньше — только сравнение по дням.
3) Таблица «источник в CRM × источник сеанса в GA4» по совпавшим формам: видно, где в CRM потеряна метка, а GA4 знает канал.
Тестовые номера (`--test-phones`) исключаются из CRM; в GA4 исключаются test/tagassistant.
Использование: PYTHONIOENCODING=utf-8 python profimet_forms_reconcile.py [--from 2026-08-01] [--match-from 2026-08-22]
Пишет `Клиенты/ProfiMet/Статистика/forms_reconcile_<с>_<по>.csv` (строки CRM с признаком «есть в GA4»). Запускать без -I.
"""
import argparse
from datetime import date

import pandas as pd
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from _config import client_stats_dir
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_sources_dashboard import GA4_KEY, GA4_PROPERTY, SITE

W = "Europe/Warsaw"
TEST_PHONES = "111111111,123456789,222222222,444444444,445454444,123123123,333333333,111113691"
EVENT_FILTER = {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}


def ga4_report(session, dims, frm, to):
    body = {"dateRanges": [{"startDate": frm, "endDate": to}], "dimensions": [{"name": d} for d in dims],
            "metrics": [{"name": "eventCount"}, {"name": "sessions"}], "limit": 100000, "dimensionFilter": EVENT_FILTER}
    r = session.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=120)
    r.raise_for_status()
    return pd.DataFrame([[v["value"] for v in x["dimensionValues"]] + [int(float(v["value"])) for v in x["metricValues"]]
                         for x in r.json().get("rows", [])], columns=dims + ["events", "sessions"])


def channel(s):
    s = s.lower()
    return "Google Ads" if s in ("google / cpc", "Google Ads".lower()) else "Facebook" if "facebook" in s or s == "facebook" else "Прочее/без метки"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--to", default=str(date.today()))
    ap.add_argument("--match-from", default="2026-08-22")
    ap.add_argument("--tol-min", type=float, default=5)
    ap.add_argument("--test-phones", default=TEST_PHONES)
    a = ap.parse_args()
    tests = set(a.test_phones.split(","))

    sheet = load_sheet(SHEET_ID)
    f = sheet[(sheet["type"] == "форма") & (sheet["site"] == SITE)].copy()
    f["w"] = f["ts"].dt.tz_convert(W)
    f = f[(f["w"] >= pd.Timestamp(a.frm, tz=W))].reset_index(drop=True)
    f["src"] = f["src"].replace("", "Нет метки")
    f["test"] = f["p9"].isin(tests)
    f["day"] = f["w"].dt.strftime("%Y-%m")
    real = f[~f["test"]].copy()

    s = AuthorizedSession(Credentials.from_service_account_file(GA4_KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))
    ga_day = ga4_report(s, ["date", "sessionSourceMedium"], a.frm, a.to)
    ga_day = ga_day[~ga_day["sessionSourceMedium"].str.contains("test|tagassistant", case=False)]
    ga_day["month"] = ga_day["date"].str[:4] + "-" + ga_day["date"].str[4:6]

    print(f"=== Формы CRM {SITE} с {a.frm}: всего {len(f)}, тестовых номеров {int(f['test'].sum())}, реальных {len(real)} ===")
    t = pd.DataFrame({"CRM все": f.groupby("day").size(), "CRM без тестов": real.groupby("day").size(),
                      "CRM уник. телефонов": real.groupby("day")["p9"].nunique(),
                      "GA4 события": ga_day.groupby("month")["events"].sum(), "GA4 сеансы": ga_day.groupby("month")["sessions"].sum()})
    t.loc["итого"] = t.sum()
    print(t.to_string())
    real["ch"] = real["src"].map(lambda x: x if x in ("Google Ads", "Facebook") else "Прочее/без метки")
    ga_day["ch"] = ga_day["sessionSourceMedium"].map(channel)
    print("\nПо каналам (CRM по метке строки | GA4 сеансы по источнику сеанса):")
    print(pd.concat({"CRM": real.groupby(["ch", "day"]).size().unstack(fill_value=0),
                    "GA4": ga_day.groupby(["ch", "month"])["sessions"].sum().unstack(fill_value=0)}, axis=1).to_string())

    ga_min = ga4_report(s, ["dateHourMinute", "sessionSourceMedium"], a.match_from, a.to)
    ga_min["w"] = pd.to_datetime(ga_min["dateHourMinute"], format="%Y%m%d%H%M").dt.tz_localize(W, ambiguous="NaT", nonexistent="shift_forward")
    ev = pd.DataFrame([(r.w, r.sessionSourceMedium) for r in ga_min.itertuples() for _ in range(r.events)], columns=["w", "sm"])
    ev = ev[~ev["sm"].str.contains("test|tagassistant", case=False)].sort_values("w").reset_index(drop=True)
    rc = real[real["w"] >= pd.Timestamp(a.match_from, tz=W)].copy()
    used, link = set(), {}
    for i, r in rc.iterrows():
        d = (ev["w"] - r["w"]).abs()
        cand = [(d[j], j) for j in d.index if d[j] <= pd.Timedelta(minutes=a.tol_min) and j not in used]
        if cand:
            j = min(cand)[1]
            used.add(j)
            link[i] = j
    rc["in_ga"] = rc.index.isin(link.keys())
    rc["ga_sm"] = [ev["sm"][link[i]] if i in link else "" for i in rc.index]
    print(f"\n=== Сопоставление по минуте с {a.match_from}: форм CRM {len(rc)}, найдено в GA4 {int(rc['in_ga'].sum())} ({rc['in_ga'].mean():.0%}); "
          f"событий GA4 {len(ev)}, нашли пару в CRM {len(used)} ({len(used)/max(len(ev),1):.0%}) ===")
    print(pd.crosstab(rc["src"], rc["in_ga"], margins=True).to_string())
    print("\nИсточник в CRM × источник сеанса в GA4 (совпавшие формы):")
    print(pd.crosstab(rc[rc["in_ga"]]["ga_sm"], rc[rc["in_ga"]]["src"], margins=True).to_string())
    print("\nСобытия GA4 без пары в CRM:")
    print(ev[~ev.index.isin(used)].to_string())
    out = client_stats_dir("ProfiMet") / f"forms_reconcile_{a.frm}_{a.to}.csv"
    rc[["w", "phone", "src", "utm_source", "utm_campaign", "gclid", "in_ga", "ga_sm"]].to_csv(out, index=False, encoding="utf-8-sig")
    print("\nCSV:", out)


if __name__ == "__main__":
    main()
