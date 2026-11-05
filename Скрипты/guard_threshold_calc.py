#!/usr/bin/env python
# coding: utf-8
"""Расчёт порогов остановки сторожа (gads_spend_guard_cpa.py) по его же логу. ТОЛЬКО ЧТЕНИЕ, в кабинеты и конфиги не пишет.

Зачем: пороги «пауза при расходе ≥ N × цель / N × бюджет при нуле заявок» не выбираем на глаз (решение пользователя
2026-11-04), а считаем: модель + проверка на истории.

Что считает:
  1) Модель по кампании. Заявки ~ Пуассон со скоростью λ = 1 / CPL заявок на единицу расхода. CPL оценивается по истории
     (расход ÷ заявки по дням без аварийной паузы), 90%-интервал — байесовский (Gamma(Σзаявок + 0.5, Σрасхода), Jeffreys).
     Вероятность «здоровая кампания на этом расходе не дала ни одной заявки» P0(s) = exp(−s / CPL). Это вероятность ЛОЖНОЙ
     паузы правилом «при нуле заявок расход ≥ s». Печатается для s = 1×бюджет и 2×бюджет, а также 2×цель и 3×цель.
     Если P0(1×бюджет) > 20% — правило «пауза при нуле заявок на 1×бюджета» там статистически не работает: нулевой день у
     здоровой кампании обычное дело. Дополнительно — эмпирическая доля дней с нулём заявок среди дней с расходом ≥ 0.9×бюджета.
  2) Проверка правил на истории (бэктест). Для каждого кампании-дня ищем первый такт, где правило сработало бы, и считаем:
     «сэкономлено» = расход дня после этого такта; «потеряно заявок» = заявки, пришедшие в этот день после этого такта.
     Итог правила = сэкономлено − потеряно × V, V = ценность заявки в долях цели (по умолчанию 1.0 и 1.5 × цель).
     Доверительный интервал разницы с действующим набором правил — бутстрэп по дням (кампания-день = единица).
  Правила: G(g) «расход ≥ (g + заявок) × цель», A(m) «расход ≥ m × макс. бюджет дня» (любое число заявок),
           Z(k) «заявок 0 и расход ≥ k × макс. бюджет дня». Действующий набор = G(2) + A(2).
Оговорки (печатаются в конце): «темп» (+40% за 30 мин) здесь не моделируется; дни с реальной паузой сторожа цензурированы
(правило мягче реального проверить нельзя); лаг API (заявки/расход приходят с задержкой) в расчёт не входит; выборка мала.

Использование:
    python guard_threshold_calc.py --client ProfiMet [--client EkspertAgro] [--value 1.0,1.5] [--boot 2000]
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "Клиенты"
G_GRID = [1.5, 2, 3, 4, 5, 6]
A_GRID = [1.5, 2, 3]
Z_GRID = [None, 1.0, 1.5, 2.0]


def load(client):
    p = CLIENTS_DIR / client / "Статистика" / "gads_spend_guard_cpa_log.csv"
    df = pd.read_csv(p, encoding="utf-8", on_bad_lines="skip")
    for c in ("status", "budget", "cost_today", "target_cpa", "n"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["cost_today", "budget", "n", "target_cpa"])
    df["time"] = pd.to_datetime(df["time"])
    df["day"] = df["time"].dt.date
    df["event"] = df["event"].fillna("").astype(str)
    return df.sort_values("time")


def days(df):
    """Список кампания-дней: массивы (cost, n), макс. бюджет, цель, признак реальной паузы."""
    out = []
    for (cid, name, day), g in df.groupby(["campaign_id", "name", "day"]):
        g = g[g["status"] == 2] if (g["status"] == 2).any() else g
        cost = np.maximum.accumulate(g["cost_today"].to_numpy())
        n = np.maximum.accumulate(g["n"].to_numpy())
        if cost[-1] <= 0:
            continue
        T = float(g["target_cpa"].iloc[-1])
        B = float(g["budget"].max())
        if T <= 0 or B <= 0:
            continue
        paused = g["event"].str.startswith("ПАУЗА").any()
        out.append(dict(cid=cid, name=name, day=day, cost=cost, n=n, B=B, T=T, paused=paused,
                        fc=float(cost[-1]), fn=float(n[-1])))
    return out


def first_hit(d, rule):
    kind, p = rule
    c, n = d["cost"], d["n"]
    if kind == "G":
        m = c >= (p + n) * d["T"]
    elif kind == "A":
        m = c >= p * d["B"]
    else:   # Z
        m = (n == 0) & (c >= p * d["B"])
    idx = np.flatnonzero(m)
    return int(idx[0]) if len(idx) else None


def outcome(d, rules, V):
    """Итог набора правил по одному дню: (сработало?, сэкономлено, потеряно заявок, итог в деньгах)."""
    hits = [h for h in (first_hit(d, r) for r in rules) if h is not None]
    if not hits:
        return 0, 0.0, 0.0, 0.0
    i = min(hits)
    saved = d["fc"] - float(d["cost"][i])
    lost = d["fn"] - float(d["n"][i])
    return 1, saved, lost, saved - lost * V * d["T"]


def model_table(ds, client):
    print(f"\n=== {client}: модель по кампаниям (Пуассон + байесовский CPL; дни без аварийной паузы) ===")
    print(f"{'кампания':28}{'дней':>5}{'заявок':>7}{'расход':>9}{'CPL':>8}{'CPL 90%':>14}{'цель':>7}{'бюджет':>8}"
          f"{'P0(1×бюдж)':>12}{'P0(2×бюдж)':>12}{'P0(2×цель)':>12}{'P0(3×цель)':>12}{'эмп.P0|≥0.9бюдж':>17}")
    rng = np.random.default_rng(1)
    by = {}
    for d in ds:
        if not d["paused"]:
            by.setdefault((d["cid"], d["name"]), []).append(d)
    res = {}
    for (cid, name), L in sorted(by.items(), key=lambda t: t[0][1]):
        S = sum(x["fc"] for x in L)
        N = sum(x["fn"] for x in L)
        if len(L) < 5 or S <= 0:
            continue
        # скорость заявок на единицу расхода: Gamma(N+0.5, S); CPL = 1/скорость
        rate = rng.gamma(N + 0.5, 1.0 / S, 20000)
        cpl = 1.0 / rate
        cpl_pt = S / max(N, 0.5)
        lo, hi = np.percentile(cpl, [5, 95])
        B = float(np.median([x["B"] for x in L]))
        T = float(np.median([x["T"] for x in L]))
        p0 = lambda s: float(np.mean(np.exp(-s * rate)))     # усреднено по неопределённости CPL
        full = [x for x in L if x["fc"] >= 0.9 * x["B"]]
        emp = (f"{sum(1 for x in full if x['fn'] == 0)}/{len(full)}" if full else "—")
        print(f"{name[:27]:28}{len(L):>5}{int(N):>7}{S:>9.0f}{cpl_pt:>8.1f}{f'{lo:.0f}–{hi:.0f}':>14}{T:>7.1f}{B:>8.0f}"
              f"{p0(B):>12.0%}{p0(2 * B):>12.0%}{p0(2 * T):>12.0%}{p0(3 * T):>12.0%}{emp:>17}")
        res[name] = dict(P0_1B=p0(B), P0_2B=p0(2 * B), P0_2T=p0(2 * T), cpl=cpl_pt, n_days=len(L))
    return res


def backtest(ds, client, values, boot):
    print(f"\n=== {client}: бэктест правил на истории (дней всего {len(ds)}, из них с реальной паузой сторожа {sum(d['paused'] for d in ds)}) ===")
    rng = np.random.default_rng(2)
    base = [("G", 2.0), ("A", 2.0)]
    combos = []
    for g in G_GRID:
        for a in A_GRID:
            for z in Z_GRID:
                rules = [("G", g), ("A", a)] + ([("Z", z)] if z else [])
                combos.append(((g, a, z), rules))
    for V in values:
        print(f"\n  ценность заявки V = {V:g} × цель")
        base_out = np.array([outcome(d, base, V)[3] for d in ds])
        rows = []
        for key, rules in combos:
            o = np.array([outcome(d, rules, V) for d in ds])
            hits, saved, lost, net = o[:, 0].sum(), o[:, 1].sum(), o[:, 2].sum(), o[:, 3]
            diff = net - base_out
            bs = [rng.choice(diff, len(diff)).sum() for _ in range(boot)]
            lo, hi = np.percentile(bs, [5, 95])
            rows.append((key, int(hits), saved, lost, net.sum(), diff.sum(), lo, hi))
        rows.sort(key=lambda r: -r[4])
        print(f"  {'G (×цель)':>10}{'A (×бюдж)':>11}{'Z (×бюдж)':>11}{'пауз':>6}{'сэконом.':>10}{'потер.заяв':>11}{'итог':>9}"
              f"{'к действ.':>11}{'90%-интервал':>20}")
        shown = set()
        for r in rows[:8] + [x for x in rows if x[0] == (2, 2, None)]:
            if r[0] in shown:
                continue
            shown.add(r[0])
            g, a, z = r[0]
            tag = "  ← действующий" if r[0] == (2, 2, None) else ""
            print(f"  {g:>10g}{a:>11g}{(str(z) if z else '—'):>11}{r[1]:>6}{r[2]:>10.0f}{r[3]:>11.0f}{r[4]:>9.0f}"
                  f"{r[5]:>+11.0f}{f'[{r[6]:+.0f}; {r[7]:+.0f}]':>20}{tag}")


def underspend(ds, client, k0=3.0, gate=0.8):
    """Сценарий «недобор расхода»: как расход дня делится на бюджет и можно ли доверять цене заявки кампании.
    Две модели цены заявки (CPL) сравниваются, чтобы не полагаться на одну при малых данных:
      А) по кампании отдельно, неинформативный приор Jeffreys — честно, но при малом числе заявок интервал огромный;
      Б) с частичным объединением: приор по проекту (CPL проекта, вес k0 «заявок»), данные кампании перевешивают при N >> k0.
    Критерий пропускает кампанию к предложению поднять рычаг, только если ОБЕ модели дают P(CPL ≤ цель) ≥ gate."""
    last_day = max(d["day"] for d in ds)
    full = [d for d in ds if d["day"] < last_day and not d["paused"]]
    print(f"\n=== {client}: недобор расхода (полные дни без аварийной паузы: {len(full)}, без последнего неполного дня {last_day}) ===")
    r_all = np.array([d["fc"] / d["B"] for d in full])
    edges = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0, 1.2, 9]
    h, _ = np.histogram(r_all, bins=edges)
    print("  доля бюджета, потраченная за день → число кампания-дней:")
    for i in range(len(h)):
        hi = f"{edges[i + 1]:.0%}" if edges[i + 1] < 9 else "∞"
        print(f"    {edges[i]:>4.0%}–{hi:<5} {h[i]:>4}  " + "#" * int(h[i] * 40 / max(h.max(), 1)))
    S_all = sum(d["fc"] for d in full)
    N_all = sum(d["fn"] for d in full)
    cpl_pool = S_all / max(N_all, 1)
    print(f"  проект: расход {S_all:.0f}, заявок {N_all:.0f}, CPL проекта {cpl_pool:.1f}")
    rng = np.random.default_rng(3)
    by = {}
    for d in full:
        by.setdefault((d["cid"], d["name"]), []).append(d)
    print(f"\n  {'кампания':28}{'дней':>5}{'мед.доля':>9}{'дней<50%':>9}{'≥85%':>6}{'заявок':>7}{'CPL':>7}{'цель':>7}"
          f"{'P(CPL≤цель) А':>15}{'Б':>6}{'допуск':>8}")
    for (cid, name), L in sorted(by.items(), key=lambda t: t[0][1]):
        if len(L) < 3:
            continue
        r = np.array([x["fc"] / x["B"] for x in L])
        S, N = sum(x["fc"] for x in L), sum(x["fn"] for x in L)
        T = float(np.median([x["T"] for x in L]))
        pa = float(np.mean(1.0 / rng.gamma(N + 0.5, 1.0 / max(S, 1e-9), 20000) <= T))
        pb = float(np.mean(1.0 / rng.gamma(k0 + N, 1.0 / (k0 * cpl_pool + S), 20000) <= T))
        ok = "да" if (pa >= gate and pb >= gate) else "нет"
        print(f"  {name[:27]:28}{len(L):>5}{np.median(r):>9.0%}{(r < .5).mean():>9.0%}{(r >= .85).mean():>6.0%}{int(N):>7}"
              f"{S / max(N, .5):>7.1f}{T:>7.1f}{pa:>15.0%}{pb:>6.0%}{ok:>8}")
    # шанс ложного срабатывания «3 дня подряд < 50%» у кампании, у которой доля дней <50% равна q
    print("\n  Шанс, что у кампании с долей «дней < 50%» q случайно набралось N дней подряд < 50%:")
    for q in (.3, .5):
        print("   q=%.0f%%: " % (q * 100) + ", ".join(f"{n} дн. — {q ** n:.1%}" for n in (2, 3, 4, 5)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", action="append", required=True)
    ap.add_argument("--value", default="1.0,1.5")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--underspend", action="store_true", help="только раздел «недобор расхода»")
    a = ap.parse_args()
    values = [float(x) for x in a.value.split(",")]
    for c in a.client:
        ds = days(load(c))
        if a.underspend:
            underspend(ds, c)
            continue
        model_table(ds, c)
        backtest(ds, c, values, a.boot)
    print("\nОговорки: «темп» (+40% за 30 мин) не моделируется; дни с реальной паузой цензурированы; лаг API не учтён; "
          "выборка — 3 недели; Пуассон не учитывает перегруженность (разброс заявок по дням шире), поэтому P0 — оценка снизу; "
          "суммы в разных валютах (ProfiMet €, EkspertAgro zł) не складываются.")


if __name__ == "__main__":
    main()
