import csv, collections, glob, math, os, sys
sys.stdout.reconfigure(encoding="utf-8")
base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Статистика"))
f = glob.glob(os.path.join(base, "gads_campaigns_by_day_2026-08-18_to_2026-11-15.csv"))[0]
rows = list(csv.DictReader(open(f, encoding="utf-8")))

def agg(a, b):
    r = collections.defaultdict(lambda: [0, 0, 0.0])
    for x in rows:
        if a <= x["Date"] <= b and not x["Campaign"].startswith("yt_"):
            v = r[x["Campaign"]]; v[0] += int(x["Impressions"]); v[1] += int(x["Clicks"]); v[2] += float(x["Cost"])
    return r

for a, b in [("2026-10-01", "2026-10-08"), ("2026-10-09", "2026-10-31")]:
    print("==", a, b); T = [0, 0, 0.0]
    for k, v in sorted(agg(a, b).items(), key=lambda t: -t[1][2]):
        print(f"{k[:40]:40} показы {v[0]:6} клики {v[1]:5} расход {v[2]:7.1f} CPC {v[2]/v[1] if v[1] else 0:.2f}")
        for i in range(3): T[i] += v[i]
    print(f"{'ВСЕГО':40} показы {T[0]:6} клики {T[1]:5} расход {T[2]:7.1f} CPC {T[2]/T[1]:.2f}")

days = collections.defaultdict(lambda: [0, 0.0])
for x in rows:
    if "2026-10-01" <= x["Date"] <= "2026-10-31" and not x["Campaign"].startswith("yt_"):
        days[x["Date"]][0] += int(x["Clicks"]); days[x["Date"]][1] += float(x["Cost"])
print("день;клики;расход")
for k in sorted(days): print(k, days[k][0], round(days[k][1], 1))

# Вилки цены по Пуассону (точный Гарвуд) для срезов: (расход, заявки)
try:
    from scipy.stats import chi2
    def ci(n, al):
        lo = 0 if n == 0 else chi2.ppf(al/2, 2*n)/2
        hi = chi2.ppf(1-al/2, 2*(n+1))/2
        return lo, hi
    print("\nВилки цены заявки (Гарвуд), допустимая 23 €")
    cases = {"1-8.10 аккаунт": (1196.9, 36), "1-8.10 pmax1_test": (561.1, 16), "1-8.10 Brand": (143.1, 6), "1-8.10 Poliweglan": (304.4, 11),
             "9-31.10 аккаунт": (3177.1, 123), "9-31.10 pmax1_test": (1077.9, 50), "9-31.10 Brand": (581.4, 30), "9-31.10 Poliweglan": (807.0, 25), "9-31.10 pmax01_call_test": (450.6, 11),
             "октябрь аккаунт": (4374.0, 159), "октябрь pmax01 (0 заявок)": (143.5, 0)}
    for k, (c, n) in cases.items():
        for al in (0.05, 0.20):
            lo, hi = ci(n, al)
            print(f"{k:28} расход {c:7.1f} заявок {n:3}  {int((1-al)*100)}%: цена {c/hi:6.1f} .. {c/lo if lo>0 else float('inf'):6.1f}")
except ImportError:
    print("scipy нет")
