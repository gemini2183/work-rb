#!/usr/bin/env python
# coding: utf-8
"""Калибровка порога «темпа» сторожа (gads_spend_guard_cpa.py) по его же логу. ТОЛЬКО ЧТЕНИЕ, в кабинеты не пишет.

Зачем: порог «+N% дневного бюджета за 30 минут» не угадываем, а выбираем по истории клиента (решение пользователя
2026-11-04, ProfiMet + EkspertAgro: 40% и условие «заявок за день 0»). Скрипт берёт `gads_spend_guard_cpa_log.csv`
клиента (боевой лог, не *_plan), считает для каждого такта рост расхода за ~30 минут относительно опорной точки
(как сторож: самая свежая точка не моложе окна, рост приводится к окну) и печатает:
  1) распределение роста в долях бюджета (перцентили) — что для кампании «нормально»;
  2) по каждой кампании: p95 / p99 / максимум и число измерений;
  3) таблицу «порог → срабатывания в кампании-днях → чем закончился день»:
     «слив» = день закончился без заявок; «ложная тревога» = цена дня ≤ цели; «спорно» = цена дня > цели,
     для двух условий: А «в окне заявок не прибавилось» (старое правило) и Б «за день заявок 0» (действует с 2026-11-04).
Оговорки (печатаются в конце): «слив» считается по заявкам, которые видит сторож (Ringostat, Supabase, звонки из
объявлений) — формы без UTM он не видит; малая выборка; суммы в разных валютах не складываются.

Использование:
    python guard_pace_calibration.py --client ProfiMet --client EkspertAgro [--window-min 30] [--thresholds 0.2,0.3,0.4,0.5] [--save]
Каждый --client — отдельно, затем «все вместе». Минимум для вывода по клиенту: ≥ 10 кампаний-дней в логе.
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "Клиенты"
MIN_CAMPAIGN_DAYS = 10


def load_log(client):
    path = CLIENTS_DIR / client / "Статистика" / "gads_spend_guard_cpa_log.csv"
    rows, header = [], None
    with open(path, encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        for x in r:
            if len(x) >= len(header):   # строки старого формата и обрезанные пропускаем
                rows.append(x[:len(header)])
    d = pd.DataFrame(rows, columns=header)
    d["client"] = client
    d["t"] = pd.to_datetime(d["time"], errors="coerce")
    for k in ("budget", "cost_today", "n", "target_cpa"):
        d[k] = pd.to_numeric(d[k], errors="coerce")
    d = d[d["t"].notna() & (d["budget"] > 0) & d["cost_today"].notna()].copy()
    d["n"] = d["n"].fillna(0)
    d["day"] = d["t"].dt.date
    return d.sort_values(["client", "campaign_id", "t"])


def windows(d, window_min):
    """Для каждого такта: рост расхода за окно (приведён к окну), доля бюджета, число заявок сейчас и в опорной точке."""
    out = []
    for (cl, cid, day), g in d.groupby(["client", "campaign_id", "day"]):
        g = g.reset_index(drop=True)
        ts = g["t"].values.astype("datetime64[s]").astype(np.int64)
        for i in range(len(g)):
            older = np.where(ts <= ts[i] - window_min * 60)[0]
            if len(older) == 0:
                continue
            j = older[-1]
            age = (ts[i] - ts[j]) / 60
            if age >= 2 * window_min:   # опорная точка после дыры в логе — не сравниваем
                continue
            grow = (g.cost_today[i] - g.cost_today[j]) * (window_min / max(age, window_min))
            out.append((cl, g["name"][i], day, g.t[i], g.budget[i], g.cost_today[i], g.n[i], g.n[j], grow, grow / g.budget[i]))
    return pd.DataFrame(out, columns=["client", "name", "day", "t", "budget", "cost", "n", "n_ref", "grow", "share"])


def day_outcomes(d):
    return d.groupby(["client", "name", "day"]).agg(end_cost=("cost_today", "max"), end_n=("n", "max"),
                                                   T=("target_cpa", "last")).reset_index()


def classify(row):
    if row.end_n == 0:
        return "слив"
    return "ложная тревога" if row.end_cost / row.end_n <= row["T"] else "спорно"


def report(label, d, w, thresholds):
    days = d.groupby(["client", "name", "day"]).ngroups
    print(f"\n==================== {label}: тактов {len(d)}, кампаний-дней {days}, измерений окна {len(w)} ====================")
    if days < MIN_CAMPAIGN_DAYS or w.empty:
        print(f"  мало данных (< {MIN_CAMPAIGN_DAYS} кампаний-дней) — порог по этой выборке не выбираем, берём 40% по умолчанию")
        return
    print("доля дневного бюджета за окно, перцентили:",
          {f"p{int(q*1000)/10:g}": round(float(w.share.quantile(q)), 3) for q in (.5, .9, .95, .99, .999)})
    pc = w.groupby(["client", "name"]).share.agg(["count", lambda s: s.quantile(.95), lambda s: s.quantile(.99), "max"])
    pc.columns = ["измерений", "p95", "p99", "макс"]
    print("\nпо кампаниям (доля бюджета за окно):")
    print(pc.round(3).sort_values("макс", ascending=False).to_string())
    last = day_outcomes(d)
    for cond, mask_fn in (("А: в окне заявок не прибавилось (старое правило)", lambda x: x.n == x.n_ref),
                          ("Б: за день заявок 0 (действует с 2026-11-04)", lambda x: x.n == 0)):
        print(f"\nусловие {cond}")
        for thr in thresholds:
            s = w[(w.share >= thr) & mask_fn(w)].sort_values("t").groupby(["client", "name", "day"]).head(1)
            s = s.merge(last, on=["client", "name", "day"])
            if s.empty:
                print(f"  порог {thr:.0%}: срабатываний 0")
                continue
            vc = s.apply(classify, axis=1).value_counts().to_dict()
            print(f"  порог {thr:.0%}: срабатываний {len(s)} (кампаний-дней) -> {vc}")


def main():
    ap = argparse.ArgumentParser(description="Калибровка порога «темпа» сторожа по логу (только чтение)")
    ap.add_argument("--client", action="append", required=True, help="папка клиента; можно несколько раз")
    ap.add_argument("--window-min", type=float, default=30.0)
    ap.add_argument("--thresholds", default="0.2,0.3,0.4,0.5", help="доли бюджета через запятую")
    ap.add_argument("--save", action="store_true", help="сохранить вывод в Клиенты/<первый клиент>/Статистика/guard_pace_calibration_<дата>.txt")
    args = ap.parse_args()
    thresholds = [float(x) for x in args.thresholds.split(",")]
    import io
    import sys
    from contextlib import redirect_stdout
    buf = io.StringIO()
    frames = []
    for c in args.client:
        frames.append(load_log(c))
    class Tee:
        def write(self, s):
            sys.__stdout__.write(s)
            buf.write(s)
        def flush(self):
            sys.__stdout__.flush()
    with redirect_stdout(Tee()):
        for d in frames:
            report(d["client"].iloc[0], d, windows(d, args.window_min), thresholds)
        if len(frames) > 1:
            d = pd.concat(frames)
            report("все клиенты вместе", d, windows(d, args.window_min), thresholds)
        print("\nОговорки: «слив» — по заявкам, которые видит сторож (формы без UTM не видны); выборка мала и не покрывает "
              "Search/Shopping/LSA; суммы в разных валютах не складываются; лаг API делает «темп» запоздалым у Demand Gen.")
    if args.save:
        from datetime import date
        out = CLIENTS_DIR / args.client[0] / "Статистика" / f"guard_pace_calibration_{date.today():%Y-%m-%d}.txt"
        out.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\nсохранено: {out}")


if __name__ == "__main__":
    main()
