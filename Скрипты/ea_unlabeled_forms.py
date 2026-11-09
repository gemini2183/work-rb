#!/usr/bin/env python
# coding: utf-8
"""EkspertAgro: формы Supabase БЕЗ метки источника — что о них известно из других мест. ТОЛЬКО ЧТЕНИЕ.

Для каждой формы (Supabase `expertagro_leads`, не мусорные пачки, один телефон за день) без utm_source/medium/campaign и gclid:
  1) все поля строки Supabase (utm_content, page_url, gclid — если колонки есть);
  2) строки CRM (таблица клиента) с тем же телефоном: тип, источник, utm, gclid, заказ — до и после формы;
  3) событие GA4 `form_submit` в ±3 минуты: источник/кампания сеанса, источник первого касания пользователя, посадочная.
Печатает вывод по каждой форме: «Google по GA4/CRM», «не Google» или «нет данных».
Использование (из папки Скрипты): PYTHONUTF8=1 python ea_unlabeled_forms.py [--from 2026-11-01] [--to 2026-11-09]
"""
import argparse
from pathlib import Path

import pandas as pd
import requests
import yaml

import gads_spend_guard_cpa as G
from ea_forms_ga4_vs_crm import ga4_report
from ea_sales_orders_check import SHEET_ID as CRM_ID, load as load_sheet
from ea_sources_dashboard import ga4_session
from leads_standard import MON_DIR, WARSAW, _p9

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-01")
    ap.add_argument("--to", dest="d1", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    ap.add_argument("--client", default="EkspertAgro")
    a = ap.parse_args()

    gc = yaml.safe_load((HERE.parent / "Клиенты" / a.client / "guard_config.yaml").read_text(encoding="utf-8"))
    m_r, m_s, _tg, cfg = G.load_monitoring(MON_DIR, str(Path(MON_DIR) / "config" / gc["monitoring_config"]))
    sb = cfg["supabase"]
    h = {"apikey": sb["secret_key"], "Authorization": f"Bearer {sb['secret_key']}"}
    since = (pd.Timestamp(a.d0) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    r = requests.get(f"{sb['url']}/rest/v1/{sb['table']}", headers={**h, "Range": "0-4999"}, timeout=60,
                     params={"select": "*", "created_at": f"gte.{since}T00:00:00", "order": "created_at.asc"})
    r.raise_for_status()
    rows = m_s.mark_bursts(r.json())
    print(f"Колонки Supabase: {sorted(rows[0].keys()) if rows else '—'}")

    seen, todo = set(), []
    for x in rows:
        if x.get("_burst"):
            continue
        ts = pd.to_datetime(x["created_at"], utc=True)
        day = ts.tz_convert(WARSAW).date()
        if not (pd.Timestamp(a.d0).date() <= day <= pd.Timestamp(a.d1).date()):
            continue
        p9 = _p9(x.get("phone"))
        key = (day, p9) if p9 else (ts.isoformat(), "")
        if key in seen:
            continue
        seen.add(key)
        if any(str(x.get(k) or "").strip() for k in ("utm_source", "utm_medium", "utm_campaign", "gclid")):
            continue
        todo.append((ts, p9, x))
    print(f"Форм без метки за {a.d0} … {a.d1}: {len(todo)}\n")

    crm = load_sheet(CRM_ID, "Ekspertagro.pl")
    crm["p9"] = crm["phone"].map(_p9)
    s = ga4_session()
    d0g = (pd.Timestamp(a.d0) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    dims = ["dateHourMinute", "sessionSourceMedium", "sessionCampaignName", "firstUserSourceMedium", "firstUserCampaignName", "landingPagePlusQueryString"]
    try:
        ev = ga4_report(s, d0g, a.d1, dims, ["eventCount"], "form_submit")
        ev["ts"] = pd.to_datetime(ev["dateHourMinute"], format="%Y%m%d%H%M").dt.tz_localize(WARSAW).dt.tz_convert("UTC")
    except Exception as ex:   # noqa: BLE001
        print(f"GA4 не прочитан: {type(ex).__name__}: {str(ex)[:150]}")
        ev = pd.DataFrame(columns=dims + ["eventCount", "ts"])

    for ts, p9, x in todo:
        loc = ts.tz_convert(WARSAW)
        print("=" * 100)
        print(f"{loc:%Y-%m-%d %H:%M:%S} Варшава | телефон …{p9[-4:] if p9 else 'нет'} | Supabase: "
              + ", ".join(f"{k}={str(v)[:70]}" for k, v in x.items() if k not in ("id", "created_at", "phone", "_burst") and str(v or "").strip()))
        verdict = []
        if p9:
            c = crm[crm["p9"] == p9].sort_values("ts")
            if len(c):
                print("  CRM, строки с этим телефоном:")
                for _, y in c.iterrows():
                    print(f"    {y['ts'].tz_convert(WARSAW):%m-%d %H:%M} {y['type']:8s} src={y['src']:14s} utm={y['utm_source']}/{y['utm_medium']}/{str(y['utm_campaign'])[:30]} gclid={'да' if y['gclid'] else 'нет'} заказ={str(y['order'])[:8]} {y['status']}")
                    s_ = (str(y["src"]) + str(y["utm_source"])).lower()
                    if y["gclid"] or "google" in s_:
                        verdict.append("CRM: Google")
                    elif "facebook" in s_:
                        verdict.append("CRM: Facebook")
            else:
                print("  CRM: строк с этим телефоном нет (таблица отстаёт или телефон другой)")
        near = ev[(ev["ts"] - ts).abs() <= pd.Timedelta(minutes=3)]
        if len(near):
            for _, e in near.iterrows():
                print(f"  GA4 form_submit {e['dateHourMinute']}: сеанс {e['sessionSourceMedium']} / {e['sessionCampaignName']} | первое касание {e['firstUserSourceMedium']} / {e['firstUserCampaignName']} | посадочная {str(e['landingPagePlusQueryString'])[:90]}")
                t = (e["sessionSourceMedium"] + e["firstUserSourceMedium"]).lower()
                if "google / cpc" in t:
                    verdict.append("GA4: Google CPC")
                elif "facebook" in t or "fb" in t or "instagram" in t:
                    verdict.append("GA4: Facebook")
                elif "(direct)" in t:
                    verdict.append("GA4: прямой")
                else:
                    verdict.append(f"GA4: {e['sessionSourceMedium']}")
        else:
            print("  GA4: события form_submit в ±3 мин нет")
        print(f"  ВЫВОД: {'; '.join(dict.fromkeys(verdict)) if verdict else 'нет данных'}")


if __name__ == "__main__":
    main()
