#!/usr/bin/env python3
"""usage_startup_share.py - доля стартового груза и вес по размеру контекста в основных сессиях. ТОЛЬКО ЧТЕНИЕ.

Использует claude_usage.py (шкала веса и допущения - в его шапке). Без субагентов.
Примеры:
  python Скрипты/usage_startup_share.py --since 2026-11-06 --until 2026-11-12      # «до» чекпоинтов
  python Скрипты/usage_startup_share.py --since 2026-11-13 --sessions               # «после», со списком сессий
Метрики сравнения «до/после»: доля веса при контексте >150 тыс., медиана пикового контекста,
вес на сессию и на календарный день (объём работы разный - сравнивать осторожно).
"""
import argparse
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_usage as cu  # noqa: E402

THRESHOLD = 150_000
ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-11-06")
ap.add_argument("--until", default=None, help="включительно, ГГГГ-ММ-ДД (по умолчанию - сегодня)")
ap.add_argument("--min-calls", type=int, default=20)
ap.add_argument("--sessions", action="store_true", help="показать список сессий")
a = ap.parse_args()
since = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc)
until = (datetime.fromisoformat(a.until).replace(tzinfo=timezone.utc) + timedelta(days=1)) if a.until else None

proj = cu.PROJECTS / cu.DEFAULT_PROJECT
rows, comp = [], dict(cr=0.0, cw=0.0, out=0.0, inp=0.0)
bins = [(0, 100), (100, 150), (150, 250), (250, 400), (400, 10**6)]
binw = {b: [0.0, 0] for b in bins}
over = 0.0
perday = defaultdict(float)
for p in proj.glob("*.jsonl"):
    calls, _ = cu.read_calls(p)
    if len(calls) < a.min_calls or calls[0].ts < since or (until and calls[0].ts >= until):
        continue
    n, S = len(calls), calls[0].ctx
    first = calls[0]
    wcw = (first.cw5 * cu.W_CW5 + first.cw1 * cu.W_CW1H) if first.cw else S * cu.W_CW5
    startup = S * cu.W_CR * (n - 1) + wcw
    W = sum(c.weight for c in calls)
    for c in calls:
        comp["cr"] += c.cr * cu.W_CR
        comp["cw"] += c.cw5 * cu.W_CW5 + c.cw1 * cu.W_CW1H
        comp["out"] += c.out * cu.W_OUT
        comp["inp"] += c.inp
        for b in bins:
            if b[0] <= c.ctx / 1e3 < b[1]:
                binw[b][0] += c.weight
                binw[b][1] += 1
        if c.ctx > THRESHOLD:
            over += c.weight
        perday[c.ts.date()] += c.weight
    rows.append((p.stem[:8], n, S, W, startup, max(c.ctx for c in calls)))

if not rows:
    sys.exit("сессий в периоде нет")
rows.sort(key=lambda r: -r[3])
W = sum(r[3] for r in rows)
St = sum(r[4] for r in rows)
if a.sessions:
    print("сессия | вызовов | старт ctx, тыс | вес, тыс | вес груза, тыс | доля груза | пик ctx, тыс")
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]/1e3:.0f} | {r[3]/1e3:.0f} | {r[4]/1e3:.0f} | {r[4]/r[3]*100:.0f}% | {r[5]/1e3:.0f}")
    print()
print(f"Период {a.since} .. {a.until or 'сегодня'}: сессий {len(rows)}, вес {W/1e6:.1f} млн")
print(f"Вес стартового груза: {St/1e6:.1f} млн = {St/W*100:.0f}% (нижняя оценка)")
t = sum(comp.values())
print("Состав веса: " + ", ".join(f"{k} {v/t*100:.0f}%" for k, v in comp.items()))
for b, (w, n) in binw.items():
    hi = "+" if b[1] > 10**5 else f"-{b[1]}"
    print(f"  контекст {b[0]}{hi} тыс: вызовов {n}, вес {w/1e6:.1f} млн ({w/W*100:.0f}%)")
print(f"МЕТРИКА A: доля веса при контексте >150 тыс: {over/W*100:.0f}%")
print(f"МЕТРИКА B: медиана пикового контекста: {statistics.median(r[5] for r in rows)/1e3:.0f} тыс; сессий с пиком >250 тыс: {sum(1 for r in rows if r[5] > 250_000)} из {len(rows)}")
print(f"МЕТРИКА C: вес на сессию (медиана): {statistics.median(r[3] for r in rows)/1e3:.0f} тыс; на календарный день (среднее по дням с работой): {statistics.mean(perday.values())/1e6:.1f} млн, дней {len(perday)}")
