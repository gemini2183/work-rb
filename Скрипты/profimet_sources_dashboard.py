#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: НАШ дашборд «По источникам» из выгрузки продаж CRM, Google Ads и BigQuery — ТОЛЬКО ЧТЕНИЕ.

Те же строки и колонки, что в клиентском дашборде (Источник, Цена, Клики, Показы, Цена клика, CTR, Конверсии, % конверсии,
Цена заявки, Звонки, Продажи, % продажи, Цена продажи), но все определения собственные и выписаны под таблицей. Нужен, чтобы
человек сравнил его с клиентским глазами; сами расхождения скрипт не разбирает (решение пользователя 2026-10-20).

Откуда данные и как считаем (лист `mocnaszklarnia.pl` выгрузки CRM):
  • Цена / Клики / Показы — Google Ads: из API по аккаунту (все кампании) за даты периода; Facebook: BigQuery
    `redbird-196813.adwhite.fb_stats_profimet` (в таблице хранится в долларах, пересчёт в евро — параметр `--usd-eur`).
    У «Нет метки», «Телефон», «Прочее» рекламных показателей нет.
  • Конверсии = звонки + формы. С 2026-11-09 — `profimet_our_leads.py`: звонки Ringostat и формы CRM в ОДНОЙ лестнице 60 дней на номер
    (первое обращение засчитывается, повторы нет, в один день — кто раньше), формы «Нет метки» проверяются по Supabase / Tilda / GA4 / gclid:
    реклама найдена — идут в Google Ads / Facebook, иначе не засчитываются. Звонки без рекламного канала (общий номер сайта, SEO) в заявки не входят.
  • Звонки — звонки Google Ads и Facebook из Ringostat.
  • Продажи — проданные заказы (в выгрузке есть «Дата продажи» в периоде; количество товара в выгрузке нет, поэтому это заказы,
    не единицы). Источник продажи в НАШЕМ режиме — источник ПЕРВОГО обращения этого номера за 60 дней до первой строки заказа (наше правило; в режиме «как у клиента» окон нет, вся история с 01.08.2025).
  • % конверсии = Конверсии ÷ Клики; Цена заявки = Цена ÷ Конверсии; % продажи = Продажи ÷ Конверсии; Цена продажи = Цена ÷ Продажи;
    CTR = Клики ÷ Показы; Цена клика = Цена ÷ Клики. «Итого»: цена и показатели Google + Facebook, конверсии и продажи по всем строкам.
  • Справочно под таблицей: звонки Google/Facebook по боевому правилу Ringostat (только входящие, в памяти 4 канала) — те же, что в
    таблице агентства `ringostat_calls_profimet2`.

Использование:
    PYTHONIOENCODING=utf-8 python profimet_sources_dashboard.py [--from 2026-08-01] [--to 2026-10-19] [--by month|week]
        [--usd-eur 0.85] [--cache путь.pkl]
Пишет `Клиенты/ProfiMet/Статистика/dashboard_sources_<с>_<по>.csv`. Запускать без -I.
"""
import argparse
import pickle
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE, client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_season_audit import W, fetch_ringostat_full, prod_unique
from profimet_our_leads import our_leads, AD as OUR_AD

SITE = "mocnaszklarnia.pl"
ADS_CUSTOMER = "7552781705"
SOURCES = ["Google Ads", "YouTube", "Facebook", "Нет метки", "Телефон", "Прочее"]  # YouTube — второй, как в дашборде клиента (решение пользователя 2026-11-10)
AD_SRC = ("Google Ads", "YouTube", "Facebook")   # источники с рекламным расходом
YT_PREFIX = "yt_"                                 # признак YouTube: название кампании и utm_campaign начинаются с yt_
WINDOW = 60


def ads_daily(frm, to):
    c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    q = (f"SELECT segments.date, metrics.cost_micros, metrics.clicks, metrics.impressions FROM customer "
         f"WHERE segments.date BETWEEN '{frm}' AND '{to}'")
    rows = [(r.segments.date, r.metrics.cost_micros / 1e6, r.metrics.clicks, r.metrics.impressions)
            for r in c.get_service("GoogleAdsService").search(customer_id=ADS_CUSTOMER, query=q)]
    d = pd.DataFrame(rows, columns=["date", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def is_yt(name):
    return str(name or "").lower().startswith(YT_PREFIX)


def ads_daily_split(frm, to):
    """Расход Google Ads по дням с разделением на «Google Ads» и «YouTube» (название кампании начинается с yt_). Колонки: date, src, cost, clicks, impr.
    Сумма двух источников равна ads_daily (проверено 10.11: 643,89 € и 643,89 € за 01–10.11)."""
    c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    q = (f"SELECT segments.date, campaign.name, metrics.cost_micros, metrics.clicks, metrics.impressions FROM campaign "
         f"WHERE segments.date BETWEEN '{frm}' AND '{to}'")
    rows = [(r.segments.date, "YouTube" if is_yt(r.campaign.name) else "Google Ads", r.metrics.cost_micros / 1e6, r.metrics.clicks, r.metrics.impressions)
            for r in c.get_service("GoogleAdsService").search(customer_id=ADS_CUSTOMER, query=q)]
    d = pd.DataFrame(rows, columns=["date", "src", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d.groupby(["date", "src"], as_index=False).sum(numeric_only=True)


def tag_youtube(ringo, sheet):
    """YouTube — по utm_campaign yt_* (инструкция Инструкция_клиенту_отдельный_учёт_YouTube): звонки Ringostat категории Google Ads и строки CRM с меткой Google Ads
    или без метки получают источник «YouTube». our_unique и пр. посчитаны до замены и не меняются. Возвращает (ringo, sheet, число звонков, число строк CRM)."""
    ringo, sheet = ringo.copy(), sheet.copy()
    m_r = (ringo["category"] == "Google Ads") & ringo["utm_campaign"].map(is_yt)
    ringo.loc[m_r, "category"] = "YouTube"
    m_s = sheet["src"].isin(["Google Ads", ""]) & sheet["utm_campaign"].map(is_yt)
    sheet.loc[m_s, "src"] = "YouTube"
    return ringo, sheet, int(m_r.sum()), int(m_s.sum())


def fb_daily(frm, to):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/bigquery"])
    c = bigquery.Client(project="redbird-196813", credentials=creds)
    q = (f"SELECT date, SUM(spend) cost, SUM(clicks) clicks, SUM(impressions) impr FROM `redbird-196813.adwhite.fb_stats_profimet` "
         f"WHERE date BETWEEN '{frm}' AND '{to}' GROUP BY date")
    d = pd.DataFrame([dict(r.items()) for r in c.query(q).result()], columns=["date", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


GA4_KEY = r"E:/PythonProjects/RedBird/google-cloud-jobs/adwhite/func/ga4_profimet/redbird-196813-ga4.json"  # сервисный аккаунт ga4-analytics (в вики не копировать)
GA4_PROPERTY = "349001266"
MODE_OUR = "Наш (60 дней без дублей)"
MODE_CLIENT = "Как у клиента (звонки за всю историю, формы GA4)"


def ga4_forms_daily(frm, to):
    """Формы из GA4: СЕАНСЫ с событием form_submit по дате и источнику сеанса (так считает клиентский дашборд, подтверждено 2026-10-20):
    google / cpc → Google Ads, любой источник с facebook → Facebook, остальное → «Нет метки»."""
    from google.auth.transport.requests import AuthorizedSession
    s = AuthorizedSession(Credentials.from_service_account_file(GA4_KEY, scopes=["https://www.googleapis.com/auth/analytics.readonly"]))
    body = {"dateRanges": [{"startDate": str(frm), "endDate": str(to)}], "dimensions": [{"name": "date"}, {"name": "sessionSourceMedium"}, {"name": "sessionCampaignName"}],
            "metrics": [{"name": "sessions"}], "limit": 100000,
            "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "form_submit"}}}}
    r = s.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", json=body, timeout=120)
    r.raise_for_status()
    rows = []
    for x in r.json().get("rows", []):
        d, sm, camp = x["dimensionValues"][0]["value"], x["dimensionValues"][1]["value"].lower(), x["dimensionValues"][2]["value"]
        src = "YouTube" if is_yt(camp) else "Google Ads" if sm == "google / cpc" else "Facebook" if "facebook" in sm else "Нет метки"
        rows.append({"day": pd.Timestamp(d).date(), "src2": src, "forms_c": int(float(x["metricValues"][0]["value"]))})
    df = pd.DataFrame(rows, columns=["day", "src2", "forms_c"])
    return df.groupby(["day", "src2"], as_index=False)["forms_c"].sum()


CLIENT_HISTORY_FROM = pd.Timestamp("2025-08-01", tz="UTC")   # так считает клиент: история обращений с 01.08.2025 (решение пользователя 2026-11-10)


def client_like_daily(ringo, ga4f):
    """Конверсии «как у клиента»: звонки — первый звонок номера за всю историю с 01.08.2025 (входящие, отслеживаемые каналы: Google Ads, YouTube, Facebook,
    Google SEO, без источника; в конверсии идут Google Ads, YouTube, Facebook), формы — сеансы GA4. По дате и источнику. Без окна 60 дней."""
    tr = ringo[(ringo["call_type"] == "in") & ringo["category"].isin(list(AD_SRC) + ["Google SEO", "No Source"]) & (ringo["ts"] >= CLIENT_HISTORY_FROM)].sort_values("ts", kind="mergesort")
    seen, keep = set(), []
    for idx, p9 in zip(tr.index, tr["p9"]):
        if p9 not in seen:
            keep.append(idx)
        seen.add(p9)
    r = tr.loc[keep]
    r = r[r["category"].isin(AD_SRC)].copy()
    global CLIENT_CALLS
    CLIENT_CALLS = r.copy()   # для списка заявок (build_leads)
    r["day"] = r["ts"].dt.tz_convert(W).dt.date
    r["src2"] = r["category"]
    calls = r.groupby(["day", "src2"]).size().rename("calls_c").reset_index()
    out = pd.merge(calls, ga4f, on=["day", "src2"], how="outer").fillna(0)
    out["calls_c"], out["forms_c"] = out["calls_c"].astype(int), out["forms_c"].astype(int)
    return out


def contacts_with_new_flag(sheet):
    """Обращения (звонок/форма) листа с флагом «новое по правилу 60 дн» (лестница: окно от последнего засчитанного)."""
    s = sheet[(sheet["site"] == SITE) & sheet["type"].isin(["звонок", "форма"]) & (sheet["p9"] != "")].copy()
    s["src2"] = s["src"].replace("", "Нет метки")
    s.loc[~s["src2"].isin(SOURCES), "src2"] = "Прочее"
    s["day"] = s["ts"].dt.tz_convert(W).dt.date
    s = s.sort_values("ts", kind="mergesort")
    last, flags = {}, []
    for p9, day in zip(s["p9"], s["day"]):
        prev = last.get(p9)
        new = prev is None or (day - prev).days > WINDOW
        if new:
            last[p9] = day
        flags.append(new)
    s["new"] = flags
    return s


def sales_with_source(sheet):
    """Проданные заказы: дата продажи, источник первого обращения номера за 60 дн до первой строки заказа."""
    s = sheet[sheet["site"] == SITE]
    # История номера для «первого обращения» — ОБА сайта ProfiMet (основной и SEO szklarniaprofimet.pl); заказы — только основного (решение пользователя 2026-11-10:
    # наш режим строится по своему принципу «первое касание», SEO-обращение раньше рекламного делает продажу нерекламной, даже если клиент её считает).
    hist = sheet[sheet["site"].isin([SITE, "szklarniaprofimet.pl"])]
    by_phone = {p: g for p, g in hist.groupby("p9") if p}
    rows = []
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd:
            continue
        cd = [d for d in grp["cancel_date"] if d]
        od = [d for d in grp["order_date"] if d] if "order_date" in grp.columns else []
        cancelled_later = bool(cd) and max(cd) >= min(sd)  # как в схеме клиента: отмена не раньше продажи; в нашем режиме такая продажа считается, число показано отдельно
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        parts = [by_phone[p] for p in set(grp["p9"]) if p in by_phone]
        t_all = pd.concat(parts) if parts else grp
        t = t_all[(t_all["ts"] >= t0 - pd.Timedelta(days=WINDOW)) & (t_all["ts"] <= t0)].sort_values("ts", kind="mergesort")
        first_row = t.iloc[0] if not t.empty else grp.iloc[0]
        src = first_row["src"] or "Нет метки"
        # рекламный контакт Google Ads / Facebook СТАРШЕ окна 60 дней при нерекламном источнике по окну: в источник не засчитывается (решение 2026-11-09), число показано под таблицей
        ad_older = src not in AD_SRC and bool(len(t_all[(t_all["ts"] < t0 - pd.Timedelta(days=WINDOW)) & t_all["src"].isin(list(AD_SRC))]))
        rows.append({"order": order, "sale_date": pd.Timestamp(min(sd)).date(), "src2": src if src in SOURCES else "Прочее", "cancelled_later": cancelled_later,
                     "ad_older": ad_older, "touch_date": first_row["ts"].tz_convert(W).date(),
                     "first_type": first_row["type"], "first_ts": first_row["ts"], "first_p9": first_row["p9"], "first_gclid": first_row["gclid"],
                     "counted": (src in AD_SRC), "restored": False, "reason": "",
                     # контроль данных: «Дата заказа» CRM раньше первого касания (к заказу привязаны более поздние звонки) — 57 из 428 на 01.08–08.11
                     "od_before_touch": bool(od) and pd.Timestamp(min(od)[:10]).date() < first_row["ts"].tz_convert(W).date()})
    return pd.DataFrame(rows)


def apply_sales_form_check(sales, frm=date(2026, 8, 1)):
    """Решение пользователя 2026-11-09. (1) Продажа, первое касание которой в окне 60 дней — форма «Нет метки», проверяется теми же следами, что заявки
    (gclid CRM, Supabase, Tilda, GA4 в ту же минуту; Facebook — только cpc): реклама найдена → источник Google Ads / Facebook; не реклама или не найдено → остаётся «Нет метки».
    (2) В наш отчёт входят только продажи с рекламным первым касанием в окне 60 дней (`counted`); «Телефон», «Нет метки» без найденной рекламы, «Прочее» не включаются, их число
    показано под таблицей. Рекламный контакт старше окна у «Телефон» — отдельная пометка (`ad_older`)."""
    from profimet_our_leads import resolve_unlabeled
    sales = sales.copy()
    m = (sales["src2"] == "Нет метки") & (sales["first_type"] == "форма") & (sales["touch_date"] >= frm)
    if m.any():
        forms = pd.DataFrame({"ts": sales.loc[m, "first_ts"], "p9": sales.loc[m, "first_p9"], "gclid": sales.loc[m, "first_gclid"]})
        r = resolve_unlabeled(forms, GA4_KEY, GA4_PROPERTY, sales.loc[m, "touch_date"].min(), sales["touch_date"].max())
        for i in forms.index:
            v = r.at[i, "verdict"]
            if v in AD_SRC:
                sales.at[i, "src2"], sales.at[i, "restored"], sales.at[i, "ad_older"] = v, True, False
            else:
                sales.at[i, "reason"] = f"форма: {v}"
    sales["counted"] = sales["src2"].isin(list(AD_SRC))
    for i in sales.index[~sales["counted"] & (sales["reason"] == "")]:
        sales.at[i, "reason"] = "звонок на номер сайта" if (sales.at[i, "src2"] == "Нет метки" and sales.at[i, "first_type"] == "звонок") else f"источник {sales.at[i, 'src2']}"
    return sales


def _last9(x):
    d = re.sub(r"\D", "", str(x or ""))
    return d[-9:] if len(d) >= 9 else ""


def read_client_list(path):
    """Список продаж дашборда клиента (TSV из его вкладки «Ads + FB»: Дата, Заказ, Телефон, Товар, Кол-во, Источник, UTM, Площадка, Автор) → одна строка на заказ."""
    paths = [path] if isinstance(path, (str, Path)) else list(path)  # несколько списков за разные периоды склеиваются
    # Один заказ в нескольких списках (списки перекрываются, клиент пересчитывает даты) берётся ТОЛЬКО из самого свежего файла: иначе строки с разной датой
    # не схлопываются и штуки удваиваются (09.11: четыре списка дали 30 штук вместо 17 за 01–08.11).
    frames = []
    for x in sorted(paths, key=lambda q: Path(q).stat().st_mtime):
        f = pd.read_csv(x, sep="	", dtype=str).fillna("")
        frames.append(f)
        f["_file"] = len(frames)
    c = pd.concat(frames, ignore_index=True)
    c = c[c["_file"] == c.groupby("Заказ")["_file"].transform("max")].drop(columns="_file").drop_duplicates(["Заказ", "Дата", "Товар"])
    c["qty"] = c["Кол-во"].replace("", "1").astype(int)
    return c.groupby("Заказ", sort=False).agg(
        client_date=("Дата", "min"), client_phone=("Телефон", "first"), product=("Товар", lambda s: "; ".join(s)), qty=("qty", "sum"),
        client_source=("Источник", "first"), platform=("Площадка", "first"), author=("Автор", "first")).reset_index().rename(columns={"Заказ": "key"})


def _ga_paid_phones():
    """Телефоны форм, которые Google Analytics показывает с платного клика (cpc): по последнему `forms_reconcile_*.csv` (profimet_forms_reconcile.py)."""
    files = sorted(client_stats_dir("ProfiMet").glob("forms_reconcile_*.csv"))
    if not files:
        return set()
    f = pd.read_csv(files[-1], dtype=str).fillna("")
    return set(f.loc[f["ga_sm"].str.contains("cpc"), "phone"].map(_last9)) - {""}


def client_scheme_orders(sheet, client=None, frm=None, to=None):
    """Заказы «по схеме клиента» из выгрузки CRM (лист mocnaszklarnia.pl).
    Продажа = заказ с датой продажи; отменён, если дата отмены не раньше даты продажи (отмена до продажи и новая продажа: заказ действует).
    Источник заказа по правилу клиента: есть строка-форма → источник формы (Google Ads, YouTube, Facebook, иначе «Нет метки»); формы нет → заказ менеджера: первая строка — звонок с рекламной меткой или «Телефон» → «Телефон», звонок без метки → «Нет метки».
    Дата заказа (оценка, UTC): даты создания в выгрузке нет; берём дату продажи, если первая строка позже продажи или раньше продажи больше чем на 7 дней, иначе первую строку.
    В схему входят действующие заказы, у которых либо есть форма, либо первое обращение номера за ВСЮ историю выгрузки (с 01.08.2025) не «Телефон» и не Google SEO.
    Возвращает (заказы схемы, расхождения с дашбордом клиента); без списка клиента расхождения пустые."""
    pm = sheet[sheet["site"] == SITE].sort_values("ts", kind="mergesort")
    # История номера для «первого обращения за 60 дн» включает сайт SEO: заказ, начатый звонком с SEO, клиент в рекламный дашборд не берёт
    # (01–20.10: единственный такой заказ c04c84af у клиента отсутствует; 04.11: 5335cc45). Сайт EkspertAgro не включаем: заказы, начатые там, у клиента есть не всегда.
    pmh = sheet[sheet["site"].isin([SITE, "szklarniaprofimet.pl"])].sort_values("ts", kind="mergesort")
    other_keys = set(sheet.loc[(sheet["site"] != SITE) & (sheet["order"] != ""), "order"].str[:8])
    ga_paid = _ga_paid_phones()
    rows = []
    for order, g in pm[pm["order"] != ""].groupby("order"):
        g = g.sort_values("ts", kind="mergesort")
        sale = min([d for d in g["sale_date"] if d] or [""])
        canc = max([d for d in g["cancel_date"] if d] or [""])
        created = g.iloc[0]["ts"]
        forms = g[g["type"] == "форма"]
        # Заказ менеджера без формы (решение пользователя 2026-11-10, сверка 64 общих заказов октября и 01–09.11: совпало 62): первая строка заказа — звонок;
        # метка звонка Google Ads / YouTube / Facebook или «Телефон» → «Телефон» (49 из 49 и 3 из 3), звонок без метки → «Нет метки» (10 из 12; иногда менеджер выбирает вручную).
        first_call_src = g.iloc[0]["src"] or "Нет метки"
        rule = ((forms.iloc[0]["src"] if forms.iloc[0]["src"] in AD_SRC else "Нет метки") if len(forms) else ("Нет метки" if first_call_src == "Нет метки" else "Телефон"))
        hist = pmh[(pmh["p9"] == g.iloc[0]["p9"]) & (pmh["ts"] <= created + pd.Timedelta(minutes=3))]
        w = hist   # ВСЯ история номера в выгрузке CRM (с 01.08.2025), без окна 60 дней: так считает клиент (пользователь 2026-11-10; заказ 58909717: первое обращение за 255 дней)
        first60 = (w.iloc[0]["src"] or "Нет метки") if len(w) else ""
        ad_touch = bool(len(hist[hist["src"].isin(list(AD_SRC)) | hist["gclid"].ne("")])) or g.iloc[0]["p9"] in ga_paid
        active = bool(sale) and (not canc or canc < sale)
        # Дата заказа (оценка): даты создания в выгрузке нет. Дата продажи, если первая строка позже продажи или раньше продажи больше чем на 7 дней,
        # иначе первая строка. На 01–20.10 совпало с датой клиента у 74 из 75 общих заказов (по первой строке только у 71).
        fr = created.tz_convert("UTC").tz_localize(None)
        est = pd.Timestamp(sale) if (sale and (pd.Timestamp(sale) < fr.normalize() or (pd.Timestamp(sale) - fr.normalize()).days > 7)) else fr
        # С 06–09.11.2026 клиент отдаёт в выгрузке колонку «Дата заказа»: она совпала с датой дашборда клиента у 83 из 91 заказов
        # (Хроника_2026-11, 09.11). Если она есть — берём её, оценка выше остаётся запасным вариантом для старых строк.
        od = [d for d in g["order_date"] if d] if "order_date" in g.columns else []
        real_od = bool(od)
        if od:
            est = pd.Timestamp(min(od)[:10])
        # Режим «как у клиента»: период — по ДАТЕ ЗАКАЗА (колонка «Дата заказа» CRM). Проверено 09.11 на списке клиента за 01–08.11 (18 заказов):
        # по дате заказа 17 из 18 номеров совпали, лишних у нас 0 (единственный недостающий — заказ 08.11 без даты продажи в CRM);
        # по дате продажи — 7 лишних заказов (созданы в октябре, проданы в ноябре). Клиент после добавления колонки пересчитал свой дашборд:
        # заказы 1d5b7726, 815cc018, 87713917 из его списка 02–04.11 ушли в октябрь. «Наш» режим считает по дате продажи (build, sales_with_source).
        day = est.date()
        art = False
        rows.append({"order": order, "key": order[:8], "p9": g.iloc[0]["p9"], "phone": g.iloc[0]["phone"], "created": created,
                     "day": day, "est": est, "real_od": real_od, "sale": sale, "active": active, "art": art, "has_form": len(forms) > 0, "first60": first60, "ad_touch": ad_touch,
                     "rule": rule, "first_src": g.iloc[0]["src"] or "Нет метки", "first_type": g.iloc[0]["type"]})
    O = pd.DataFrame(rows)
    if frm is not None:
        f0, t0 = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
        O["in_period"] = (O["day"] >= f0) & (O["day"] <= t0)
    else:
        O["in_period"] = True
    O["selected"] = O["active"] & ~O["art"] & (O["has_form"] | ~O["first60"].isin(["Телефон", "Google SEO"])) & O["in_period"]
    act = O[O["active"]]
    O["repeat"] = [bool(len(act[(act["p9"] == r.p9) & (act["order"] != r.order) &
                                 (pd.to_datetime(act["sale"]) <= r.created.tz_convert("UTC").tz_localize(None) - pd.Timedelta(days=7))])) for r in O.itertuples()]
    qty = client.set_index("key")["qty"].to_dict() if client is not None else {}
    O["qty"] = [qty.get(k, 1) for k in O["key"]]
    sel = O[O["selected"]].copy()
    if client is None:
        return sel, pd.DataFrame()
    ck = client.set_index("key")
    sel["in_client"] = sel["key"].isin(ck.index)
    diff = []
    by_key = O.drop_duplicates("key").set_index("key")
    for r in client.itertuples():
        if r.key in set(sel["key"]):
            rule = sel[sel["key"] == r.key].iloc[0]["rule"]
            if rule != r.client_source:
                diff.append(("Источник у клиента другой", r.key, r.client_date, r.client_source, rule,
                             f"Правило клиента даёт «{rule}», у клиента «{r.client_source}» (вероятно, менеджер выбрал источник вручную)", "", ""))
            continue
        if r.key in by_key.index:
            o = by_key.loc[r.key]
            why = (f"Дата заказа в CRM {o['est']:%d.%m.%Y} (продажа {o['sale'] or 'не внесена'}), вне периода; у клиента {r.client_date[:10]}" if not o["in_period"] else
                   "В выгрузке CRM заказ отменён или без продажи" if not o["active"] else "По правилу клиента не отнесён к рекламному дашборду")
        elif r.key in other_keys:
            why = "Заказ найден только на листе другого сайта"
        elif len(pm[pm["p9"] == _last9(r.client_phone)]):
            why = "Заказа с таким номером в выгрузке CRM нет, есть только обращения с этим телефоном"
        else:
            why = "В выгрузке CRM нет ни заказа, ни обращений с этим телефоном"
        diff.append(("Есть у клиента, нет у нас", r.key, r.client_date, r.client_source, "", why, "", ""))
    for r in sel[~sel["in_client"]].itertuples():
        diff.append(("Есть у нас, нет у клиента", r.key, r.est.strftime("%Y-%m-%d %H:%M"), "", r.rule,
                     "Повторная покупка: человек уже покупал раньше" if r.repeat else "Причина неизвестна",
                     r.first60 or "нет в выгрузке CRM", "да" if r.ad_touch else "нет"))
    return sel, pd.DataFrame(diff, columns=["Раздел", "Заказ", "Дата", "Источник у клиента", "Наш расчёт: источник заказа по схеме клиента", "Причина", "Первое обращение за 60 дней", "Было рекламное касание"])


MATURITY = None      # доля продаж когорты, созревшая к возрасту k дней (k = 0…60); считается в main
CURVE_TEXT = ""      # то же словами — для пояснения под таблицей


def maturity_curve(sales, to, frm=date(2026, 8, 1), full_days=60, max_age=60):
    """Доля продаж, пришедшая не позже k дней после первого касания (по заказам, чьё касание старше full_days дней от конца данных, чтобы когорта созрела).
    Прогноз когорты: продаж к сегодняшнему дню ÷ m(возраст)."""
    end = pd.Timestamp(to).date() - timedelta(days=full_days)
    x = sales[(sales["touch_date"] >= frm) & (sales["touch_date"] <= end)]
    lag = pd.Series([max((a - b).days, 0) for a, b in zip(x["sale_date"], x["touch_date"])])
    m = [float((lag <= k).mean()) if len(lag) else 1.0 for k in range(max_age + 1)]
    txt = (f"за день касания {m[0]:.0%}, за 2 дня {m[2]:.0%}, за 7 дней {m[7]:.0%}, за 14 дней {m[14]:.0%}, за 30 дней {m[30]:.0%} "
           f"(по {len(x)} заказам с касанием {frm:%d.%m}–{end:%d.%m.%Y})")
    return m, txt, len(x)


def expected_sales(df, to, m, floor=0.3):
    """df: продажи с touch_date; возвращает Series «ожидается» по строке (продажа ÷ доля, созревшая к возрасту когорты на дату to)."""
    t = pd.Timestamp(to).date()
    return pd.Series([1.0 / max(m[min(max((t - d).days, 0), len(m) - 1)], floor) for d in df["touch_date"]], index=df.index)


def leads_notes(w):
    """Пояснения под таблицей для нашего режима: что не засчитано и почему (w — обращения периода из OurLeads.window)."""
    unl = w[(w["type"] == "форма") & (w["crm_src"] == "Нет метки") & w["new"]]
    k = int(unl["final"].isin(OUR_AD).sum())
    m, n = int(unl["reason"].str.endswith("не реклама").sum()), int(unl["reason"].str.endswith("не установлен").sum())
    rep = w[~w["new"] & ((w["crm_src"].isin(OUR_AD) | (w["type"] == "форма") & (w["crm_src"] == "Нет метки")))]
    mixed = int((rep["type"] != rep["prev_type"]).sum())
    fbn = int((w["type"].eq("форма") & w["reason"].str.startswith("форма Facebook: не cpc")).sum())
    return ["Facebook в нашем режиме — только cpc: звонки utm_source=facebook + utm_medium=cpc; формы с меткой Facebook только при utm_medium=cpc; формы без метки только по "
            f"GA4 facebook / cpc или адресу с utm_medium=cpc. Не засчитано форм Facebook не cpc: {fbn} (facebook / free, реферал facebook.com, fbclid без cpc не считаются)",
            f"Нет метки: в заявки не входит. Форм без метки {len(unl)}: реклама (Google Ads / Facebook cpc) найдена у {k} (добавлены к Google Ads / Facebook), "
            f"не реклама или не Facebook cpc {m}, источник не найден {n} (не засчитаны)",
            f"Повторы не засчитаны: {len(rep)} (звонок и форма одного номера в пределах 60 дней: {mixed}); у каждого номера засчитано первое обращение"]


def build(frm, to, ads, fb, contacts, sales, usd_eur, client=None, mode="our", ours=None):
    """ours — OurLeads (profimet_our_leads): звонки Ringostat и формы CRM в одной лестнице 60 дней на номер, формы без метки проверены по Supabase/Tilda/GA4
    (решение пользователя 2026-11-09). Если передан, в НАШЕМ режиме Google Ads / Facebook берутся из него, «Нет метки» в заявках — 0."""
    f, t = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
    w = ours.window(f, t) if ours is not None else None
    a = ads[(ads["date"] >= f) & (ads["date"] <= t)]   # ads — расход Google Ads с колонкой src: «Google Ads» / «YouTube» (ads_daily_split)
    b = fb[(fb["date"] >= f) & (fb["date"] <= t)]
    ag, ay = a[a["src"] == "Google Ads"], a[a["src"] == "YouTube"]
    paid = {"Google Ads": (ag["cost"].sum(), ag["clicks"].sum(), ag["impr"].sum()),
            "YouTube": (ay["cost"].sum(), ay["clicks"].sum(), ay["impr"].sum()),
            "Facebook": (b["cost"].sum() * usd_eur, b["clicks"].sum(), b["impr"].sum())}
    c = contacts[contacts["new"] & (contacts["day"] >= f) & (contacts["day"] <= t)]
    cl = client[(client["day"] >= f) & (client["day"] <= t)] if client is not None else None
    dcol = "sale_date" if mode == "client" else "touch_date"  # «Наш»: когорта — продажа относится ко дню первого касания в окне 60 дней (решение 2026-11-09)
    sl = sales[(sales[dcol] >= f) & (sales[dcol] <= t)]
    slc = sl if mode == "client" else sl[sl["counted"]]  # «Наш»: только продажи с рекламным первым касанием в окне 60 дней
    out, notes = [], []
    if mode == "client":
        notes.append("Режим «как у клиента»: звонки — первый звонок номера за всю историю Ringostat; формы — сеансы GA4 form_submit по источнику сеанса; "
                     "«Телефон» и «Прочее» без конверсий. Продажи — по нашему правилу (выгрузка CRM) в обоих режимах.")
    for src in SOURCES:
        cost, clk, imp = paid.get(src, (None, None, None))
        if mode == "client":
            x = cl[cl["src2"] == src]
            calls_c, forms_c = int(x["calls_c"].sum()), int(x["forms_c"].sum())
            if src in AD_SRC:
                conv, calls = calls_c + forms_c, calls_c
            elif src == "Нет метки":
                conv, calls = forms_c, None
            else:
                conv = calls = None
            out.append({"Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": conv, "Звонки": calls,
                        "Продажи": int((slc["src2"] == src).sum())})
            continue
        cc = c[c["src2"] == src]
        conv, calls = len(cc), int((cc["type"] == "звонок").sum())
        if w is not None and src in AD_SRC:
            x = w[w["counted"] & (w["final"] == src)]
            calls = int((x["type"] == "звонок").sum())
            conv = len(x)
        elif w is not None and src == "Нет метки":
            notes.extend(leads_notes(w))
            out.append({"Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": 0, "Звонки": None,
                        "Продажи": int((slc["src2"] == src).sum())})
            continue
        # Структура колонок как у клиентского дашборда: конверсиями считаются Google Ads, Facebook, «Нет метки» (звонки — только
        # у Google и Facebook); перезвоны «Телефон» и «Прочее» в конверсии не входят. Убранное из колонок печатается под таблицей.
        if src in ("Телефон", "Прочее"):
            notes.append(f"{src}: новых обращений {conv} (из них звонков {calls}) — в «Конверсии» и «Звонки» не включены")
            conv = calls = None
        elif src == "Нет метки":
            notes.append(f"Нет метки: из {conv} конверсий звонков {calls} — в колонке «Звонки» не показаны")
            calls = None
        out.append({"Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": conv, "Звонки": calls,
                    "Продажи": int((slc["src2"] == src).sum())})
    if mode != "client":
        nc = slc[slc["cancelled_later"]]
        notes.append("Продажи считаются ЗАКАЗАМИ, не штуками: количества товара в выгрузке CRM нет. Формы в заявках — из выгрузки CRM (сервер), а не из Google Analytics 4")
        notes.append(f"Отменено после продажи: {len(nc)} (в продажи входят; по источникам: " +
                     (", ".join(f"{k} {v}" for k, v in nc.groupby("src2").size().items()) or "нет") + ")")
        if MATURITY is not None:
            ex = expected_sales(slc, to, MATURITY)
            by = ", ".join(f"{k} {ex[slc['src2'] == k].sum():.0f}" for k in SOURCES if (slc["src2"] == k).any())
            notes.append(f"Продажи по дате первого касания (когорта). Ожидается {ex.sum():.0f} (уже есть {len(slc)}, созрело {len(slc) / max(ex.sum(), 1e-9):.0%}); по источникам: {by}. "
                         f"Прогноз = продажи когорты ÷ доля продаж, созревшая к её возрасту: {CURVE_TEXT}")
        ex_ = sl[~sl["counted"]]
        nm = ex_[ex_["src2"] == "Нет метки"]
        notes.append(f"Не включены в наш отчёт (первое касание в окне 60 дней не рекламное): Телефон {int((ex_['src2'] == 'Телефон').sum())}; Нет метки {len(nm)} "
                     f"(формы: не реклама {int((nm['reason'] == 'форма: не реклама').sum())}, источник не найден {int((nm['reason'] == 'форма: не установлен').sum())}; "
                     f"звонки на номер сайта {int((nm['reason'] == 'звонок на номер сайта').sum())}); Прочее {int((ex_['src2'] == 'Прочее').sum())}. "
                     f"Продаж «Нет метки», у которых проверка формы нашла рекламу и они добавлены к Google Ads / Facebook: {int(slc['restored'].sum())}")
        notes.append(f"Рекламный контакт старше 60 дней, в источник не засчитан: {int(sl['ad_older'].sum())} продаж (источник взят из окна 60 дней, по этим заказам он нерекламный)")
    df = pd.DataFrame(out)
    tot_cost = sum(v[0] for v in paid.values())
    tot = {"Источник": "Итого", "Цена": tot_cost, "Клики": sum(v[1] for v in paid.values()), "Показы": sum(v[2] for v in paid.values()),
           "Конверсии": int(df["Конверсии"].sum()), "Звонки": int(df["Звонки"].sum()), "Продажи": int(df["Продажи"].sum())}
    df = pd.concat([df, pd.DataFrame([tot])], ignore_index=True)
    df["Цена клика"] = df["Цена"] / df["Клики"]
    df["CTR %"] = df["Клики"] / df["Показы"] * 100
    df["% конверсии"] = df["Конверсии"] / df["Клики"] * 100
    df["Цена заявки"] = df["Цена"] / df["Конверсии"].where(df["Конверсии"] > 0)
    df["% продажи"] = df["Продажи"] / df["Конверсии"].where(df["Конверсии"] > 0) * 100
    df["Цена продажи"] = df["Цена"] / df["Продажи"].where(df["Продажи"] > 0)
    # «Итого»: клики/показы только Google+Facebook, поэтому % конверсии у строк без рекламы не считаем
    df.loc[df["Клики"].isna(), ["Цена клика", "CTR %", "% конверсии"]] = None
    cols = ["Источник", "Цена", "Клики", "Показы", "Цена клика", "CTR %", "Конверсии", "% конверсии", "Цена заявки", "Звонки",
            "Продажи", "% продажи", "Цена продажи"]
    df = df[cols]
    df.attrs["notes"] = notes
    return df


def show(df, title):
    print(f"\n=== {title} ===")
    fmt = df.copy()
    for c in ("Цена", "Цена клика", "Цена заявки", "Цена продажи"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:,.2f} €".replace(",", " "))
    for c in ("Клики", "Показы", "Конверсии", "Звонки"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", " "))
    for c in ("CTR %", "% конверсии", "% продажи"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}%")
    print(fmt.to_string(index=False))
    for n in df.attrs.get("notes", []):
        print("  *", n)


DEFINITIONS = [
    "Цена, клики, показы: Google Ads — из Google Ads API по аккаунту целиком; Facebook — из BigQuery adwhite.fb_stats_profimet "
    "(там доллары, в евро пересчитано по курсу из параметра --usd-eur).",
    "Конверсии (наш режим, решение пользователя 2026-11-09) = звонки + формы в ОДНОЙ лестнице 60 дней на номер. Звонки — входящие из Ringostat (Google Ads, Google SEO, Facebook, No Source), "
    "формы — из выгрузки CRM без тестовых номеров. Первое обращение номера засчитывается; следующие в пределах 60 календарных дней от последнего засчитанного — повторы (окно они не продлевают); "
    "в один день первым считается то, что пришло раньше по времени. В лестнице стоят и обращения без рекламного источника (SEO, органика): номер уже обращался. В заявки идут только звонки Google Ads / Facebook "
    "и формы с рекламным источником. Форма с меткой Google Ads / Facebook в CRM — как есть. Форма «Нет метки» проверяется по следам: gclid в CRM, Supabase profimet_leads по телефону, таблица заявок Tilda по телефону, "
    "GA4 form_submit в ту же минуту (±6 мин, если событий несколько — не используется). Нашли рекламу — форма идёт в Google Ads / Facebook; нашли не рекламу (прямой заход, органика, реферал) или не нашли ничего — не засчитывается. "
    "Минутный срез GA4 хранится около 60 дней, для форм старше — только Supabase / Tilda / gclid. Facebook в нашем режиме — ТОЛЬКО cpc (решение 2026-11-09): звонок — utm_source=facebook и utm_medium=cpc; форма с меткой Facebook — только при utm_medium=cpc "
    "(facebook / free не считается); форма без метки — только GA4 facebook / cpc или адрес с facebook и utm_medium=cpc; facebook.com / referral и fbclid без cpc не считаются "
    "(в режиме «как у клиента» Facebook — любой источник с facebook). Засчитываются обращения с 2026-08-01.",
    "Звонки: входящие звонки Google Ads и Facebook, засчитанные по правилу выше; у «Нет метки» звонков нет.",
    "Продажи (наш режим): проданные заказы — у заказа есть «Дата продажи»; в период заказ попадает по ДАТЕ ПЕРВОГО КАСАНИЯ (первая строка контакта номера в окне 60 дней до первой строки заказа), то есть по дню, когда возник контакт (когорта). Поэтому последние дни периода недосчитаны: колонка «Продажи: ожидается» = продажи когорты ÷ доля продаж, созревшая к её возрасту (кривая считается по заказам с касанием старше 60 дней). В наш отчёт входят только продажи с РЕКЛАМНЫМ первым касанием в окне 60 дней: «Телефон» (звонки без рекламной метки) и «Нет метки» без найденной рекламы не включаются, их число показано под таблицей; форма «Нет метки» перед этим проверяется теми же следами, что заявки (gclid, Supabase, Tilda, GA4; Facebook только cpc). Считаются ЗАКАЗЫ, не штуки: количества товара в выгрузке нет. Заказ, отменённый после продажи, остаётся в продажах, "
    "его число показано отдельно под таблицей. Источник продажи — самое раннее обращение этого номера (звонок или форма) на любом из двух сайтов ProfiMet (основной и SEO) в 60 днях до первой строки заказа: если оно SEO, продажа не рекламная, даже если потом были рекламные звонки. "
    "Формы в заявках считаются по выгрузке CRM (сервер), а не по Google Analytics 4. В режиме «как у клиента» продажа привязана к колонке «Дата заказа».",
    "% конверсии = Конверсии ÷ Клики; Цена заявки = Цена ÷ Конверсии; % продажи = Продажи ÷ Конверсии; Цена продажи = Цена ÷ Продажи; "
    "CTR = Клики ÷ Показы; Цена клика = Цена ÷ Клики. «Итого»: цена, клики, показы — Google + Facebook; конверсии и продажи — по всем строкам.",
]


def _fmt_df(df):
    f = df.copy()
    for c in ("Цена", "Цена клика", "Цена заявки", "Цена продажи"):
        f[c] = f[c].map(lambda v: "—" if pd.isna(v) else f"{v:,.2f} €".replace(",", " "))
    for c in ("Клики", "Показы", "Конверсии", "Звонки", "Продажи"):
        f[c] = f[c].map(lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", " "))
    for c in ("CTR %", "% конверсии", "% продажи"):
        f[c] = f[c].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}%")
    return f


def write_html(path, frames, meta):
    """Самодостаточная страница: таблицы по источникам (весь период и по месяцам), определения, дата данных. Открывается двойным щелчком."""
    import html as H
    blocks = []
    for title, df in frames:
        f = _fmt_df(df)
        head = "".join(f"<th{' class=\"l\"' if i == 0 else ''}>{H.escape(c)}</th>" for i, c in enumerate(f.columns))
        rows = []
        for _, r in f.iterrows():
            cls = ' class="tot"' if r["Источник"] == "Итого" else ""
            rows.append(f"<tr{cls}>" + "".join(f"<td{' class=\"l\"' if i == 0 else ''}>{H.escape(str(v))}</td>" for i, v in enumerate(r)) + "</tr>")
        notes = "".join(f"<li>{H.escape(n)}</li>" for n in df.attrs.get("notes", []))
        blocks.append(f"<section><h2>{H.escape(title)}</h2><div class='w'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
                      f"<ul class='n'>{notes}</ul></section>")
    defs = "".join(f"<li>{H.escape(d)}</li>" for d in DEFINITIONS)
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProfiMet по источникам</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--tot:#f3f6f4;--acc:#1b7f4a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--line:#333;--tot:#1f2a24;--acc:#4cc28a}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif;max-width:1400px;margin:auto}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 8px;color:var(--acc)}} .m{{color:var(--mut);font-size:13px}}
.w{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:1100px}}
th,td{{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}} th{{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}}
.l{{text-align:left}} tr.tot td{{font-weight:600;background:var(--tot)}} ul.n{{margin:6px 0 0;padding-left:18px;color:var(--mut);font-size:13px}}
ol.d{{margin:12px 0;padding-left:20px;font-size:13px;color:var(--mut)}}
</style></head><body>
<h1>ProfiMet: по источникам</h1><div class="m">{H.escape(meta)}</div>
{''.join(blocks)}
<h2>Как считается</h2><ol class="d">{defs}</ol>
</body></html>"""
    Path(path).write_text(page, encoding="utf-8")


MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def daily_table(frm, to, ads, fb, contacts, sales, client, scheme=None, ours=None):
    """Длинная таблица «дата × источник»: расход/клики/показы (Google — евро, Facebook — доллары как в BigQuery), конверсии,
    звонки (из конверсий), продажи, а также конверсии и звонки «как у клиента» (режим переключается на листе «Дашборд»). Из неё формулы
    листа «Дашборд» собирают любой период."""
    cm = contacts[contacts["new"]].groupby(["day", "src2"]).agg(conv=("type", "size"), calls=("type", lambda s: int((s == "звонок").sum())))
    forms_new = contacts[contacts["new"] & (contacts["type"] == "форма")].groupby(["day", "src2"]).size()
    if ours is not None:
        oc = ours.contacts[ours.contacts["day"] >= pd.Timestamp("2026-08-01").date()]
        cnt = ours.counted.groupby(["day", "final", "type"]).size()
        restored = ours.counted[(ours.counted["type"] == "форма") & (ours.counted["crm_src"] == "Нет метки")].groupby(["day", "final"]).size()
        unl = oc[(oc["type"] == "форма") & (oc["crm_src"] == "Нет метки") & oc["new"]]
        not_ad = unl[unl["reason"].str.endswith("не реклама")].groupby("day").size()
        not_found = unl[unl["reason"].str.endswith("не установлен")].groupby("day").size()
        fb_nocpc = oc[(oc["type"] == "форма") & oc["reason"].str.startswith("форма Facebook: не cpc")].groupby("day").size()
        rp = oc[~oc["new"]].copy()
        rp["row"] = [c if c in OUR_AD else ("Нет метки" if (t == "форма" and c == "Нет метки") else "") for c, t in zip(rp["crm_src"], rp["type"])]
        rp = rp[rp["row"] != ""]
        rep_all = rp.groupby(["day", "row"]).size()
        rep_mix = rp[rp["type"] != rp["prev_type"]].groupby(["day", "row"]).size()
    sc_ = sales[sales["counted"]]                          # «Наш»: только продажи с рекламным первым касанием в окне 60 дней
    sm = sc_.groupby(["touch_date", "src2"]).size()       # продажа — в день первого касания (когорта)
    sm_c = sc_[sc_["cancelled_later"]].groupby(["touch_date", "src2"]).size()
    sm_o = sales[sales["ad_older"]].groupby(["touch_date", "src2"]).size()
    sm_x = (expected_sales(sc_, to, MATURITY).groupby([sc_["touch_date"], sc_["src2"]]).sum() if MATURITY is not None else sm)
    nc_ = sales[~sales["counted"]]
    sm_nc = nc_.groupby(["touch_date", "src2"]).size()
    sm_nf = nc_[(nc_["src2"] == "Нет метки") & (nc_["reason"] == "форма: не реклама")].groupby("touch_date").size()
    sm_nn = nc_[(nc_["src2"] == "Нет метки") & (nc_["reason"] == "форма: не установлен")].groupby("touch_date").size()
    sm_nt = nc_[(nc_["src2"] == "Нет метки") & (nc_["reason"] == "звонок на номер сайта")].groupby("touch_date").size()
    sm_rs = sales[sales["restored"]].groupby(["touch_date", "src2"]).size()
    sc = scheme.groupby(["day", "rule"])["qty"].sum() if scheme is not None else None
    cdx = client.set_index(["day", "src2"])
    a, y, b = ads[ads["src"] == "Google Ads"].set_index("date"), ads[ads["src"] == "YouTube"].set_index("date"), fb.set_index("date")
    rows = []
    for d in pd.date_range(frm, to).date:
        for src in SOURCES:
            cost = clk = imp = None
            src_df = a if src == "Google Ads" else y if src == "YouTube" else b if src == "Facebook" else None
            if src_df is not None:
                if d in src_df.index:
                    cost, clk, imp = float(src_df.loc[d, "cost"]), int(src_df.loc[d, "clicks"]), int(src_df.loc[d, "impr"])
                else:
                    cost, clk, imp = 0.0, 0, 0
            conv = int(cm["conv"].get((d, src), 0)) if (d, src) in cm.index else 0
            calls = int(cm["calls"].get((d, src), 0)) if (d, src) in cm.index else 0
            restored_n = not_ad_n = not_found_n = rep_n = rep_mix_n = fb_nocpc_n = 0
            if ours is not None and src in AD_SRC:  # наш режим: одна лестница 60 дн на звонки Ringostat и формы CRM
                calls = int(cnt.get((d, src, "звонок"), 0))
                conv = calls + int(cnt.get((d, src, "форма"), 0))
                restored_n = int(restored.get((d, src), 0))
                fb_nocpc_n = int(fb_nocpc.get(d, 0)) if src == "Facebook" else 0
            elif ours is not None and src == "Нет метки":  # формы без метки: реклама найдена — ушли в Google/Facebook, остальное не засчитано
                calls, conv = 0, 0
                not_ad_n, not_found_n = int(not_ad.get(d, 0)), int(not_found.get(d, 0))
            if ours is not None and src in AD_SRC + ("Нет метки",):
                rep_n, rep_mix_n = int(rep_all.get((d, src), 0)), int(rep_mix.get((d, src), 0))
            calls_c = int(cdx["calls_c"].get((d, src), 0)) if (d, src) in cdx.index else 0
            forms_c = int(cdx["forms_c"].get((d, src), 0)) if (d, src) in cdx.index else 0
            rows.append({"Дата": d, "Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": conv,
                         "Звонки": calls, "Продажи": int(sm.get((d, src), 0)),
                         "Продажи_клиент": int(sc.get((d, src), 0)) if sc is not None else int(sm.get((d, src), 0)),
                         "Конверсии_клиент": calls_c + forms_c if src in AD_SRC else (forms_c if src == "Нет метки" else 0),
                         "Звонки_клиент": calls_c if src in AD_SRC else 0,
                         "Формы_восстановлены": restored_n, "Формы_не_реклама": not_ad_n, "Формы_не_найдено": not_found_n,
                         "Повторы": rep_n, "Повторы_звонок_и_форма": rep_mix_n, "Формы_Facebook_не_cpc": fb_nocpc_n, "Продажи_отменены_позже": int(sm_c.get((d, src), 0)), "Продажи_реклама_старше_60": int(sm_o.get((d, src), 0)), "Продажи_ожидается": round(float(sm_x.get((d, src), 0)), 2),
                         "Продажи_не_включены": int(sm_nc.get((d, src), 0)), "Продажи_НМ_форма_не_реклама": int(sm_nf.get(d, 0)) if src == "Нет метки" else 0,
                         "Продажи_НМ_форма_не_найдена": int(sm_nn.get(d, 0)) if src == "Нет метки" else 0, "Продажи_НМ_звонок_сайт": int(sm_nt.get(d, 0)) if src == "Нет метки" else 0,
                         "Продажи_восстановлены": int(sm_rs.get((d, src), 0))})
    return pd.DataFrame(rows)


# Пояснения под таблицей в режиме «как у клиента» (решение пользователя 2026-11-10: описать подробно, как в нашем режиме).
# Тексты без ASCII-кавычек (они идут в формулы Google Таблицы); числа «за период» добавляются формулами в client_notes().
CLIENT_TEXT = {
    16: "Режим «как у клиента» повторяет схему клиентской вкладки «Ads + FB». Ниже по пунктам, как считается каждая колонка; «за период» — число по выбранному периоду.",
    17: "Цена, клики, показы: Google Ads и YouTube — Google Ads API, аккаунт 7552781705; YouTube — кампании, название которых начинается с yt_, Google Ads — все остальные кампании аккаунта; "
        "Facebook — BigQuery fb_stats_profimet, доллары × курс из B5. У строк «Нет метки», «Телефон», «Прочее» расхода и кликов нет («—»). Эти цифры такие же, как в нашем режиме.",
    18: "Звонки (только Google Ads, YouTube и Facebook): входящие звонки из Ringostat. Считается ПЕРВЫЙ звонок номера за всю историю с 01.08.2025 (как у клиента, окна 60 дней нет): повторный звонок того же номера не считается, "
        "даже через год; при этом «уже звонил» учитывает звонки с метками Google Ads, Facebook, Google SEO и без источника. Источник звонка — метка Ringostat (Facebook: utm_source facebook и utm_medium cpc; "
        "Google Ads: метка содержит google, dspl, kms или performance_max; если utm_campaign начинается с yt_ — YouTube). День звонка — по времени Варшавы.",
    19: "Формы: СЕАНСЫ Google Analytics 4 с событием form_submit, а не заявки из CRM. Источник сеанса: название кампании начинается с yt_ → YouTube; иначе google / cpc → Google Ads; любой источник со словом facebook (cpc, реферал facebook.com и т.п.) → Facebook; "
        "всё остальное (прямой заход, органика, реферал, не определён) → «Нет метки». Телефона в GA4 нет, поэтому звонок и форма одного человека не склеиваются и считаются оба. "
        "GA4 не видит формы без cookie: за 01.10–08.11 пару в GA4 нашли у 69% форм CRM, значит рекламных форм здесь меньше, чем в CRM (особенно Facebook).",
    20: "Конверсии = звонки + формы. «Нет метки» — только формы GA4 с неопознанным источником, звонков у неё нет. «Телефон» и «Прочее» в конверсиях и звонках не участвуют («—»). "
        "% конверсии и цена заявки считаются только у Google Ads и Facebook: у остальных строк нет кликов и расхода. В «Итого» конверсии — сумма Google Ads, YouTube, Facebook и «Нет метки», поэтому цена заявки в «Итого» = весь расход ÷ все четыре строки.",
    21: "Продажи — заказы из выгрузки CRM (лист mocnaszklarnia.pl). Единица — ЗАКАЗ: количества товара в CRM нет, поэтому одна строка = одна продажа (у клиента продажа считается штукой, "
        "заказ из двух штук у него = 2, так что цифра клиента может быть больше). "
        "Отмена после продажи или в тот же день: заказ не считается продажей. Отмена до даты продажи (отменили 4-го, продали 5-го): заказ считается продажей, так делает и клиент, пример: заказ 94230110. "
        "В нашем режиме наоборот: заказы, отменённые после продажи, входят в продажи, их число показано отдельно.",
    22: "Источник продажи — по правилу клиента, а не по первому обращению: в заказе есть форма → метка ПЕРВОЙ формы в CRM (Google Ads, YouTube или Facebook, любая другая или пустая → «Нет метки»). "
        "Формы нет, заказ создал менеджер после звонка → смотрим первую строку заказа: звонок с рекламной меткой (Google Ads, YouTube, Facebook) или с меткой «Телефон» → «Телефон», даже если звонок был рекламным; "
        "звонок без метки → «Нет метки» (на 64 общих заказах октября и 01–09.11 совпало с клиентом в 62; иногда менеджер выбирает источник вручную). "
        "Метка продажи берётся из CRM, а конверсии — из GA4, поэтому продаж у «Нет метки» может быть больше, чем конверсий, и «% продажи» тогда выше 100%.",
    23: "Какие заказы входят: действующие (см. выше), у которых есть форма, либо первое обращение номера за ВСЮ историю выгрузки (с 01.08.2025, окна 60 дней нет) не «Телефон» (звонок без рекламной метки) и не Google SEO. "
        "Заказ, начатый звонком без метки или с SEO-сайта szklarniaprofimet.pl, в рекламный дашборд клиента не берётся. Заказы с листов других сайтов (EkspertAgro) не входят.",
    24: "Период продажи — по колонке «Дата заказа» выгрузки CRM, а не по дате продажи: заказ, созданный в октябре и проданный в ноябре, идёт в октябрь (так считает клиент; сверка 01–08.11: наборы номеров заказов совпали). "
        "Для строк без этой колонки дата оценивается по первой строке заказа. Дата продажи вносится в CRM с опозданием, поэтому последние дни периода недосчитаны; прогноза «ожидается» в этом режиме нет.",
    25: "Формулы: % конверсии = Конверсии ÷ Клики; Цена заявки = Цена ÷ Конверсии; % продажи = Продажи ÷ Конверсии (штуки к заявкам, а не доля заявок, ставших продажами); Цена продажи = Цена ÷ Продажи; "
        "CTR = Клики ÷ Показы; Цена клика = Цена ÷ Клики. «Итого»: цена, клики, показы — Google Ads + YouTube + Facebook; конверсии и продажи — по всем строкам, включая «Нет метки» и «Телефон»; "
        "цена продажи в «Итого» = весь расход ÷ все продажи, как в клиентской вкладке, где все строки считаются платным каналом.",
    26: "Чем этот режим отличается от «Нашего»: звонки и отбор заказов — вся история с 01.08.2025 вместо окна 60 дней; формы — GA4 вместо CRM с проверкой; Facebook — любой источник со словом facebook вместо только cpc; "
        "продажи — заказы по схеме клиента, по «Дате заказа» и с источником «Телефон», вместо заказов по первому касанию в окне 60 дней только с рекламным источником. "
        "Источник у части заказов клиент выбирает вручную, поэтому у отдельных заказов он может отличаться от нашего расчёта.",
}


ROW = {s: 9 + i for i, s in enumerate(SOURCES)}   # строка источника на листе «Дашборд»: Google Ads 9, YouTube 10, Facebook 11, Нет метки 12, Телефон 13, Прочее 14
TOT = 9 + len(SOURCES)                              # строка «Итого» (15)
NOTE_SHIFT = 1                                      # пункт пояснений n (16…27) лежит в строке n + NOTE_SHIFT; строка 16 пустая

YT_NOTE = ("YouTube — отдельная строка (решение пользователя 2026-11-10). Признак: название кампании в Google Ads начинается с yt_ (расход, клики, показы) и utm_campaign начинается с yt_ "
           "(звонки Ringostat, формы CRM и GA4, продажи, у которых первое обращение с такой меткой). Эти данные вычтены из строки Google Ads. Кампания yt_warm идёт с 04.11, до этой даты строка пустая.")


def client_definitions():
    """Лист «Как считается»: подробное описание режима «как у клиента» (те же пункты, что под таблицей, без чисел за период)."""
    return ["РЕЖИМ «КАК У КЛИЕНТА» — подробно (переключатель в B7 листа «Дашборд»)"] + [CLIENT_TEXT[k] for k in range(16, 27)] + [YT_NOTE]


def _S(col, r, sep=","):
    """Сумма колонки листа «Данные» за выбранный период по источнику из ячейки A{r}."""
    return f"SUMIFS('Данные'!${col}:${col}{sep}'Данные'!$A:$A{sep}\">=\"&$B$3{sep}'Данные'!$A:$A{sep}\"<=\"&$B$4{sep}'Данные'!$B:$B{sep}$A{r})"


def client_notes(sep=","):
    """Выражения (без «=») для ветки «как у клиента» в пунктах 16…26. К статичному тексту добавлены числа за период из таблицы выше (колонки G «Конверсии», J «Звонки»)."""
    g, y, f, nm = ROW["Google Ads"], ROW["YouTube"], ROW["Facebook"], ROW["Нет метки"]
    t = {k: '"' + v + '"' for k, v in CLIENT_TEXT.items()}
    t[18] = t[18] + f'&" За период: звонков Google Ads "&J{g}&", YouTube "&J{y}&", Facebook "&J{f}&"."'
    t[19] = t[19] + f'&" За период: форм Google Ads "&(G{g}-J{g})&", YouTube "&(G{y}-J{y})&", Facebook "&(G{f}-J{f})&", Нет метки "&G{nm}&"."'
    return t


def notes_formulas(sep=","):
    """Формулы пояснений под таблицей: {номер строки: формула}. В нашем режиме — формы без метки, повторы, продажи; в режиме «как у клиента» — client_notes();
    пункт YouTube одинаков в обоих режимах. sep — разделитель аргументов (живая таблица: локаль ru → «;»)."""
    S = lambda col, src: _S(col, ROW[src], sep)
    cl = client_notes(sep)
    ad3 = lambda col: "+".join(S(col, s) for s in AD_SRC)
    every = lambda col: "+".join(S(col, s) for s in SOURCES)
    k_, m_, n_ = f'({ad3("L")})', S("M", "Нет метки"), S("N", "Нет метки")
    ours = {
        16: f'"Телефон: новых обращений "&{S("F", "Телефон")}&" (из них звонков "&{S("G", "Телефон")}&") — в «Конверсии» и «Звонки» не включены"',
        17: (f'"Нет метки: в заявки не входит. Форм без метки "&({k_}+{m_}+{n_})&": реклама найдена у "&{k_}&'
             f'" (добавлены к Google Ads / YouTube / Facebook), не реклама "&{m_}&", источник не найден "&{n_}&" (не засчитаны)"'),
        18: f'"Прочее: новых обращений "&{S("F", "Прочее")}&" — в «Конверсии» и «Звонки» не включены"',
        19: (f'"Повторы не засчитаны: "&({ad3("O")}+{S("O", "Нет метки")})&" (звонок и форма одного номера в пределах 60 дней: "&'
             f'({ad3("P")}+{S("P", "Нет метки")})&"); у каждого номера засчитано первое обращение"'),
        20: (f'"Facebook в нашем режиме — только cpc: звонки utm_source=facebook + utm_medium=cpc; формы с меткой Facebook только при utm_medium=cpc; '
             f'формы без метки только по GA4 facebook / cpc или адресу с utm_medium=cpc. Не засчитано форм Facebook не cpc: "&{S("Q", "Facebook")}&" (facebook / free, реферал facebook.com, fbclid без cpc не считаются)"'),
        21: '"Продажи считаются ЗАКАЗАМИ, не штуками: количества товара в выгрузке CRM нет. Формы в заявках — из выгрузки CRM (сервер), а не из Google Analytics 4"',
        22: (f'"Отменено после продажи: "&({every("R")})&" (в продажи входят; Google Ads "&{S("R", "Google Ads")}&", YouTube "&{S("R", "YouTube")}&", Facebook "&{S("R", "Facebook")}&'
             f'", Нет метки "&{S("R", "Нет метки")}&", Телефон "&{S("R", "Телефон")}&", Прочее "&{S("R", "Прочее")}&")"'),
        23: (f'"Рекламный контакт старше 60 дней, в источник не засчитан: "&({every("S")})&'
             f'" продаж (источник взят из окна 60 дней, по этим заказам он нерекламный)"'),
        24: (f'IFERROR("Продажи по дате первого касания (когорта). Ожидается "&ROUND(N{TOT}{sep}0)&", уже есть "&K{TOT}&" (созрело "&TEXT(K{TOT}/N{TOT}{sep}"0%")&"). '
             f'Прогноз = продажи когорты ÷ доля продаж, созревшая к её возрасту: {CURVE_TEXT}"{sep}"")'),
        25: (f'"Не включены в наш отчёт (первое касание в окне 60 дней не рекламное): Телефон "&{S("U", "Телефон")}&"; Нет метки "&{S("U", "Нет метки")}&'
             f'" (формы: не реклама "&{S("V", "Нет метки")}&", источник не найден "&{S("W", "Нет метки")}&"; звонки на номер сайта "&{S("X", "Нет метки")}&"); Прочее "&{S("U", "Прочее")}&'
             f'". Продаж «Нет метки», у которых проверка формы нашла рекламу и они добавлены к Google Ads / YouTube / Facebook: "&({ad3("Y")})'),
        26: '""',
    }
    out = {n + NOTE_SHIFT: f'=IF(LEFT($B$7{sep}3)="Как"{sep}{cl[n]}{sep}{ours[n]})' for n in ours}
    out[27 + NOTE_SHIFT] = '="' + YT_NOTE + '"'
    return out


def table_cells(sep=","):
    """Ячейки таблицы A9:M{TOT} листа «Дашборд» (значения и формулы) + колонки N, O (прогноз). Одна функция на xlsx (sep «,») и живую таблицу (sep «;»)."""
    cells = {}
    D = "—"
    S = lambda col, r: _S(col, r, sep)
    for src in SOURCES:
        r = ROW[src]
        paid, has_conv = src in AD_SRC, src in AD_SRC + ("Нет метки",)
        cells[f"A{r}"] = src
        cells[f"B{r}"] = (f"={S('C', r)}" + ("*$B$5" if src == "Facebook" else "")) if paid else D
        cells[f"C{r}"] = f"={S('D', r)}" if paid else D
        cells[f"D{r}"] = f"={S('E', r)}" if paid else D
        cells[f"E{r}"] = f'=IFERROR(B{r}/C{r}{sep}"")' if paid else D
        cells[f"F{r}"] = f'=IFERROR(C{r}/D{r}*100{sep}"")' if paid else D
        cells[f"G{r}"] = f'=IF(LEFT($B$7{sep}3)="Как"{sep}{S("I", r)}{sep}{S("F", r)})' if has_conv else D
        cells[f"H{r}"] = f'=IFERROR(G{r}/C{r}*100{sep}"")' if paid else D
        cells[f"I{r}"] = f'=IFERROR(B{r}/G{r}{sep}"")' if paid else D
        cells[f"J{r}"] = f'=IF(LEFT($B$7{sep}3)="Как"{sep}{S("J", r)}{sep}{S("G", r)})' if paid else D
        cells[f"K{r}"] = f'=IF(LEFT($B$7{sep}3)="Как"{sep}{S("K", r)}{sep}{S("H", r)})'
        cells[f"L{r}"] = f'=IFERROR(K{r}/G{r}*100{sep}"")' if has_conv else D
        cells[f"M{r}"] = f'=IFERROR(B{r}/K{r}{sep}"")' if paid else D
    g, f, nm, pr = ROW["Google Ads"], ROW["Facebook"], ROW["Нет метки"], ROW["Прочее"]
    T = TOT
    cells.update({f"A{T}": "Итого", f"B{T}": f"=SUM(B{g}:B{f})", f"C{T}": f"=SUM(C{g}:C{f})", f"D{T}": f"=SUM(D{g}:D{f})",
                  f"E{T}": f'=IFERROR(B{T}/C{T}{sep}"")', f"F{T}": f'=IFERROR(C{T}/D{T}*100{sep}"")', f"G{T}": f"=SUM(G{g}:G{nm})",
                  f"H{T}": f'=IFERROR(G{T}/C{T}*100{sep}"")', f"I{T}": f'=IFERROR(B{T}/G{T}{sep}"")', f"J{T}": f"=SUM(J{g}:J{f})",
                  f"K{T}": f"=SUM(K{g}:K{pr})", f"L{T}": f'=IFERROR(K{T}/G{T}*100{sep}"")', f"M{T}": f'=IFERROR(B{T}/K{T}{sep}"")'})
    cells.update(forecast_cells(sep))
    return cells


def forecast_cells(sep=","):
    """Колонки N и O листа «Дашборд»: N «Продажи, ожидается» = сумма Данные!T за период (только режим «Наш»); O «Цена продажи, ожидается» = расход ÷ N."""
    def S(r):
        return _S("T", r, sep)
    cells = {f"N{r}": f'=IF(LEFT($B$7{sep}3)="Как"{sep}""{sep}ROUND({S(r)}{sep}1))' for r in range(9, TOT)}
    cells[f"N{TOT}"] = f'=IF(LEFT($B$7{sep}3)="Как"{sep}""{sep}SUM(N9:N{TOT - 1}))'
    for r in range(9, TOT + 1):
        cells[f"O{r}"] = f'=IF(LEFT($B$7{sep}3)="Как"{sep}""{sep}IFERROR(B{r}/N{r}{sep}""))'
    return cells


def write_xlsx_dynamic(path, daily, usd_eur, frm, to, orders_tbl=None, diff_tbl=None):
    """Книга для Google Таблиц: «Дашборд» (выпадающий выбор периода + формулы), «Данные» (по дням), «Списки» (периоды), «Как считается»."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "Дашборд"
    wd = wb.create_sheet("Данные")
    wl = wb.create_sheet("Списки")
    wh = wb.create_sheet("Как считается")
    bold, head, inp = Font(bold=True), PatternFill("solid", fgColor="DDEBF7"), PatternFill("solid", fgColor="FFF2CC")

    # --- Данные
    wd.append(["Дата", "Источник", "Цена (Google — €, Facebook — $ как в BigQuery)", "Клики", "Показы", "Конверсии (наш режим: звонки Ringostat + формы CRM, одна лестница 60 дн)", "из них звонки (Ringostat)", "Продажи",
               "Конверсии (как у клиента: звонки + формы GA4)", "из них звонки (первый звонок за всю историю)",
               "Продажи (как у клиента: по правилу клиента, количество товара)",
               "Наш режим: формы без метки, реклама найдена (уже в конверсиях)", "Наш режим: формы без метки, не реклама (не засчитаны)",
               "Наш режим: формы без метки, источник не найден (не засчитаны)", "Наш режим: повторы за 60 дней (не засчитаны)",
               "Наш режим: из повторов — звонок и форма одного номера", "Наш режим: формы Facebook не cpc (не засчитаны)", "Наш режим: продажи, отменённые после продажи (входят в продажи)",
               "Наш режим: продажи, где рекламный контакт старше 60 дней (в источник не засчитан)",
               "Наш режим: продажи ожидается (прогноз по когорте)", "Наш режим: продажи не включены (первое касание не рекламное)",
               "Наш режим: из них «Нет метки» — форма, не реклама", "Наш режим: из них «Нет метки» — форма, источник не найден",
               "Наш режим: из них «Нет метки» — звонок на номер сайта", "Наш режим: продажи «Нет метки», реклама найдена проверкой формы (уже в продажах)"])
    for c in wd[1]:
        c.font, c.fill = bold, head
    for _, r in daily.iterrows():
        wd.append([r["Дата"], r["Источник"], r["Цена"], r["Клики"], r["Показы"], r["Конверсии"], r["Звонки"], r["Продажи"],
                   r["Конверсии_клиент"], r["Звонки_клиент"], r["Продажи_клиент"], r["Формы_восстановлены"], r["Формы_не_реклама"],
                   r["Формы_не_найдено"], r["Повторы"], r["Повторы_звонок_и_форма"], r["Формы_Facebook_не_cpc"], r["Продажи_отменены_позже"], r["Продажи_реклама_старше_60"], r["Продажи_ожидается"], r["Продажи_не_включены"], r["Продажи_НМ_форма_не_реклама"], r["Продажи_НМ_форма_не_найдена"], r["Продажи_НМ_звонок_сайт"], r["Продажи_восстановлены"]])
        wd.cell(wd.max_row, 1).number_format = "DD.MM.YYYY"
    wd.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJKLMNOPQRSTUVWXY", (12, 12, 22, 10, 12, 20, 14, 10, 24, 24, 28, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22)):
        wd.column_dimensions[col].width = w

    # --- Списки: готовые периоды (динамические от сегодняшней даты и статические месяцы/недели)
    wl.append(["Период", "Начало", "Конец"])
    for c in wl[1]:
        c.font, c.fill = bold, head
    dyn = [("Текущий месяц", "=DATE(YEAR(TODAY()),MONTH(TODAY()),1)", "=EOMONTH(TODAY(),0)"),
           ("Прошлый месяц", "=EOMONTH(TODAY(),-2)+1", "=EOMONTH(TODAY(),-1)"),
           ("Текущая неделя", "=TODAY()-WEEKDAY(TODAY(),2)+1", None),
           ("Прошлая неделя", "=TODAY()-WEEKDAY(TODAY(),2)-6", None),
           ("Последние 7 дней", "=TODAY()-7", "=TODAY()-1"),
           ("Последние 30 дней", "=TODAY()-30", "=TODAY()-1")]
    for label, b, e in dyn:
        wl.append([label, b, e if e else f"=B{wl.max_row + 1}+6"])
    f0, t0 = pd.Timestamp(frm), pd.Timestamp(to)
    wl.append([f"Весь период ({f0:%d.%m.%Y}–{t0:%d.%m.%Y})", f0.date(), t0.date()])
    for s, e, _ in periods(frm, to, "month"):
        wl.append([f"{MONTHS_RU[s.month - 1]} {s.year}", s, e])
    for s, e, _ in periods(frm, to, "week"):
        wl.append([f"Неделя {s:%d.%m}–{e:%d.%m.%Y}", s, e])
    wl.append(["Свой период", None, None])
    last_list = wl.max_row
    for row in wl.iter_rows(min_row=2, min_col=2, max_col=3):
        for c in row:
            c.number_format = "DD.MM.YYYY"
    wl.column_dimensions["A"].width = 34
    wl.column_dimensions["B"].width = wl.column_dimensions["C"].width = 14

    # --- Дашборд
    ws["A1"] = "ProfiMet: по источникам"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"], ws["B2"] = "Период (выберите из списка)", "Текущий месяц"
    ws["A3"], ws["B3"] = "Начало", '=IF($B$2="Свой период",$E$3,VLOOKUP($B$2,\'Списки\'!$A$2:$C$%d,2,FALSE))' % last_list
    ws["A4"], ws["B4"] = "Конец", ('=IF($B$2="Свой период",$E$4,MIN(VLOOKUP($B$2,\'Списки\'!$A$2:$C$%d,3,FALSE),MAX(\'Данные\'!$A:$A)))' % last_list)
    ws["D3"], ws["E3"] = "Свой период: начало", f0.date()
    ws["D4"], ws["E4"] = "Свой период: конец", t0.date()
    ws["A5"], ws["B5"] = "Курс USD→EUR для Facebook (допущение, можно менять)", usd_eur
    ws["A6"], ws["B6"] = "Данные есть по", "=MAX('Данные'!$A:$A)"
    ws["A7"], ws["B7"] = "Режим подсчёта конверсий и звонков", MODE_OUR
    for ref in ("B3", "B4", "B6", "E3", "E4"):
        ws[ref].number_format = "DD.MM.YYYY"
    for ref in ("B2", "E3", "E4", "B5", "B7"):
        ws[ref].fill = inp
    for ref in ("A2", "A3", "A4", "A5", "A6", "A7", "D3", "D4"):
        ws[ref].font = bold
    dv = DataValidation(type="list", formula1=f"='Списки'!$A$2:$A${last_list}", allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv)
    dv.add("B2")
    dv2 = DataValidation(type="list", formula1=f'"{MODE_OUR},{MODE_CLIENT}"', allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv2)
    dv2.add("B7")

    cols = ["Источник", "Цена", "Клики", "Показы", "Цена клика", "CTR %", "Конверсии", "% конверсии", "Цена заявки", "Звонки", "Продажи", "% продажи", "Цена продажи"]
    for j, c in enumerate(cols, 1):
        cell = ws.cell(8, j, c)
        cell.font, cell.fill, cell.alignment = bold, head, Alignment(horizontal="center", wrap_text=True)

    for ref, v in table_cells().items():
        ws[ref] = v
    for c in ws[TOT]:
        c.font = bold
    money, intf, pct = '#,##0.00 "€"', "#,##0", '0.00"%"'
    fm = {2: money, 5: money, 9: money, 13: money, 3: intf, 4: intf, 7: intf, 10: intf, 11: intf, 6: pct, 8: pct, 12: pct}
    for r in range(9, TOT + 1):
        for j, f in fm.items():
            ws.cell(r, j).number_format = f
            ws.cell(r, j).alignment = Alignment(horizontal="right")
    for r, f in notes_formulas().items():
        ws[f"A{r}"] = f
    ws["N8"] = "Продажи: ожидается (прогноз по когорте)"
    ws["N8"].font, ws["N8"].fill, ws["N8"].alignment = bold, head, Alignment(horizontal="center", wrap_text=True)
    ws["O8"] = "Цена продажи: ожидается (расход ÷ ожидаемые продажи)"
    ws["O8"].font, ws["O8"].fill, ws["O8"].alignment = bold, head, Alignment(horizontal="center", wrap_text=True)
    for r in range(9, TOT + 1):
        ws[f"N{r}"].number_format, ws[f"O{r}"].number_format = "#,##0", money
        ws[f"N{r}"].alignment = ws[f"O{r}"].alignment = Alignment(horizontal="right")
    ws[f"N{TOT}"].font = bold
    ws[f"O{TOT}"].font = bold
    ws.column_dimensions["N"].width = 16
    ws.column_dimensions["O"].width = 20
    ws.column_dimensions["A"].width = 46
    for col in "BCDEFGHIJKLM":
        ws.column_dimensions[col].width = 14
    ws.column_dimensions["D"].width = 22
    ws.row_dimensions[8].height = 32
    ws.freeze_panes = "A9"

    # --- Как считается
    wh.column_dimensions["A"].width = 150
    for t in DEFINITIONS + ["Курс USD→EUR для Facebook — ячейка B5 листа «Дашборд» (допущение; в BigQuery расход хранится в долларах).",
                            "Режим B7: «Наш» — звонки Ringostat и формы CRM в одной лестнице 60 дней на номер, формы без метки проверены по Supabase / Tilda / GA4 (подробно выше); «Как у клиента» — звонки: первый звонок номера за всю "
                            "историю Ringostat (входящие, отслеживаемые каналы), формы: сеансы GA4 form_submit по источнику сеанса (google / cpc → Google Ads, facebook* → Facebook, "
                            "остальное → Нет метки); подтверждено на двух периодах скринов клиента 2026-10-20. Продажи в режиме «Как у клиента»: источник заказа по правилу клиента (есть форма → источник формы, нет формы → «Телефон»), "
                            "период по колонке «Дата заказа» выгрузки CRM, количество товара из списка клиента, где он есть, иначе 1; в режиме «Наш» продажи по первому обращению за 60 дней (подробно режим «как у клиента» описан ниже).",
                            "Лист «Заказы по схеме клиента»: правила, которые использует клиент (как мы их поняли), применены к данным нашей выгрузки CRM. Поэтому в нём есть заказы, которых нет в дашборде клиента, и нет заказов клиента, которых нет в выгрузке CRM; все такие случаи с причинами на листе «Расхождения».",
                            "Период выбирается в ячейке B2 листа «Дашборд»; для «Свой период» даты вводятся в E3 и E4. «Текущий месяц» и «Текущая неделя» считаются "
                            "от сегодняшней даты, но данных нет позже даты, указанной в B6 (данные обновляются повторным запуском скрипта profimet_sources_dashboard.py)."]:
        wh.append([t])
        wh.cell(wh.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    for t in client_definitions():
        wh.append([t])
        wh.cell(wh.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
        if t.startswith("РЕЖИМ"):
            wh.cell(wh.max_row, 1).font = bold
    if orders_tbl is not None:
        wo = wb.create_sheet("Заказы по схеме клиента")
        wo.append(list(orders_tbl.columns))
        for c in wo[1]:
            c.font, c.fill = bold, head
        for row in orders_tbl.itertuples(index=False):
            wo.append(list(row))
        wo.freeze_panes = "A2"
        for i, w in enumerate((18, 10, 16, 40, 8, 22, 22, 14, 14, 30), 1):
            wo.column_dimensions[chr(64 + i)].width = w
    if diff_tbl is not None and len(diff_tbl):
        wr = wb.create_sheet("Расхождения")
        wr.append(list(diff_tbl.columns))
        for c in wr[1]:
            c.font, c.fill = bold, head
        for row in diff_tbl.itertuples(index=False):
            wr.append(list(row))
        wr.freeze_panes = "A2"
        for i, w in enumerate((26, 10, 18, 20, 22, 90, 22, 18), 1):
            wr.column_dimensions[chr(64 + i)].width = w
        for rr in wr.iter_rows(min_row=2):
            rr[5].alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


DASHBOARD_SHEET_ID = "1yQ4YnDv0M_XjXFt2XQLf0wZfLqCJYJ7mC_kCtA-8xAk"  # «ProfiMet — по источникам (дашборд)» в Google Диске пользователя; сервисному аккаунту выдан «Редактор»


def refresh_google_sheet(file_id, daily, frm, to):
    """Обновляет в Google Таблице только листы «Данные» и «Списки» (периоды) и диапазон выпадающего списка; лист «Дашборд»
    (выбранный период, свои даты, курс) не трогает. Нужен доступ «Редактор» сервисному аккаунту."""
    import datetime
    from google.auth.transport.requests import AuthorizedSession
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    s = AuthorizedSession(creds)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    ser = lambda d: (d - datetime.date(1899, 12, 30)).days
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]}

    import json

    def clean(v):  # NaN/None → пусто (JSON null), numpy → python
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return v.item() if hasattr(v, "item") else v

    # Сначала готовим и проверяем ВСЕ данные (json.dumps упадёт на NaN), и только потом очищаем листы: сбой не оставит таблицу пустой.
    rows = [[clean(x) for x in (ser(r["Дата"]), r["Источник"], r["Цена"], r["Клики"], r["Показы"], r["Конверсии"], r["Звонки"], r["Продажи"],
                                      r["Конверсии_клиент"], r["Звонки_клиент"], r["Продажи_клиент"],
                                      r["Формы_восстановлены"], r["Формы_не_реклама"], r["Формы_не_найдено"], r["Повторы"], r["Повторы_звонок_и_форма"], r["Формы_Facebook_не_cpc"], r["Продажи_отменены_позже"], r["Продажи_реклама_старше_60"], r["Продажи_ожидается"], r["Продажи_не_включены"], r["Продажи_НМ_форма_не_реклама"], r["Продажи_НМ_форма_не_найдена"], r["Продажи_НМ_звонок_сайт"], r["Продажи_восстановлены"])]
            for _, r in daily.iterrows()]
    f0, t0 = pd.Timestamp(frm), pd.Timestamp(to)
    st = [[f"Весь период ({f0:%d.%m.%Y}–{t0:%d.%m.%Y})", ser(f0.date()), ser(t0.date())]]
    st += [[f"{MONTHS_RU[sd.month - 1]} {sd.year}", ser(sd), ser(ed)] for sd, ed, _ in periods(frm, to, "month")]
    st += [[f"Неделя {sd:%d.%m}–{ed:%d.%m.%Y}", ser(sd), ser(ed)] for sd, ed, _ in periods(frm, to, "week")]
    st += [["Свой период", None, None]]
    json.dumps(rows), json.dumps(st)

    # Данные: очистить и записать заново (даты — числами: так таблица не зависит от локали)
    s.post(base + "/values/Данные!A2:Y5000:clear", json={}, timeout=60).raise_for_status()
    s.put(base + "/values/Данные!A2?valueInputOption=USER_ENTERED", json={"values": rows}, timeout=120).raise_for_status()

    # Списки: статическая часть (весь период, месяцы, недели, «Свой период») начиная с 8-й строки; динамические 2–7 не трогаем
    s.post(base + "/values/Списки!A8:C200:clear", json={}, timeout=60).raise_for_status()
    s.put(base + "/values/Списки!A8?valueInputOption=USER_ENTERED", json={"values": st}, timeout=60).raise_for_status()
    last = 7 + len(st)
    fmt = {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}}
    req = [{"setDataValidation": {"range": {"sheetId": ids["Дашборд"], "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": f"='Списки'!$A$2:$A${last}"}]}, "strict": True, "showCustomUi": True,
                     "inputMessage": "Выберите период из списка. Для произвольных дат выберите «Свой период» и впишите даты в E3 и E4."}}},
           {"repeatCell": {"range": {"sheetId": ids["Данные"], "startRowIndex": 1, "endRowIndex": len(rows) + 1, "startColumnIndex": 0, "endColumnIndex": 1},
                           "cell": fmt, "fields": "userEnteredFormat.numberFormat"}},
           {"repeatCell": {"range": {"sheetId": ids["Списки"], "startRowIndex": 1, "endRowIndex": last, "startColumnIndex": 1, "endColumnIndex": 3},
                           "cell": fmt, "fields": "userEnteredFormat.numberFormat"}}]
    s.post(base + ":batchUpdate", json={"requests": req}, timeout=60).raise_for_status()
    patch_live_dashboard(s, base, ids)
    return len(rows), last


def ensure_youtube_row(s, base, ids):
    """Если на листе «Дашборд» нет строки «YouTube» — вставляет пустую строку 10 (между Google Ads и Facebook) с форматом строки выше. Формулы потом пишутся из кода."""
    col = s.get(base + "/values/Дашборд!A9:A16", timeout=60).json().get("values", [])
    if any(r and r[0] == "YouTube" for r in col):
        return False
    s.post(base + ":batchUpdate", json={"requests": [{"insertDimension": {
        "range": {"sheetId": ids["Дашборд"], "dimension": "ROWS", "startIndex": ROW["YouTube"] - 1, "endIndex": ROW["YouTube"]}, "inheritFromBefore": True}}]},
        timeout=60).raise_for_status()
    return True


def write_dashboard_cells(s, base):
    """Таблица A9:O{TOT}, подписи N8/O8 и пояснения под таблицей — из кода (локаль таблицы ru_RU: разделитель аргументов «;»)."""
    cells = {**table_cells(";"), "N8": "Продажи: ожидается (прогноз по когорте)", "O8": "Цена продажи: ожидается (расход ÷ ожидаемые продажи)"}
    for r, f in notes_formulas(";").items():
        cells[f"A{r}"] = f
    data = [{"range": f"Дашборд!{ref}", "values": [[v]]} for ref, v in cells.items()]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()
    return len(cells)


def patch_live_dashboard(s, base, ids):
    """Точечно приводит живую таблицу к структуре кода БЕЗ пересборки (пересборка стирает вкладки «Платформы», «Заказы» и ручные правки):
    заголовки колонок «Данные», строка YouTube на листе «Дашборд» (если её ещё нет), таблица и пояснения из кода, подпись режима B7 и её выпадающий список, лист «Как считается»."""
    heads = ["Наш режим: формы без метки, реклама найдена (уже в конверсиях)", "Наш режим: формы без метки, не реклама (не засчитаны)",
             "Наш режим: формы без метки, источник не найден (не засчитаны)", "Наш режим: повторы за 60 дней (не засчитаны)",
             "Наш режим: из повторов — звонок и форма одного номера", "Наш режим: формы Facebook не cpc (не засчитаны)", "Наш режим: продажи, отменённые после продажи (входят в продажи)",
             "Наш режим: продажи, где рекламный контакт старше 60 дней (в источник не засчитан)",
             "Наш режим: продажи ожидается (прогноз по когорте)", "Наш режим: продажи не включены (первое касание не рекламное)",
             "Наш режим: из них «Нет метки» — форма, не реклама", "Наш режим: из них «Нет метки» — форма, источник не найден",
             "Наш режим: из них «Нет метки» — звонок на номер сайта", "Наш режим: продажи «Нет метки», реклама найдена проверкой формы (уже в продажах)"]
    s.put(base + "/values/Данные!L1?valueInputOption=USER_ENTERED", json={"values": [heads]}, timeout=60).raise_for_status()
    s.put(base + "/values/Данные!F1?valueInputOption=USER_ENTERED",
          json={"values": [["Конверсии (наш режим: звонки Ringostat + формы CRM, одна лестница 60 дн)"]]}, timeout=60).raise_for_status()
    b7 = s.get(base + "/values/Дашборд!B7", timeout=60).json().get("values", [[""]])[0][0]
    if b7.startswith("Наш"):
        s.put(base + "/values/Дашборд!B7?valueInputOption=USER_ENTERED", json={"values": [[MODE_OUR]]}, timeout=60).raise_for_status()
    inserted = ensure_youtube_row(s, base, ids)
    n = write_dashboard_cells(s, base)
    dash = ids["Дашборд"]
    s.post(base + ":batchUpdate", json={"requests": [
        {"repeatCell": {"range": {"sheetId": dash, "startRowIndex": 8, "endRowIndex": TOT, "startColumnIndex": 13, "endColumnIndex": 14},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}, "horizontalAlignment": "RIGHT"}},
                        "fields": "userEnteredFormat(numberFormat,horizontalAlignment)"}},
        {"repeatCell": {"range": {"sheetId": dash, "startRowIndex": 8, "endRowIndex": TOT, "startColumnIndex": 14, "endColumnIndex": 15},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00\" €\""}, "horizontalAlignment": "RIGHT"}},
                        "fields": "userEnteredFormat(numberFormat,horizontalAlignment)"}},
        {"repeatCell": {"range": {"sheetId": dash, "startRowIndex": TOT - 1, "endRowIndex": TOT, "startColumnIndex": 0, "endColumnIndex": 15},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}},
        {"setDataValidation": {"range": {"sheetId": dash, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 1, "endColumnIndex": 2},
                               "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": MODE_OUR}, {"userEnteredValue": MODE_CLIENT}]},
                                        "strict": True, "showCustomUi": True, "inputMessage": "Наш режим или «как у клиента» (звонки за всю историю + формы GA4)."}}}]},
        timeout=60).raise_for_status()
    patch_how_it_works(s, base, ids)
    return inserted, n


def patch_how_it_works(s, base, ids):
    """Лист «Как считается»: определения нашего режима, исправление фразы про режимы и подробное описание режима «как у клиента» в конце."""
    col = s.get(base + "/values/Как считается!A1:A40", timeout=60).json().get("values", [])
    new = {"Конверсии = звонки + формы.": DEFINITIONS[1], "Конверсии (наш режим": DEFINITIONS[1], "Звонки: звонки Google Ads": DEFINITIONS[2], "Продажи: проданные заказы": DEFINITIONS[3], "Продажи (наш режим)": DEFINITIONS[3]}
    for i, row in enumerate(col, 1):
        t = row[0] if row else ""
        if t.startswith("РЕЖИМ «КАК У КЛИЕНТА»"):
            break
        for key, val in new.items():
            if t.startswith(key):
                s.put(base + f"/values/Как считается!A{i}?valueInputOption=USER_ENTERED", json={"values": [[val]]}, timeout=60).raise_for_status()
        if t.startswith("Режим B7: «Наш»") and "Продажи в обоих режимах одинаковые (наше правило)." in t:
            fixed = t.replace("Продажи в обоих режимах одинаковые (наше правило).",
                              "Продажи в режиме «Как у клиента»: источник заказа по правилу клиента (есть форма → метка формы, нет формы → «Телефон»), период по колонке «Дата заказа» выгрузки CRM, "
                              "штуки товара; в режиме «Наш» — заказы по первому обращению за 60 дней. Подробно режим «как у клиента» описан ниже.")
            t = fixed  # запись — ниже, вместе с заменой про «лестницу 60 дней»
        if t.startswith("Режим B7: «Наш»"):
            s.put(base + f"/values/Как считается!A{i}?valueInputOption=USER_ENTERED",
                  json={"values": [[t.replace("«Наш» — звонки Google Ads и Facebook из Ringostat (боевое правило, уникальные за 60 дней), формы из выгрузки CRM (новые за 60 дней)",
                                              "«Наш» — звонки Ringostat и формы CRM в одной лестнице 60 дней на номер, формы без метки проверены по Supabase / Tilda / GA4 (подробно выше)")]]},
                  timeout=60).raise_for_status()
    # подробное описание режима «как у клиента» в конце листа «Как считается» (идемпотентно: перезаписывается с той же строки)
    first = next((n for n, row in enumerate(col, 1) if row and row[0].startswith("РЕЖИМ «КАК У КЛИЕНТА»")), len(col) + 2)
    defs = client_definitions()
    s.put(base + f"/values/Как считается!A{first}?valueInputOption=USER_ENTERED", json={"values": [[d] for d in defs]}, timeout=60).raise_for_status()
    wrap = [{"repeatCell": {"range": {"sheetId": ids["Как считается"], "startRowIndex": first - 1, "endRowIndex": first - 1 + len(defs), "startColumnIndex": 0, "endColumnIndex": 1},
                            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}}, "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
            {"repeatCell": {"range": {"sheetId": ids["Как считается"], "startRowIndex": first - 1, "endRowIndex": first, "startColumnIndex": 0, "endColumnIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}}]
    s.post(base + ":batchUpdate", json={"requests": wrap}, timeout=60).raise_for_status()


def patch_client_notes(file_id):
    """Только пояснения под таблицей и лист «Как считается» — без обновления данных и без пересборки (решение 2026-11-10: режим «как у клиента»
    описан так же подробно, как «Наш»). Текст кривой созревания для пункта про когорту берётся из живой формулы, поэтому прежнее пояснение нашего режима не теряется."""
    import re as _re
    global CURVE_TEXT
    from google.auth.transport.requests import AuthorizedSession
    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]}
    row24 = 24 + NOTE_SHIFT
    a24 = s.get(base + f"/values/Дашборд!A{row24}", params={"valueRenderOption": "FORMULA"}, timeout=60).json().get("values", [[""]])[0][0]
    m = _re.search(r'созревшая к её возрасту: (.*?)"[;,]""\)\)', a24, _re.S)
    if not m:
        raise SystemExit(f"A{row24}: не нашёл текст кривой созревания в живой формуле (проверьте, что строка YouTube уже вставлена), ничего не записано")
    CURVE_TEXT = m.group(1)
    cells = notes_formulas(";")
    data = [{"range": f"Дашборд!A{r_}", "values": [[f_]]} for r_, f_ in cells.items()]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()
    patch_how_it_works(s, base, ids)
    return sorted(cells)


def periods(frm, to, by):
    f, t = pd.Timestamp(frm), pd.Timestamp(to)
    if by == "month":
        cur = f
        while cur <= t:
            end = min((cur + pd.offsets.MonthEnd(0)), t)
            yield cur.date(), end.date(), cur.strftime("%Y-%m")
            cur = end + pd.Timedelta(days=1)
    elif by == "week":
        cur = f - pd.Timedelta(days=f.weekday())
        while cur <= t:
            s, e = max(cur, f), min(cur + pd.Timedelta(days=6), t)
            yield s.date(), e.date(), f"неделя {cur.strftime('%d.%m')}"
            cur += pd.Timedelta(days=7)


def rebuild_google_sheet(file_id, xlsx_path):
    """Полная пересборка Google Таблицы из xlsx (структура листов и формул): загрузка через Drive API с конвертацией, затем то, что
    конвертация теряет: русская локаль и часовой пояс, выпадающие списки периода (B2) и режима (B7), формат дат. Выбор периода/режима
    возвращается к значениям по умолчанию. Нужен доступ «Редактор» сервисному аккаунту."""
    import json
    from google.auth.transport.requests import AuthorizedSession
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/drive"])
    s = AuthorizedSession(creds)
    b = "xxBOUNDARYxx"
    body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + json.dumps({"mimeType": "application/vnd.google-apps.spreadsheet"}) +
            f"\r\n--{b}\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode() + open(xlsx_path, "rb").read() \
        + f"\r\n--{b}--".encode()
    s.patch(f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=multipart&supportsAllDrives=true", data=body,
            headers={"Content-Type": f"multipart/related; boundary={b}"}, timeout=180).raise_for_status()
    s2 = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    meta = s2.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in meta["sheets"]}
    n = len(s2.get(base + "/values/Списки!A2:A200", timeout=60).json()["values"])
    dash = ids["Дашборд"]
    msg = "Выберите период из списка. Для произвольных дат выберите «Свой период» и впишите даты в E3 и E4."
    req = [{"updateSpreadsheetProperties": {"properties": {"locale": "ru_RU", "timeZone": "Europe/Warsaw"}, "fields": "locale,timeZone"}},
           {"setDataValidation": {"range": {"sheetId": dash, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": f"='Списки'!$A$2:$A${n + 1}"}]}, "strict": True, "showCustomUi": True,
                     "inputMessage": msg}}},
           {"setDataValidation": {"range": {"sheetId": dash, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": MODE_OUR}, {"userEnteredValue": MODE_CLIENT}]},
                     "strict": True, "showCustomUi": True, "inputMessage": "Наш режим или «как у клиента» (звонки за всю историю + формы GA4)."}}},
           {"repeatCell": {"range": {"sheetId": dash, "startRowIndex": 2, "endRowIndex": 4, "startColumnIndex": 4, "endColumnIndex": 5},
                           "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}}, "fields": "userEnteredFormat.numberFormat"}}]
    s2.post(base + ":batchUpdate", json={"requests": req}, timeout=60).raise_for_status()
    return n


CLIENT_CALLS = None   # строки звонков «как у клиента» (первый звонок номера с 01.08.2025), заполняет client_like_daily — нужны для списка заявок


def _phone_fmt(x):
    dg = re.sub(r"\D", "", str(x or ""))
    return ("+" + dg) if dg else ""


def build_leads(ours, ringo, sheet, ga4f, frm, to):
    """Список заявок для листа «Заявки_данные» (решение пользователя 2026-11-10). Одна строка = заявка, колонки A…K:
    A дата, B время (Варшава), C тип, D телефон, E номер заявки (звонок — Ringostat uniqueid, форма — номер заказа CRM, 8 знаков), F и G — формулы листа (источник и количество по выбранному режиму),
    H кампания (utm_campaign), I источник в нашем режиме («» — не засчитана), J источник «как у клиента», K количество «как у клиента».
    Звонки — по uniqueid в обоих режимах; формы нашего режима — строки CRM; формы «как у клиента» — сеансы GA4 (телефона в GA4 нет): строка = день × источник с количеством."""
    f0, t0 = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
    ser = lambda dd: (dd - date(1899, 12, 30)).days
    rg = ringo.assign(uid=ringo["uniqueid"].astype(str)).drop_duplicates("uid").set_index("uid")
    oc = ours.counted[ours.counted["type"] == "звонок"]
    our_call = dict(zip(oc["id"].astype(str), oc["final"]))
    cli_call = dict(zip(CLIENT_CALLS["uniqueid"].astype(str), CLIENT_CALLS["category"])) if CLIENT_CALLS is not None else {}
    rows = []
    for uid in set(our_call) | set(cli_call):
        if uid not in rg.index:
            continue
        r = rg.loc[uid]
        ts = r["ts"].tz_convert(W)
        if not (f0 <= ts.date() <= t0):
            continue
        rows.append([ser(ts.date()), f"{ts:%H:%M}", "звонок", _phone_fmt(r["caller"]), uid, "", "", r["utm_campaign"] or "", our_call.get(uid, ""), cli_call.get(uid, ""), 1 if uid in cli_call else ""])
    shf = sheet[(sheet["site"] == SITE) & (sheet["type"] == "форма")].copy()
    shf["id"] = shf["ts_raw"].astype(str) + "|" + shf["phone"].astype(str)
    shf = shf.drop_duplicates("id").set_index("id")
    of = ours.counted[ours.counted["type"] == "форма"]
    for fid, src in zip(of["id"], of["final"]):
        if fid not in shf.index:
            continue
        r = shf.loc[fid]
        ts = r["ts"].tz_convert(W)
        if f0 <= ts.date() <= t0:
            rows.append([ser(ts.date()), f"{ts:%H:%M}", "форма (CRM)", _phone_fmt(r["phone"]), str(r["order"])[:8], "", "", r["utm_campaign"] or "", src, "", ""])
    for x in ga4f[ga4f["forms_c"] > 0].itertuples():
        if f0 <= x.day <= t0:
            rows.append([ser(x.day), "", "форма (GA4, без телефона)", "", "", "", "", "", "", x.src2, int(x.forms_c)])
    rows.sort(key=lambda z: (z[0], z[1], z[2]))
    return rows


LEADS_HEAD = ["Дата", "Время", "Тип", "Телефон", "Номер заявки", "Источник (по режиму)", "Кол-во (по режиму)", "Кампания", "Источник: наш режим", "Источник: как у клиента", "Кол-во: как у клиента"]


def write_leads_tabs(file_id, rows):
    """Листы «Заявки_данные» (плоская таблица) и «Заявки» (список за период и по режиму листа «Дашборд», формулы FILTER). Остальные листы не трогает."""
    from google.auth.transport.requests import AuthorizedSession
    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]}
    need = [n for n in ("Заявки", "Заявки_данные") if n not in ids]
    if need:
        s.post(base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": n}}} for n in need]}, timeout=60).raise_for_status()
        ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]}
    D, L = "Заявки_данные", "Заявки"
    n = len(rows)
    # --- данные (RAW: телефоны остаются текстом); F и G — формулы одной ячейкой на столбец
    s.post(base + f"/values/{D}!A1:K10000:clear", json={}, timeout=60).raise_for_status()
    body = [LEADS_HEAD] + [[None if i in (5, 6) else v for i, v in enumerate(r)] for r in rows]   # F и G заполняет ARRAYFORMULA: пустые строки "" в них блокируют разворот массива
    s.put(base + f"/values/{D}!A1?valueInputOption=RAW", json={"values": body}, timeout=120).raise_for_status()
    for col, f in (("F", '=ARRAYFORMULA(IF(A2:A="";"";IF(LEFT(Дашборд!$B$7;3)="Как";J2:J;I2:I)))'),
                   ("G", '=ARRAYFORMULA(IF(A2:A="";"";IF(LEFT(Дашборд!$B$7;3)="Как";K2:K;IF(I2:I<>"";1;""))))')):
        s.put(base + f"/values/{D}!{col}2?valueInputOption=USER_ENTERED", json={"values": [[f]]}, timeout=60).raise_for_status()
    # --- список
    s.post(base + f"/values/{L}!A1:K5000:clear", json={}, timeout=60).raise_for_status()
    cells = {
        "A1": "ProfiMet: список заявок за период (период и режим выбираются на листе «Дашборд»: B2, B3, B4, B7)",
        "A2": '="Период: "&TEXT(Дашборд!B3;"dd.mm.yyyy")&" — "&TEXT(Дашборд!B4;"dd.mm.yyyy")&" · режим: "&Дашборд!B7',
        "A3": "Заявок в списке (штук)", "B3": "=SUM(G7:G)",
        "A4": "«Конверсии» в таблице «Дашборд», Итого", "B4": f"=Дашборд!G{TOT}",
        "A5": '=IF(B3=B4;"Сходится с таблицей «Дашборд»";"НЕ СХОДИТСЯ с таблицей «Дашборд», разница "&(B3-B4))',
        "J2": "Наш режим: звонки Google Ads / YouTube / Facebook и формы CRM по правилу 60 дней (одна лестница на номер, формы без метки проверены по Supabase / Tilda / GA4). Номер заявки: звонок — Ringostat uniqueid, форма — номер заказа CRM (8 знаков).",
        "J3": "Как у клиента: первый звонок номера с 01.08.2025; формы — сеансы GA4 form_submit, в GA4 нет телефона, поэтому строка «форма (GA4, без телефона)» = день × источник, число форм в колонке «Кол-во». «Нет метки» есть только в этом режиме.",
        "J4": "Данные обновляются запуском profimet_sources_dashboard.py --update-sheet (до даты в «Дашборд»!B6). Плоская таблица — лист «Заявки_данные».",
        "A6": "Дата", "B6": "Время", "C6": "Тип", "D6": "Телефон", "E6": "Номер заявки", "F6": "Источник", "G6": "Кол-во", "H6": "Кампания",
        "A7": f"=IFERROR(SORT(FILTER('{D}'!A2:H;'{D}'!A2:A>=Дашборд!B3;'{D}'!A2:A<=Дашборд!B4;'{D}'!F2:F<>\"\");1;FALSE;2;FALSE);\"Нет заявок за период\")",
    }
    data = [{"range": f"{L}!{ref}", "values": [[v]]} for ref, v in cells.items()]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()
    rng = lambda sid, r0, r1, c0, c1: {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}
    dt = {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}}
    bold = {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.867, "green": 0.922, "blue": 0.969}}}
    widths = [(0, 95), (1, 60), (2, 190), (3, 120), (4, 250), (5, 110), (6, 80), (7, 260)]
    req = [{"repeatCell": {"range": rng(ids[L], 6, 5000, 0, 1), "cell": dt, "fields": "userEnteredFormat.numberFormat"}},
           {"repeatCell": {"range": rng(ids[D], 1, 10000, 0, 1), "cell": dt, "fields": "userEnteredFormat.numberFormat"}},
           {"repeatCell": {"range": rng(ids[L], 5, 6, 0, 8), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
           {"repeatCell": {"range": rng(ids[D], 0, 1, 0, 11), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
           {"repeatCell": {"range": rng(ids[L], 0, 1, 0, 1), "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}}, "fields": "userEnteredFormat.textFormat"}},
           {"updateSheetProperties": {"properties": {"sheetId": ids[L], "gridProperties": {"frozenRowCount": 6}}, "fields": "gridProperties.frozenRowCount"}},
           {"updateSheetProperties": {"properties": {"sheetId": ids[D], "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}}]
    req += [{"updateDimensionProperties": {"range": {"sheetId": ids[L], "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}, "properties": {"pixelSize": w}, "fields": "pixelSize"}} for i, w in widths]
    s.post(base + ":batchUpdate", json={"requests": req}, timeout=60).raise_for_status()
    return n


ORDERS_HEAD = ["Дата (по режиму)", "Заказ", "Телефон", "Источник (по режиму)", "Кол-во (по режиму)", "Дата продажи", "Дата отмены",
               "Дата заказа (как у клиента)", "Дата первого касания (наш)", "Источник: наш режим", "Источник: как у клиента", "Кол-во: как у клиента"]


def build_orders(sales, scheme, sheet, frm, to):
    """Список ЗАКАЗОВ для листа «Заказы_данные» (решение пользователя 2026-11-10: только данные выгрузки CRM, ручные списки клиента в таблицу не попадают).
    Строка = заказ; колонки A…L: A дата, D источник, E количество — формулы листа по режиму (в строки пишутся пустыми), B номер заказа (8 знаков), C телефон (первая строка заказа в CRM),
    F дата продажи (самая ранняя в CRM), G дата отмены (самая поздняя в CRM), H дата заказа «как у клиента» (колонка «Дата заказа» CRM, для старых строк оценка), I дата первого касания
    в нашем режиме, J источник в нашем режиме («» — не входит), K источник по схеме клиента («» — не входит), L штуки по схеме клиента (в CRM количества нет: 1 на заказ).
    В список входят заказы, у которых дата по режиму ИЛИ дата продажи попадает в [frm, to]: так видны продажи периода, отнесённые к предыдущему."""
    f0, t0 = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
    ser = lambda dd: (dd - date(1899, 12, 30)).days
    inr = lambda dd: dd is not None and f0 <= dd <= t0
    info = {}
    for order, g in sheet[(sheet["site"] == SITE) & (sheet["order"] != "")].groupby("order"):
        sd, cd = [x for x in g["sale_date"] if x], [x for x in g["cancel_date"] if x]
        info[str(order)[:8]] = (g.sort_values("ts", kind="mergesort").iloc[0]["phone"], pd.Timestamp(min(sd)).date() if sd else None, pd.Timestamp(max(cd)).date() if cd else None)
    ours = {str(r.order)[:8]: r for r in sales[sales["counted"]].itertuples() if inr(r.touch_date) or inr(r.sale_date)}
    cli = {r.key: r for r in scheme.itertuples() if inr(r.est.date()) or inr(pd.Timestamp(r.sale).date() if r.sale else None)}
    rows = []
    for k in sorted(set(ours) | set(cli)):
        o, c = ours.get(k), cli.get(k)
        phone, sale, canc = info.get(k, ("", None, None))
        est_d = c.est.date() if c is not None else None
        rows.append([None, k, _phone_fmt(phone), None, None, ser(sale) if sale else None, ser(canc) if canc else None,
                     ser(est_d) if est_d else None, ser(o.touch_date) if o is not None else None, o.src2 if o is not None else "", c.rule if c is not None else "", int(c.qty) if c is not None else None])
    rows.sort(key=lambda z: (z[7] or z[8] or 0, z[1]))
    return rows


def write_orders_tabs(file_id, rows):
    """Листы «Заказы_данные» (плоская таблица) и «Заказы за период» (список по периоду и режиму листа «Дашборд», FILTER; справа — продажи периода, отнесённые к предыдущему).
    Старый лист «Заказы» (profimet_orders_list.py) не трогает."""
    from google.auth.transport.requests import AuthorizedSession
    s = AuthorizedSession(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    meta = lambda: {x["properties"]["title"]: x["properties"]["sheetId"] for x in s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]}
    ids = meta()
    need = [n for n in ("Заказы за период", "Заказы_данные") if n not in ids]
    if need:
        s.post(base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": n}}} for n in need]}, timeout=60).raise_for_status()
        ids = meta()
    D, L = "Заказы_данные", "Заказы за период"
    s.post(base + f"/values/{D}!A1:Z10000:clear", json={}, timeout=60).raise_for_status()
    body = [ORDERS_HEAD] + [[None if i in (0, 3, 4) else v for i, v in enumerate(r)] for r in rows]   # A, D, E — ARRAYFORMULA: значения в них блокируют разворот массива
    s.put(base + f"/values/{D}!A1?valueInputOption=RAW", json={"values": body}, timeout=120).raise_for_status()
    cl = 'LEFT(Дашборд!$B$7;3)="Как"'
    for col, f in (("A", f'=ARRAYFORMULA(IF(B2:B="";"";IF({cl};H2:H;I2:I)))'),
                   ("D", f'=ARRAYFORMULA(IF(B2:B="";"";IF({cl};K2:K;J2:J)))'),
                   ("E", f'=ARRAYFORMULA(IF(B2:B="";"";IF({cl};L2:L;IF(J2:J<>"";1;""))))')):
        s.put(base + f"/values/{D}!{col}2?valueInputOption=USER_ENTERED", json={"values": [[f]]}, timeout=60).raise_for_status()
    s.post(base + f"/values/{L}!A1:T5000:clear", json={}, timeout=60).raise_for_status()
    q = f"'{D}'"
    cells = {
        "A1": "ProfiMet: список заказов за период (период и режим выбираются на листе «Дашборд»: B2, B3, B4, B7). Только данные выгрузки CRM.",
        "A2": '="Период: "&TEXT(Дашборд!B3;"dd.mm.yyyy")&" — "&TEXT(Дашборд!B4;"dd.mm.yyyy")&" · режим: "&Дашборд!B7',
        "A3": "Заказов в списке (штук)", "B3": "=SUM(E7:E)",
        "A4": "«Продажи» в таблице «Дашборд», Итого", "B4": f"=Дашборд!K{TOT}",
        "A5": '=IF(B3=B4;"Сходится с таблицей «Дашборд»";"НЕ СХОДИТСЯ с таблицей «Дашборд», разница "&(B3-B4))',
        "K2": "Как у клиента: заказы по схеме клиента, дата — «Дата заказа» CRM, одна строка = один заказ (количества товара в CRM нет). Наш режим: заказы с рекламным первым касанием в окне 60 дней, дата — день первого касания.",
        "K3": "Слева — заказы, отнесённые к выбранному периоду. Справа — заказы, проданные в выбранном периоде, но отнесённые к предыдущему (по режиму: дата заказа или дата первого касания раньше начала периода).",
        "K4": "Данные обновляются запуском profimet_sources_dashboard.py --update-sheet. Плоская таблица — лист «Заказы_данные». Старый лист «Заказы» — отдельная таблица для сверки.",
        "K5": '="Продано в периоде, но отнесено к предыдущему: "&SUM(O7:O)&" шт."',
        "A6": "Дата", "B6": "Заказ", "C6": "Телефон", "D6": "Источник", "E6": "Кол-во", "F6": "Дата продажи", "G6": "Дата отмены",
        "K6": "Отнесён к дате", "L6": "Заказ", "M6": "Телефон", "N6": "Источник", "O6": "Кол-во", "P6": "Дата продажи", "Q6": "Дата отмены",
        "A7": f"=IFERROR(SORT(FILTER({q}!A2:G;{q}!A2:A>=Дашборд!B3;{q}!A2:A<=Дашборд!B4;{q}!D2:D<>\"\");1;FALSE;2;TRUE);\"Нет заказов за период\")",
        "K7": f"=IFERROR(SORT(FILTER({q}!A2:G;{q}!F2:F>=Дашборд!B3;{q}!F2:F<=Дашборд!B4;{q}!A2:A<Дашборд!B3;{q}!D2:D<>\"\");1;FALSE;2;TRUE);\"Нет таких заказов\")",
    }
    data = [{"range": f"{L}!{ref}", "values": [[v]]} for ref, v in cells.items()]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()
    rng = lambda sid, r0, r1, c0, c1: {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}
    dt = {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}}
    bold = {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.867, "green": 0.922, "blue": 0.969}}}
    req = []
    for c in (0, 5, 6, 10, 15, 16):
        req.append({"repeatCell": {"range": rng(ids[L], 6, 5000, c, c + 1), "cell": dt, "fields": "userEnteredFormat.numberFormat"}})
    for c in (0, 5, 6, 7, 8):
        req.append({"repeatCell": {"range": rng(ids[D], 1, 10000, c, c + 1), "cell": dt, "fields": "userEnteredFormat.numberFormat"}})
    req += [{"repeatCell": {"range": rng(ids[L], 5, 6, 0, 7), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
            {"repeatCell": {"range": rng(ids[L], 5, 6, 10, 17), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
            {"repeatCell": {"range": rng(ids[D], 0, 1, 0, 12), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
            {"repeatCell": {"range": rng(ids[L], 0, 1, 0, 1), "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}}, "fields": "userEnteredFormat.textFormat"}},
            {"repeatCell": {"range": rng(ids[L], 4, 5, 10, 11), "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat"}},
            {"updateSheetProperties": {"properties": {"sheetId": ids[L], "gridProperties": {"frozenRowCount": 6}}, "fields": "gridProperties.frozenRowCount"}},
            {"updateSheetProperties": {"properties": {"sheetId": ids[D], "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}}]
    req += [{"updateDimensionProperties": {"range": {"sheetId": ids[L], "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}, "properties": {"pixelSize": w}, "fields": "pixelSize"}}
            for i, w in ((0, 95), (1, 90), (2, 120), (3, 110), (4, 70), (5, 100), (6, 100), (7, 40), (8, 40), (9, 40), (10, 110), (11, 90), (12, 120), (13, 110), (14, 70), (15, 100), (16, 100))]
    s.post(base + ":batchUpdate", json={"requests": req}, timeout=60).raise_for_status()
    return len(rows)


def main():
    global MATURITY, CURVE_TEXT
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--to", dest="to", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--by", choices=["month", "week"], default=None)
    ap.add_argument("--usd-eur", type=float, default=0.8244,
                    help="курс для расхода Facebook (в BigQuery — доллары); 0.8244 — курс, который даёт расход клиентского дашборда (509.12 € = 617.56 $ × 0.8244, "
                         "01.10–19.10.2026); допущение, не рыночный курс")
    ap.add_argument("--cache", default=None, help="pickle (sheet, ringo_full), как у profimet_season_audit.py")
    ap.add_argument("--no-open", action="store_true", help="не открывать страницу в браузере после запуска")
    ap.add_argument("--client-list", nargs="+", default=None, help="списки продаж дашборда клиента (TSV, можно несколько за разные периоды): дают количество товара, товар, площадку, автора и лист «Расхождения»")
    ap.add_argument("--update-sheet", nargs="?", const=DASHBOARD_SHEET_ID, default=None, metavar="ID",
                    help="обновить данные в Google Таблице дашборда (по умолчанию — «ProfiMet — по источникам (дашборд)»): листы «Данные» и «Списки»")
    ap.add_argument("--patch-client-notes", nargs="?", const=DASHBOARD_SHEET_ID, default=None, metavar="ID",
                    help="только пояснения под таблицей (A16:A26) и лист «Как считается» в Google Таблице дашборда; данные не читаются и не обновляются")
    ap.add_argument("--rebuild-sheet", nargs="?", const=DASHBOARD_SHEET_ID, default=None, metavar="ID",
                    help="полностью пересобрать Google Таблицу из xlsx (если менялась структура формул); выбор периода и режима сбрасывается")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.patch_client_notes:
        rows = patch_client_notes(a.patch_client_notes)
        print(f"Пояснения записаны в Дашборд!A{rows[0]}:A{rows[-1]} и в лист «Как считается»: https://docs.google.com/spreadsheets/d/{a.patch_client_notes}/edit")
        return

    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    ringo, sheet, n_yt_calls, n_yt_rows = tag_youtube(ringo, sheet)  # YouTube — utm_campaign yt_* (решение пользователя 2026-11-10)
    print(f"YouTube (utm_campaign yt_*): звонков Ringostat {n_yt_calls}, строк CRM {n_yt_rows}")
    ads, fb = ads_daily_split(a.frm, a.to), fb_daily(a.frm, a.to)
    contacts, sales = contacts_with_new_flag(sheet), sales_with_source(sheet)
    sales = apply_sales_form_check(sales)  # проверка форм «Нет метки» у продаж и отбор рекламных продаж (наш режим)
    _c = sales[(sales["touch_date"] >= date(2026, 8, 1)) & (sales["touch_date"] <= pd.Timestamp(a.to).date())]
    print("Продажи нашего режима (касание с 01.08): рекламных", int(_c["counted"].sum()), "из", len(_c), "| не включены:", _c[~_c["counted"]]["reason"].value_counts().to_dict(),
          "| «Нет метки» → реклама:", int(_c["restored"].sum()))
    MATURITY, CURVE_TEXT, n_mature = maturity_curve(sales, a.to)  # прогноз по когорте: доля продаж, созревшая к возрасту k дней
    print(f"Созревание продаж (по {n_mature} заказам): " + CURVE_TEXT)
    chk = sales[(sales['sale_date'] >= pd.Timestamp(a.frm).date()) & (sales['sale_date'] <= pd.Timestamp(a.to).date())]
    print(f"КОНТРОЛЬ ДАННЫХ: заказов, у которых «Дата заказа» раньше даты первого касания (к заказу привязаны более поздние звонки): {int(chk['od_before_touch'].sum())} из {len(chk)} проданных в периоде")
    client = client_like_daily(ringo, ga4_forms_daily(a.frm, a.to))
    ours = our_leads(ringo, sheet, a.to, GA4_KEY, GA4_PROPERTY)  # звонки Ringostat + формы CRM, одна лестница 60 дн; формы без метки проверены по Supabase/Tilda/GA4

    out_dir = client_stats_dir("ProfiMet")
    total = build(a.frm, a.to, ads, fb, contacts, sales, a.usd_eur, ours=ours)
    total_c = build(a.frm, a.to, ads, fb, contacts, sales, a.usd_eur, client=client, mode="client")
    show(total, f"ПО-НАШЕМУ (60 дней без дублей), {a.frm} — {a.to}")
    show(total_c, f"КАК У КЛИЕНТА (звонки за всю историю, формы GA4), {a.frm} — {a.to}")
    total.to_csv(out_dir / f"dashboard_sources_{a.frm}_{a.to}.csv", index=False, encoding="utf-8-sig")
    total_c.to_csv(out_dir / f"dashboard_sources_client_mode_{a.frm}_{a.to}.csv", index=False, encoding="utf-8-sig")
    if a.by:
        for s, e, label in periods(a.frm, a.to, a.by):
            show(build(s, e, ads, fb, contacts, sales, a.usd_eur, ours=ours), f"{label} (наш): {s} — {e}")
            show(build(s, e, ads, fb, contacts, sales, a.usd_eur, client=client, mode="client"), f"{label} (как у клиента): {s} — {e}")

    # страница: весь период и каждый месяц в обоих режимах, открывается в браузере
    frames = [(f"Весь период, наш режим: {a.frm} — {a.to}", total), (f"Весь период, как у клиента: {a.frm} — {a.to}", total_c)]
    for s, e, label in periods(a.frm, a.to, "month"):
        frames.append((f"{label}, наш режим: {s} — {e}", build(s, e, ads, fb, contacts, sales, a.usd_eur, ours=ours)))
        frames.append((f"{label}, как у клиента: {s} — {e}", build(s, e, ads, fb, contacts, sales, a.usd_eur, client=client, mode="client")))
    meta = (f"Данные выгрузки CRM до {sheet['ts'].max().tz_convert(W):%d.%m.%Y %H:%M}; расход Facebook — BigQuery (доллары) × {a.usd_eur} "
            f"(курс — параметр); сформировано {pd.Timestamp.now(tz=W):%d.%m.%Y %H:%M}.")
    html_path = out_dir / f"dashboard_sources_{a.frm}_{a.to}.html"
    write_html(html_path, frames, meta)
    xlsx_path = out_dir / f"dashboard_sources_{a.frm}_{a.to}.xlsx"
    cl = read_client_list(a.client_list) if a.client_list else None
    scheme_all, diff = client_scheme_orders(sheet, cl, None, None)   # все заказы схемы клиента: нужны листу заказов (продажи периода, отнесённые к предыдущему)
    _f0, _t0 = pd.Timestamp(a.frm).date(), pd.Timestamp(a.to).date()
    scheme = scheme_all[(scheme_all["day"] >= _f0) & (scheme_all["day"] <= _t0)]
    daily = daily_table(a.frm, a.to, ads, fb, contacts, sales, client, scheme, ours=ours)
    orders_tbl = scheme.merge(cl, on="key", how="left") if cl is not None else scheme.assign(product="", platform="", author="", client_source="")
    orders_tbl = orders_tbl.sort_values("est", ascending=False)
    orders_tbl = pd.DataFrame({
        "Дата заказа (CRM; иначе оценка) UTC": orders_tbl["est"].dt.strftime("%Y-%m-%d %H:%M"), "Заказ": orders_tbl["key"],
        "Телефон": orders_tbl["phone"], "Товар": orders_tbl["product"].fillna(""), "Кол-во": orders_tbl["qty_x"] if "qty_x" in orders_tbl else orders_tbl["qty"],
        "Наш расчёт: источник заказа по схеме клиента": orders_tbl["rule"], "Дашборд клиента: источник заказа": orders_tbl["client_source"].fillna(""),
        "Есть у клиента": ["да" if (isinstance(x, str) and x) else "нет" for x in orders_tbl["client_source"]] if cl is not None else "",
        "Площадка": orders_tbl["platform"].fillna(""), "Автор": orders_tbl["author"].fillna("")})
    write_xlsx_dynamic(xlsx_path, daily, a.usd_eur, a.frm, a.to, orders_tbl, diff)
    print(f"{chr(10)}По схеме клиента из выгрузки CRM: заказов {len(scheme)}, количество товара {int(scheme['qty'].sum())}; расхождений с дашбордом клиента: {len(diff)}")
    if len(diff):
        print(diff["Раздел"].value_counts().to_string())
    if a.rebuild_sheet:
        n = rebuild_google_sheet(a.rebuild_sheet, xlsx_path)
        print(f"Google Таблица пересобрана: https://docs.google.com/spreadsheets/d/{a.rebuild_sheet}/edit — периодов в списке {n}")
    elif a.update_sheet:
        n, last = refresh_google_sheet(a.update_sheet, daily, a.frm, a.to)
        print(f"Google Таблица обновлена: https://docs.google.com/spreadsheets/d/{a.update_sheet}/edit — строк данных {n}, периодов в списке {last - 1}")
        leads = build_leads(ours, ringo, sheet, ga4_forms_daily(a.frm, a.to), a.frm, a.to)
        print(f"Листы «Заявки» и «Заявки_данные»: записано строк {write_leads_tabs(a.update_sheet, leads)}")
        print(f"Листы «Заказы за период» и «Заказы_данные»: записано строк {write_orders_tabs(a.update_sheet, build_orders(sales, scheme_all, sheet, a.frm, a.to))}")
    print(f"\nСтраница: {html_path}\nТаблица Excel (можно загрузить в Google Таблицы): {xlsx_path}")
    if not a.no_open:
        import os
        try:
            os.startfile(str(html_path))
        except Exception as ex:
            print("(не удалось открыть автоматически:", ex, ")")

    pu = prod_unique(ringo, count_other=False, date_to=a.to)
    pu = pu[(pu["date"] >= pd.Timestamp(a.frm).date()) & (pu["date"] <= pd.Timestamp(a.to).date())]
    print("\nСправочно: звонки по боевому правилу Ringostat (ringostat_profimet2) за период:",
          {k: int((pu["category"] == k).sum()) for k in ("Google Ads", "Facebook", "Google SEO")})
    print(f"Расход Facebook в BigQuery хранится в долларах; пересчёт в евро по курсу {a.usd_eur} (параметр --usd-eur). "
          f"Последняя дата в выгрузке CRM: {sheet['ts'].max().tz_convert(W):%Y-%m-%d %H:%M}.")


if __name__ == "__main__":
    main()
