#!/usr/bin/env python
# coding: utf-8
"""Матрица «значение utm_campaign → какой номер выдаёт сайт» (проверка каналов и пулов Ringostat).

Зачем: условия каналов трафика Ringostat (регулярные выражения по UTM) не читаются ни через API, ни из скрипта на
сайте — их можно проверить только поведением. Скрипт открывает сайт в мобильном режиме с заданными UTM и показывает,
какой номер подставлен, сопоставляя его с пулами из Клиенты/<клиент>/Коллтрекинг/Пул_номеров.yaml (если файл дан).
Запросы аналитики (GA4, Ads, Метрика, Facebook) блокируются, тест не попадает в статистику клиента. Каждый случай
повторяется --repeats раз: у динамических пулов номер меняется от захода к заходу.

Использование:
    python ringostat_channel_matrix.py --url https://mocnaszklarnia.pl/ \\
        --campaigns dspl_rtg_basket dspl_rtg_engage_mid dspl_other pmax1_test xdspl_rtg_basket \\
        --pool-file "../Клиенты/ProfiMet/Коллтрекинг/Пул_номеров.yaml" --repeats 2
    # другие UTM: --source facebook --medium cpc ; без utm_campaign: добавить пустую строку "" в --campaigns
"""
import argparse
import re
from urllib.parse import urlencode

import yaml
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TRACK = re.compile(r"(google-analytics\.com/g/collect|googleadservices\.com|google\.com/pagead|doubleclick\.net|"
                   r"mc\.yandex\.\w+/watch|facebook\.com/tr)")


def digits(raw):
    d = re.sub(r"\D", "", raw or "")
    return d[-9:]


def load_pools(path):
    if not path:
        return {}
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    pools = {}
    for ch in cfg.get("channels", []):
        for n in ch.get("pool", []):
            pools[digits(n)] = ch["name"]
    return pools


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--source", default="google")
    ap.add_argument("--medium", default="cpc")
    ap.add_argument("--campaigns", nargs="+", required=True, help='значения utm_campaign; "" — без utm_campaign')
    ap.add_argument("--pool-file", help="Пул_номеров.yaml клиента (для подписи пула)")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--wait-ms", type=int, default=3500)
    args = ap.parse_args()

    pools = load_pools(args.pool_file)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for camp in args.campaigns:
            q = {"utm_source": args.source, "utm_medium": args.medium}
            if camp:
                q["utm_campaign"] = camp
            url = args.url + ("&" if "?" in args.url else "?") + urlencode(q)
            seen = []
            for _ in range(args.repeats):
                ctx = browser.new_context(user_agent=UA, viewport={"width": 390, "height": 844},
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.route(TRACK, lambda r: r.abort())
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(args.wait_ms)
                nums = page.evaluate("[...new Set([...document.querySelectorAll('a[href^=\"tel:\"]')]"
                                     ".map(a=>a.getAttribute('href').replace('tel:','')))]")
                seen.append(nums[0] if nums else None)
                ctx.close()
            labels = sorted({pools.get(digits(n), "вне пулов yaml (номер сайта или другой статический)") for n in seen if n})
            print(f"{camp or '(без utm_campaign)':34} {seen}  -> {'; '.join(labels)}")
        browser.close()


if __name__ == "__main__":
    main()
