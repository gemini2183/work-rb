#!/usr/bin/env python
# coding: utf-8
"""Проверка тега «Клик по номеру» на живом сайте ProfiMet (мобильный режим, UTM как у PMax).

Принимает cookie, тапает каждый видимый tel:-элемент и показывает, что добавилось в
dataLayer и какие запросы ушли в GA4/Ads/Метрику. Сами запросы после записи блокируются,
чтобы тест не попал в статистику клиента. Нужен, чтобы ответить на вопрос «срабатывает ли
конверсия на один тап один раз и что её запускает». Результат 2026-10-07 —
Клиенты/ProfiMet/Решения.md.

Использование:
    python phone_click_probe.py
"""
import re

from playwright.sync_api import sync_playwright

URL = ("https://mocnaszklarnia.pl/?utm_source=google&utm_medium=cpc&utm_campaign=cid|23775369828|context"
       "&utm_content=rb|cid|23775369828|context|device|mobile")
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TRACK = re.compile(r"(google-analytics\.com/g/collect|analytics\.google\.com/g/collect|googleadservices\.com|"
                   r"google\.com/pagead|doubleclick\.net|mc\.yandex\.\w+/watch|facebook\.com/tr|connect\.facebook)")
PARAMS = re.compile(r"(en=[^&]+|label=[^&/]+|cv=[^&]+|ev=[^&]+|goal[^&]*|ut=[^&]+)")
CONSENT = re.compile("Zaakceptuj wszystkie", re.I)


def short(url):
    m = PARAMS.search(url)
    return re.sub(r"\?.*", "", url)[:90] + (" ?" + m.group(1) if m else "")


def accept_cookies(page, timeout):
    try:
        page.get_by_text(CONSENT).first.click(timeout=timeout)
        page.wait_for_timeout(1500)
        return True
    except Exception:
        return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=UA, viewport={"width": 390, "height": 844},
                                  has_touch=True, is_mobile=True)
        page = ctx.new_page()
        log = []

        def on_route(route):
            log.append(route.request.url)
            route.abort()

        page.route(TRACK, on_route)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(3000)
        print("cookie: принято" if accept_cookies(page, 4000) else "cookie: кнопку не нашёл")
        els = page.evaluate("""() => [...document.querySelectorAll('a[href^="tel:"]')].map((a,i)=>{
            const r=a.getBoundingClientRect();
            return {i, href:a.getAttribute('href'), text:(a.innerText||'').trim().slice(0,30),
                    cls:a.className.slice(0,50),
                    vis: r.width>0&&r.height>0&&getComputedStyle(a).visibility!='hidden'&&getComputedStyle(a).display!='none',
                    w:Math.round(r.width), h:Math.round(r.height), y:Math.round(r.top+scrollY)}})""")
        print("tel-ссылок на странице:", len(els))
        for e in els:
            print(" ", e)
        for e in els:
            if not e["vis"]:
                continue
            page.goto(URL, wait_until="networkidle")
            page.wait_for_timeout(2000)
            accept_cookies(page, 2500)
            n_before = len(log)
            dl_before = page.evaluate("window.dataLayer.length")
            page.evaluate(f"document.querySelectorAll('a[href^=\"tel:\"]')[{e['i']}]"
                          ".scrollIntoView({block:'center'})")
            page.wait_for_timeout(500)
            try:
                page.locator('a[href^="tel:"]').nth(e["i"]).click(timeout=3000, no_wait_after=True)
            except Exception as ex:
                print(" клик не удался:", e["i"], str(ex)[:80])
                continue
            page.wait_for_timeout(3000)
            new_dl = page.evaluate(f"JSON.stringify(window.dataLayer.slice({dl_before})"
                                   ".map(x=>x.event||Object.keys(x).join(',')))")
            print(f"\n[tel #{e['i']}] {e['text']!r} cls={e['cls']!r}\n  dataLayer новые: {new_dl}\n"
                  f"  запросов трекеров: {len(log) - n_before}")
            for u in log[n_before:]:
                print("   ", short(u))
        browser.close()


if __name__ == "__main__":
    main()
