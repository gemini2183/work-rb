#!/usr/bin/env python
# coding: utf-8
"""Streamlit-дашборд: эффективность Google Ads кампании в целом, динамика по
неделям/месяцам — визуальная надстройка над CSV campaign x день, который
собирает gads_campaigns_breakdown.py --by-day.

Не ходит в Google Ads API сам — только читает уже собранный CSV. Разделение
специально: сбор данных (скрипт, требует секретов/токена) и визуализация
(дашборд, можно переоткрывать много раз без новых запросов к API) — разные
шаги. Переиспользуемый инструмент — кампания/клиент/период не зашиты, только
путь к CSV с нужным диапазоном дат.

Подготовка данных (один раз на нужный период):
    cd Скрипты
    python gads_campaigns_breakdown.py --customer-id 7552781705 \
        --client-folder "ProfiMet" --date-from 2026-08-01 --date-to 2026-08-29 \
        --by-day --campaigns "Search | Poliweglan | Pl"
    python gads_change_history.py --customer-id 7552781705 \
        --client-folder "ProfiMet" --campaign "Search | Poliweglan | Pl"

Запуск дашборда:
    streamlit run dashboard_campaign_overview.py -- \
        --csv "../Клиенты/ProfiMet/Статистика/gads_campaigns_by_day_2026-08-01_to_2026-08-29.csv" \
        --changes-csv "../Клиенты/ProfiMet/Статистика/gads_change_history_Search - Poliweglan - Pl_2026-09-01_to_2026-09-30.csv"

Если --csv не передан — дашборд открывает файловый picker (text input с
путём) прямо в интерфейсе, чтобы не перезапускать процесс под каждый новый
клиент/период. --changes-csv опционален — без него дашборд просто не рисует
метки правок (можно смотреть на график до того, как собрана история
изменений, но тогда любой вывод о причине колебания в выводе дашборда
помечается "не проверено против change history", см. Часть "Gate-проверка 2"
в База_знаний/Паттерны/Алгоритм-анализа-эффективности-кампании-блок-схема.md).

Формат входного CSV — фиксированный (колонки Campaign, Date, Impressions,
Clicks, Cost, Conversions), ровно то, что пишет fetch_campaigns_by_day() в
gads_campaigns_breakdown.py. Если кампаний в файле несколько (--campaigns с
несколькими именами) — дашборд даёт выбрать одну через selectbox, метрики
считаются только по выбранной, не суммируются по умолчанию (см. предупреждение
в Скрипты/README.md про смешение Search и Performance Max в одну сумму — то
же правило "не смешивать разнородное" применимо и здесь).

Дашборд НЕ формулирует текстовые выводы о причинах сам — это сознательное
решение (см. Клиенты/ProfiMet/Решения.md, запись 2026-09-30): автоматический
причинный вердикт без проверки альтернативных объяснений повторил бы ту же
ошибку, что уже была поймана на этой кампании. Дашборд только подсвечивает
кандидатов на внимание (флаги аномалий, метки правок, неполные периоды) —
формулировка вывода и его проверка по чек-листу причинности остаётся за
аналитиком, каждое утверждение подкрепляется конкретной цифрой из данных,
видимых здесь же (принцип "утверждение → цифра → источник").
"""
import argparse
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def parse_args():
    """--csv/--changes-csv передаются после "--" в команде streamlit run —
    обычный argv парсинг здесь не работает, streamlit сам прокидывает
    хвостовые аргументы."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--changes-csv", default=None, help="CSV от gads_change_history.py — опционально")
    args, _ = ap.parse_known_args(sys.argv[1:])
    return args


@st.cache_data
def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df


@st.cache_data
def load_changes(csv_path: str) -> pd.DataFrame:
    """gads_change_history.py CSV -> только релевантные правки (Is_relevant),
    по дням (дашборд работает на дневной/недельной гранулярности, не на
    точных timestamp внутри дня)."""
    df = pd.read_csv(csv_path)
    if df.empty:
        return df
    df = df[df["Is_relevant"]].copy()
    df["Date"] = pd.to_datetime(df["Datetime"].str[:10])
    return df


def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """CTR/ср.цена клика/CPA/коэффициент конверсии — считаются из сумм
    (клики/показы/расход/конверсии), НЕ усредняются построчно. Усреднение
    дневных CTR/CPC даёт смещённую оценку на днях с малым объёмом трафика
    (день с 5 показами и день с 900 показами получили бы одинаковый вес)."""
    df = df.copy()
    df["CTR_%"] = (df["Clicks"] / df["Impressions"] * 100).round(2)
    df["CPC"] = (df["Cost"] / df["Clicks"]).round(2)
    df["CPA"] = (df["Cost"] / df["Conversions"]).round(2)
    df["CR_%"] = (df["Conversions"] / df["Clicks"] * 100).round(2)
    return df


def aggregate(df: pd.DataFrame) -> dict:
    impressions = int(df["Impressions"].sum())
    clicks = int(df["Clicks"].sum())
    cost = float(df["Cost"].sum())
    conversions = float(df["Conversions"].sum())
    return {
        "Impressions": impressions,
        "Clicks": clicks,
        "CTR_%": round(clicks / impressions * 100, 2) if impressions else None,
        "CPC": round(cost / clicks, 2) if clicks else None,
        "Cost": round(cost, 2),
        "Conversions": round(conversions, 2),
        "CPA": round(cost / conversions, 2) if conversions else None,
        "CR_%": round(conversions / clicks * 100, 2) if clicks else None,
    }


def weekly_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Понедельная агрегация (неделя начинается с понедельника, ISO) —
    устойчивее к календарным перекосам (день недели/лаг атрибуции), чем
    посуточная динамика."""
    g = df.copy()
    g["Week_start"] = g["Date"].dt.to_period("W-SUN").apply(lambda p: p.start_time)
    agg = g.groupby("Week_start").agg(
        Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"),
        Cost=("Cost", "sum"),
        Conversions=("Conversions", "sum"),
    ).reset_index()
    agg["CTR_%"] = (agg["Clicks"] / agg["Impressions"] * 100).round(2)
    agg["CPC"] = (agg["Cost"] / agg["Clicks"]).round(2)
    agg["CPA"] = (agg["Cost"] / agg["Conversions"]).round(2)
    agg["CR_%"] = (agg["Conversions"] / agg["Clicks"] * 100).round(2)
    return agg


def monthly_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    g = df.copy()
    g["Month"] = g["Date"].dt.to_period("M").astype(str)
    agg = g.groupby("Month").agg(
        Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"),
        Cost=("Cost", "sum"),
        Conversions=("Conversions", "sum"),
    ).reset_index()
    agg["CTR_%"] = (agg["Clicks"] / agg["Impressions"] * 100).round(2)
    agg["CPC"] = (agg["Cost"] / agg["Clicks"]).round(2)
    agg["CPA"] = (agg["Cost"] / agg["Conversions"]).round(2)
    agg["CR_%"] = (agg["Conversions"] / agg["Clicks"] * 100).round(2)
    return agg


def detect_anomalies(df: pd.DataFrame, metric: str, x_col: str, z_threshold: float = 1.5) -> pd.DataFrame:
    """Грубая флажковая детекция для Шага 1 (не байесовская — та применяется
    позже, на срезах, см. блок-схема) - z-score точки относительно среднего и
    стандартного отклонения ОСТАЛЬНЫХ точек ряда (leave-one-out, чтобы сам
    выброс не размывал собственный порог обнаружения). Возвращает df с
    колонками Z_score/Is_anomaly/Deviation_pct — числа для цитирования в
    выводе ("утверждение -> цифра"), не сам вывод."""
    g = df.copy().reset_index(drop=True)
    values = g[metric].astype(float)
    n = len(values)
    z_scores, deviations = [], []
    for i in range(n):
        others = values.drop(index=i)
        mean_others = others.mean() if len(others) else float("nan")
        std_others = others.std(ddof=1) if len(others) > 1 else float("nan")
        z = (values[i] - mean_others) / std_others if std_others and std_others > 0 else 0.0
        dev_pct = (values[i] - mean_others) / mean_others * 100 if mean_others else 0.0
        z_scores.append(round(z, 2))
        deviations.append(round(dev_pct, 1))
    g["Z_score"] = z_scores
    g["Deviation_pct"] = deviations
    g["Is_anomaly"] = g["Z_score"].abs() >= z_threshold
    return g


def render_kpi_row(totals: dict):
    cols = st.columns(4)
    cols[0].metric("Показы", f"{totals['Impressions']:,}".replace(",", " "))
    cols[1].metric("Клики", f"{totals['Clicks']:,}".replace(",", " "))
    cols[2].metric("CTR", f"{totals['CTR_%']}%" if totals["CTR_%"] is not None else "—")
    cols[3].metric("Ср. цена клика", f"{totals['CPC']} zł" if totals["CPC"] is not None else "—")

    cols2 = st.columns(4)
    cols2[0].metric("Расход", f"{totals['Cost']:,.2f} zł".replace(",", " "))
    cols2[1].metric("Конверсии", totals["Conversions"])
    cols2[2].metric("CPA", f"{totals['CPA']} zł" if totals["CPA"] is not None else "—")
    cols2[3].metric("Коэфф. конверсии", f"{totals['CR_%']}%" if totals["CR_%"] is not None else "—")


def render_dynamics_chart(df: pd.DataFrame, x_col: str, title: str, changes: pd.DataFrame = None):
    """Расход+клики (левая ось) и CPA+коэфф.конверсии (правая ось) на одном
    графике по оси времени — так сразу видно, растёт ли расход/трафик синхронно
    с эффективностью или в разные стороны (напр. расход растёт, а CPA ухудшается).

    changes (опционально) — df от load_changes(), рисуется вертикальными
    линиями на дату правки, с подписью изменённых полей при наведении. Только
    для x_col="Date" (посуточный график) — на недельной/месячной агрегации
    точная дата правки внутри периода теряет смысл как отметка на оси."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(x=df[x_col], y=df["Cost"], name="Расход, zł", marker_color="#4C78A8", opacity=0.7),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=df[x_col], y=df["Clicks"], name="Клики", mode="lines+markers", marker_color="#F58518"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=df[x_col], y=df["CPA"], name="CPA, zł", mode="lines+markers", marker_color="#E45756"),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(x=df[x_col], y=df["CR_%"], name="Коэфф. конверсии, %", mode="lines+markers", marker_color="#54A24B"),
        secondary_y=True,
    )

    if changes is not None and not changes.empty and x_col == "Date":
        by_day = changes.groupby("Date")["Relevant_fields"].apply(lambda s: "; ".join(s)).reset_index()
        for _, row in by_day.iterrows():
            fig.add_vline(
                x=row["Date"], line_width=1.5, line_dash="dash", line_color="#888888",
            )
        fig.add_trace(
            go.Scatter(
                x=by_day["Date"], y=[0] * len(by_day), mode="markers",
                marker=dict(symbol="triangle-up", size=10, color="#888888"),
                name="Правка в кампании", text=by_day["Relevant_fields"], hoverinfo="text+x",
            ),
            secondary_y=False,
        )

    fig.update_layout(title=title, hovermode="x unified", legend=dict(orientation="h", y=1.15))
    fig.update_yaxes(title_text="Расход / Клики", secondary_y=False)
    fig.update_yaxes(title_text="CPA / Коэфф. конверсии, %", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)


def main():
    st.set_page_config(page_title="Эффективность кампании", layout="wide")
    st.title("Эффективность рекламной кампании")

    args = parse_args()
    csv_path = st.sidebar.text_input("Путь к CSV (campaign x день)", value=args.csv or "")
    changes_csv_path = st.sidebar.text_input(
        "Путь к CSV правок (опционально)", value=args.changes_csv or "",
        help="Из gads_change_history.py — без него дашборд не сможет отличить "
             "правку кампании от внешней причины аномалии (Gate-проверка 2).",
    )
    if not csv_path:
        st.info("Укажите путь к CSV в поле слева — файл готовится "
                 "gads_campaigns_breakdown.py --by-day (см. докстринг скрипта).")
        return

    try:
        raw = load_data(csv_path)
    except FileNotFoundError:
        st.error(f"Файл не найден: {csv_path}")
        return

    changes_df = pd.DataFrame()
    if changes_csv_path:
        try:
            changes_df = load_changes(changes_csv_path)
        except FileNotFoundError:
            st.warning(f"Файл правок не найден: {changes_csv_path} — графики без меток правок.")
    else:
        st.caption(
            "⚠ CSV правок не указан — любая аномалия ниже НЕ проверена против "
            "истории изменений кампании (Gate-проверка 2). Причинный вывод без "
            "этой проверки недоказуем, см. Ошибку 6 в База_знаний/Паттерны/"
            "Google-Ads-аудит-кампании-алгоритм-и-ошибки-смешения-данных.md."
        )

    campaigns = sorted(raw["Campaign"].unique())
    campaign = campaigns[0] if len(campaigns) == 1 else st.sidebar.selectbox("Кампания", campaigns)
    df = raw[raw["Campaign"] == campaign].copy()

    min_d, max_d = df["Date"].min().date(), df["Date"].max().date()
    date_range = st.sidebar.date_input("Период", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        df = df[(df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)]

    df = add_derived_metrics(df)

    st.subheader(f"{campaign} — итого за {df['Date'].min().date()} → {df['Date'].max().date()}")
    totals = aggregate(df)
    render_kpi_row(totals)

    missing_days = pd.date_range(df["Date"].min(), df["Date"].max()).difference(df["Date"])
    if len(missing_days) > 0:
        st.caption(
            f"Дней без строк в выгрузке: {len(missing_days)} "
            f"(вероятно 0 показов — напр. выходной по расписанию показа, "
            f"не путать с ошибкой сбора данных)."
        )

    st.divider()
    st.subheader("Динамика по неделям")
    weekly = weekly_breakdown(df)

    full_weeks = df.groupby(df["Date"].dt.to_period("W-SUN")).size()
    incomplete = full_weeks[full_weeks < 7]
    if len(incomplete) > 0:
        st.caption(
            f"⚠ Неполные недели в выборке (меньше 7 дней данных): "
            f"{', '.join(str(p.start_time.date()) for p in incomplete.index)} — "
            f"не сравнивать напрямую с полными неделями по объёму (Gate-проверка 1, "
            f"блок-схема Шага 1)."
        )

    render_dynamics_chart(weekly, "Week_start", "По неделям", changes_df)
    st.dataframe(weekly, use_container_width=True)

    st.markdown("**Флаги аномалий по неделям** (z-score конверсий относительно остальных недель периода — "
                "не вывод, а кандидат на проверку по чек-листу причинности):")
    weekly_flags = detect_anomalies(weekly, "Conversions", "Week_start")
    anomalous_weeks = weekly_flags[weekly_flags["Is_anomaly"]]
    if not anomalous_weeks.empty:
        st.dataframe(
            anomalous_weeks[["Week_start", "Conversions", "Deviation_pct", "Z_score"]],
            use_container_width=True,
        )
    else:
        st.caption("Недель с отклонением ≥1.5σ от остальных не найдено.")

    st.divider()
    st.subheader("Динамика по дням")
    render_dynamics_chart(df, "Date", "По дням", changes_df)
    st.dataframe(
        df[["Date", "Impressions", "Clicks", "CTR_%", "CPC", "Cost", "Conversions", "CPA", "CR_%"]],
        use_container_width=True,
    )

    if not changes_df.empty:
        st.markdown("**Правки кампании за период (из change history):**")
        st.dataframe(
            changes_df[["Date", "Operation", "Relevant_fields", "User_email"]],
            use_container_width=True,
        )

    months = monthly_breakdown(df)
    if len(months) > 1:
        st.divider()
        st.subheader("Динамика по месяцам")
        render_dynamics_chart(months, "Month", "По месяцам")
        st.dataframe(months, use_container_width=True)


if __name__ == "__main__":
    main()
