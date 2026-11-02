"""
Novotel Moscow City: цели и трафик Директа в счётчике Метрики (только чтение).

Что делает:
  1. список счётчиков, доступных токену клиента, и цели выбранного счётчика (в CSV);
  2. по месяцам: визиты всего и визиты из Директа (последний значимый источник);
  3. по кампаниям (utm_campaign оканчивается на ID кампании Директа) × месяц × достижения целей,
     только платный трафик (lastsignTrafficSource='ad').

Токен клиента — только из файла вне vault (как в direct_express_audit.py), в вывод не попадает.

Запуск:
    PYTHONUTF8=1 python novotel_metrika_goals.py --counter 33956404 \
        --token-file "C:\\Users\\infob\\AppData\\Local\\Temp\\novotel_direct.token.txt" \
        --client-folder Novotel_Moscow_City --date-from 2026-01-01 --date-to 2026-10-31
"""
import argparse
import csv
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://api-metrika.yandex.net"


def get(h, path, **params):
    # Лимит Метрики — по числу запросов в секунду/минуту: пауза на каждый запрос, на 429 ждём дольше.
    for attempt in range(8):
        time.sleep(0.7)
        r = requests.get(API + path, headers=h, params=params, timeout=120)
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"-> {path.relative_to(ROOT)} ({len(rows)} строк)")


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--counter", type=int, required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    args = ap.parse_args()

    tok = Path(args.token_file).read_text(encoding="utf-8").strip()
    h = {"Authorization": "OAuth " + tok}
    out = ROOT / "Клиенты" / args.client_folder / "Статистика"
    cid = args.counter

    cs = get(h, "/management/v1/counters", per_page=100)["counters"]
    print("Доступные счётчики:", [(c["id"], c["site"], c["permission"]) for c in cs])

    goals = get(h, f"/management/v1/counter/{cid}/goals")["goals"]
    rows = []
    for g in goals:
        conds = "; ".join(f"{c.get('type')}:{c.get('url')}" for c in (g.get("conditions") or []))
        rows.append([g["id"], g["name"], g["type"], g.get("default_price"), conds])
    write_csv(out / f"metrika_{cid}_goals.csv", ["goal_id", "name", "type", "default_price", "conditions"], rows)

    # Оставляем цели не-«Авто»: ручные и звонковые. Автоцели тоже берём, но они шумные — отдельно в имени.
    gids = [g["id"] for g in goals]
    names = {g["id"]: g["name"] for g in goals}
    direct_filter = "ym:s:lastsignAdvEngine=='ya_direct'"

    # Помесячно: «слишком сложный запрос» API отдаёт на длинный интервал с разрезами.
    months = []
    y, m = map(int, args.date_from.split("-")[:2])
    ey, em = map(int, args.date_to.split("-")[:2])
    while (y, m) <= (ey, em):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def month_range(y, m):
        d1 = f"{y}-{m:02d}-01"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end_day = (__import__("datetime").date(ny, nm, 1) - __import__("datetime").timedelta(days=1)).isoformat()
        return d1, end_day

    vis_rows, goal_rows = [], []
    for y, m in months:
        d1, d2 = month_range(y, m)
        ym = f"{y}-{m:02d}"
        tot = get(h, "/stat/v1/data", ids=cid, metrics="ym:s:visits", date1=d1, date2=d2)["totals"][0]
        dr = get(h, "/stat/v1/data", ids=cid, metrics="ym:s:visits", date1=d1, date2=d2, filters=direct_filter)["totals"][0]
        src = get(h, "/stat/v1/data", ids=cid, metrics="ym:s:visits", dimensions="ym:s:lastsignTrafficSource",
                  date1=d1, date2=d2, limit=50)["data"]
        src_s = "; ".join(f"{r['dimensions'][0]['id']}={int(r['metrics'][0])}" for r in src)
        vis_rows.append([ym, int(tot), int(dr), src_s])
        for part in chunks(gids, 20):
            metrics = ",".join(f"ym:s:goal{g}reaches" for g in part)
            allr = get(h, "/stat/v1/data", ids=cid, metrics=metrics, date1=d1, date2=d2)["totals"]
            dirr = get(h, "/stat/v1/data", ids=cid, metrics=metrics, date1=d1, date2=d2, filters=direct_filter)["totals"]
            for g, a, d in zip(part, allr, dirr):
                goal_rows.append([ym, g, names[g], int(a), int(d)])
            time.sleep(0.5)
    write_csv(out / f"metrika_{cid}_visits_monthly.csv", ["month", "visits_all", "visits_direct", "visits_by_source"], vis_rows)
    write_csv(out / f"metrika_{cid}_goals_monthly.csv", ["month", "goal_id", "goal_name", "reaches_all", "reaches_direct"], goal_rows)

    # 3) платный трафик по utm_campaign × месяц × цели
    ad_filter = "ym:s:lastsignTrafficSource=='ad'"
    camp_rows = []
    for y, m in months:
        d1, d2 = month_range(y, m)
        ym = f"{y}-{m:02d}"
        acc = {}
        for part in chunks(gids, 19):  # +visits = лимит 20 метрик
            metrics = ",".join(["ym:s:visits"] + [f"ym:s:goal{g}reaches" for g in part])
            data = get(h, "/stat/v1/data", ids=cid, metrics=metrics, dimensions="ym:s:lastsignUTMCampaign",
                       date1=d1, date2=d2, filters=ad_filter, limit=200)["data"]
            for r in data:
                name = r["dimensions"][0].get("name") or ""
                rec = acc.setdefault(name, {"visits": int(r["metrics"][0])})
                for g, v in zip(part, r["metrics"][1:]):
                    rec[g] = int(v)
            time.sleep(0.5)
        for name, rec in acc.items():
            for g in gids:
                if g in rec and (rec[g] or g == gids[0]):
                    camp_rows.append([ym, name, rec["visits"], g, names[g], rec[g]])
    write_csv(out / f"metrika_{cid}_utm_campaign_goals_monthly.csv",
              ["month", "utm_campaign", "visits", "goal_id", "goal_name", "reaches"], camp_rows)


if __name__ == "__main__":
    main()
