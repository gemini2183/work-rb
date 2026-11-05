"""Единый стандарт «заявка из Google Ads» (решение пользователя 2026-11-05). ТОЛЬКО ЧТЕНИЕ.

Заявка = уникальный звонок Ringostat (источник Google Ads, схема уникальности как в мониторе RedBird)
       + форма Supabase (без пачек-мусора, один телефон за день = одна форма; источник Google по `utm_source` или `gclid`).
Кампания:
  • звонок по UTM-метке Ringostat (динамический канал);
  • звонок из объявлений (статический канал, кампании в Ringostat нет) — по времени сопоставляется со строкой
    `call_view` Google Ads (время, длительность, кампания), допуск ±3 минуты;
  • форма — по `utm_campaign` (id кампании внутри метки), запасной вариант `utm_content`.
Что не входит в «Google»: формы Facebook, другие источники и формы без метки считаются отдельными строками («источник неизвестен»
не приписывается Google молча). Конверсии Google Ads в счёт заявок не входят, они выводятся только для сравнения.

Запуск (из папки Скрипты):  PYTHONUTF8=1 python leads_standard.py --client ProfiMet [--from 2026-11-01] [--daily]
Модуль: month_leads(folder, d0=None) → dict, его читает state_digest.py (раздел [4]).
"""
import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gads_spend_guard_cpa as G  # noqa: E402  (load_monitoring, all_campaign_names, UNRESOLVED)
from gads_stats import GOOGLE_ADS_YAML  # noqa: E402

MON_DIR = r"E:\PythonProjects\RedBird\monitoring scripts\monitoring"
WARSAW = "Europe/Warsaw"
MATCH_SEC = 180   # допуск сопоставления звонка Ringostat со строкой call_view


def _p9(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-9:] if len(d) >= 9 else d


def _gads_client():
    from google.ads.googleads.client import GoogleAdsClient
    p = Path(GOOGLE_ADS_YAML)
    return GoogleAdsClient.load_from_storage(str(p if p.is_absolute() else HERE / p))


# ---------- Ringostat ----------
def ringostat_google_calls(cfg, m, id_to_name):
    """Уникальные звонки Google Ads: DataFrame [ts (Варшава), day, camp, pool]. Логика `calls_by_day` сторожа, но по звонкам."""
    rs = cfg["ringostat"]
    today = date.today()
    google_keywords = list(rs.get("source_filter", {}).get("include_keywords", ["google", "dspl", "kms"]))
    if "performance_max" not in google_keywords:
        google_keywords.append("performance_max")
    excluded = set(rs.get("excluded_campaigns", []))
    regex = rs.get("campaign_id_regex", r"s_(\d+)_")
    kw = rs.get("pmax_keywords", ["pmax", "performance max"])
    resp = requests.get(
        "https://api.ringostat.net/calls/list",
        params={"export_type": "json", "from": rs["date_from"], "to": today.strftime("%Y-%m-%d 23:59:59"),
                "fields": "calldate,caller,call_type,utm_source,utm_medium,utm_campaign,pool_name"},
        headers={"Content-Type": "application/json; charset=utf-8", "Auth-key": rs["auth_key"]}, timeout=180)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    if df.empty:
        return pd.DataFrame(columns=["ts", "day", "camp", "pool"])
    for c in ("utm_source", "utm_medium", "utm_campaign", "pool_name"):
        df[c] = df[c].fillna("")
    df["call_date"] = df["calldate"].apply(m._parse_local_date)
    df = df[df["call_date"].notna()].copy()
    df["date_only"] = df["call_date"].dt.date
    df["category"] = df.apply(lambda r: m.categorize_source(str(r["utm_source"]), str(r["utm_medium"]), google_keywords), axis=1)
    df.loc[df["utm_campaign"].isin(excluded), "category"] = "No Source"
    df = df[df["call_type"] == "in"].copy()
    if rs.get("unique_scheme", "channels") == "clients":
        df["client"] = df.apply(m._determine_client, axis=1)
        chain = df[df["client"].notna()].copy()
        chain["chain_key"] = chain["client"] + "|" + chain["caller"].astype(str)
    else:
        chain = df
        if not rs.get("count_other_channels", False):
            chain = df[df["category"].isin(m.TRACKED_CATEGORIES)].copy()
        chain["chain_key"] = chain["caller"].astype(str)
    cl = m._mark_new_calls(chain, int(rs.get("unique_window_days", 60)))
    cl = cl[(cl["category"] == m.GOOGLE_ADS) & (cl["call_type_unique"] == "unique")].copy()
    if cl.empty:
        return pd.DataFrame(columns=["ts", "day", "camp", "pool"])
    static = rs.get("pmax_static_name", "")
    cl["camp"] = cl.apply(lambda r: m._resolve_campaign_name(r, id_to_name, G.UNRESOLVED, regex, kw, static), axis=1)
    cl["ts"] = pd.to_datetime(cl["calldate"], utc=True).dt.tz_convert(WARSAW).dt.tz_localize(None)
    return pd.DataFrame({"ts": cl["ts"].values, "day": cl["date_only"].values, "camp": cl["camp"].values,
                         "pool": cl["pool_name"].values}).reset_index(drop=True)


def call_view_rows(ga, cid, d0):
    q = ("SELECT call_view.start_call_date_time, call_view.call_duration_seconds, campaign.id, campaign.name FROM call_view "
         f"WHERE call_view.start_call_date_time >= '{d0} 00:00:00' ORDER BY call_view.start_call_date_time")
    rows = [(pd.Timestamp(r.call_view.start_call_date_time), int(r.call_view.call_duration_seconds), str(r.campaign.id), r.campaign.name)
            for r in ga.search(customer_id=cid, query=q)]
    return pd.DataFrame(rows, columns=["t", "dur", "cid", "camp"])


def attach_call_view(calls, cv):
    """Сопоставляет звонки Ringostat (кроме динамического пула) со строками call_view по времени.
    Кампанию из call_view подставляем только там, где Ringostat её не знает (статический канал «из объявлений»);
    где знает обоих, проверяем согласие. → (calls, строки call_view без пары, число расхождений кампании)."""
    calls = calls.copy()
    calls["via_call_view"] = False
    used, mismatch = set(), 0
    for i, r in calls.iterrows():
        if cv.empty or "_dyn" in str(r["pool"]).lower():
            continue
        d = (cv["t"] - r["ts"]).abs().dt.total_seconds()
        cand = d[(d <= MATCH_SEC) & ~d.index.isin(used)]
        if not len(cand):
            continue
        j = cand.idxmin()
        used.add(j)
        if r["camp"] in (G.UNRESOLVED, "(без кампании)") or "calls from ads" in str(r["pool"]).lower():
            calls.at[i, "camp"] = cv.at[j, "camp"]
            calls.at[i, "via_call_view"] = True
        elif r["camp"] != cv.at[j, "camp"]:
            mismatch += 1
    return calls, cv[~cv.index.isin(used)], mismatch


# ---------- Supabase ----------
def supabase_forms(cfg, m_ringostat, m_supabase, id_to_name, d0):
    """Настоящие формы: [day, p9, src (google/facebook/other/none), camp]. Мусорные пачки и повторы телефона за день убраны."""
    sb = cfg["supabase"]
    h = {"apikey": sb["secret_key"], "Authorization": f"Bearer {sb['secret_key']}"}
    since = (pd.Timestamp(d0) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    rows, off = [], 0
    while True:
        r = requests.get(f"{sb['url']}/rest/v1/{sb['table']}", headers={**h, "Range": f"{off}-{off + 999}"}, timeout=60,
                         params={"select": "phone,utm_source,utm_medium,utm_campaign,utm_content,gclid,created_at",
                                 "created_at": f"gte.{since}T00:00:00", "order": "created_at.asc"})
        r.raise_for_status()
        part = r.json()
        rows += part
        if len(part) < 1000:
            break
        off += 1000
    rows = m_supabase.mark_bursts(rows)
    rs = cfg.get("ringostat", {})
    regex = rs.get("campaign_id_regex", r"s_(\d+)_")
    kw = rs.get("pmax_keywords", ["pmax", "performance max"])
    out, seen = [], set()
    for x in rows:
        if x.get("_burst"):
            continue
        ts = pd.to_datetime(x["created_at"], utc=True).tz_convert(WARSAW)
        if ts.date() < pd.Timestamp(d0).date():
            continue
        p9 = _p9(x.get("phone"))
        key = (ts.date(), p9) if p9 else (ts.isoformat(), "")
        if key in seen:
            continue
        seen.add(key)
        s = str(x.get("utm_source") or "").lower()
        if "google" in s or (x.get("gclid") or "").strip():
            src = "google"
        elif any(t in s for t in ("facebook", "fb", "instagram", "ig")):
            src = "facebook"
        elif s or str(x.get("utm_medium") or "").strip() or str(x.get("utm_campaign") or "").strip():
            src = "other"
        else:
            src = "none"
        camp = ""
        if src == "google":
            for field in ("utm_campaign", "utm_content"):
                row = {"utm_source": x.get("utm_source") or "", "utm_campaign": x.get(field) or "", "pool_name": ""}
                camp = m_ringostat._resolve_campaign_name(row, id_to_name, G.UNRESOLVED, regex, kw, "")
                if camp not in ("(без кампании)", G.UNRESOLVED):
                    break
            else:
                camp = ""
        out.append({"day": ts.date(), "p9": p9, "src": src, "camp": camp, "has_phone": bool(p9)})
    return pd.DataFrame(out, columns=["day", "p9", "src", "camp", "has_phone"])


# ---------- Google Ads (расход и сравнение) ----------
def ads_month(ga, cid, d0, d1, form_action, ad_call_actions):
    cost, prim, forms, adcalls = {}, {}, {}, {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, campaign.name, metrics.cost_micros, metrics.conversions FROM campaign "
            f"WHERE segments.date BETWEEN '{d0}' AND '{d1}'")):
        k = str(r.campaign.id)
        cost[k] = cost.get(k, 0.0) + r.metrics.cost_micros / 1e6
        prim[k] = prim.get(k, 0.0) + r.metrics.conversions
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.id, segments.conversion_action_name, metrics.all_conversions FROM campaign "
            f"WHERE segments.date BETWEEN '{d0}' AND '{d1}' AND metrics.all_conversions > 0")):
        k, name = str(r.campaign.id), r.segments.conversion_action_name
        if name == form_action:
            forms[k] = forms.get(k, 0.0) + r.metrics.all_conversions
        elif name in ad_call_actions:
            adcalls[k] = adcalls.get(k, 0.0) + r.metrics.all_conversions
    return cost, prim, forms, adcalls


# ---------- сборка ----------
def month_leads(folder, d0=None, d1=None):
    today = date.today()
    d0 = d0 or today.replace(day=1).isoformat()
    d1 = d1 or today.isoformat()
    cdir = HERE.parent / "Клиенты" / folder
    gc = yaml.safe_load((cdir / "guard_config.yaml").read_text(encoding="utf-8"))
    cid = str(gc["customer_id"])
    m_r, m_s, _tg, cfg = G.load_monitoring(MON_DIR, str(Path(MON_DIR) / "config" / gc["monitoring_config"]))
    ga = _gads_client().get_service("GoogleAdsService")
    id_to_name = G.all_campaign_names(ga, cid)
    name_to_id = {v: k for k, v in id_to_name.items()}
    calls = ringostat_google_calls(cfg, m_r, id_to_name)
    calls = calls[(calls["day"] >= pd.Timestamp(d0).date()) & (calls["day"] <= pd.Timestamp(d1).date())].reset_index(drop=True)
    cv = call_view_rows(ga, cid, d0)
    calls, cv_orphans, cv_mismatch = attach_call_view(calls, cv)
    forms = supabase_forms(cfg, m_r, m_s, id_to_name, d0)
    forms = forms[forms["day"] <= pd.Timestamp(d1).date()]
    cost, prim, f_ads, c_ads = ads_month(ga, cid, d0, d1, gc.get("form_action", ""), list(gc.get("ad_call_actions") or []))
    plan_row_of = {str(c["id"]): c.get("plan_row") for c in gc.get("campaigns", [])}
    default_row = gc.get("default_plan_row")
    return {"folder": folder, "d0": d0, "d1": d1, "calls": calls, "forms": forms, "cv_orphans": cv_orphans, "cv_mismatch": cv_mismatch, "cv_total": len(cv), "cost": cost,
            "ads_primary": prim, "ads_forms": f_ads, "ads_adcalls": c_ads, "id_to_name": id_to_name, "name_to_id": name_to_id,
            "plan_row_of": plan_row_of, "default_row": default_row, "guard_cfg": gc}


def by_plan_row(res):
    """{строка плана: {'attributed': заявки с кампанией, 'cost': расход}} + '__unassigned__' — заявки Google без кампании."""
    out, n2i = {}, res["name_to_id"]
    def row_of(cid_):
        return res["plan_row_of"].get(cid_) or res["default_row"] or "__single__"
    for cid_, c in res["cost"].items():
        out.setdefault(row_of(cid_), {"attributed": 0, "cost": 0.0})["cost"] += c
    un = 0
    for camp in list(res["calls"]["camp"]) + list(res["forms"].loc[res["forms"]["src"] == "google", "camp"]):
        cid_ = n2i.get(camp)
        if cid_:
            out.setdefault(row_of(cid_), {"attributed": 0, "cost": 0.0})["attributed"] += 1
        else:
            un += 1
    out["__unassigned__"] = un
    return out


def report(res, daily=False):
    calls, forms, n2i, i2n = res["calls"], res["forms"], res["name_to_id"], res["id_to_name"]
    print(f"=== Единый стандарт заявок Google Ads: {res['folder']}, {res['d0']} … {res['d1']} (только чтение) ===")
    print("Заявка = уникальный звонок Ringostat (Google Ads) + форма Supabase (без мусора, телефон за день один раз).")
    rows = {}
    def row(k):
        return rows.setdefault(k, {"dyn": 0, "adc": 0, "forms": 0})
    for _, r in calls.iterrows():
        k = n2i.get(r["camp"])
        (row(k) if k else row("__none__"))["adc" if r["via_call_view"] else "dyn"] += 1
    g = forms[forms["src"] == "google"]
    for _, r in g.iterrows():
        k = n2i.get(r["camp"])
        row(k if k else "__none__")["forms"] += 1
    ids = sorted(set(rows) | {k for k, v in res["cost"].items() if v > 0}, key=lambda x: (x == "__none__", i2n.get(x, "")))
    print(f"\n{'кампания':38} {'расход':>8} {'звонки':>7} {'из объявл.':>10} {'формы':>6} {'ИТОГО':>6} {'цена':>7} | {'Ads основн.':>11} {'Ads ф+зв':>8}")
    tot = {"cost": 0.0, "dyn": 0, "adc": 0, "forms": 0, "prim": 0.0, "fa": 0.0}
    for k in ids:
        rr = rows.get(k, {"dyn": 0, "adc": 0, "forms": 0})
        name = "(Google без кампании)" if k == "__none__" else i2n.get(k, k)
        cost = res["cost"].get(k, 0.0) if k != "__none__" else 0.0
        n = rr["dyn"] + rr["adc"] + rr["forms"]
        prim, fa = res["ads_primary"].get(k, 0.0), res["ads_forms"].get(k, 0.0) + res["ads_adcalls"].get(k, 0.0)
        print(f"{name[:38]:38} {cost:8.1f} {rr['dyn']:7d} {rr['adc']:10d} {rr['forms']:6d} {n:6d} {(cost / n if n else 0):7.1f} | {prim:11.1f} {fa:8.1f}")
        tot["cost"] += cost; tot["dyn"] += rr["dyn"]; tot["adc"] += rr["adc"]; tot["forms"] += rr["forms"]; tot["prim"] += prim; tot["fa"] += fa
    total = tot["dyn"] + tot["adc"] + tot["forms"]
    print(f"{'ВСЕГО Google Ads':38} {tot['cost']:8.1f} {tot['dyn']:7d} {tot['adc']:10d} {tot['forms']:6d} {total:6d} {(tot['cost'] / total if total else 0):7.1f} | {tot['prim']:11.1f} {tot['fa']:8.1f}")
    other = forms[forms["src"] != "google"].groupby("src").size().to_dict()
    nophone = int((~forms["has_phone"]).sum())
    print(f"\nФормы Supabase не из Google (не входят в счёт): Facebook {other.get('facebook', 0)}, другие источники {other.get('other', 0)}, "
          f"без метки (источник неизвестен) {other.get('none', 0)}. Форм без телефона {nophone}.")
    print(f"Если все формы без метки окажутся Google: заявок до {total + other.get('none', 0)}, цена от {(tot['cost'] / (total + other.get('none', 0)) if total + other.get('none', 0) else 0):.1f}.")
    orph = res["cv_orphans"]
    print(f"Звонки Google Ads (call_view) за период: {res['cv_total']}; без пары среди уникальных звонков Ringostat: {len(orph)}"
          + (" (" + ", ".join(f"{t:%d.%m %H:%M}" for t in orph['t']) + "; это повторные звонящие или звонки вне учёта клиента, в заявки не входят)" if len(orph) else "")
          + f"; кампания у Ringostat и call_view расходится: {res['cv_mismatch']}")
    print("Колонки «Ads»: основные конверсии (то, что считала сводка раньше) и формы+звонки из объявлений по названиям действий. Не стандарт, только сравнение.")
    pr = by_plan_row(res)
    un = pr.pop("__unassigned__", 0)
    if len(pr) > 1 or "__single__" not in pr:
        print("\nПо плановым проектам (заявки только с известной кампанией):")
        for k, v in pr.items():
            print(f"  {k}: расход {v['cost']:.1f}, заявок {v['attributed']}")
        print(f"  не распределено по проектам (Google без кампании): {un}")
    if daily:
        print("\nПо дням (Google Ads): звонки / из объявлений / формы")
        d = {}
        for _, r in calls.iterrows():
            d.setdefault(r["day"], [0, 0, 0])[1 if r["via_call_view"] else 0] += 1
        for _, r in g.iterrows():
            d.setdefault(r["day"], [0, 0, 0])[2] += 1
        for k in sorted(d):
            print(f"  {k}: {d[k][0]} / {d[k][1]} / {d[k][2]}")


def main():
    ap = argparse.ArgumentParser(description="Единый стандарт заявки Google Ads (Ringostat + Supabase), только чтение")
    ap.add_argument("--client", required=True)
    ap.add_argument("--from", dest="d0")
    ap.add_argument("--to", dest="d1")
    ap.add_argument("--daily", action="store_true")
    a = ap.parse_args()
    report(month_leads(a.client, a.d0, a.d1), daily=a.daily)


if __name__ == "__main__":
    main()
