#!/usr/bin/env python
# coding: utf-8
"""Подмена номера на РЕАЛЬНЫХ посадочных страницах рекламы: только чтение (Google Ads) + Playwright без записи куда-либо.

Зачем: `phone_swap_check.py` проверяет только главную страницу из пула, а реклама ведёт на другие. Скрипт берёт из
Google Ads посадочные страницы за последние дни (`landing_page_view`, клики и расход), для самых кликабельных открывает
страницу с UTM канала (по умолчанию динамический Google CPC) и строго проверяет каждый элемент с номером: tel:-ссылку
(href и текст) и номер, лежащий обычным текстом. Любой номер вне пула канала — это место, где посетитель из рекламы
увидит статический номер сайта, а звонок попадёт в «Нет метки».

Использование:
    python gads_landing_swap_check.py --customer-id 755-278-1705 --client-folder ProfiMet --days 30 --top 15 \
        [--channel "Google CPC_dyn (google_cpc_dyn)"] [--desktop-only]
Пул и UTM канала — из `Клиенты/<клиент>/Коллтрекинг/Пул_номеров.yaml` (как у phone_swap_check.py).
"""
import argparse
import sys
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import yaml
from google.ads.googleads.client import GoogleAdsClient
from playwright.sync_api import sync_playwright

from _config import VAULT_ROOT, client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from phone_swap_check import UA, canon, check_one


def landing_pages(customer_id, days):
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    q = f"""SELECT landing_page_view.unexpanded_final_url, metrics.clicks, metrics.cost_micros
            FROM landing_page_view WHERE segments.date DURING LAST_{days}_DAYS AND metrics.clicks > 0"""
    acc = {}
    for r in ga.search(customer_id=customer_id.replace("-", ""), query=q):
        u = urlsplit(r.landing_page_view.unexpanded_final_url)
        key = urlunsplit((u.scheme, u.netloc, u.path, "", ""))
        a = acc.setdefault(key, {"url": key, "clicks": 0, "cost": 0.0})
        a["clicks"] += r.metrics.clicks
        a["cost"] += r.metrics.cost_micros / 1e6
    return pd.DataFrame(acc.values()).sort_values("clicks", ascending=False).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--channel", default=None, help="имя канала из Пул_номеров.yaml (по умолчанию первый — динамический Google)")
    ap.add_argument("--pool-file", default="Коллтрекинг/Пул_номеров.yaml")
    ap.add_argument("--wait-ms", type=int, default=6000)
    ap.add_argument("--desktop-only", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cfg = yaml.safe_load(open(VAULT_ROOT / "Клиенты" / a.client_folder / a.pool_file, encoding="utf-8"))
    ch = next(c for c in cfg["channels"] if a.channel is None or c["name"] == a.channel)
    ignore = {canon(n) for n in cfg.get("ignore_numbers", [])} - {None}
    print(f"Канал для проверки: {ch['name']} {ch['utm_test']}, номеров в пуле {len(ch['pool'])}")

    lp = landing_pages(a.customer_id, a.days)
    total = lp["clicks"].sum()
    print(f"\nПосадочных страниц с кликами за {a.days} дн: {len(lp)}; кликов {int(total)}")
    print(lp.head(a.top).assign(доля=(lp['clicks'] / total).round(3)).to_string(index=False))

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for _, r in lp.head(a.top).iterrows():
            for vp, w, h in [("desktop", 1280, 900)] + ([] if a.desktop_only else [("mobile", 390, 844)]):
                ctx = browser.new_context(user_agent=UA, viewport={"width": w, "height": h})
                page = ctx.new_page()
                try:
                    res = check_one(page, r["url"], ch["utm_test"], ch["pool"], a.wait_ms, ignore)
                    err = ""
                except Exception as e:
                    res, err = {"ok": False, "bad": [], "found": [], "matched": []}, str(e)[:120]
                finally:
                    ctx.close()
                status = "OK" if res["ok"] else ("ОШИБКА" if err else "НЕ ВСЕ НОМЕРА ПОДМЕНЕНЫ")
                print(f"[{status}] {vp} {r['url']} (кликов {int(r['clicks'])}) нашли {res.get('found')}{' ' + err if err else ''}")
                seen = set()
                for b in res["bad"]:
                    k = (b["kind"], b["section"], b["cls"], tuple(b["outside"]))
                    if k in seen:
                        continue
                    seen.add(k)
                    print(f"    !! не из пула {b['outside']}: {b['kind']} section={b['section'] or '-'} class={b['cls'] or '-'} "
                          f"href={b['href'] or '-'} text={b['text']!r} {'видим' if b['visible'] else 'скрыт'}")
                rows.append({"url": r["url"], "clicks": int(r["clicks"]), "viewport": vp, "ok": res["ok"], "error": err,
                             "bad": " | ".join(f"{b['kind']}:{b['section']}:{b['cls'][:30]}:{','.join(b['outside'])}" for b in res["bad"])})
        browser.close()
    df = pd.DataFrame(rows)
    out = client_stats_dir(a.client_folder) / f"gads_landing_swap_check_{date.today().isoformat()}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    bad = df[~df["ok"]]
    print(f"\nСтраниц-проверок не прошло: {len(bad)} из {len(df)}; кликов на страницах с проблемой (десктоп): "
          f"{int(bad[bad['viewport'] == 'desktop']['clicks'].sum())} из {int(df[df['viewport'] == 'desktop']['clicks'].sum())}")
    print("(сохранено:", out, ")")


if __name__ == "__main__":
    main()
