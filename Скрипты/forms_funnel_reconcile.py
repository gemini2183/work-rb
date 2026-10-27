#!/usr/bin/env python
# coding: utf-8
"""Воронка форм сайта: Tilda → Supabase → GA4 → CRM клиента — ТОЛЬКО ЧТЕНИЕ (2026-10-27).

Клиенты: ProfiMet (mocnaszklarnia.pl), ExpertAgro (ekspertagro.pl). Период — `--from` … `--to` (по умолчанию с 1-го числа
текущего месяца по сегодня).
Источники:
  Tilda     — выгрузка заявок (Google-таблица «Tilda_Leads_…», id в TILDA_SHEET): все отправки форм на сайте;
  Supabase  — таблица `<клиент>_leads`, куда пишет GTM (ключ читается из конфига мониторинга RedBird, не печатается);
              пачки без телефона и UTM (≥3 строк за ≤2 с) отбрасываются как в мониторинге;
  GA4       — событие `form_submit` (минутный срез, ~60 дней хранения);
  CRM       — строки-формы в таблице клиента (type = «форма»).
Сопоставление Tilda↔Supabase↔CRM — по последним 9 цифрам телефона; Tilda↔GA4 — по минуте (GA4 не знает телефона).
Часовой пояс времени `sent` в Tilda оценивается автоматически по паре Tilda↔Supabase (медиана разницы, округление до часа).
Использование (из папки Скрипты): PYTHONUTF8=1 python forms_funnel_reconcile.py --client ProfiMet [--from 2026-10-01] [--to 2026-10-27]
Пишет CSV построчно в `Клиенты/<Имя>/Статистика/forms_funnel_<с>_<по>.csv`.
"""
import argparse
import re
from datetime import date

import gspread
import pandas as pd
import requests
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE, client_stats_dir
from ea_sales_orders_check import SHEET_ID as CRM_SHEET, load as load_crm

W = "Europe/Warsaw"
GA4_KEY = r"E:/PythonProjects/RedBird/google-cloud-jobs/adwhite/func/ga4_profimet/redbird-196813-ga4.json"
MON_CFG = "E:/PythonProjects/RedBird/monitoring scripts/monitoring/config/"
CLIENTS = {
    "ProfiMet": dict(folder="ProfiMet", tilda="1D0hPuCjZ4wXVjPFYst-90Busme9bHyUFfBh0FIX7FXw", tab="Лист1", crm_tab="mocnaszklarnia.pl",
                     ga4="349001266", cfg="profimet.yaml"),
    "ExpertAgro": dict(folder="EkspertAgro", tilda="1dszemEoBXkVvjh2mHLMuEeLufROgrf8mmF5dYquXW3g", tab="Заявки", crm_tab="Ekspertagro.pl",
                       ga4="514863743", cfg="experagro.yaml"),
}
TEST_P9 = {"111111111", "123456789", "222222222", "444444444", "445454444", "123123123", "333333333", "111113691"}
ISO = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d")


def last9(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-9:] if len(d) >= 9 else d


def is_test(p9, name=""):
    return p9 in TEST_P9 or bool(re.fullmatch(r"(\d)\1{8}", p9 or "")) or "test" in str(name).lower()


def chan(src, medium=""):
    s, m = str(src).lower(), str(medium).lower()
    if s in ("google", "google ads") and (m in ("cpc", "") or s == "google ads"):
        return "Google Ads"
    if "facebook" in s or s in ("fb", "ig", "instagram"):
        return "Facebook"
    return "Нет метки" if not s else "Прочее"


def load_tilda(c):
    sc = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    v = gspread.authorize(sc).open_by_key(c["tilda"]).worksheet(c["tab"]).get_all_values()
    h = [x or f"c{i}" for i, x in enumerate(v[0])]
    # в таблице ExpertAgro первая часть — ручная разметка со сдвигом колонок; берём только строки в родной раскладке Tilda
    # (дата в формате ГГГГ-ММ-ДД чч:мм:сс в колонке `sent`)
    i_sent = h.index("sent")
    rows = [r + [""] * (len(h) - len(r)) for r in v[1:] if len(r) > i_sent and ISO.fullmatch(r[i_sent])]
    df = pd.DataFrame(rows, columns=h)
    phone = pd.Series("", index=df.index)
    for col in ("Phone", "phone", "Telefon"):
        if col in df:
            phone = phone.where(phone != "", df[col])
    out = pd.DataFrame({
        "sent": pd.to_datetime(df["sent"]),
        "phone": phone, "p9": phone.map(last9),
        "form": df.get("Form name", ""), "formid": df.get("formid", ""), "ga_cid": df.get("ga_client_id", ""),
        "name": df.get("Imię_Nazwisko", ""),
        "t_src": df.get("utm_source", pd.Series("", index=df.index)), "t_med": df.get("utm_medium", pd.Series("", index=df.index)),
        "t_camp": df.get("utm_campaign", pd.Series("", index=df.index)), "referer": df.get("referer", ""),
    })
    out["test"] = [is_test(p, n) for p, n in zip(out["p9"], out["name"])]
    return out.sort_values("sent").reset_index(drop=True)


def load_supabase(c, d0, d1):
    cfg = yaml.safe_load(open(MON_CFG + c["cfg"], encoding="utf-8"))["supabase"]
    h = {"apikey": cfg["secret_key"], "Authorization": f"Bearer {cfg['secret_key']}"}
    rows, off = [], 0
    while True:
        r = requests.get(f"{cfg['url']}/rest/v1/{cfg['table']}", headers=h, timeout=60, params={
            "select": "id,phone,utm_source,utm_medium,utm_campaign,created_at", "order": "created_at.asc",
            "created_at": f"gte.{pd.Timestamp(d0) - pd.Timedelta(days=1):%Y-%m-%d}T00:00:00", "limit": 1000, "offset": off})
        r.raise_for_status()
        b = r.json()
        rows += b
        if len(b) < 1000:
            break
        off += 1000
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["created_at"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    for k in ("phone", "utm_source", "utm_medium", "utm_campaign"):
        df[k] = df[k].fillna("")
    # пачки: ≥3 строк подряд с интервалом ≤2 с, без телефона и UTM
    df["burst"] = False
    grp = (df["ts"].diff().dt.total_seconds().fillna(99) > 2).cumsum()
    for _, g in df.groupby(grp):
        if len(g) >= 3 and (g["phone"] + g["utm_source"] + g["utm_medium"] + g["utm_campaign"] == "").all():
            df.loc[g.index, "burst"] = True
    df["p9"] = df["phone"].map(last9)
    return df


def ga4_minutes(c, d0, d1):
    s = AuthorizedSession(Credentials.from_service_account_file(GA4_KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))
    body = {"dateRanges": [{"startDate": d0, "endDate": d1}], "dimensions": [{"name": "dateHourMinute"}, {"name": "sessionSourceMedium"}],
            "metrics": [{"name": "eventCount"}], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{c['ga4']}:runReport", json=body, timeout=180)
    r.raise_for_status()
    rows = [(x["dimensionValues"][0]["value"], x["dimensionValues"][1]["value"], int(float(x["metricValues"][0]["value"])))
            for x in r.json().get("rows", [])]
    g = pd.DataFrame(rows, columns=["dhm", "sm", "n"])
    g = g[~g["sm"].str.contains("test|tagassistant", case=False)]
    g["w"] = pd.to_datetime(g["dhm"], format="%Y%m%d%H%M").dt.tz_localize(W, ambiguous="NaT", nonexistent="shift_forward")
    ev = g.loc[g.index.repeat(g["n"])].reset_index(drop=True)
    ev["ts"] = ev["w"].dt.tz_convert("UTC")
    ev["ch"] = ev["sm"].map(lambda x: "Google Ads" if x.lower() == "google / cpc" else "Facebook" if "facebook" in x.lower() else "Прочее/без метки")
    return ev.sort_values("ts").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, choices=list(CLIENTS))
    ap.add_argument("--from", dest="d0", default=date.today().replace(day=1).isoformat())
    ap.add_argument("--to", dest="d1", default=date.today().isoformat())
    ap.add_argument("--tol-min", type=float, default=3, help="допуск сопоставления с GA4, минут")
    a = ap.parse_args()
    c = CLIENTS[a.client]

    t = load_tilda(c)
    sb = load_supabase(c, a.d0, a.d1)
    # часовой пояс Tilda: медиана (sent − created_at Supabase) по общим телефонам
    m = t[~t["test"] & (t["p9"] != "")].merge(sb[sb["p9"] != ""][["p9", "ts"]].drop_duplicates("p9"), on="p9")
    off_h = round(((m["sent"] - m["ts"].dt.tz_localize(None)).dt.total_seconds() / 3600).median()) if len(m) else 0
    print(f"Часовой пояс Tilda `sent`: UTC{off_h:+d} (оценка по {len(m)} парам Tilda↔Supabase, медиана разницы "
          f"{((m['sent'] - m['ts'].dt.tz_localize(None)).dt.total_seconds() / 60).median():.1f} мин)" if len(m) else "Пар Tilda↔Supabase нет")
    t["ts"] = (t["sent"] - pd.Timedelta(hours=off_h)).dt.tz_localize("UTC")
    lo, hi = pd.Timestamp(a.d0, tz=W).tz_convert("UTC"), (pd.Timestamp(a.d1, tz=W) + pd.Timedelta(days=1)).tz_convert("UTC")
    t = t[(t["ts"] >= lo) & (t["ts"] < hi)].reset_index(drop=True)
    sbp = sb[(sb["ts"] >= lo) & (sb["ts"] < hi)].copy()

    crm = load_crm(CRM_SHEET, c["crm_tab"])
    crm = crm[(crm["type"] == "форма") & (crm["ts"] >= lo) & (crm["ts"] < hi)].copy()
    crm["p9"] = crm["phone"].map(last9)
    crm["test"] = crm["p9"].map(is_test)
    ev = ga4_minutes(c, a.d0, a.d1)
    ev = ev[(ev["ts"] >= lo) & (ev["ts"] < hi)].reset_index(drop=True)

    real = t[~t["test"]].copy()
    print(f"\n=== {a.client}: {a.d0} … {a.d1} ===")
    print(f"Tilda: строк {len(t)}, тестовых {int(t['test'].sum())}, реальных {len(real)} "
          f"(из них без телефона {int((real['p9'] == '').sum())}, уникальных телефонов {real.loc[real['p9'] != '', 'p9'].nunique()})")
    print("Tilda по названию формы:\n" + real["form"].value_counts().to_string())
    nb = sbp[~sbp["burst"]]
    print(f"\nSupabase: строк {len(sbp)}, пачек-мусора {int(sbp['burst'].sum())}, остальных {len(nb)} "
          f"(без телефона {int((nb['p9'] == '').sum())}, уникальных телефонов {nb.loc[nb['p9'] != '', 'p9'].nunique()})")
    print(f"GA4 form_submit (события, без test/tagassistant): {len(ev)}")
    print(f"CRM: строк-форм {len(crm)}, тестовых {int(crm['test'].sum())}, реальных {int((~crm['test']).sum())}")
    crm = crm[~crm["test"]]

    # --- сопоставление по телефону ---
    sb_ph = nb[nb["p9"] != ""].drop_duplicates("p9", keep="first").set_index("p9")
    crm_ph = crm[crm["p9"] != ""].sort_values("ts").drop_duplicates("p9", keep="first").set_index("p9")
    real["in_sb"] = real["p9"].isin(sb_ph.index)
    real["in_crm"] = real["p9"].isin(crm_ph.index)
    real["sb_src"] = real["p9"].map(sb_ph["utm_source"]).fillna("")
    real["sb_med"] = real["p9"].map(sb_ph["utm_medium"]).fillna("")
    real["crm_src"] = real["p9"].map(crm_ph["src"]).fillna("")

    # --- сопоставление с GA4 по минуте ---
    used, link = set(), {}
    for i, r in real.iterrows():
        d = (ev["ts"] - r["ts"]).abs()
        cand = d[(d <= pd.Timedelta(minutes=a.tol_min)) & ~d.index.isin(used)]
        if len(cand):
            j = cand.idxmin()
            used.add(j)
            link[i] = j
    real["in_ga"] = real.index.isin(link)
    real["ga_ch"] = [ev.at[link[i], "ch"] if i in link else "" for i in real.index]
    real["ga_sm"] = [ev.at[link[i], "sm"] if i in link else "" for i in real.index]

    # канал заявки: UTM в Tilda → UTM в Supabase → метка CRM → источник сеанса GA4
    def ch_of(r):
        for s, md in ((r["t_src"], r["t_med"]), (r["sb_src"], r["sb_med"])):
            if s:
                return chan(s, md)
        if r["crm_src"] in ("Google Ads", "Facebook"):
            return r["crm_src"]
        return r["ga_ch"] or "Нет метки"
    real["ch"] = real.apply(ch_of, axis=1)
    real["ch"] = real["ch"].replace({"Прочее/без метки": "Прочее", "": "Нет метки"})

    print("\n=== Воронка по каналам (канал заявки: UTM Tilda → UTM Supabase → метка CRM → GA4) ===")
    f = real.groupby("ch").agg(Tilda=("ts", "size"), Supabase=("in_sb", "sum"), GA4=("in_ga", "sum"), CRM=("in_crm", "sum"))
    f.loc["ИТОГО"] = f.sum()
    print(f.to_string())
    print("\nПо названию формы (Tilda | попали в Supabase | в GA4 | в CRM):")
    ff = real.groupby("form").agg(Tilda=("ts", "size"), Supabase=("in_sb", "sum"), GA4=("in_ga", "sum"), CRM=("in_crm", "sum"))
    print(ff.to_string())
    print("\nПо дням (Tilda | Supabase | GA4 | CRM):")
    real["day"] = real["ts"].dt.tz_convert(W).dt.strftime("%m-%d")
    dd = real.groupby("day").agg(Tilda=("ts", "size"), Supabase=("in_sb", "sum"), GA4=("in_ga", "sum"), CRM=("in_crm", "sum"))
    dd["Supabase строк (не пачки)"] = nb.groupby(nb["ts"].dt.tz_convert(W).dt.strftime("%m-%d")).size()
    dd["GA4 событий"] = ev.groupby(ev["ts"].dt.tz_convert(W).dt.strftime("%m-%d")).size()
    print(dd.fillna(0).astype(int).to_string())

    # с какого дня Supabase пишет телефон — воронка Tilda→Supabase имеет смысл только с него
    dday = nb.groupby(nb["ts"].dt.tz_convert(W).dt.normalize()).agg(n=("id", "size"), ph=("p9", lambda x: (x != "").sum()))
    good = dday[(dday["ph"] / dday["n"] >= 0.5)]
    print(f"\nSupabase строк без пачек: {len(nb)} против отправок Tilda {len(real)} (строка есть почти на каждую отправку, вопрос в том, заполнен ли телефон)")
    if len(good):
        sd = good.index.min()
        r2 = real[real["ts"] >= sd]
        print(f"\nТелефон в Supabase заполнен в большинстве строк с {sd:%Y-%m-%d}. С этого момента: Tilda {len(r2)}, "
              f"в Supabase {int(r2['in_sb'].sum())} ({r2['in_sb'].mean():.0%}), в GA4 {int(r2['in_ga'].sum())} ({r2['in_ga'].mean():.0%}), "
              f"в CRM {int(r2['in_crm'].sum())} ({r2['in_crm'].mean():.0%})")
        print(r2.groupby("ch").agg(Tilda=("ts", "size"), Supabase=("in_sb", "sum"), GA4=("in_ga", "sum"), CRM=("in_crm", "sum")).to_string())

    # --- чего нет в Tilda, но есть в других источниках ---
    tp = set(real["p9"]) - {""}
    only_sb = sb_ph[~sb_ph.index.isin(tp)]
    only_crm = crm_ph[~crm_ph.index.isin(tp)]
    free_ev = ev[~ev.index.isin(used)]
    # дубли: свободное событие в пределах минуты от уже сопоставленного с тем же источником сеанса
    matched = ev.loc[sorted(used)]
    is_dup = [bool(((matched["sm"] == r.sm) & ((matched["ts"] - r.ts).abs() <= pd.Timedelta(minutes=1))).any()) for r in free_ev.itertuples()]
    dups = free_ev[is_dup]
    free_ev = free_ev[[not x for x in is_dup]]
    print(f"\nGA4: событий {len(ev)} = пара с заявкой Tilda {len(used)} + дубли (второе событие в ту же минуту) {len(dups)} + без пары {len(free_ev)}")
    print(f"\nЕсть в Supabase, нет в Tilda: {len(only_sb)} телефонов; есть в CRM, нет в Tilda: {len(only_crm)}; "
          f"событий GA4 без пары в Tilda: {len(free_ev)}")
    print("События GA4 без пары по источнику сеанса:\n" + free_ev["sm"].value_counts().head(10).to_string() if len(free_ev) else "")
    print("\nСтрок Supabase с телефоном по каналу (UTM) против заявок Tilda: см. CSV")

    out = client_stats_dir(c["folder"]) / f"forms_funnel_{a.d0}_{a.d1}.csv"
    real[["ts", "phone", "ga_cid", "form", "ch", "t_src", "t_med", "t_camp", "in_sb", "sb_src", "sb_med", "in_ga", "ga_sm", "in_crm", "crm_src"]].to_csv(out, index=False, encoding="utf-8-sig")
    print("CSV:", out)


if __name__ == "__main__":
    main()
