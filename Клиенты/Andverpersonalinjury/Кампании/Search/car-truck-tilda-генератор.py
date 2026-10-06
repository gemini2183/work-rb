# coding: utf-8
"""Сборка файлов импорта для кампании "search / car+truck injuries / s / lp - tilda" (Landver Law).

Источник правды для текстов/ключей/минус-слов этой кампании: правишь списки ниже и перегенерируешь
CSV в Статистика/ (gads_bulksheet_car_truck_tilda*.csv). Проверяет лимиты 30/90 (с учётом {KeyWord:..}),
межгрупповые дубли ключей и то, что минус-фразы не блокируют собственные ключи.
Запуск: python car-truck-tilda-генератор.py
"""
import csv, re, sys, os

CAMPAIGN = "search / car+truck injuries / s / lp - tilda"
URL = "https://landverpersonalinjury.tilda.ws/california-car-truck-accident"
HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(CLIENT, "Статистика")

# ---- универсальные блоки: только то, что подтверждено на самой странице ----
U_H = [  # порядок = приоритет: в 15 слотов попадает начало списка
    "Free Case Review",              # страница: Free Case Review / free consultation
    "No Fee Unless We Win",          # FAQ: contingency, fee при recovery
    "20+ Years in California",       # Admitted June 2004
    "Early Offer? Talk to Us First", # секция Early Offer
    "Know What Your Case Is Worth",  # секция Understanding Case Value
    "4.8-Star Client Rating",        # 4.8 / 45 public reviews
    "Trial-Focused Representation",  # "Trial-Focused Representation"
    "Beverly Hills Law Firm",        # 8730 Wilshire Blvd
    "No Upfront Costs",              # FAQ: advances litigation costs
    "Defense-Side Experience",       # former defense-side experience
    "Landver Law Injury Attorneys",
]
U_D = [
    "Free case review. Contingency fee, litigation costs advanced. Call Landver Law today.",
    "20+ years in California. Trial-focused preparation and former defense-side insight.",
    "Got an early insurance offer? Get a free review of your case before you decide.",
]

GROUPS = {
    "Car Accident": dict(
        path1="car-accident",
        h1=["Car Accident Injury Lawyer", "Injured in a Car Accident?", "Car Crash Injury Attorneys"],
        dki="{KeyWord:Car Accident Lawyer}",
        h_spec=["Hit by Another Driver?", "Rear-End or T-Bone Crash?", "Still Treating After a Crash?"],
        d_spec=["Injured in a car crash? We represent injury victims only. Get a free case review today.",
                "We investigate the crash, document your injuries and build the case for trial."],
        kw=[
            "car accident lawyer", "car accident attorney", "car accident law firm", "car accident lawyers",
            "car crash lawyer", "car crash attorney", "car wreck lawyer", "car wreck attorney",
            "car collision lawyer", "car accident injury lawyer", "car accident injury attorney",
            "car accident personal injury lawyer", "personal injury lawyer car accident",
            "lawyer for car accident", "attorney for car accident", "injured in car accident lawyer",
            "car injury lawyer", "car injury attorney", "rear end collision lawyer", "rear end accident lawyer",
            "los angeles car accident lawyer", "car accident lawyer los angeles", "car accident attorney los angeles",
            "beverly hills car accident lawyer", "car accident lawyer beverly hills",
        ],
    ),
    "Auto Accident": dict(
        path1="auto-accident",
        h1=["Auto Accident Injury Lawyer", "Injured in an Auto Accident?", "Auto Accident Injury Attorneys"],
        dki="{KeyWord:Auto Accident Lawyer}",
        h_spec=["Hit by Another Driver?", "Car, SUV or Pickup Crash?", "Injured in a Vehicle Crash?"],
        d_spec=["Hurt in an auto accident? We represent injury victims only. Get a free case review today.",
                "We investigate the crash, document your injuries and build the case for trial."],
        kw=[
            "auto accident lawyer", "auto accident attorney", "auto accident law firm", "auto accident lawyers",
            "auto accident injury lawyer", "auto accident injury attorney", "auto accident personal injury lawyer",
            "auto injury lawyer", "auto injury attorney",
            "automobile accident lawyer", "automobile accident attorney", "automobile accident injury lawyer",
            "vehicle accident lawyer", "vehicle accident attorney", "vehicle accident injury lawyer",
            "motor vehicle accident lawyer", "motor vehicle accident attorney",
            "traffic accident lawyer", "traffic accident attorney",
            "los angeles auto accident lawyer", "auto accident lawyer los angeles", "la auto accident lawyer",
            "auto accident attorney los angeles", "beverly hills auto accident lawyer",
        ],
    ),
    "Truck Accident": dict(
        path1="truck-accident",
        h1=["Truck Accident Injury Lawyer", "Injured in a Truck Crash?", "Truck Accident Injury Attorney"],
        dki="{KeyWord:Truck Accident Lawyer}",
        h_spec=["Hit by a Commercial Truck?", "Trucking Company at Fault?", "Preserve Truck ELD Evidence", "Truck Cases Are Different"],
        d_spec=["Injured in a truck crash? We represent injury victims only. Get a free case review today.",
                "We act to preserve ELD data, dashcam video, GPS and maintenance records."],
        kw=[
            "truck accident lawyer", "truck accident attorney", "truck accident law firm", "truck accident lawyers",
            "truck crash lawyer", "truck crash attorney", "truck wreck lawyer", "truck wreck attorney",
            "truck collision lawyer", "truck collision attorney",
            "truck accident injury lawyer", "truck accident injury attorney", "truck injury lawyer", "truck injury attorney",
            "commercial truck accident lawyer", "commercial truck accident attorney", "commercial truck crash lawyer",
            "trucking accident lawyer", "trucking accident attorney", "trucking company accident lawyer",
            "delivery truck accident lawyer", "delivery van accident lawyer",
            "lawyer for truck accident", "attorney for truck accident",
            "los angeles truck accident lawyer", "truck accident lawyer los angeles", "truck accident attorney los angeles",
            "beverly hills truck accident lawyer",
        ],
    ),
    "18 Wheeler and Semi": dict(
        path1="18-wheeler",
        h1=["18-Wheeler Injury Lawyer", "Hurt in an 18-Wheeler Crash?", "Semi-Truck Injury Attorneys"],
        dki="{KeyWord:18 Wheeler Accident Lawyer}",
        h_spec=["Hit by a Semi or Big Rig?", "Semi, Big Rig or 18-Wheeler?", "Jackknife or Rollover Crash?", "Rear-Ended by a Semi?"],
        d_spec=["Injured in an 18-wheeler or semi crash? We represent injury victims only. Free review.",
                "Big rig cases can involve the driver, carrier and owner. We preserve the evidence."],
        kw=[
            "18 wheeler accident lawyer", "18 wheeler accident attorney", "18 wheeler accident law firm",
            "18 wheeler crash lawyer", "18 wheeler crash attorney", "18 wheeler wreck lawyer", "18 wheeler wreck attorney",
            "18 wheeler injury lawyer", "18 wheeler injury attorney", "18 wheeler lawyer", "18 wheeler attorney",
            "eighteen wheeler accident lawyer", "lawyer for 18 wheeler accident",
            "semi truck accident lawyer", "semi truck accident attorney", "semi truck crash lawyer", "semi truck wreck attorney",
            "semi accident lawyer", "lawyer for semi truck accident",
            "big rig accident lawyer", "big rig accident attorney", "big rig crash lawyer", "big rig wreck lawyer",
            "tractor trailer accident lawyer", "tractor trailer accident attorney", "tractor trailer crash lawyer",
            "tractor trailer wreck attorney",
            "los angeles 18 wheeler accident lawyer", "18 wheeler accident lawyer los angeles",
            "semi truck accident lawyer los angeles", "big rig accident lawyer los angeles",
        ],
    ),
}

# ---- перекрёстные минус-фразы на уровне групп (чтобы запрос шёл в самую точную группу) ----
GROUP_NEG = {
    "Car Accident":   ["truck", "trucking", "semi", "18 wheeler", "18-wheeler", "big rig", "tractor trailer", "auto", "automobile", "vehicle"],
    "Auto Accident":  ["truck", "trucking", "semi", "18 wheeler", "18-wheeler", "big rig", "tractor trailer", "car"],
    "Truck Accident": ["semi", "18 wheeler", "18-wheeler", "eighteen wheeler", "big rig", "tractor trailer"],
    "18 Wheeler and Semi": [],
}

CAMPAIGN_NEG = [
    # дела без травм (только машина / страховая)
    "property damage", "car damage", "vehicle damage", "body shop", "auto body", "car repair", "repair cost",
    "diminished value", "totaled", "total loss", "fender bender", "minor accident", "minor car accident",
    "no injuries", "no injury", "car insurance claim", "auto insurance claim", "parked car", "rental car",
    "towing", "windshield", "scratch",
    # виновник / защита, а не пострадавший
    "criminal defense", "defense attorney", "defense lawyer", "dui defense", "dui lawyer", "dui attorney", "dwi",
    "traffic ticket", "speeding ticket", "citation", "reckless driving", "vehicular manslaughter", "manslaughter",
    "felony", "misdemeanor", "arrested", "court date", "license suspension", "dmv",
    "i hit", "i rear ended", "i caused", "i was driving", "hit and run charge", "charged with",
    # водители-перевозчики со своей стороны
    "cdl", "fmcsa violation", "dot violation", "logbook violation",
]

SITELINKS = [
    ("Free Case Review", "#ldv-final-review", "Tell us what happened.", "Start with the crash and injury."),
    ("Why Truck Cases Differ", "#ldv-truck-cases", "Driver, carrier, owner & more.", "More than one party may be liable."),
    ("How We Build Your Case", "#ldv-case-process", "Investigate and preserve evidence.", "Negotiate from a trial-ready view."),
    ("Common Crash Injuries", "#ldv-injuries", "TBI, spine, fractures & more.", "See how injuries shape a case."),
    ("Client Reviews", "#ldv-reviews", "4.8-star client rating.", "Read what clients say."),
    ("Questions & Answers", "#ldv-faq", "Costs, timing, partial fault.", "Answers after a serious crash."),
]
CALLOUTS = ["Free Case Review", "No Fee Unless We Win", "20+ Years in California", "Trial-Focused Preparation",
            "Beverly Hills Office", "Contingency Fee Basis", "Defense-Side Experience"]
SNIPPET = ("Types", ["Car Accidents", "Truck Accidents", "18-Wheeler Crashes", "Semi-Truck Crashes",
                     "Big Rig Crashes", "Delivery Truck Crashes", "Rear-End Collisions", "Rideshare Crashes"])


def vis(t):
    t = re.sub(r"\{KeyWord:([^}]+)\}", r"\1", t)
    return re.sub(r"\{LOCATION\([^)]*\):([^}]+)\}", r"\1", t)


bad = []
def chk(t, lim, where):
    if len(vis(t)) > lim:
        bad.append((where, len(vis(t)), lim, t))

FIELDS = (["Row Type", "Campaign", "Ad group", "Keyword", "Match Type", "Final URL"]
          + [f"Headline {i}" for i in range(1, 16)] + [f"Headline {i} position" for i in range(1, 16)]
          + [f"Description {i}" for i in range(1, 5)] + [f"Description {i} position" for i in range(1, 5)]
          + ["Path 1", "Path 2"])

rows = []
for g, d in GROUPS.items():
    heads = d["h1"] + [d["dki"]] + d["h_spec"] + U_H
    heads = heads[:15]
    descs = d["d_spec"] + U_D
    descs = descs[:4]
    # D1 закреплён в позиции 1: первое описание ВСЕГДА отсекает (травма + только пострадавшие)
    r = {"Row Type": "Responsive search ad", "Campaign": CAMPAIGN, "Ad group": g, "Final URL": URL,
         "Path 1": d["path1"], "Path 2": "california"}
    for i, h in enumerate(heads, 1):
        r[f"Headline {i}"] = h; chk(h, 30, f"{g} H{i}")
    for i in range(1, 4):
        r[f"Headline {i} position"] = "1"
    for i, t in enumerate(descs, 1):
        r[f"Description {i}"] = t; chk(t, 90, f"{g} D{i}")
    chk(d["path1"], 15, f"{g} path1")
    r["Description 1 position"] = "1"
    rows.append(r)
    seen = set()
    for k in d["kw"]:
        assert k not in seen, k
        seen.add(k)
        rows.append({"Row Type": "Keyword", "Campaign": CAMPAIGN, "Ad group": g, "Keyword": k, "Match Type": "PHRASE"})
    print(g, "keywords:", len(seen), "headlines:", len(heads), "descs:", len(descs))

# межгрупповые дубли ключей
allk = {}
for g, d in GROUPS.items():
    for k in d["kw"]:
        allk.setdefault(k, []).append(g)
print("dup across groups:", {k: v for k, v in allk.items() if len(v) > 1})

for t, w in [(x[0], "sl") for x in SITELINKS]:
    chk(t, 25, "sitelink " + t)
for s in SITELINKS:
    chk(s[2], 35, "sl d1 " + s[0]); chk(s[3], 35, "sl d2 " + s[0])
for c in CALLOUTS:
    chk(c, 25, "callout " + c)
for v in SNIPPET[1]:
    chk(v, 25, "snippet " + v)

with open(os.path.join(OUT, "gads_bulksheet_car_truck_tilda.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)

with open(os.path.join(OUT, "gads_bulksheet_car_truck_tilda_group_negatives.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Campaign", "Ad Group", "Criterion Type", "Keyword"])
    for g, negs in GROUP_NEG.items():
        for n in negs:
            w.writerow([CAMPAIGN, g, "Negative Phrase", n])

existing = set()
# уже имеющиеся минуса кампании — из Editor-выгрузки (utf-16, табы), чтобы не дублировать
_exp = [f for f in os.listdir(CLIENT) if "car+truck injuries" in f and f.endswith(".csv")]
if _exp:
    import io
    _t = open(os.path.join(CLIENT, _exp[0]), "rb").read().decode("utf-16")
    for _r in csv.DictReader(io.StringIO(_t), delimiter="	"):
        if "Negative" in (_r.get("Criterion Type") or "") and _r.get("Keyword"):
            existing.add(_r["Keyword"].strip().lower())
else:
    print("Editor-выгрузка кампании не найдена — проверка дублей минус-слов пропущена")
print("existing neg loaded:", len(existing))
new_neg = [n for n in CAMPAIGN_NEG if n.lower() not in existing]
print("campaign negatives:", len(new_neg), "(уже были в кампании:", [n for n in CAMPAIGN_NEG if n.lower() in existing], ")")
# конфликт: минус-фраза не должна блокировать наши же ключи
allkw = [k for d in GROUPS.values() for k in d["kw"]]
def blocks(neg, kw):
    return re.search(r"(?<!\w)" + re.escape(neg) + r"(?!\w)", kw) is not None
print("negatives blocking our keywords:", [(n, k) for n in new_neg for k in allkw if blocks(n, k)] or "none")
with open(os.path.join(OUT, "gads_bulksheet_car_truck_tilda_campaign_negatives.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Campaign", "Ad Group", "Criterion Type", "Keyword"])
    for n in new_neg:
        w.writerow([CAMPAIGN, "", "Campaign Negative Phrase", n])

with open(os.path.join(OUT, "gads_bulksheet_car_truck_tilda_sitelinks.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Row Type", "Campaign", "Ad group", "Final URL", "Link Text", "Description Line 1", "Description Line 2"])
    for t, a, d1, d2 in SITELINKS:
        w.writerow(["Sitelink", CAMPAIGN, "", URL + a, t, d1, d2])

print("PROBLEMS:", bad if bad else "none")
for r in rows:
    if r["Row Type"] != "Keyword":
        print("\n==", r["Ad group"], "|", r["Path 1"], "/", r["Path 2"])
        for i in range(1, 16):
            if r.get(f"Headline {i}"):
                print(f"  H{i:<2} [{len(vis(r[f'Headline {i}']))}] pin={r.get(f'Headline {i} position','')} {r[f'Headline {i}']}")
        for i in range(1, 5):
            if r.get(f"Description {i}"):
                print(f"  D{i} [{len(r[f'Description {i}'])}] {r[f'Description {i}']}")
