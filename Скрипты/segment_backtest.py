#!/usr/bin/env python
# coding: utf-8
"""Проверка окна и порога для оценки СЕГМЕНТОВ кампаний (запросы, ключи, группы, устройства, часы, дни недели, гео, каналы PMax).
ТОЛЬКО ЧТЕНИЕ: в кабинеты, Таблицы и вики не пишет (--execute нет); пишет только локальные CSV в Клиенты/<клиент>/Статистика/.

Зачем: критерии успеха записаны ДО запуска в
База_знаний/Паттерны/Методология-выбора-метода-и-периода-анализа-кампаний.md, раздел «Проверка окна и порога для сегментов: критерии успеха».
Скрипт реализует их дословно; чисел, которых там нет, не добавляет. Что не записано в реестре (число повторов бутстрепа 2000, зерно, уровень 5 %,
поправка Холма, Джеффрис 0,5 у ставки кампании, сетка силы подтягивания kappa, корзины S/T) - стандартная практика, помечено «не утверждено».
Результат не меняет статус параметров: числа утверждает пользователь.

Шаги реестра:
  0  Сверка данных: сумма среза = кампания по каждому дню (расход 0,01 €, клики 0, показы 0); покрытие; конверсии Ads по имени
     конверсионного действия против заявок leads_standard (разрыв и ранговая корреляция). Не прошёл шаг 0 - шаги 1-3 по этой паре
     «срез x кампания» не запускаются (флаг --allow-partial нужен только для отдельного вспомогательного прогона, в отчёт критериев он не идёт).
  1  Вердикт устойчив? Флаг: 0 конверсий и S >= k x T за W недель; смотрим 1 и 2 недели вперёд: наблюдаемое / ожидаемое (по кампании без сегмента);
     кластерный бутстреп по сегментам. + калибровка e^-k по корзинам S/T (интервал Уилсона).
  2  Окно W из {1,2,3,4,6} недель: прогноз конверсий сегмента на неделю = расход недели x ставка с подтягиванием к кампании (сила подтягивания kappa
     оценивается по данным ДО t максимумом правдоподобия); ошибка - девианс Пуассона; парные разности, кластерный бутстреп, Холм; эталон - только уровень кампании.
  3  Порог k = S/T из сетки 1; 1,5; 2; 2,5; 3; 4; 5: доля ложных тревог с верхней границей Уилсона 95 %, ожидаемое число ложных при чистом Пуассоне,
     расход сегментов с флагом в следующие 2 недели.

Конверсия сегмента = metrics.conversions Google Ads (меток запроса/устройства в Ringostat и Supabase нет). Недели целые (пн-вс), дни без расхода кампании исключены,
на дату t (понедельник) используются только данные до t. Окна считаются от t-W БЕЗ обрезки по датам правок кампаний (дата последней крупной правки не рассчитана).
Кампании yt_* исключены. Допустимая цена заявки T = 22 € (sales_pace.py, 16.11.2026); в правиле участвует только S/T.

Режимы:
  --plan       только число запросов и операций API по срезам и чанкам (API не вызывается)
  --fetch      выгрузка чанками (месяц) в кэш Статистика/segment_backtest_cache/, ошибки квоты не теряют выгруженное (segment_backtest_errors.csv)
  --step0      шаг 0 по кэшу (+ leads_standard, режим по умолчанию; кэш segment_backtest_leads_daily.csv)
  --steps123   шаги 1-3 по кэшу
  --all        --fetch + --step0 + --steps123

Пример (из папки Скрипты, PYTHONUTF8=1):
    python segment_backtest.py --plan
    python segment_backtest.py --all --client ProfiMet --customer-id 7552781705
Создан 2026-11-16.
"""
import argparse
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8")

EXCLUDE_PREFIX = "yt_"
# Клиентские значения - только здесь (правило 4). Менеджер (login_customer_id) берётся из secrets/google-ads.yaml, как у соседних скриптов.
CLIENTS = {"ProfiMet": {"customer_id": "7552781705",
                        "focus": ["Search | Brand | Pl", "Search | Poliweglan | Pl", "pmax1_test"]}}
T_EUR = 22.0                                  # допустимая цена заявки, € (sales_pace.py на 16.11.2026)
W_SET = [1, 2, 3, 4, 6]                       # окна, недель (реестр)
K_STEP1 = 3.0                                 # порог шага 1 (реестр)
K_GRID = [1, 1.5, 2, 2.5, 3, 4, 5]            # сетка шага 3 (реестр)
HORIZONS = [1, 2]                             # недель вперёд, шаг 1 (реестр)
ALPHA = 0.05                                  # не утверждено: стандарт
N_BOOT = 2000                                 # не утверждено: реестр требует не меньше 2000
SEED = 20261116                               # фиксированное зерно
JEFFREYS = 0.5                                # не утверждено: добавка к конверсиям кампании в ставке эталона шага 2 (чтобы ставка не была 0)
KAPPA_GRID = [0.1, 0.3, 1, 3, 10, 30, 100, 300, 1e3, 3e3, 1e4, 1e5, 1e7]   # не утверждено: сетка силы подтягивания (€ расхода-эквивалента)
BUCKETS = [0, 1, 1.5, 2, 2.5, 3, 4, 5, np.inf]   # не утверждено: корзины S/T для калибровки (границы = сетка k)
TOL_COST, TOL_CLICKS, TOL_IMPR = 0.01, 0, 0   # реестр: 0,01 € / 0 кликов; показы - тоже 0 (реестр называет показы в сумме)
W0 = date(2025, 8, 4)                         # первый понедельник после 2025-08-01
MAIN_METRICS = "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions"
NO_YT = "campaign.name NOT REGEXP_MATCH '(?i)^yt_.*'"

# Срезы: res - ресурс GAQL, dims_key - поля ключа, dims_name - дополнительные поля названия (только в основном запросе), extra - условие
SLICES = {
    "campaign": dict(res="campaign", dims_key="", dims_name="", extra="", label="кампания (эталон)"),
    "device": dict(res="campaign", dims_key="segments.device", dims_name="", extra="", label="устройства"),
    "hour": dict(res="campaign", dims_key="segments.hour", dims_name="", extra="", label="часы"),
    "network": dict(res="campaign", dims_key="segments.ad_network_type", dims_name="", extra="", label="каналы / сети (ad_network_type)"),
    "geo": dict(res="user_location_view", dims_key="segments.geo_target_region", dims_name="", extra="", label="гео (регион пользователя)"),
    "adgroup": dict(res="ad_group", dims_key="ad_group.id", dims_name="ad_group.name", extra="", label="группы объявлений"),
    "keyword": dict(res="keyword_view", dims_key="ad_group.id, ad_group_criterion.criterion_id",
                    dims_name="ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type", extra="", label="ключи"),
    "term": dict(res="search_term_view", dims_key="search_term_view.search_term", dims_name="", extra="", label="поисковые запросы (Search)"),
    "assetgroup": dict(res="asset_group", dims_key="asset_group.id", dims_name="asset_group.name", extra="", label="группы активов PMax"),
    "pmax_term": dict(res="campaign_search_term_view", dims_key="campaign_search_term_view.search_term", dims_name="", extra="",
                      label="поисковые категории PMax (campaign_search_term_view)"),
}
DERIVED = {"dow": "дни недели (из подневного ряда кампании: день = ровно один день недели)"}
ALL_SLICES = list(SLICES) + list(DERIVED)
DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def stat_dir(client):
    return HERE.parent / "Клиенты" / client / "Статистика"


def months(d0, d1):
    out, a = [], d0
    while a <= d1:
        nxt = (a.replace(day=1) + timedelta(days=32)).replace(day=1)
        b = min(d1, nxt - timedelta(days=1))
        out.append((a, b))
        a = nxt
    return out


def chunk_file(cache, sl, kind, a):
    return cache / f"segment_backtest_{sl}_{kind}_{a:%Y-%m}.csv"


def gaql(sl, kind, a, b):
    s = SLICES[sl]
    key = f", {s['dims_key']}" if s["dims_key"] else ""
    where = f"segments.date BETWEEN '{a}' AND '{b}' AND {NO_YT}"
    if s["extra"]:
        where += f" AND {s['extra']}"
    if kind == "main":
        nm = f", {s['dims_name']}" if s["dims_name"] else ""
        return f"SELECT campaign.id, campaign.name, segments.date{key}{nm}, {MAIN_METRICS} FROM {s['res']} WHERE {where}"
    return (f"SELECT campaign.id, campaign.name, segments.date{key}, segments.conversion_action_name, metrics.conversions, metrics.all_conversions "
            f"FROM {s['res']} WHERE {where} AND metrics.all_conversions > 0")


def seg_of(sl, r, E):
    """(ключ сегмента, название) из строки ответа."""
    if sl == "campaign":
        return "all", "вся кампания"
    if sl == "device":
        n = E.DeviceEnum.Device.Name(r.segments.device)
        return n, n
    if sl == "hour":
        return f"{int(r.segments.hour):02d}", f"{int(r.segments.hour):02d}:00"
    if sl == "network":
        n = E.AdNetworkTypeEnum.AdNetworkType.Name(r.segments.ad_network_type)
        return n, n
    if sl == "geo":
        return str(r.segments.geo_target_region), str(r.segments.geo_target_region)
    if sl == "adgroup":
        return str(r.ad_group.id), r.ad_group.name
    if sl == "keyword":
        return f"{r.ad_group.id}~{r.ad_group_criterion.criterion_id}", ""   # название в основном запросе добавляется ниже
    if sl == "term":
        return r.search_term_view.search_term, r.search_term_view.search_term
    if sl == "assetgroup":
        return str(r.asset_group.id), r.asset_group.name
    if sl == "pmax_term":
        return r.campaign_search_term_view.search_term, r.campaign_search_term_view.search_term
    raise KeyError(sl)


def parse_chunk(sl, kind, rows, E):
    out = []
    for r in rows:
        k, nm = seg_of(sl, r, E)
        if sl == "keyword" and kind == "main":
            nm = f"{r.ad_group_criterion.keyword.text} [{E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.ad_group_criterion.keyword.match_type)}]"
        base = [r.segments.date, str(r.campaign.id), r.campaign.name, k, nm]
        if kind == "main":
            m = r.metrics
            out.append(base + [int(m.impressions), int(m.clicks), m.cost_micros / 1e6, float(m.conversions)])
        else:
            out.append(base + [r.segments.conversion_action_name, float(r.metrics.conversions), float(r.metrics.all_conversions)])
    cols = ["day", "camp_id", "camp", "seg", "segname"] + (["impr", "clicks", "cost", "conv"] if kind == "main" else ["action", "conv", "allconv"])
    return pd.DataFrame(out, columns=cols)


def err_text(e):
    try:
        return "; ".join(f"{x.error_code}: {x.message}" for x in e.failure.errors)[:400]
    except Exception:   # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:380]}"


def log_error(cache, sl, kind, a, text):
    p = cache.parent / "segment_backtest_errors.csv"
    new = not p.exists()
    with open(p, "a", encoding="utf-8-sig", newline="") as f:
        if new:
            f.write("time;slice;kind;chunk;error\n")
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S};{sl};{kind};{a:%Y-%m};\"{text.replace(chr(34), chr(39)).replace(chr(10), ' ')}\"\n")


def plan(client, d0, d1, slices):
    cache = stat_dir(client) / "segment_backtest_cache"
    ch = months(d0, d1)
    print(f"=== ПЛАН выгрузки (API не вызывался): {client}, {d0}..{d1}, чанков по месяцам: {len(ch)} ===")
    print(f"{'срез':11} {'запросов main':>13} {'запросов conv-по-действию':>26} {'в кэше':>7} {'к выгрузке':>11} {'операций API':>13}")
    tot_req = tot_todo = 0
    for sl in slices:
        if sl in DERIVED:
            print(f"{sl:11} {'-':>13} {'-':>26} {'-':>7} {'-':>11} {0:>13}   (считается из среза campaign)")
            continue
        n = 2 * len(ch)
        cached = sum(chunk_file(cache, sl, k, a).exists() for k in ("main", "act") for a, _ in ch)
        tot_req += n
        tot_todo += n - cached
        print(f"{sl:11} {len(ch):>13} {len(ch):>26} {cached:>7} {n - cached:>11} {n - cached:>13}")
    print(f"ИТОГО запросов GAQL: {tot_req}; к выгрузке сейчас: {tot_todo}; операций API: {tot_todo} (search_stream = 1 операция за запрос, как в gads_quota_ledger.py; "
          f"запрос не страничный), + leads_standard.month_leads ~5-10 операций (оценка). Суточный лимит basic: 15000.")
    print("Что API отдаёт не полностью (шаг 0 измерит число): search_term_view (запросы ниже порога приватности скрыты), user_location_view, campaign_search_term_view.")


def fetch(client, cid, d0, d1, slices):
    from google.ads.googleads.client import GoogleAdsClient
    from gads_stats import GOOGLE_ADS_YAML
    from gads_quota_ledger import wrap_ga
    gcl = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = wrap_ga(gcl.get_service("GoogleAdsService"), "segment_backtest")
    E = gcl.enums
    cache = stat_dir(client) / "segment_backtest_cache"
    cache.mkdir(parents=True, exist_ok=True)
    ops = done = errs = 0
    quota_streak = 0
    for sl in slices:
        if sl in DERIVED:
            continue
        for kind in ("main", "act"):
            for a, b in months(d0, d1):
                f = chunk_file(cache, sl, kind, a)
                if f.exists():
                    continue
                text = None
                for attempt in range(3):
                    try:
                        rows = []
                        ops += 1
                        for batch in ga.search_stream(customer_id=cid, query=gaql(sl, kind, a, b)):
                            rows.extend(batch.results)
                        df = parse_chunk(sl, kind, rows, E)
                        df = df[~df["camp"].str.lower().str.startswith(EXCLUDE_PREFIX)]
                        df.to_csv(f, index=False, encoding="utf-8-sig")
                        done += 1
                        quota_streak = 0
                        print(f"  {sl}/{kind}/{a:%Y-%m}: {len(df)} строк", flush=True)
                        text = None
                        break
                    except Exception as e:   # noqa: BLE001
                        text = err_text(e)
                        if any(x in text.upper() for x in ("RESOURCE_EXHAUSTED", "RATE_EXCEEDED", "QUOTA")) and attempt < 2:
                            time.sleep(30 * (attempt + 1))
                            continue
                        break
                if text:
                    errs += 1
                    log_error(cache, sl, kind, a, text)
                    print(f"  ОШИБКА {sl}/{kind}/{a:%Y-%m}: {text[:200]}", flush=True)
                    quota_streak = quota_streak + 1 if any(x in text.upper() for x in ("RESOURCE_EXHAUSTED", "RATE_EXCEEDED", "QUOTA")) else 0
                    if quota_streak >= 3:
                        print("  Квота: 3 ошибки подряд, выгрузка остановлена; выгруженное сохранено, остальное - Пробел.", flush=True)
                        return ops, done, errs
    print(f"Выгрузка: запросов {ops}, чанков записано {done}, ошибок {errs}")
    return ops, done, errs


def load_slice(client, sl, d0, d1):
    """Склейка чанков среза -> (main df, act df, список пропавших чанков)."""
    cache = stat_dir(client) / "segment_backtest_cache"
    out, miss = {}, []
    for kind in ("main", "act"):
        parts = []
        for a, _ in months(d0, d1):
            f = chunk_file(cache, sl, kind, a)
            if f.exists():
                parts.append(pd.read_csv(f, dtype={"camp_id": str, "seg": str}, encoding="utf-8-sig"))
            else:
                miss.append(f"{kind}:{a:%Y-%m}")
        df = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else pd.DataFrame()
        if len(df):
            df["day"] = pd.to_datetime(df["day"]).dt.date
            df["seg"] = df["seg"].fillna("").astype(str)
            df["segname"] = df["segname"].fillna("").astype(str)
        out[kind] = df
    return out["main"], out["act"], miss


def dow_slice(camp_main, camp_act):
    m = camp_main.copy()
    m["seg"] = m["day"].map(lambda d: DOW[d.weekday()])
    m["segname"] = m["seg"]
    a = camp_act.copy() if len(camp_act) else camp_act
    if len(a):
        a["seg"] = a["day"].map(lambda d: DOW[d.weekday()])
        a["segname"] = a["seg"]
    return m, a


def geo_names(client, cid, df):
    """Названия регионов (кэш segment_backtest_geo_names.csv); при ошибке остаются id."""
    p = stat_dir(client) / "segment_backtest_geo_names.csv"
    known = pd.read_csv(p, encoding="utf-8-sig").set_index("seg")["name"].to_dict() if p.exists() else {}
    need = [s for s in df["seg"].unique() if s not in known and s.startswith("geoTargetConstants/")]
    if need:
        try:
            from google.ads.googleads.client import GoogleAdsClient
            from gads_stats import GOOGLE_ADS_YAML
            from gads_quota_ledger import wrap_ga
            ga = wrap_ga(GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).get_service("GoogleAdsService"), "segment_backtest")
            for i in range(0, len(need), 150):
                part = need[i:i + 150]
                q = ("SELECT geo_target_constant.resource_name, geo_target_constant.canonical_name FROM geo_target_constant "
                     "WHERE geo_target_constant.resource_name IN (" + ",".join(f"'{x}'" for x in part) + ")")
                for b in ga.search_stream(customer_id=cid, query=q):
                    for r in b.results:
                        known[r.geo_target_constant.resource_name] = r.geo_target_constant.canonical_name
        except Exception as e:   # noqa: BLE001
            print("  geo: названия не получены:", err_text(e)[:160])
        pd.DataFrame({"seg": list(known), "name": list(known.values())}).to_csv(p, index=False, encoding="utf-8-sig")
    df["segname"] = df["seg"].map(lambda s: known.get(s, s))
    return df


# ======================= ШАГ 0 =======================
def wilson(k, n, z=1.959964):
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def holm(p):
    p = np.array(p, float)
    ok = ~np.isnan(p)
    adj = np.full_like(p, np.nan)
    order = np.argsort(np.where(ok, p, np.inf))
    run = 0.0
    for rank, i in enumerate(order[:int(ok.sum())]):
        run = max(run, min(1.0, (int(ok.sum()) - rank) * p[i]))
        adj[i] = run
    return adj


def step0_cover(data, camp_main, focus_ids, out):
    """Сверка суммы среза с кампанией по дням. data: {slice: (main, act, missing)}. -> DataFrame покрытия, set допущенных (slice, camp_id)."""
    ref = camp_main.groupby(["camp_id", "day"], as_index=False)[["impr", "clicks", "cost", "conv"]].sum()
    ref = ref[(ref["cost"] > 0) | (ref["clicks"] > 0) | (ref["impr"] > 0)]
    names = camp_main.drop_duplicates("camp_id").set_index("camp_id")["camp"].to_dict()
    rows, eligible, bad = [], set(), []
    for sl, (m, a, miss) in data.items():
        if sl == "campaign":
            continue
        if len(m):
            g = m.groupby(["camp_id", "day"], as_index=False)[["impr", "clicks", "cost", "conv"]].sum()
        else:
            g = pd.DataFrame(columns=["camp_id", "day", "impr", "clicks", "cost", "conv"])
        j = ref.merge(g, on=["camp_id", "day"], how="left", suffixes=("", "_s")).fillna({"impr_s": 0, "clicks_s": 0, "cost_s": 0, "conv_s": 0})
        j["ok"] = ((j["cost"] - j["cost_s"]).abs() <= TOL_COST + 1e-9) & ((j["clicks"] - j["clicks_s"]).abs() <= TOL_CLICKS) & ((j["impr"] - j["impr_s"]).abs() <= TOL_IMPR)
        j["slice"] = sl
        bad.append(j[~j["ok"]][["slice", "camp_id", "day", "impr", "impr_s", "clicks", "clicks_s", "cost", "cost_s"]])
        scopes = [("ВСЕ кампании без yt_", None)] + [(names.get(c, c), c) for c in focus_ids]
        for label, cid_ in scopes:
            jj = j if cid_ is None else j[j["camp_id"] == cid_]
            if len(jj) == 0:
                continue
            n, nok = len(jj), int(jj["ok"].sum())
            pas = (nok == n) and not (cid_ is None and False)
            rows.append({"срез": sl, "кампания": label, "дней_кампании": n, "дней_совпало": nok, "доля_дней_совпало": round(nok / n, 4),
                         "покрытие_расход": round(jj["cost_s"].sum() / jj["cost"].sum(), 4) if jj["cost"].sum() else np.nan,
                         "покрытие_клики": round(jj["clicks_s"].sum() / jj["clicks"].sum(), 4) if jj["clicks"].sum() else np.nan,
                         "покрытие_показы": round(jj["impr_s"].sum() / jj["impr"].sum(), 4) if jj["impr"].sum() else np.nan,
                         "расход_кампании": round(jj["cost"].sum(), 2), "расход_среза": round(jj["cost_s"].sum(), 2),
                         "конв_кампании": round(jj["conv"].sum(), 2), "конв_среза": round(jj["conv_s"].sum(), 2),
                         "пропущено_чанков_выгрузки": len(miss), "критерий_шага0": "пройден" if (pas and not miss) else "НЕ пройден"})
            if cid_ is not None and pas and not miss:
                eligible.add((sl, cid_))
    cov = pd.DataFrame(rows)
    cov.to_csv(out / "segment_backtest_step0_coverage.csv", index=False, encoding="utf-8-sig")
    if bad:
        pd.concat(bad, ignore_index=True).to_csv(out / "segment_backtest_step0_mismatch_days.csv", index=False, encoding="utf-8-sig")
    return cov, eligible


def build_leads(client, d0, d1, out, refresh=False):
    """Заявки по стандарту leads_standard (режим по умолчанию 'ringostat') по (день, кампания): call / adcall / form. Кэш CSV."""
    p = out / "segment_backtest_leads_daily.csv"
    if p.exists() and not refresh:
        return pd.read_csv(p, encoding="utf-8-sig", parse_dates=["day"]), "кэш"
    import leads_standard as LS
    res = LS.month_leads(client, str(d0), str(d1), calls_from_ads="ringostat")
    recs = []
    for _, r in res["calls"].iterrows():
        recs.append((pd.Timestamp(r["day"]), r["camp"] if r["camp"] not in (LS.UNRESOLVED, "") else "(без кампании)", "adcall" if r["via_call_view"] else "call"))
    for _, r in res["forms"][res["forms"]["src"] == "google"].iterrows():
        recs.append((pd.Timestamp(r["day"]), r["camp"] or "(без кампании)", "form"))
    df = pd.DataFrame(recs, columns=["day", "camp", "kind"])
    df = df[~df["camp"].str.lower().str.startswith(EXCLUDE_PREFIX)]
    df = df.groupby(["day", "camp", "kind"], as_index=False).size().rename(columns={"size": "n"})
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return df, "месячный запуск leads_standard.month_leads (режим по умолчанию ringostat)"


def step0_conv_vs_leads(camp_main, camp_act, leads, focus_names, out):
    """Конверсии Ads по имени действия против заявок leads_standard по (день, кампания): разрыв и ранговая корреляция."""
    from scipy.stats import spearmanr
    cm = camp_main.copy()
    cm["day"] = pd.to_datetime(cm["day"])
    act = camp_act.copy()
    act["day"] = pd.to_datetime(act["day"])
    lw = leads.pivot_table(index=["day", "camp"], columns="kind", values="n", aggfunc="sum", fill_value=0).reset_index()
    for k in ("call", "adcall", "form"):
        if k not in lw:
            lw[k] = 0
    lw["total"] = lw["call"] + lw["adcall"] + lw["form"]
    base = cm.groupby(["day", "camp"], as_index=False)["cost"].sum()
    base = base[base["cost"] > 0]
    rows = []
    periods = [("2025-08-01..2026-11-15", pd.Timestamp("2025-08-01")), ("2026-04-01..2026-11-15", pd.Timestamp("2026-04-01"))]
    for plabel, pstart in periods:
        for scope, camps in [("ВСЕ кампании без yt_", None)] + [(n, [n]) for n in focus_names]:
            b = base[base["day"] >= pstart]
            if camps is not None:
                b = b[b["camp"].isin(camps)]
            aa = act[(act["day"] >= pstart)]
            if camps is not None:
                aa = aa[aa["camp"].isin(camps)]
            for an in sorted(aa["action"].unique()):
                x = aa[aa["action"] == an].groupby(["day", "camp"], as_index=False)["conv"].sum().rename(columns={"conv": "ads"})
                j = b.merge(x, on=["day", "camp"], how="left").merge(lw, on=["day", "camp"], how="left").fillna(0)
                for kind in ("call", "adcall", "form", "total"):
                    sa, sl_ = j["ads"].sum(), j[kind].sum()
                    rho = np.nan
                    if len(j) >= 3 and j["ads"].nunique() > 1 and j[kind].nunique() > 1:
                        rho = spearmanr(j["ads"], j[kind]).correlation
                    rows.append({"период": plabel, "кампании": scope, "действие_Ads": an, "тип_заявки_leads_standard": kind, "режим_leads_standard": "ringostat (по умолчанию)",
                                 "дней_кампании": len(j), "конв_Ads": round(sa, 2), "заявок_leads_standard": int(sl_), "разрыв_Ads_минус_заявки": round(sa - sl_, 2),
                                 "ранговая_корреляция_Спирмен": round(float(rho), 3) if rho == rho else np.nan})
    df = pd.DataFrame(rows)
    df.to_csv(out / "segment_backtest_step0_conv_vs_leads.csv", index=False, encoding="utf-8-sig")
    return df


# ======================= ШАГИ 1-3 =======================
def build_units(m, camp_cost_days, T):
    """Недельные матрицы сегмент x неделя по паре (кампания, сегмент). -> dict."""
    d = m.copy()
    d = d.merge(camp_cost_days, on=["camp_id", "day"], how="inner")   # дни без расхода кампании исключены
    d["w"] = d["day"].map(lambda x: (x - W0).days // 7)
    d = d[(d["w"] >= 0) & (d["w"] < T)]
    key = d["camp_id"] + "|" + d["seg"]
    codes, uniq = pd.factorize(key)
    U = len(uniq)
    S = np.zeros((U, T))
    Y = np.zeros((U, T))
    np.add.at(S, (codes, d["w"].values), d["cost"].values)
    np.add.at(Y, (codes, d["w"].values), d["conv"].values)
    camps = [u.split("|", 1)[0] for u in uniq]
    cuniq = sorted(set(camps))
    c_idx = np.array([cuniq.index(c) for c in camps])
    return {"S": S, "Y": Y, "c_idx": c_idx, "camps": cuniq, "keys": list(uniq), "U": U, "T": T}


def cumsum0(A):
    return np.concatenate([np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)], axis=1)


def camp_sum(A, c_idx, n_c):
    out = np.zeros((n_c, A.shape[1]))
    for c in range(n_c):
        out[c] = A[c_idx == c].sum(axis=0)
    return out[c_idx]


def boot_sums(M, B=N_BOOT, seed=SEED):
    """Кластерный бутстреп: M (n кластеров x m величин) -> (B x m) суммы по пересэмплированным кластерам."""
    n = M.shape[0]
    rng = np.random.default_rng(seed)
    out = np.empty((B, M.shape[1]))
    bs = max(1, int(4e6 // max(n, 1)))
    i = 0
    while i < B:
        b = min(bs, B - i)
        w = rng.multinomial(n, np.full(n, 1.0 / n), size=b).astype(np.float64)
        out[i:i + b] = w @ M
        i += b
    return out


def step1(U, T_eur, slice_name):
    S, Y, c_idx, T = U["S"], U["Y"], U["c_idx"], U["T"]
    nc = len(U["camps"])
    CS, CY = cumsum0(S), cumsum0(Y)
    rows, calib = [], []
    for W in W_SET:
        # --- калибровка e^-k: все (сегмент, t) с расходом > 0 за окно
        ts = np.arange(W, T)
        SW, YW = CS[:, ts] - CS[:, ts - W], CY[:, ts] - CY[:, ts - W]
        ScW, YcW = camp_sum(SW, c_idx, nc), camp_sum(YW, c_idx, nc)
        mask = (SW > 0) & (ScW > 0)
        r = np.where(ScW > 0, YcW / np.where(ScW > 0, ScW, 1), 0)
        p0 = np.exp(-SW * r)[mask]
        zero = (YW[mask] <= 1e-9)
        x = (SW[mask] / T_eur)
        for lo, hi in zip(BUCKETS[:-1], BUCKETS[1:]):
            sel = (x >= lo) & (x < hi)
            n = int(sel.sum())
            if n == 0:
                continue
            kz = int(zero[sel].sum())
            wl, wh = wilson(kz, n)
            ex = float(p0[sel].mean())
            calib.append({"срез": slice_name, "окно_нед": W, "корзина_S_на_T": f"[{lo};{hi})", "сегмент_дат": n, "нулей_наблюдено": kz, "доля_нулей": round(kz / n, 4),
                          "Уилсон_нижн": round(wl, 4), "Уилсон_верх": round(wh, 4), "ожидаемая_доля_e^(-S*ставка_кампании)": round(ex, 4),
                          "ожидаемая_внутри_интервала": bool(wl <= ex <= wh)})
        # --- вердикт устойчив?
        for h in HORIZONS:
            ts = np.arange(W, T - h + 1)
            if len(ts) == 0:
                continue
            SW, YW = CS[:, ts] - CS[:, ts - W], CY[:, ts] - CY[:, ts - W]
            Sn, Yn = CS[:, ts + h] - CS[:, ts], CY[:, ts + h] - CY[:, ts]
            ScW, YcW = camp_sum(SW, c_idx, nc), camp_sum(YW, c_idx, nc)
            den = ScW - SW
            rate = np.where(den > 0, (YcW - YW) / np.where(den > 0, den, 1), np.nan)
            flag = (YW <= 1e-9) & (SW >= K_STEP1 * T_eur) & (den > 0)
            iu, it = np.nonzero(flag)
            obs, exp_ = Yn[iu, it], Sn[iu, it] * rate[iu, it]
            nfl = len(iu)
            row = {"срез": slice_name, "окно_нед": W, "горизонт_нед": h, "k": K_STEP1, "флагов": nfl, "сегментов_с_флагом": int(len(np.unique(iu))),
                   "наблюдено_конв": round(float(obs.sum()), 2) if nfl else np.nan, "ожидалось_конв": round(float(exp_.sum()), 2) if nfl else np.nan}
            if nfl and exp_.sum() > 0:
                uu, inv = np.unique(iu, return_inverse=True)
                M = np.zeros((len(uu), 2))
                np.add.at(M[:, 0], inv, obs)
                np.add.at(M[:, 1], inv, exp_)
                bt = boot_sums(M)
                ok = bt[:, 1] > 0
                ratio = bt[ok, 0] / bt[ok, 1]
                R = obs.sum() / exp_.sum()
                if len(uu) < 2:   # бутстреп по одному кластеру не имеет разброса: интервал не определён, «подтверждено» не присваивается
                    row.update({"отношение_набл_к_ожид": round(float(R), 4), "ДИ95_нижн": np.nan, "ДИ95_верх": np.nan, "p_бутстреп_R<1": np.nan,
                                "подтверждено_верх<1": False, "примечание": "1 сегмент с флагом: ДИ не определён"})
                    rows.append(row)
                    continue
                row.update({"отношение_набл_к_ожид": round(float(R), 4), "ДИ95_нижн": round(float(np.percentile(ratio, 2.5)), 4),
                            "ДИ95_верх": round(float(np.percentile(ratio, 97.5)), 4), "p_бутстреп_R<1": round(float((np.sum(ratio >= 1) + 1) / (len(ratio) + 1)), 4)})
                row["подтверждено_верх<1"] = bool(row["ДИ95_верх"] < 1)
            rows.append(row)
    df = pd.DataFrame(rows)
    if len(df) and "p_бутстреп_R<1" in df:
        df["p_Холм_семья_окно_x_горизонт"] = np.round(holm(df["p_бутстреп_R<1"].values), 4)
    return df, pd.DataFrame(calib)


def dev_pois(y, mu):
    y = np.asarray(y, float)
    t = np.where(y > 0, y * np.log(np.where(y > 0, y, 1.0) / mu), 0.0)
    return 2.0 * (t - (y - mu))


def nb_ll(y, Sn, a, b):
    from scipy.special import gammaln
    return gammaln(y + a) - gammaln(a) - gammaln(y + 1) + a * np.log(b / (b + Sn)) + y * np.log(Sn / (b + Sn))


def step2(U, slice_name):
    S, Y, c_idx, T = U["S"], U["Y"], U["c_idx"], U["T"]
    nc = len(U["camps"])
    Wm = max(W_SET)
    CS, CY = cumsum0(S), cumsum0(Y)
    ts = np.arange(Wm, T)                      # прогноз недели t по данным до t (горизонт 1 неделя)
    Sn, Yn = S[:, ts], Y[:, ts]
    valid = Sn > 0
    per = {}
    for W in W_SET:
        SW, YW = CS[:, ts] - CS[:, ts - W], CY[:, ts] - CY[:, ts - W]
        ScW, YcW = camp_sum(SW, c_idx, nc), camp_sum(YW, c_idx, nc)
        den = ScW - SW
        r = (YcW - YW + JEFFREYS) / np.where(den > 0, den, np.nan)
        valid &= (den > 0) & np.isfinite(r)
        per[W] = (SW, YW, r)
    kap = np.array(KAPPA_GRID)
    iu, it = np.nonzero(valid)
    if len(iu) == 0:
        return None
    y, sn = Yn[iu, it], Sn[iu, it]
    # t-индексы строк; наличие предыдущих строк для оценки kappa
    cnt_t = np.bincount(it, minlength=len(ts))
    prior_cnt = np.concatenate([[0], np.cumsum(cnt_t)[:-1]])
    eval_row = prior_cnt[it] > 0
    res, kap_choice = {}, {}
    mu_all = {}
    for W in W_SET:
        SW, YW, r = per[W]
        sw, yw, rr = SW[iu, it], YW[iu, it], r[iu, it]
        a = kap[None, :] * rr[:, None] + yw[:, None]
        b = kap[None, :] + sw[:, None]
        LL = nb_ll(y[:, None], sn[:, None], a, b)
        LLt = np.zeros((len(ts), len(kap)))
        np.add.at(LLt, it, LL)
        cum = np.cumsum(LLt, axis=0)
        cum_prev = np.vstack([np.zeros((1, len(kap))), cum[:-1]])
        ik = np.argmax(cum_prev, axis=1)         # kappa по данным строго до t
        kc = ik[it]
        kk = kap[kc]
        mu = sn * (yw + kk * rr) / (sw + kk)
        mu_all[W] = mu
        kap_choice[W] = (float(np.median(kk[eval_row])), float(np.mean(np.isin(kc[eval_row], [0, len(kap) - 1]))))
        res[W] = (dev_pois(y, np.maximum(mu, 1e-12)), dev_pois(y, np.maximum(sn * rr, 1e-12)))
    # кластеры = сегменты
    uu, inv = np.unique(iu[eval_row], return_inverse=True)
    cols = []
    for W in W_SET:
        cols += [res[W][0][eval_row], res[W][1][eval_row]]
    M = np.zeros((len(uu), len(cols)))
    for j, c in enumerate(cols):
        np.add.at(M[:, j], inv, c)
    bt = boot_sums(M)
    tot = M.sum(axis=0)
    N = int(eval_row.sum())
    idx = {("cand", W): 2 * i for i, W in enumerate(W_SET)}
    idx.update({("ref", W): 2 * i + 1 for i, W in enumerate(W_SET)})

    def pval(a_, b_):    # H1: ошибка a меньше ошибки b
        d = bt[:, a_] - bt[:, b_]
        return float((np.sum(d >= 0) + 1) / (len(d) + 1)), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), float(tot[a_] - tot[b_])
    tests = []
    for W in W_SET:
        p, lo, hi, dd = pval(idx[("cand", W)], idx[("ref", W)])
        tests.append({"сравнение": f"окно {W} нед. против эталона (кампания без данных сегмента)", "тип": "эталон", "a": W, "b": "эталон", "разность_девианса_a_минус_b": round(dd, 3), "ДИ95_нижн": round(lo, 3), "ДИ95_верх": round(hi, 3), "p": p})
    for i, Wa in enumerate(W_SET):
        for Wb in W_SET[:i]:
            p, lo, hi, dd = pval(idx[("cand", Wa)], idx[("cand", Wb)])
            tests.append({"сравнение": f"окно {Wa} нед. против более короткого {Wb} нед.", "тип": "пара", "a": Wa, "b": Wb, "разность_девианса_a_минус_b": round(dd, 3), "ДИ95_нижн": round(lo, 3), "ДИ95_верх": round(hi, 3), "p": p})
    tdf = pd.DataFrame(tests)
    tdf["p_Холм_семья"] = holm(tdf["p"].values)
    tdf.insert(0, "срез", slice_name)
    summ = []
    for W in W_SET:
        summ.append({"срез": slice_name, "окно_нед": W, "строк_сегмент_неделя": N, "сегментов_кластеров": len(uu), "девианс_суммарный": round(float(tot[idx[("cand", W)]]), 2),
                     "девианс_эталона": round(float(tot[idx[("ref", W)]]), 2), "девианс_на_строку": round(float(tot[idx[("cand", W)]]) / N, 4),
                     "kappa_медиана_€": kap_choice[W][0], "доля_недель_kappa_на_краю_сетки": round(kap_choice[W][1], 3)})
    sdf = pd.DataFrame(summ)
    # вердикт по правилу реестра
    ref_tests = tdf[tdf["тип"] == "эталон"]
    beats = ref_tests[(ref_tests["p_Холм_семья"] < ALPHA) & (ref_tests["разность_девианса_a_минус_b"] < 0)]
    best = int(sdf.loc[sdf["девианс_суммарный"].idxmin(), "окно_нед"])
    if len(beats) == 0:
        verdict = "НИ ОДНО окно не лучше эталона (Холм 5 %): данные сегмента не предсказывают, ранжировать сегменты по заявкам нельзя"
    else:
        shorter = tdf[(tdf["тип"] == "пара") & (tdf["a"] == best)]
        notsig = shorter[~((shorter["p_Холм_семья"] < ALPHA) & (shorter["разность_девианса_a_минус_b"] < 0))]
        if len(shorter) == 0:
            verdict = f"лучшее по ошибке окно {best} нед. (самое короткое), лучше эталона значимо; окно не утверждено"
        elif len(notsig):
            verdict = f"лучшее по ошибке окно {best} нед., но разница с более коротким ({', '.join(str(int(x)) for x in notsig['b'])} нед.) не значима: окна НЕ РАЗЛИЧИМЫ, окно не назначается"
        else:
            verdict = f"окно {best} нед. значимо лучше всех более коротких и эталона; окно не утверждено"
    sdf["вердикт_правила_реестра"] = verdict
    return sdf, tdf


def step3(U, T_eur, slice_name):
    S, Y, c_idx, T = U["S"], U["Y"], U["c_idx"], U["T"]
    nc = len(U["camps"])
    CS, CY = cumsum0(S), cumsum0(Y)
    rows = []
    for W in W_SET:
        ts = np.arange(W, T - 1)
        if len(ts) == 0:
            continue
        SW, YW = CS[:, ts] - CS[:, ts - W], CY[:, ts] - CY[:, ts - W]
        Sn, Yn = CS[:, ts + 2] - CS[:, ts], CY[:, ts + 2] - CY[:, ts]
        for k in K_GRID:
            risk = (SW >= k * T_eur)
            flag = risk & (YW <= 1e-9)
            ev = Sn >= T_eur
            nfl = int(flag.sum())
            fl_eval = flag & ev
            n_eval = int(fl_eval.sum())
            with np.errstate(divide="ignore", invalid="ignore"):
                false = fl_eval & (Yn > 0) & (Sn / np.where(Yn > 0, Yn, np.nan) <= T_eur)
            nf = int(false.sum())
            lo, hi = wilson(nf, n_eval)
            rows.append({"срез": slice_name, "окно_нед": W, "k": k, "флагов": nfl, "флагов_с_расходом_след2нед>=T": n_eval, "ложных": nf,
                         "доля_ложных": round(nf / n_eval, 4) if n_eval else np.nan, "Уилсон_верх95": round(hi, 4) if n_eval else np.nan,
                         "под_риском_(S>=kT и S_след>=T)": int((risk & ev).sum()),
                         "ожидаемо_ложных_при_чистом_Пуассоне": round(float((risk & ev).sum() * math.exp(-k)), 2),
                         "расход_флагов_след2нед_€": round(float(Sn[flag].sum()), 1), "k_проходит_верх<=5%": bool(n_eval > 0 and hi <= ALPHA)})
    return pd.DataFrame(rows)


# ======================= ОРКЕСТРАЦИЯ =======================
def fmt(df, cols=None, n=60):
    with pd.option_context("display.width", 250, "display.max_columns", 40, "display.max_rows", n, "display.max_colwidth", 60):
        return (df[cols] if cols else df).to_string(index=False)


def run_analysis(client, cid, d0, d1, slices, do0, do123, allow_partial, refresh_leads):
    out = stat_dir(client)
    focus_names = CLIENTS[client]["focus"]
    data = {}
    for sl in [s for s in slices if s in SLICES]:
        m, a, miss = load_slice(client, sl, d0, d1)
        if sl == "geo" and len(m):
            m = geo_names(client, cid, m)
            if len(a):
                a = geo_names(client, cid, a)
        data[sl] = (m, a, miss)
        if len(m):
            m.to_csv(out / f"segment_backtest_{sl}_daily.csv", index=False, encoding="utf-8-sig")
        if len(a):
            a.to_csv(out / f"segment_backtest_{sl}_conv_by_action.csv", index=False, encoding="utf-8-sig")
    if "campaign" not in data or not len(data["campaign"][0]):
        print("Нет данных среза campaign: шаг 0 невозможен. Пробел.")
        return
    camp_main, camp_act, _ = data["campaign"]
    if "dow" in slices:
        data["dow"] = dow_slice(camp_main, camp_act) + ([],)
        data["dow"][0].to_csv(out / "segment_backtest_dow_daily.csv", index=False, encoding="utf-8-sig")
    name2id = camp_main.drop_duplicates("camp_id").set_index("camp")["camp_id"].to_dict()
    focus_ids = [name2id[n] for n in focus_names if n in name2id]
    missing_focus = [n for n in focus_names if n not in name2id]
    if missing_focus:
        print("Фокус-кампании не найдены в данных:", missing_focus)
    print(f"Кампаний в данных (без yt_): {camp_main['camp_id'].nunique()}; фокус: {focus_names}")
    cov, eligible = step0_cover(data, camp_main, focus_ids, out)
    # dow: по построению каждый день относится к одному дню недели -> сумма = кампании
    for c in focus_ids:
        eligible.add(("dow", c))
    cov_dow = pd.DataFrame([{"срез": "dow", "кампания": "ВСЕ кампании без yt_", "критерий_шага0": "пройден по построению (сумма дней недели = кампания)", "покрытие_расход": 1.0}])
    if do0:
        print("\n=== ШАГ 0: сверка суммы среза с кампанией по дням (критерий реестра: расход 0,01 €, клики 0, показы 0) ===")
        print(fmt(cov, ["срез", "кампания", "дней_кампании", "дней_совпало", "доля_дней_совпало", "покрытие_расход", "покрытие_клики", "покрытие_показы",
                         "конв_кампании", "конв_среза", "пропущено_чанков_выгрузки", "критерий_шага0"], 200))
        print("dow: пройден по построению.")
        gaps = cov[(cov["кампания"] == "ВСЕ кампании без yt_") & (cov["критерий_шага0"] != "пройден")]
        if len(gaps):
            print("\nПробелы (API отдаёт не всё), покрытие по ВСЕМ кампаниям:")
            for _, r in gaps.iterrows():
                print(f"  {r['срез']}: расход {r['покрытие_расход']:.1%}, клики {r['покрытие_клики']:.1%}, показы {r['покрытие_показы']:.1%}; дней совпало {r['дней_совпало']} из {r['дней_кампании']}")
        leads, src = build_leads(client, d0, d1, out, refresh_leads)
        print(f"\nЗаявки leads_standard: {src}; режим звонков из объявлений: ringostat (по умолчанию, старое правило). Формы Supabase доступны с 2026-03-25 (period_backtest).")
        cv = step0_conv_vs_leads(camp_main, camp_act, leads, focus_names, out)
        print("\n=== ШАГ 0 (конверсии): Ads по имени действия против leads_standard (по дню и кампании; порога нет, числа для пользователя) ===")
        print(fmt(cv[cv["тип_заявки_leads_standard"].isin(["call", "adcall", "form", "total"])], None, 400))
    if not do123:
        return
    T = ((d1 - W0).days + 1) // 7
    camp_days = camp_main.groupby(["camp_id", "day"], as_index=False)["cost"].sum()
    camp_days = camp_days[camp_days["cost"] > 0][["camp_id", "day"]]
    s1, cal, s2s, s2t, s3 = [], [], [], [], []
    print(f"\nНедель в ряду T={T} (с {W0}), T_допустимая цена заявки = {T_EUR} €")
    for sl in [s for s in slices if s in data or s == "dow"]:
        if sl == "campaign":
            continue
        m = data[sl][0]
        if not len(m):
            continue
        okc = [c for c in focus_ids if (sl, c) in eligible or allow_partial]
        if not okc:
            print(f"\n[{sl}] шаг 0 НЕ пройден ни по одной фокус-кампании - шаги 1-3 не запускаются.")
            continue
        mm = m[m["camp_id"].isin(okc)]
        if not len(mm):
            print(f"\n[{sl}] данных по допущенным кампаниям нет.")
            continue
        U = build_units(mm, camp_days, T)
        print(f"\n[{sl}] допущено кампаний: {[camp_main[camp_main['camp_id'] == c]['camp'].iloc[0] for c in U['camps']]}; сегментов: {U['U']}", flush=True)
        a, b = step1(U, T_EUR, sl)
        s1.append(a)
        cal.append(b)
        r2 = step2(U, sl)
        if r2:
            s2s.append(r2[0])
            s2t.append(r2[1])
        s3.append(step3(U, T_EUR, sl))
    suffix = "_ВНЕ_КРИТЕРИЯ_partial" if allow_partial else ""
    for name, lst in (("step1_stability", s1), ("step1_calibration", cal), ("step2_windows", s2s), ("step2_tests", s2t), ("step3_threshold", s3)):
        if lst:
            pd.concat(lst, ignore_index=True).to_csv(out / f"segment_backtest_{name}{suffix}.csv", index=False, encoding="utf-8-sig")
    if s1:
        d = pd.concat(s1, ignore_index=True)
        print("\n=== ШАГ 1: вердикт «тратит впустую» устойчив? (k=3; подтверждено, если верхняя граница ДИ95 отношения наблюдаемое/ожидаемое < 1 для ОБОИХ горизонтов) ===")
        print(fmt(d, None, 400))
        g1 = d.groupby(["срез", "окно_нед"]).agg(флагов_сумма_по_2_горизонтам=("флагов", "sum"), горизонтов_подтверждено=("подтверждено_верх<1", "sum")).reset_index()
        g1["критерий_шага1_пройден_(оба_горизонта)"] = g1["горизонтов_подтверждено"] == len(HORIZONS)
        print("\nШАГ 1, итог по срезу и окну (критерий: верхняя граница ДИ95 < 1 для обоих горизонтов):")
        print(fmt(g1, None, 200))
        g1.to_csv(out / "segment_backtest_step1_summary.csv", index=False, encoding="utf-8-sig")
    if cal:
        c = pd.concat(cal, ignore_index=True)
        g = c.groupby(["срез", "окно_нед"]).agg(корзин=("ожидаемая_внутри_интервала", "size"), внутри=("ожидаемая_внутри_интервала", "sum")).reset_index()
        print("\n=== ШАГ 1: калибровка e^-k (Пуассон подходит, если ожидаемая доля нулей внутри ДИ Уилсона наблюдаемой; корзин внутри / всего) ===")
        print(fmt(g, None, 200))
    if s2s:
        d = pd.concat(s2s, ignore_index=True)
        print("\n=== ШАГ 2: окна и эталон ===")
        print(fmt(d.drop(columns=["вердикт_правила_реестра"]), None, 200))
        for sl, v in d.groupby("срез")["вердикт_правила_реестра"].first().items():
            print(f"  вердикт [{sl}]: {v}")
    if s3:
        d = pd.concat(s3, ignore_index=True)
        print("\n=== ШАГ 3: порог k (ложная тревога; наименьшее k с верхней границей Уилсона <= 5 %) ===")
        print(fmt(d, None, 800))
        for (sl, W), g in d.groupby(["срез", "окно_нед"]):
            okk = g[g["k_проходит_верх<=5%"]]
            print(f"  [{sl}] окно {W} нед.: " + (f"наименьшее k = {okk['k'].min()}" if len(okk) else "порог не найден"))


def main():
    ap = argparse.ArgumentParser(description="Проверка окна и порога оценки сегментов кампаний (только чтение, --execute нет)")
    ap.add_argument("--plan", action="store_true", help="число запросов и операций API без выгрузки")
    ap.add_argument("--fetch", action="store_true", help="выгрузка чанками в кэш")
    ap.add_argument("--step0", action="store_true")
    ap.add_argument("--steps123", action="store_true")
    ap.add_argument("--all", action="store_true", help="fetch + step0 + steps123")
    ap.add_argument("--client", default="ProfiMet")
    ap.add_argument("--customer-id", default=None)
    ap.add_argument("--from", dest="d0", default="2025-08-01")
    ap.add_argument("--to", dest="d1", default="2026-11-15")
    ap.add_argument("--slices", default=",".join(ALL_SLICES), help="список через запятую; по умолчанию все")
    ap.add_argument("--allow-partial", action="store_true", help="вспомогательный прогон шагов 1-3 по срезам, не прошедшим шаг 0 (вне критериев реестра; файлы с суффиксом)")
    ap.add_argument("--refresh-leads", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id or CLIENTS[a.client]["customer_id"]
    d0, d1 = date.fromisoformat(a.d0), date.fromisoformat(a.d1)
    slices = [s.strip() for s in a.slices.split(",") if s.strip()]
    if "campaign" not in slices:
        slices = ["campaign"] + slices
    if a.plan:
        plan(a.client, d0, d1, slices)
        return
    if a.all:
        a.fetch = a.step0 = a.steps123 = True
    if not (a.fetch or a.step0 or a.steps123):
        ap.print_help()
        return
    print(f"Параметры (не утверждены, кроме указанных в реестре): N_boot={N_BOOT}, seed={SEED}, alpha={ALPHA}, Jeffreys={JEFFREYS}, kappa-сетка={KAPPA_GRID}, корзины S/T={BUCKETS}")
    if a.fetch:
        fetch(a.client, cid, d0, d1, slices)
    if a.step0 or a.steps123:
        run_analysis(a.client, cid, d0, d1, slices, a.step0, a.steps123, a.allow_partial, a.refresh_leads)


if __name__ == "__main__":
    main()
