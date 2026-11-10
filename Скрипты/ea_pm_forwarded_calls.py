# coding: utf-8
"""EkspertAgro → ProfiMet: переадресованные звонки в журналах Ringostat обоих проектов и в листах таблицы продаж — ТОЛЬКО ЧТЕНИЕ.

Что делает: берёт входящие ProfiMet на 48579774289 (схема `ekspertagro.pl`), ищет пару в журнале EA (тот же звонящий, ±3 мин),
затем строку звонка в листах `Ekspertagro.pl` и `mocnaszklarnia.pl` (±10 мин). Печатает: сколько звонков в обоих журналах,
в каком листе есть строка, метки ноги ProfiMet, отдельный блок «НОЯБРЬ» (строки). Период — константа D0 (по умолчанию с 2026-10-01).
Ключи: EA — из конфига мониторинга, ProfiMet — `ringostat_stats_profimet.AUTH_KEY`; в вывод не попадают.
Использование (из папки Скрипты): PYTHONUTF8=1 python ea_pm_forwarded_calls.py
Результат 10.11.2026 (с 01.10): 120 входящих ProfiMet, 115 с парой в EA; в листе EA 115, в листе ProfiMet 1; метки ноги ProfiMet пустые. См. Инфраструктура.md 2026-11-10.
"""
import sys
sys.path.insert(0, r"d:\GitHub\work-rb\Скрипты")
import pandas as pd, requests, yaml, re
from ringostat_stats_profimet import AUTH_KEY as PM_KEY
from ea_ringostat_vs_sheet import MONITORING_CONFIG, load_sheet, last9, SHEET_ID
EA_KEY = yaml.safe_load(open(MONITORING_CONFIG, encoding="utf-8"))["ringostat"]["auth_key"]
D0 = "2026-10-01"
def fetch(key):
    r = requests.get("https://api.ringostat.net/calls/list", params={"export_type":"json","from":f"{D0} 00:00:00","to":pd.Timestamp.now().strftime("%Y-%m-%d 23:59:59"),
        "fields":"calldate,caller,dst,disposition,billsec,call_type,uniqueid,utm_source,utm_medium,utm_campaign,pool_name,scheme_name"},
        headers={"Auth-key":key,"Content-Type":"application/json; charset=utf-8"}, timeout=600)
    r.raise_for_status(); df=pd.DataFrame(r.json())
    for c in ("utm_source","utm_medium","utm_campaign","pool_name","scheme_name"):
        if c not in df: df[c]=""
        df[c]=df[c].fillna("")
    df["ts"]=pd.to_datetime(df["calldate"],errors="coerce",utc=True); df=df[df.ts.notna()].copy()
    df["p9"]=df["caller"].map(last9); df["dst9"]=df["dst"].map(last9); return df
ea, pm = fetch(EA_KEY), fetch(PM_KEY)
print("EA звонков всего:", len(ea), "| PM звонков всего:", len(pm))
print("EA call_type:", ea.call_type.value_counts().to_dict())
fw = pm[(pm.dst9=="579774289")&(pm.call_type.astype(str).str.lower().str.contains("in"))].copy()
print("PM звонков на 48579774289 (входящих):", len(fw), "| схема:", fw.scheme_name.value_counts().to_dict())
ea_in = ea[ea.call_type.astype(str).str.lower().str.contains("in")].copy()
print("EA входящих:", len(ea_in))
# пара: звонок в EA и звонок в PM того же caller в пределах 3 минут
tol = pd.Timedelta(minutes=3)
pairs=[]; used=set()
for i,r in fw.iterrows():
    c = ea_in[(ea_in.p9==r.p9)&((ea_in.ts-r.ts).abs()<=tol)]
    pairs.append((i, len(c)>0, c.iloc[0].dst9 if len(c) else "", c.iloc[0].pool_name if len(c) else "", c.iloc[0].utm_medium if len(c) else "", c.iloc[0].utm_campaign if len(c) else ""))
pp = pd.DataFrame(pairs, columns=["i","в_EA","ea_dst","ea_pool","ea_medium","ea_campaign"]).set_index("i")
fw = fw.join(pp)
print("\nзвонков на 48579774289 с парой в журнале EA (±3 мин, тот же caller):", int(fw["в_EA"].sum()), "из", len(fw))
# строки листов
sh_ea = load_sheet(SHEET_ID, "Ekspertagro.pl"); sh_pm = load_sheet(SHEET_ID, "mocnaszklarnia.pl")
sh_ea = sh_ea[sh_ea.type=="звонок"]; sh_pm = sh_pm[sh_pm.type=="звонок"]
def in_sheet(sh, p9, ts, tolm=10):
    return int(((sh.p9==p9)&((sh.ts-ts).abs()<=pd.Timedelta(minutes=tolm))).any())
fw["в_листе_EA"]=[in_sheet(sh_ea,r.p9,r.ts) for _,r in fw.iterrows()]
fw["в_листе_PM"]=[in_sheet(sh_pm,r.p9,r.ts) for _,r in fw.iterrows()]
t = fw[fw["в_EA"]]
print("\nПереадресованные звонки (есть и в EA, и в PM по Ringostat):", len(t))
print(pd.crosstab(t["в_листе_EA"], t["в_листе_PM"], rownames=["в листе EA"], colnames=["в листе PM"]))
print("\nЗвонки на 48579774289 БЕЗ пары в EA (звонили прямо на этот номер):", int((~fw["в_EA"]).sum()),
      "| из них в листе PM:", int(fw[~fw["в_EA"]]["в_листе_PM"].sum()), "в листе EA:", int(fw[~fw["в_EA"]]["в_листе_EA"].sum()))
print("\nпомесячно переадресованных:", t.groupby(t.ts.dt.strftime("%Y-%m")).size().to_dict())
print("ea_dst:", t.ea_dst.value_counts().to_dict())
print("утм у EA-ноги: medium", t.ea_medium.value_counts().head(5).to_dict())
t[["ts","caller","billsec","disposition","ea_dst","ea_pool","ea_medium","ea_campaign","в_листе_EA","в_листе_PM"]].sort_values("ts").tail(12).to_csv(sys.stdout, index=False)

print("\n=== нога ProfiMet: метки ===")
print("utm_source:", fw.utm_source.replace("", "(пусто)").value_counts().to_dict())
print("utm_medium:", fw.utm_medium.replace("", "(пусто)").value_counts().to_dict())
print("pool_name:", fw.pool_name.replace("", "(пусто)").value_counts().to_dict())
one = t[t["в_листе_PM"]==1]
print("\nзвонок, который есть в листе PM:"); print(one[["ts","caller","billsec","disposition","utm_source","utm_medium","pool_name"]].to_string(index=False))

print("\n=== НОЯБРЬ ===")
nv = fw[fw.ts>=pd.Timestamp("2026-11-01",tz="UTC")].sort_values("ts")
print("всего входящих ProfiMet на 48579774289:", len(nv), "| с парой в журнале EA:", int(nv["в_EA"].sum()), "| в листе EA:", int(nv["в_листе_EA"].sum()), "| в листе PM:", int(nv["в_листе_PM"].sum()))
print(nv[["ts","caller","billsec","disposition","в_EA","ea_dst","ea_campaign","в_листе_EA","в_листе_PM"]].to_string(index=False))
