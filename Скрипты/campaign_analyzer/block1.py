"""Блок 1 методологии: данные верны? -> заявки -> план и разрыв.

Шаги (База_знаний/Паттерны/Алгоритм-анализа-эффективности-кампании-блок-схема.md):
  1. Сверка звонков Ringostat в Google Ads с СЫРЫМИ звонками Ringostat.
     Окно определяется объёмом данных (не календарём), допуск считается сам по
     истории клиента, вердикт: ok / сомнительно / недостоверно.
  2. Заявка = формы + звонки по объявлениям (Ads) + динамические звонки
     (из Ads, если сверка ок, иначе уникальные звонки Ringostat).
  3. План месяца из Google-таблицы, факт по ПРОЕКТУ, нужная цена заявки на
     остаток месяца и разрыв по объёму (вердикта "недостижимо" не выдаёт).

Только считает и печатает, в аккаунтах ничего не меняет.

Использование (из папки Скрипты/):
    python -m campaign_analyzer.block1 --client ProfiMet
    python -m campaign_analyzer.block1 --client ProfiMet --as-of 2026-10-05
"""
import argparse
import calendar
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import sources as S

LAG_DAYS = 2            # последние дни не берём в сверку: конверсии Ads "дозревают"
MIN_CALLS_WINDOW = 40   # сколько звонков нужно в окне сверки
MAX_WEEKS = 8
MIN_CALLS_HIST = 10     # окна истории с меньшим числом звонков в калибровку не берём
MIN_HIST_WINDOWS = 4    # меньше окон истории — допуск по умолчанию
DEFAULT_REL_TOL = 0.25
REL_FLOOR = 0.10
ABS_FLOOR_CALLS = 3
HARD_BAND = (0.5, 2.0)  # вне этих границ данные недостоверны независимо от истории


def _daily(df, col, start, end, mask=None):
    d = df if mask is None else df[mask]
    idx = pd.date_range(start, end)
    return d.groupby("date")[col].sum().reindex(idx, fill_value=0.0)


def pick_window(ringo_daily: pd.Series, end: pd.Timestamp):
    """Окно сверки — целые недели; берём минимальное, где достаточно звонков."""
    for w in range(1, MAX_WEEKS + 1):
        start = end - pd.Timedelta(days=7 * w - 1)
        if ringo_daily.loc[start:end].sum() >= MIN_CALLS_WINDOW:
            return w, False
    return MAX_WEEKS, True


def calibrate(ads_daily, ringo_daily, end, weeks, hist_start):
    """Отношения Ads/Ringostat на окнах той же длины, сдвигаясь назад по неделям."""
    ratios = []
    k = 1
    while True:
        e = end - pd.Timedelta(days=7 * k)
        s = e - pd.Timedelta(days=7 * weeks - 1)
        if s < hist_start:
            break
        r = ringo_daily.loc[s:e].sum()
        if r >= MIN_CALLS_HIST:
            ratios.append(ads_daily.loc[s:e].sum() / r)
        k += 1
    return ratios


def reconcile(ads_calls_daily, ringo_dyn_daily, end, hist_start):
    weeks, short = pick_window(ringo_dyn_daily, end)
    start = end - pd.Timedelta(days=7 * weeks - 1)
    a = float(ads_calls_daily.loc[start:end].sum())
    r = float(ringo_dyn_daily.loc[start:end].sum())
    ratios = calibrate(ads_calls_daily, ringo_dyn_daily, end, weeks, hist_start)
    default = len(ratios) < MIN_HIST_WINDOWS
    # Центр допуска ВСЕГДА 1.0: два источника описывают одни и те же звонки и должны
    # совпадать. По истории берём только РАЗБРОС (шум сдвига дат клик/звонок и т.п.).
    # Центр по медиане истории был бы ошибкой: хроническое занижение Ads стало бы
    # "нормой клиента" (обнаружено на первом прогоне ProfiMet: отношение 0.5 в истории).
    m = float(np.median(ratios)) if ratios else float("nan")
    if default:
        tol_rel = DEFAULT_REL_TOL
    else:
        mad = 1.4826 * float(np.median(np.abs(np.array(ratios) - m)))
        tol_rel = max(2 * mad, REL_FLOOR)
    tol_abs = max(ABS_FLOOR_CALLS, tol_rel * r)
    ratio = a / r if r else float("nan")
    if r and abs(a - r) <= tol_abs:
        status = "ok"
    elif r and HARD_BAND[0] <= ratio <= HARD_BAND[1]:
        status = "сомнительно"
    else:
        status = "недостоверно"
    bias = (not default) and (abs(m - 1.0) > tol_rel)
    return dict(start=start, end=end, weeks=weeks, short=short, ads=a, ringo=r, ratio=ratio,
                hist_median=m, tol_rel=tol_rel, tol_abs=tol_abs, n_hist=len(ratios),
                ratios=ratios, default=default, bias=bias, status=status)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="Имя папки клиента в Клиенты/")
    ap.add_argument("--as-of", help="YYYY-MM-DD, по умолчанию сегодня; данные берутся по вчера")
    args = ap.parse_args()

    cfg = S.load_config(args.client)
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(date.today())
    data_end = as_of - pd.Timedelta(days=1)
    hist_start = pd.Timestamp(cfg["history_start"])
    cust = cfg["customer_id"]
    acts = cfg["ads_actions"]

    svc = S.ads_service()
    spend = S.fetch_ads_spend(svc, cust, hist_start.date(), data_end.date())
    conv = S.fetch_ads_conversions(svc, cust, hist_start.date(), data_end.date())
    calls = S.fetch_calls(cfg, f"{data_end.date()} 23:59:59")

    idx_all = (hist_start, data_end)
    ads_ringo = _daily(conv, "conversions", *idx_all, mask=conv["action"].isin(acts["ringostat_calls"]))
    dyn_raw = calls[(calls.category == "Google Ads") & (~calls.is_static)]
    ringo_raw_daily = dyn_raw.groupby("day").size().reindex(pd.date_range(*idx_all), fill_value=0).astype(float)
    ringo_new_daily = dyn_raw[dyn_raw.is_new].groupby("day").size().reindex(pd.date_range(*idx_all), fill_value=0).astype(float)

    # ---------- 1. сверка ----------
    rec_end = data_end - pd.Timedelta(days=LAG_DAYS)
    rec = reconcile(ads_ringo, ringo_raw_daily, rec_end, hist_start)
    print(f"=== 1. ДАННЫЕ ВЕРНЫ? ({args.client}, на {as_of.date()}) ===")
    print(f"Окно сверки: {rec['start'].date()} — {rec['end'].date()} ({rec['weeks']} нед.; "
          f"последние {LAG_DAYS} дн. не берём — конверсии ещё дозревают)"
          + (" [звонков меньше нужного минимума]" if rec["short"] else ""))
    print(f"Звонки Ringostat в Google Ads: {rec['ads']:.0f} | сырые звонки Ringostat (динамические): {rec['ringo']:.0f} | отношение {rec['ratio']:.2f}")
    src = "по умолчанию (истории мало)" if rec["default"] else f"по истории клиента ({rec['n_hist']} окон)"
    print(f"Норма клиента: {rec['norm']:.2f}, допуск ±{rec['tol_rel']*100:.0f}% (не меньше {ABS_FLOOR_CALLS} звонков) — {src}")
    print(f"ВЕРДИКТ: {rec['status'].upper()}")

    cmp = (conv[(conv.action.isin(acts["ringostat_calls"])) & (conv.date >= rec["start"]) & (conv.date <= rec["end"])]
           .groupby(["campaign_id", "campaign"])["conversions"].sum().rename("Ads").reset_index())
    rr = (dyn_raw[(dyn_raw.day >= rec["start"]) & (dyn_raw.day <= rec["end"])]
          .groupby("campaign_id").size().rename("Ringostat").reset_index())
    t = cmp.merge(rr, on="campaign_id", how="outer").fillna({"Ads": 0, "Ringostat": 0})
    names = spend.drop_duplicates("campaign_id").set_index("campaign_id")["campaign"]
    t["campaign"] = t["campaign"].fillna(t["campaign_id"].map(names)).fillna("(неизвестно)")
    print("\nПо кампаниям (то же окно):")
    print(t[["campaign", "Ads", "Ringostat"]].round(1).to_string(index=False))

    # ---------- 2. заявки ----------
    if rec["status"] == "ok":
        dyn_leads, dyn_src = ads_ringo, "из Google Ads (сверка в допуске)"
    else:
        dyn_leads, dyn_src = ringo_new_daily, "уникальные звонки Ringostat (сверка вне допуска)"
    forms = _daily(conv, "conversions", *idx_all, mask=conv["action"].isin(acts["forms"]))
    adcalls = _daily(conv, "conversions", *idx_all, mask=conv["action"].isin(acts["ad_calls"]))
    leads = (forms + adcalls + dyn_leads).rename("leads")
    print(f"\n=== 2. ЗАЯВКА = формы + звонки по объявлениям + динамические звонки ===")
    print(f"Динамические звонки берём: {dyn_src}")

    # ---------- 3. план ----------
    plan = S.read_plan(cfg, data_end)
    m_start = data_end.replace(day=1)
    elapsed = data_end.day
    dim = calendar.monthrange(data_end.year, data_end.month)[1]
    remaining = dim - elapsed
    spent = float(spend[(spend.date >= m_start) & (spend.date <= data_end)]["cost"].sum())
    got = float(leads.loc[m_start:data_end].sum())
    print(f"\n=== 3. ГДЕ МЫ ОТНОСИТЕЛЬНО ПЛАНА (проект, {plan['tab']}, факт по {data_end.date()}) ===")
    print(f"План: {plan['leads']:.0f} заявок, цена заявки {plan['cpa']:.1f}, бюджет {plan['budget']:.0f}")
    print(f"Факт за {elapsed} из {dim} дн.: расход {spent:.2f} ({spent/plan['budget']*100:.1f}% бюджета), "
          f"заявок {got:.1f} ({got/plan['leads']*100:.1f}% плана), цена заявки "
          + (f"{spent/got:.1f}" if got else "—"))
    left = plan["leads"] - got
    if left <= 0:
        print("План по объёму уже выполнен.")
    else:
        req_b = (plan["budget"] - spent) / left
        req_c = (plan["cpa"] * plan["leads"] - spent) / left
        print(f"Нужная цена заявки на остаток ({remaining} дн.): {req_b:.1f} по остатку бюджета"
              + (f" | {req_c:.1f} по плановой цене заявки" if abs(req_b - req_c) > 0.5 else ""))
        need_day = left / remaining if remaining else float("nan")
        pace_mtd = got / elapsed
        l14 = float(leads.loc[data_end - pd.Timedelta(days=13):data_end].sum()) / 14
        print(f"Нужно заявок в день: {need_day:.1f} | идёт: {pace_mtd:.1f} (с начала месяца), {l14:.1f} (последние 14 дн.)")
        base = pace_mtd if pace_mtd else l14
        if base:
            print(f"РАЗРЫВ ПО ОБЪЁМУ: нужен рост темпа в {need_day / base:.1f} раза (по темпу с начала месяца). "
                  f"Рычаги закрытия разрыва оцениваются в следующих блоках.")
        print(f"Расход в день: нужно {(plan['budget'] - spent) / remaining:.0f} | идёт {spent / elapsed:.0f}"
              if remaining else "")

    # доля кампаний в заявках проекта за последние 8 недель
    s56 = data_end - pd.Timedelta(days=55)
    c = conv[(conv.date >= s56) & (conv.action.isin(acts["forms"] + acts["ad_calls"] + acts["ringostat_calls"]))]
    share = c.groupby("campaign")["conversions"].sum()
    cost = spend[spend.date >= s56].groupby("campaign")["cost"].sum()
    sh = pd.concat([share.rename("заявок"), cost.rename("расход")], axis=1).fillna(0)
    sh["доля заявок %"] = sh["заявок"] / sh["заявок"].sum() * 100
    sh["цена заявки"] = np.where(sh["заявок"] > 0, sh["расход"] / sh["заявок"], np.nan)
    print("\nДоля кампаний в заявках проекта (последние 8 нед., заявки по данным Ads):")
    print(sh.sort_values("расход", ascending=False).round(1).to_string())


if __name__ == "__main__":
    main()
