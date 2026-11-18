#!/usr/bin/env python
# coding: utf-8
"""Бэктест выбора периода и модели прогноза заявок по кампаниям. ТОЛЬКО ЧТЕНИЕ (кабинеты, таблицы, вики не пишет; --execute нет).

Зачем: методология (База_знаний/Паттерны/Методология-выбора-метода-и-периода-анализа-кампаний.md) запрещает назначать окно
анализа на глаз; здесь окно/модель выбираются «экзаменом на прошлом»: для каждой прошлой недели модель не знает будущего
и предсказывает заявки следующей недели; сравниваются ошибки кандидатов.

Режимы:
  --history   Шаг А: проверка глубины и пригодности истории (подневной ряд заявки/расход/клики по кампаниям и аккаунту,
              целые недели, дни с нулём, даты правок, доступные библиотеки). Сохраняет панель в CSV.
  --backtest  Шаг Б: скользящий бэктест (добавляется после шага А, если истории хватает).

Заявка = как в leads_standard.py: уникальный звонок Ringostat (Google Ads) + форма Supabase (src=google); звонки «из объявлений»
(статический номер) получают кампанию по времени из call_view Google Ads (допуск ±3 мин). Кампании yt_* исключены (YouTube - отдельный проект).
Кампании, удалённые из кабинета (REMOVED), в карте имён leads_standard отсутствуют: их заявки попадают в «(без кампании)».

Пример (из папки Скрипты, PYTHONUTF8=1):
    python period_backtest.py --history --client ProfiMet --customer-id 7552781705 --from 2025-08-01
Создан 2026-11-16.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8")

WORKDIR = HERE.parent / "Клиенты" / "ProfiMet" / "Работы" / "2026-11-16_selector"
EXCLUDE_PREFIX = "yt_"
CLIENTS = {"ProfiMet": "7552781705"}
NOCAMP = "(без кампании)"


def libs_report():
    import importlib
    out = {}
    for m in ["numpy", "pandas", "scipy", "statsmodels", "ruptures", "pymc", "numpyro", "arch", "sklearn", "causalimpact", "tfcausalimpact"]:
        try:
            x = importlib.import_module(m)
            out[m] = getattr(x, "__version__", "есть")
        except Exception:   # noqa: BLE001
            out[m] = "НЕТ"
    return out


def campaign_daily_ads(ga, cid, d0, d1):
    """Расход и клики по (день, кампания), включая удалённые кампании (REMOVED), без yt_*."""
    rows = []
    q = ("SELECT segments.date, campaign.id, campaign.name, campaign.status, metrics.cost_micros, metrics.clicks, metrics.impressions "
         f"FROM campaign WHERE segments.date BETWEEN '{d0}' AND '{d1}'")
    for r in ga.search(customer_id=cid, query=q):
        if str(r.campaign.name).lower().startswith(EXCLUDE_PREFIX):
            continue
        rows.append((date.fromisoformat(r.segments.date), str(r.campaign.id), r.campaign.name,
                     r.metrics.cost_micros / 1e6, int(r.metrics.clicks), int(r.metrics.impressions)))
    return pd.DataFrame(rows, columns=["day", "cid", "camp", "cost", "clicks", "impr"])


def build_panel(folder, d0, d1):
    """Подневная панель (day, camp): leads (звонки Ringostat + звонки из объявлений + формы), cost, clicks. + метаданные источников."""
    import leads_standard as LS
    res = LS.month_leads(folder, d0, d1)
    calls, forms = res["calls"], res["forms"]
    meta = {"calls_total": len(calls), "calls_via_call_view": int(calls["via_call_view"].sum()) if len(calls) else 0,
            "call_view_rows": res["cv_total"], "call_view_orphans": len(res["cv_orphans"]), "cv_mismatch": res["cv_mismatch"],
            "forms_google": int((forms["src"] == "google").sum()), "forms_google_no_campaign": int(((forms["src"] == "google") & (forms["camp"] == "")).sum()),
            "forms_first_day": str(forms["day"].min()) if len(forms) else None}
    recs = []
    for _, r in calls.iterrows():
        c = r["camp"] if r["camp"] not in (LS.UNRESOLVED, "") else NOCAMP
        recs.append((r["day"], c, "adcall" if r["via_call_view"] else "call"))
    for _, r in forms[forms["src"] == "google"].iterrows():
        recs.append((r["day"], r["camp"] or NOCAMP, "form"))
    lead = pd.DataFrame(recs, columns=["day", "camp", "kind"])
    lead = lead[~lead["camp"].str.lower().str.startswith(EXCLUDE_PREFIX)]
    lead["day"] = pd.to_datetime(lead["day"]).dt.date
    cnt = lead.pivot_table(index=["day", "camp"], columns="kind", values="camp", aggfunc="size", fill_value=0).reset_index()
    for k in ("call", "adcall", "form"):
        if k not in cnt:
            cnt[k] = 0
    cnt["leads"] = cnt["call"] + cnt["adcall"] + cnt["form"]
    ga = LS._gads_client().get_service("GoogleAdsService")
    ads = campaign_daily_ads(ga, CLIENTS[folder], d0, d1)
    ads = ads.groupby(["day", "camp"], as_index=False)[["cost", "clicks", "impr"]].sum()
    panel = ads.merge(cnt, on=["day", "camp"], how="outer")
    for c in ("cost", "clicks", "impr", "call", "adcall", "form", "leads"):
        panel[c] = panel[c].fillna(0)
    return panel, meta


def full_weeks(days):
    """Число целых недель пн-вс внутри [min(days), max(days)]."""
    if len(days) == 0:
        return 0
    a, b = pd.Timestamp(min(days)), pd.Timestamp(max(days))
    first_mon = a + pd.Timedelta(days=(7 - a.weekday()) % 7)
    last_sun = b - pd.Timedelta(days=(b.weekday() + 1) % 7)
    return max(0, ((last_sun - first_mon).days + 1) // 7)


def history_report(panel, meta, d0, d1):
    panel = panel.copy()
    panel["day"] = pd.to_datetime(panel["day"])
    last_full = pd.Timestamp(d1)   # d1 = вчера (завершённый день)
    out = []
    acc = panel.groupby("day", as_index=False)[["cost", "clicks", "leads"]].sum()
    groups = [("АККАУНТ (без yt_)", acc)] + [(c, g) for c, g in panel.groupby("camp")]
    for name, g in groups:
        g = g.sort_values("day")
        active = g[(g["cost"] > 0) | (g["clicks"] > 0)]
        first_cost = active["day"].min() if len(active) else None
        first_lead = g.loc[g["leads"] > 0, "day"].min() if (g["leads"] > 0).any() else None
        if first_cost is None:
            continue
        span = pd.date_range(first_cost, last_full)
        gg = g.set_index("day").reindex(span).fillna(0)
        out.append({"кампания": name, "первый_день_расхода": first_cost.date(), "первая_заявка": first_lead.date() if first_lead is not None else None,
                    "дней_ряда": len(span), "целых_недель": full_weeks(span), "расход": round(gg["cost"].sum(), 1), "клики": int(gg["clicks"].sum()),
                    "заявок_всего": int(gg["leads"].sum()), "дней_с_нулём_заявок": int((gg["leads"] == 0).sum()),
                    "дней_с_расходом": int((gg["cost"] > 0).sum()), "заявок_последние_28д": int(gg.loc[gg.index > last_full - pd.Timedelta(days=28), "leads"].sum())})
    return pd.DataFrame(out)


def changes_report(customer_id, date_from, date_to):
    """Правки из change_event (предел API ~29 дней). → DataFrame (как gads_change_history.fetch_change_history)."""
    import gads_change_history as H
    from gads_stats import get_ads_service
    from google.ads.googleads.client import GoogleAdsClient
    from gads_stats import GOOGLE_ADS_YAML
    ga = get_ads_service(GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id)
    df = H.fetch_change_history(ga, customer_id, date_from, date_to)
    return df, H.MAX_HISTORY_DAYS


# ======================= ШАГ Б: скользящий бэктест =======================
# Параметры с approved=False НЕ утверждены пользователем: выбраны как стандарт/минимум метода, причина рядом.
CFG = {
    "alpha": (0.05, False, "уровень значимости: стандарт 5 %, не утверждено"),
    "power": (0.80, False, "мощность для минимально обнаружимой разницы: стандарт 80 %, не утверждено"),
    "pred_level": (0.95, False, "уровень предсказательного интервала, по заданию 95 %"),
    "n_min_origins": (18, False, "минимум прогнозных недель: проверка покрытия с точностью +-10 п.п. требует n=1,96^2*0,95*0,05/0,1^2=18; "
                                  "для +-5 п.п. нужно 73; не утверждено"),
    "w_disp": (4, False, "прогнозов «в прошлом», нужных до первой оценки параметров по правдоподобию; не утверждено"),
    "w_dow": (4, False, "недель истории, с которых оценивается эффект дня недели (раньше факторы =1); не утверждено"),
    "prior_a": (0.5, False, "априор Gamma(0.5, 0): Джеффрис для интенсивности Пуассона (стандарт); не утверждено"),
    "min_total_leads": (100, False, "объект берётся, если за историю >= 100 заявок (иначе ряд почти из нулей, тест вырожден); не утверждено"),
    "delta_grid": ([0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0], False, "сетка недельного коэффициента забывания; значение выбирается по правдоподобию, не задаётся"),
    "phi_grid": ([0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0], False, "сетка сверхразброса (NB); значение выбирается по правдоподобию, не задаётся"),
}


def cfgv(k):
    return CFG[k][0]


def object_weekly(panel, name, d1):
    """Подневной ряд объекта на целых неделях пн-вс: от первого дня расхода до конца активности (действующий - до последнего воскресенья <= d1)."""
    p = panel.copy()
    p["day"] = pd.to_datetime(p["day"])
    if name == "__ACCOUNT__":
        g = p.groupby("day")[["cost", "clicks", "leads"]].sum()
    else:
        g = p[p["camp"] == name].set_index("day")[["cost", "clicks", "leads"]]
    act = g[(g["cost"] > 0) | (g["clicks"] > 0)]
    first = act.index.min()
    last_act = act.index.max()
    if (g["leads"] > 0).any():
        last_act = max(last_act, g.index[g["leads"] > 0].max())
    d1t = pd.Timestamp(d1)
    end_cap = d1t if last_act >= d1t - pd.Timedelta(days=6) else last_act
    start = first + pd.Timedelta(days=(7 - first.weekday()) % 7)
    end = end_cap - pd.Timedelta(days=(end_cap.weekday() + 1) % 7)
    if end <= start:
        return None
    idx = pd.date_range(start, end)
    y = g["leads"].reindex(idx).fillna(0).values.astype(float)
    return {"start": start, "end": end, "y": y, "T": len(idx) // 7}


def _nb_params(mu, a, phi):
    r = np.maximum(1.0 / (1.0 / np.maximum(a, 1e-12) + phi), 1e-9)
    mu = np.maximum(mu, 1e-12)
    return r, r / (r + mu)


def _nb_logpmf(y, mu, a, phi):
    """log P(Y=y): Gamma-Пуассон прогноз со средним mu, формой a и сверхразбросом phi (1/r = 1/a + phi)."""
    from scipy.stats import nbinom
    r, p = _nb_params(mu, a, phi)
    return nbinom.logpmf(y, r, p)


def _nb_q(q, mu, a, phi):
    from scipy.stats import nbinom
    r, p = _nb_params(mu, a, phi)
    return float(nbinom.ppf(q, r, p))


def _dow_factors(yd, n_days):
    """Факторы дня недели по первым n_days дням (пн=0), среднее=1; если недель < w_dow - единицы."""
    if n_days // 7 < cfgv("w_dow"):
        return np.ones(7)
    m = yd[:n_days].reshape(-1, 7).mean(axis=0)
    tot = m.mean()
    return m / tot if tot > 0 else np.ones(7)


def run_object(obj, kmax):
    """Скользящий бэктест одного объекта (прогноз недели t по данным до неё). Кандидаты: окна k=1..kmax целых недель
    (Gamma-Пуассон по недельным суммам), динамическая модель с забыванием, наивный (прошлая неделя). Параметры (phi, delta)
    на каждом шаге выбираются по накопленному предсказательному правдоподобию прошлых прогнозов (никакого заглядывания вперёд)."""
    y, T = obj["y"], obj["T"]
    w = y.reshape(T, 7).sum(axis=1)
    dg, pg, a0 = np.array(cfgv("delta_grid")), np.array(cfgv("phi_grid")), cfgv("prior_a")
    t0 = kmax + cfgv("w_disp")
    LLw = np.full((T, kmax, len(pg)), np.nan)
    MUw = np.full((T, kmax), np.nan)
    Aw = np.full((T, kmax), np.nan)
    LLd = np.full((T, len(dg), len(pg)), np.nan)
    MUd = np.full((T, len(dg)), np.nan)
    Ad = np.full((T, len(dg)), np.nan)
    dd = dg ** (1.0 / 7.0)
    for t in range(1, T):
        for k in range(1, kmax + 1):
            if t >= k:
                a = w[t - k:t].sum() + a0
                Aw[t, k - 1] = a
                MUw[t, k - 1] = a / k
                LLw[t, k - 1, :] = _nb_logpmf(w[t], a / k, a, pg)
        s = _dow_factors(y, 7 * t)
        a = np.full(len(dg), a0)
        b = np.zeros(len(dg))
        for d in range(7 * t):
            a = dd * a + y[d]
            b = dd * b + s[d % 7]
        a2, b2 = dg * a, dg * b
        Ad[t, :] = a2
        MUd[t, :] = a2 / b2 * s.sum()
        LLd[t, :, :] = _nb_logpmf(w[t], MUd[t, :, None], a2[:, None], pg[None, :])
    z = (1 - cfgv("pred_level")) / 2
    rows = []
    for t in range(t0, T):
        r = {"week": obj["start"] + pd.Timedelta(days=7 * t), "y": w[t], "naive": w[t - 1]}
        for k in range(1, kmax + 1):
            past = LLw[k:t, k - 1, :].sum(axis=0)
            j = int(np.argmax(past))
            mu, a, phi = MUw[t, k - 1], Aw[t, k - 1], pg[j]
            r[f"w{k}_mu"], r[f"w{k}_lo"], r[f"w{k}_hi"] = mu, _nb_q(z, mu, a, phi), _nb_q(1 - z, mu, a, phi)
        past = LLd[1:t].sum(axis=0)
        i, j = np.unravel_index(int(np.argmax(past)), past.shape)
        mu, a, phi = MUd[t, i], Ad[t, i], pg[j]
        r["dyn_mu"], r["dyn_lo"], r["dyn_hi"] = mu, _nb_q(z, mu, a, phi), _nb_q(1 - z, mu, a, phi)
        r["dyn_delta"], r["dyn_phi"] = dg[i], phi
        rows.append(r)
    return pd.DataFrame(rows)


def dm_test(e_a, e_b):
    """Диболд-Мариано (1995), горизонт h=1, потеря = |ошибка|; d = L_a - L_b (d>0: модель B точнее).
    Малая выборка: Харви-Лейборн-Ньюболд (1997): множитель sqrt((T+1-2h+h(h-1)/T)/T), t-распределение с T-1 степенями.
    Дисперсия d при h=1 = гамма_0. Возвращает (DM*, p одностороннее 'B точнее A', p двустороннее, sd(d), T)."""
    from scipy.stats import t as tdist
    d = np.abs(e_a) - np.abs(e_b)
    T = len(d)
    sd = d.std(ddof=0)
    if T < 3 or sd == 0:
        return np.nan, np.nan, np.nan, sd, T
    stat = d.mean() / (sd / np.sqrt(T)) * np.sqrt((T - 1) / T)
    p1 = 1 - tdist.cdf(stat, T - 1)
    return stat, p1, 2 * min(p1, 1 - p1), sd, T


def holm(p):
    """Поправка Холма (Holm 1979) к p-значениям; nan остаются nan."""
    p = np.array(p, float)
    ok = ~np.isnan(p)
    m = int(ok.sum())
    adj = np.full_like(p, np.nan)
    order = np.argsort(np.where(ok, p, np.inf))
    run = 0.0
    for rank, i in enumerate(order[:m]):
        run = max(run, min(1.0, (m - rank) * p[i]))
        adj[i] = run
    return adj


def evaluate(df, kmax):
    """Метрики кандидатов и тест DM: каждое окно против динамической модели. Холм - по окнам объекта."""
    from scipy.stats import t as tdist
    y = df["y"].values
    N = len(y)
    naive_mae = np.mean(np.abs(y - df["naive"].values))
    e_dyn = y - df["dyn_mu"].values
    mae_dyn = np.mean(np.abs(e_dyn))
    out = []
    for c, lab, k in [(f"w{k}", f"окно {k} нед.", k) for k in range(1, kmax + 1)] + [("dyn", "динамическая", None)]:
        e = y - df[f"{c}_mu"].values
        r = {"кандидат": lab, "k": k, "точек": N, "MAE": np.mean(np.abs(e)), "WAPE": np.abs(e).sum() / max(y.sum(), 1e-9),
             "MASE": np.mean(np.abs(e)) / naive_mae if naive_mae > 0 else np.nan,
             "покрытие": np.mean((y >= df[f"{c}_lo"].values) & (y <= df[f"{c}_hi"].values))}
        if c != "dyn":
            st, p1, p2, sd, _ = dm_test(e, e_dyn)
            r.update({"DM": st, "p_динамика_точнее": p1, "p_двуст": p2})
            mde = (tdist.ppf(1 - cfgv("alpha"), N - 1) + tdist.ppf(cfgv("power"), N - 1)) * sd / np.sqrt(N)
            r["MDE_доля_MAE_динамики"] = mde / mae_dyn if mae_dyn > 0 else np.nan
        out.append(r)
    res = pd.DataFrame(out)
    m = res["k"].notna()
    res.loc[m, "p_Холм"] = holm(res.loc[m, "p_динамика_точнее"].values)
    return res


def run_backtest(panel, d1, out):
    print("Параметры (утверждённых нет):")
    for k, (v, ok, why) in CFG.items():
        print(f"  {k} = {v} [{'утверждено' if ok else 'не утверждено'}] {why}")
    pan = panel.copy()
    pan["day"] = pd.to_datetime(pan["day"])
    tot = pan.groupby("camp")["leads"].sum()
    names = ["__ACCOUNT__"] + [c for c in tot.index if c != NOCAMP and tot[c] >= cfgv("min_total_leads")]
    objs = {}
    for n in names:
        o = object_weekly(pan, n, d1)
        if o is not None and o["T"] > cfgv("w_disp") + cfgv("n_min_origins"):
            objs[n] = o
    print(f"\nОбъектов в бэктесте: {len(objs)} из {len(names)} (заявок >= {cfgv('min_total_leads')} и ряд длиннее w_disp+n_min)")
    kmax_obj = {n: o["T"] - cfgv("n_min_origins") - cfgv("w_disp") for n, o in objs.items()}
    kc = min(kmax_obj.values())
    for n, o in objs.items():
        print(f"  {n[:44]:44} недель {o['T']:3d} ({o['start'].date()}..{o['end'].date()}), заявок {int(o['y'].sum()):5d}, Kmax объекта {kmax_obj[n]}")
    print(f"Общая сетка окон: 1..{kc} недель (Kmax = T - n_min - w_disp, минимум по объектам).")
    own, common = [], []
    for n, o in objs.items():
        tag = "ACCOUNT" if n == "__ACCOUNT__" else "".join(ch if ch.isalnum() else "_" for ch in n)
        df = run_object(o, kmax_obj[n])
        df.to_csv(Path(out) / f"backtest_points_{tag}.csv", index=False, encoding="utf-8-sig")
        ev = evaluate(df, kmax_obj[n])
        ev.insert(0, "объект", n)
        own.append(ev)
        dfc = run_object(o, kc)   # общая сетка 1..kc: прогнозные недели с t0 = kc + w_disp (больше точек, чем у собственной сетки)
        dfc.to_csv(Path(out) / f"backtest_points_common_{tag}.csv", index=False, encoding="utf-8-sig")
        evc = evaluate(dfc, kc)
        print(f"  [{n[:30]}] выбранное забывание delta (недельное): медиана {dfc['dyn_delta'].median():.2f}, на нижней границе сетки {np.mean(dfc['dyn_delta'] == min(cfgv('delta_grid'))):.0%} недель; phi на верхней границе {np.mean(dfc['dyn_phi'] == max(cfgv('phi_grid'))):.0%}")
        evc.insert(0, "объект", n)
        common.append(evc)
    A = pd.concat(own, ignore_index=True)
    C = pd.concat(common, ignore_index=True)
    A.to_csv(Path(out) / "backtest_candidates_own_grid.csv", index=False, encoding="utf-8-sig")
    C.to_csv(Path(out) / "backtest_candidates_common_grid.csv", index=False, encoding="utf-8-sig")
    print("\n=== ПО ОБЪЕКТАМ: динамическая против лучшего окна своей сетки (Холм по окнам объекта) ===")
    for n in objs:
        s = A[A["объект"] == n]
        d = s[s["кандидат"] == "динамическая"].iloc[0]
        w = s[s["k"].notna()]
        b = w.loc[w["MAE"].idxmin()]
        print(f"\n{n} | прогнозных недель {int(d['точек'])}, окон в сетке {len(w)}")
        print(f"  динамическая: WAPE {d['WAPE']:.3f}, MASE {d['MASE']:.3f}, покрытие95 {d['покрытие']:.2f}")
        print(f"  лучшее окно {int(b['k'])} нед.: WAPE {b['WAPE']:.3f}, MASE {b['MASE']:.3f}, покрытие95 {b['покрытие']:.2f}, "
              f"p(динамика точнее; Холм) {b['p_Холм']:.3f}, MDE {b['MDE_доля_MAE_динамики']:.2f} от MAE динамики")
        for k in (2, 4):
            if k in set(w["k"]):
                r = w[w["k"] == k].iloc[0]
                print(f"  строка сетки окно {k} нед.: WAPE {r['WAPE']:.3f}, покрытие {r['покрытие']:.2f}, p_Холм {r['p_Холм']:.3f}")
    cw = C[C["k"].notna()].copy()
    cw["p_Холм_семья"] = holm(cw["p_динамика_точнее"].values)
    cw.to_csv(Path(out) / "backtest_common_window_tests.csv", index=False, encoding="utf-8-sig")
    print(f"\n=== ОБЩЕЕ ОКНО 1..{kc}: не хуже динамики у ВСЕХ объектов? (Холм по семье из {len(cw)} пар объект x окно, alpha {cfgv('alpha')}) ===")
    ok_k = []
    for k in range(1, kc + 1):
        s = cw[cw["k"] == k]
        worse = s[s["p_Холм_семья"] < cfgv("alpha")]
        print(f"  окно {k:2d} нед.: хуже динамики у {len(worse)} из {len(s)}"
              + (" (" + ", ".join(x[:22] for x in worse["объект"]) + ")" if len(worse) else "")
              + f"; макс WAPE {s['WAPE'].max():.3f}; мин p_Холм_семья {s['p_Холм_семья'].min():.3f}")
        if len(worse) == 0:
            ok_k.append(k)
    print("ВЕРДИКТ общее окно:", (f"да, не отвергнуто для окон {ok_k} нед. (это 'не доказано хуже', не 'доказано равенство'; см. MDE)" if ok_k else "нет"))


def main():
    ap = argparse.ArgumentParser(description="Бэктест периода и модели прогноза заявок (только чтение)")
    ap.add_argument("--history", action="store_true", help="Шаг А: проверка глубины истории (строит панель CSV)")
    ap.add_argument("--backtest", action="store_true", help="Шаг Б: скользящий бэктест по панели CSV (или --rebuild)")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--client", default="ProfiMet")
    ap.add_argument("--customer-id", default=None)
    ap.add_argument("--from", dest="d0", default="2025-08-01", help="начало выгрузки (Ringostat у ProfiMet с 2025-08-01)")
    ap.add_argument("--to", dest="d1", default=None, help="по умолчанию вчера")
    ap.add_argument("--out", default=str(WORKDIR))
    a = ap.parse_args()
    d1 = a.d1 or (date.today() - timedelta(days=1)).isoformat()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.customer_id:
        CLIENTS[a.client] = a.customer_id
    print("Библиотеки:", libs_report())
    pf = out / "panel_day_campaign.csv"
    if a.history or (a.backtest and (a.rebuild or not pf.exists())):
        panel, meta = build_panel(a.client, a.d0, d1)
        panel.to_csv(pf, index=False, encoding="utf-8-sig")
        print("Источники:", meta)
        if a.history:
            rep = history_report(panel, meta, a.d0, d1)
            rep.to_csv(out / "history_report.csv", index=False, encoding="utf-8-sig")
            with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 200, "display.max_colwidth", 40):
                print(rep.to_string(index=False))
            print(f"Панель: {pf}")
    if a.backtest:
        run_backtest(pd.read_csv(pf), d1, out)


if __name__ == "__main__":
    main()
