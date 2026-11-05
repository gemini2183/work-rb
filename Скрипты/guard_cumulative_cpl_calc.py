#!/usr/bin/env python
# coding: utf-8
"""Расчёт правила «накопленная цена заявки» (последовательная граница) для кампании или теста. ТОЛЬКО РАСЧЁТ, ничего не пишет.

Модель: заявки приходят как пуассоновский поток на единицу расхода, скорость 1/CPL. Кампания «на цели»: CPL = T (цель заявки).
Граница: при j заявках сумма расхода m_j × T, на которой пауза/сигнал. m_j — наименьшее m, где P(Пуассон(m) ≤ j) ≤ alpha.
  j = 0: m_0 = −ln(alpha) (alpha 5% → 3.0 × цели — это правило «расход без заявок подряд»).
Раз границу проверяют на каждом уровне расхода, общий шанс ложной остановки выше alpha. Поэтому alpha подбирается
бисекцией (симуляция Монте-Карло) так, чтобы шанс остановить кампанию «на цели» до расхода H был ≤ max_false (10%).
Затем для плохих кампаний (CPL = 1.5T, 1.65T, 2T) считается: доля остановленных до H и средний расход на остановку.

Использование:
    python guard_cumulative_cpl_calc.py --target 87 --horizons 600,800,1000 [--max-false 0.10] [--bad 1.5,1.65,2.0]
Оговорки: независимость заявок (пачки делают ложных остановок больше), CPL в модели постоянный, лаг данных не учитывается."""
import argparse
import math

import numpy as np
from scipy.stats import poisson


def boundary(alpha, jmax=40):
    out = []
    for j in range(jmax):
        lo, hi = 0.0, 200.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if poisson.cdf(j, mid) <= alpha:
                hi = mid
            else:
                lo = mid
        out.append(hi)
    return np.array(out)


def stop_spend(arr_times, mj, H):
    """Первый расход S ≤ H, на котором N(S) ≤ j и S ≥ m_j: интервал между заявками j и j+1 -> [t_j, t_{j+1})."""
    t_prev = 0.0
    for j in range(len(mj)):
        t_next = arr_times[j] if j < len(arr_times) else math.inf
        s = max(t_prev, mj[j])
        if s < t_next and s <= H:
            return s
        if t_next > H:
            return None
        t_prev = t_next
    return None


def simulate(cpl, mj_scaled, H, n, rng):
    """Доля остановленных до H и средний расход на остановку. mj_scaled в единицах расхода."""
    stops, spends = 0, []
    for _ in range(n):
        gaps = rng.exponential(cpl, size=60)
        arr = np.cumsum(gaps)
        s = stop_spend(arr, mj_scaled, H)
        if s is not None:
            stops += 1
            spends.append(s)
    return stops / n, (float(np.mean(spends)) if spends else float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--horizons", default="600,800,1000")
    ap.add_argument("--max-false", type=float, default=0.10)
    ap.add_argument("--bad", default="1.5,1.65,2.0")
    ap.add_argument("--n", type=int, default=6000)
    a = ap.parse_args()
    T = a.target
    rng = np.random.default_rng(7)
    bads = [float(x) for x in a.bad.split(",")]
    for H in [float(x) for x in a.horizons.split(",")]:
        lo, hi = 0.005, 0.30
        for _ in range(14):   # alpha на уровень, чтобы общий шанс ложной остановки до H был ≈ max_false
            mid = (lo + hi) / 2
            mj = boundary(mid) * T
            f, _s = simulate(T, mj, H, 3000, np.random.default_rng(11))
            if f > a.max_false:
                hi = mid
            else:
                lo = mid
        alpha = lo
        mj = boundary(alpha) * T
        f, _ = simulate(T, mj, H, a.n, rng)
        print(f"\n=== горизонт (максимум расхода теста) H = {H:g} = {H / T:.1f} × цели {T:g}; alpha на уровень {alpha:.3f}; "
              f"ложная остановка кампании «на цели» до H: {f:.1%}")
        print("  граница: при j заявках пауза, когда расход ≥ ...")
        for j in range(0, 7):
            if mj[j] <= H:
                print(f"    j={j}: {mj[j]:7.1f}  (= {mj[j] / T:.2f} × цели)")
        for b in bads:
            p, s = simulate(b * T, mj, H, a.n, rng)
            print(f"  кампания с CPL = {b:g} × цели ({b * T:.0f}): остановлена до H в {p:.0%} случаев; средний расход на остановку {s:.0f}")


if __name__ == "__main__":
    main()
