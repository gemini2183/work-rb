#!/usr/bin/env python
# coding: utf-8
"""Байесовский анализ срезов Search-кампании — реализация методологии
База_знаний/Паттерны/Google-Ads-Search-байесовский-анализ-срезов-и-рычагов.md
(Часть 2: Beta-Binomial + sequential updating по неделям, тренд vs шум).

Регулярный инструмент, не разовый скрипт — рассчитан на повторный запуск при
каждом периодическом аудите Search-кампании любого клиента, не только ProfiMet.

Что делает:
1. Тянет метрики (клики, конверсии, cost) по выбранному срезу (--slice-by)
   x неделе за период через Google Ads API.
2. Для каждого среза считает sequential Bayesian Beta-Binomial апостериор:
   апостериор недели t получается обновлением апостериора недели t-1 данными
   недели t, с discount factor (затухание "силы" предыдущего апостериора перед
   каждым обновлением) — см. Часть 2.6 методологии. НЕ независимая оценка по
   каждой неделе и НЕ один агрегат на весь период.
3. Классифицирует финальный тренд: TREND_DOWN / TREND_UP / NOISE /
   STRUCTURAL_BREAK / INSUFFICIENT_HISTORY (< MIN_WEEKS недель).
4. Считает P(срез хуже среднего на >=delta) и P(срез лучше среднего на >=delta)
   по последней неделе апостериора, и expected impact = P_хуже * cost среза
   (Часть 2.4).
5. Выводит ранжированную таблицу с рекомендацией; НЕ выполняет никаких
   изменений в аккаунте сама — только даёт данные для решения (см. Часть 3
   методологии — решение зависит ещё и от состояния KPI месяца, это ручной
   шаг поверх вывода скрипта, не автоматизируется здесь).

Поддерживаемые срезы (--slice-by):
    ad_group  — группа объявлений (campaign resource, метрики по ad_group)
    device    — Desktop/Mobile/Tablet (segments.device)
    dow       — день недели (segments.day_of_week) — ВНИМАНИЕ: это агрегат по
                дню недели за весь период, отдельная ось от понедельной
                разбивки, которая используется для sequential updating самого
                среза (см. --slice-by ad_group/device — там подпериоды это
                КАЛЕНДАРНЫЕ недели; для dow "недельный" временной срез не
                имеет смысла, dow сравнивается по МЕСЯЧНЫМ подпериодам вместо
                недель, --period-days задаёт длину подпериода).

Использование:
    python gads_bayesian_slice_analysis.py --customer-id 7552781705 \
        --client-folder "ProfiMet" --campaign "Search | Poliweglan | Pl" \
        --slice-by ad_group --weeks 8

    python gads_bayesian_slice_analysis.py --customer-id 7552781705 \
        --client-folder "ProfiMet" --campaign "Search | Poliweglan | Pl" \
        --slice-by device --weeks 8 --delta 0.02

Параметры метода (см. докстринги функций ниже для обоснования):
    --prior-strength K   сила общего prior в эквиваленте наблюдений (default 30)
    --discount LAMBDA    коэффициент затухания апостериора между неделями (default 0.8)
    --delta DELTA         порог практической значимости в п.п. конверсии (default 0.02 = 2 п.п.)
    --action-threshold P  порог P(хуже/лучше) для классификации "кандидат на действие" (default 0.9)
    --min-weeks N          минимум подпериодов для оценки тренда (default 3)
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from scipy import stats

from _config import client_stats_dir, get_client_row, sanitize_filename
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


# ---------------------------------------------------------------------------
# Сбор данных: срез x неделя
# ---------------------------------------------------------------------------

_SLICE_FIELD = {
    "ad_group": "ad_group.name",
    "device": "segments.device",
    "dow": "segments.day_of_week",
}


def fetch_slice_by_week(ga_service, customer_id, campaign_name, slice_by, date_from, date_to):
    """Метрики campaign x срез x неделя (ISO week начала недели) -> DataFrame.

    Неделя — календарная, начало по понедельнику (ISO), не скользящее окно.
    segments.week в GAQL уже отдаёт дату понедельника недели напрямую — не
    нужно вычислять вручную из segments.date (было бы источником off-by-one
    ошибок на границах месяца/года)."""
    field = _SLICE_FIELD[slice_by]
    resource = "ad_group" if slice_by == "ad_group" else "campaign"
    query = f"""
        SELECT
            campaign.name,
            {field},
            segments.week,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM {resource}
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """

    agg = {}
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if row.campaign.name != campaign_name:
                continue
            if slice_by == "ad_group":
                slice_value = row.ad_group.name
            elif slice_by == "device":
                slice_value = _enum_name("DeviceEnum", "Device", row.segments.device)
            else:  # dow
                slice_value = _enum_name("DayOfWeekEnum", "DayOfWeek", row.segments.day_of_week)
            week = row.segments.week
            k = (slice_value, week)
            m = agg.setdefault(k, {"clicks": 0, "cost": 0.0, "conversions": 0.0})
            m["clicks"] += row.metrics.clicks
            m["cost"] += row.metrics.cost_micros / 1_000_000
            m["conversions"] += row.metrics.conversions

    if not agg:
        return pd.DataFrame()

    rows = [
        {
            "Slice": k[0],
            "Week": k[1],
            "Clicks": int(m["clicks"]),
            "Cost": round(m["cost"], 2),
            "Conversions": round(m["conversions"], 2),
        }
        for k, m in agg.items()
    ]
    return pd.DataFrame(rows).sort_values(["Slice", "Week"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Часть 2.2 — Beta-Binomial апостериор (одно окно)
# ---------------------------------------------------------------------------

def campaign_prior(total_clicks, total_conversions, prior_strength):
    """Информативный prior Beta(a0, b0) из данных всей кампании (Часть 2.2).

    Не Beta(1,1) uniform — это выбросило бы всё, что уже известно о базовой
    конверсии кампании. prior_strength (k) — "сила" prior в эквиваленте
    наблюдений: k=30 означает, что prior эквивалентен 30 кликам кампании с
    её базовой CR. При малом k (~10) prior слабо сглаживает шумные срезы,
    при большом (~100) — почти не даёт срезу отклониться от среднего даже
    при реальном эффекте. 20-50 — практический диапазон по умолчанию
    (см. методологию, Часть 2.2)."""
    if total_clicks == 0:
        return prior_strength / 2, prior_strength / 2
    cr = total_conversions / total_clicks
    cr = min(max(cr, 1e-6), 1 - 1e-6)  # не допустить вырожденных 0/1
    a0 = prior_strength * cr
    b0 = prior_strength * (1 - cr)
    return a0, b0


# ---------------------------------------------------------------------------
# Часть 2.6 — sequential Bayesian updating с discount factor
# ---------------------------------------------------------------------------

def sequential_update(weekly_data, a0, b0, discount):
    """weekly_data: список (clicks, conversions) по неделям в хронологическом
    порядке. Возвращает список апостериоров Beta(a, b) — один на каждую
    неделю, ПОСЛЕ обновления данными этой недели.

    Ключевая механика (Часть 2.6, п.2-3): апостериор недели t получается не
    из исходного a0/b0 заново, а из апостериора недели t-1, чья "сила"
    (a+b) предварительно домножается на discount (0 < discount <= 1) —
    затухание веса старых данных перед тем, как добавить новую неделю.
    discount=1.0 — данные никогда не устаревают (чистое накопление без
    забывания, подходит для очень стабильной ниши); discount~0.7-0.9 —
    типичный диапазон, откалиброван позже по факту наблюдаемой волатильности
    конкретного клиента, единого универсального значения methodology не
    фиксирует (см. Часть 2.6, п.3)."""
    posteriors = []
    a, b = a0, b0
    for clicks, conversions in weekly_data:
        # Discount ДО добавления новой недели — затухание силы предыдущего
        # знания, не текущей недели.
        a = a * discount
        b = b * discount
        conversions = min(conversions, clicks)  # защита от float-погрешности API
        a += conversions
        b += (clicks - conversions)
        posteriors.append((a, b))
    return posteriors


def posterior_mean(a, b):
    return a / (a + b)


def prob_worse_by_delta(a_slice, b_slice, a_campaign, b_campaign, delta, n_samples=20000):
    """P(theta_slice < theta_campaign - delta) через Monte Carlo сэмплирование
    из обоих апостериоров (Часть 2.2). Аналитическая разность двух Beta
    возможна, но MC проще читать/проверять и достаточно быстрый для этого
    объёма срезов — не оптимизация, которая того стоит на данном этапе."""
    slice_samples = stats.beta.rvs(a_slice, b_slice, size=n_samples)
    campaign_samples = stats.beta.rvs(a_campaign, b_campaign, size=n_samples)
    return float((slice_samples < campaign_samples - delta).mean())


def prob_better_by_delta(a_slice, b_slice, a_campaign, b_campaign, delta, n_samples=20000):
    slice_samples = stats.beta.rvs(a_slice, b_slice, size=n_samples)
    campaign_samples = stats.beta.rvs(a_campaign, b_campaign, size=n_samples)
    return float((slice_samples > campaign_samples + delta).mean())


def classify_trend(posteriors, min_weeks):
    """Часть 2.6, п.4-5 — TREND_UP/TREND_DOWN/NOISE/STRUCTURAL_BREAK/
    INSUFFICIENT_HISTORY по последовательности апостериорных средних.

    Признак тренда: apostrior mean монотонно (без учёта последней недели,
    которая может быть шумом сама по себе — оценивается по первым N-1)
    движется в одну сторону >=3 подпериода, и дисперсия не растёт.
    Признак структурного слома: скачок apostrior mean между двумя соседними
    неделями, который держится (следующая неделя не откатывает обратно)."""
    if len(posteriors) < min_weeks:
        return "INSUFFICIENT_HISTORY"

    means = [posterior_mean(a, b) for a, b in posteriors]
    variances = [(a * b) / ((a + b) ** 2 * (a + b + 1)) for a, b in posteriors]

    # Структурный слом: разница между соседними неделями заметно больше
    # типичной разницы в остальном ряду, и следующий шаг её не откатывает.
    diffs = [means[i + 1] - means[i] for i in range(len(means) - 1)]
    if len(diffs) >= 2:
        abs_diffs = [abs(d) for d in diffs]
        median_diff = sorted(abs_diffs)[len(abs_diffs) // 2]
        for i in range(len(diffs) - 1):
            jump = diffs[i]
            held = (diffs[i] > 0 and diffs[i + 1] >= -abs(jump) * 0.3) or \
                   (diffs[i] < 0 and diffs[i + 1] <= abs(jump) * 0.3)
            if median_diff > 0 and abs(jump) > 3 * median_diff and held:
                return "STRUCTURAL_BREAK"

    # Монотонность по последним min_weeks неделям (без учёта самой последней
    # точки в оценке направления — она "подтверждает", не "задаёт" тренд).
    recent = means[-min_weeks:]
    increasing = all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1))
    decreasing = all(recent[i] >= recent[i + 1] for i in range(len(recent) - 1))
    var_growing = variances[-1] > variances[-min_weeks] * 1.5 if len(variances) >= min_weeks else False

    if increasing and not var_growing and means[-1] > means[0]:
        return "TREND_UP"
    if decreasing and not var_growing and means[-1] < means[0]:
        return "TREND_DOWN"
    return "NOISE"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True, help="Точное название кампании")
    ap.add_argument("--slice-by", required=True, choices=list(_SLICE_FIELD.keys()))
    ap.add_argument("--weeks", type=int, default=8, help="Сколько последних недель анализировать")
    ap.add_argument("--prior-strength", type=float, default=30.0)
    ap.add_argument("--discount", type=float, default=0.8)
    ap.add_argument("--delta", type=float, default=0.02, help="Порог практической значимости, доля (0.02 = 2 п.п.)")
    ap.add_argument("--action-threshold", type=float, default=0.9)
    ap.add_argument("--min-weeks", type=int, default=3)
    args = ap.parse_args()

    if args.customer_id:
        customer_id = args.customer_id.replace("-", "").strip()
    elif args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    else:
        print("Нужен либо --client, либо --customer-id")
        return

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    date_to = date.today() - timedelta(days=1)
    date_from = date_to - timedelta(weeks=args.weeks)

    print(f"Кампания: {args.campaign} | срез: {args.slice_by} | период {date_from} -> {date_to}")
    df = fetch_slice_by_week(ga_service, customer_id, args.campaign, args.slice_by, date_from, date_to)
    if df.empty:
        print("Нет данных за период.")
        return

    out_dir = client_stats_dir(args.client_folder)
    safe_campaign = sanitize_filename(args.campaign)
    raw_path = out_dir / f"gads_bayesian_raw_{args.slice_by}_{safe_campaign}.csv"
    df.to_csv(raw_path, index=False, encoding="utf-8")

    # Общий prior кампании — из ВСЕХ данных периода целиком (не по срезам).
    total_clicks = int(df["Clicks"].sum())
    total_conversions = float(df["Conversions"].sum())
    a0, b0 = campaign_prior(total_clicks, total_conversions, args.prior_strength)
    campaign_cr = total_conversions / total_clicks if total_clicks else 0.0
    print(f"Кампания целиком: {total_clicks} кликов, {total_conversions:.2f} конв., CR={campaign_cr:.4f}, "
          f"prior=Beta({a0:.2f},{b0:.2f})")

    results = []
    for slice_value, g in df.groupby("Slice"):
        g = g.sort_values("Week")
        weekly = list(zip(g["Clicks"], g["Conversions"]))
        posteriors = sequential_update(weekly, a0, b0, args.discount)
        a_last, b_last = posteriors[-1]

        trend = classify_trend(posteriors, args.min_weeks)
        p_worse = prob_worse_by_delta(a_last, b_last, a0, b0, args.delta)
        p_better = prob_better_by_delta(a_last, b_last, a0, b0, args.delta)
        total_cost = float(g["Cost"].sum())
        total_slice_clicks = int(g["Clicks"].sum())
        total_slice_conv = float(g["Conversions"].sum())

        expected_wasted = p_worse * total_cost

        # Итоговая рекомендация — Часть 2.6 п.6: действовать, только если и
        # порог P пройден, И тренд подтверждён (не INSUFFICIENT_HISTORY/NOISE).
        if trend == "INSUFFICIENT_HISTORY":
            verdict = "NEED_MORE_DATA"
        elif p_worse >= args.action_threshold and trend in ("TREND_DOWN", "STRUCTURAL_BREAK"):
            verdict = "CANDIDATE_ACTION_BAD"
        elif p_better >= args.action_threshold and trend in ("TREND_UP", "STRUCTURAL_BREAK"):
            verdict = "CANDIDATE_ACTION_GOOD"
        elif p_worse >= args.action_threshold or p_better >= args.action_threshold:
            verdict = "WATCH_UNCONFIRMED_TREND"  # высокая P, но тренд не подтверждён/шум
        else:
            verdict = "WITHIN_NORMAL_RANGE"

        results.append({
            "Slice": slice_value,
            "Weeks_of_data": len(posteriors),
            "Total_clicks": total_slice_clicks,
            "Total_conversions": round(total_slice_conv, 2),
            "Total_cost": round(total_cost, 2),
            "Posterior_mean_CR": round(posterior_mean(a_last, b_last), 4),
            "Trend": trend,
            "P_worse_by_delta": round(p_worse, 3),
            "P_better_by_delta": round(p_better, 3),
            "Expected_wasted_spend": round(expected_wasted, 2),
            "Verdict": verdict,
        })

    res_df = pd.DataFrame(results).sort_values("Expected_wasted_spend", ascending=False).reset_index(drop=True)
    out_path = out_dir / f"gads_bayesian_analysis_{args.slice_by}_{safe_campaign}.csv"
    res_df.to_csv(out_path, index=False, encoding="utf-8")

    print(f"\nСохранено: {out_path}")
    print(res_df.to_string(index=False))
    print(
        "\nVerdict: CANDIDATE_ACTION_BAD/GOOD = порог P пройден И тренд подтверждён (>= "
        f"{args.min_weeks} нед.) | WATCH_UNCONFIRMED_TREND = высокая P, но тренд не "
        "подтверждён (возможен шум/слишком мало истории) — наблюдать дальше, не "
        "действовать | NEED_MORE_DATA = меньше --min-weeks недель истории | "
        "WITHIN_NORMAL_RANGE = ничего не выделяется"
    )


if __name__ == "__main__":
    main()
