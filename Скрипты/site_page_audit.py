#!/usr/bin/env python
# coding: utf-8
"""Аудит посадочной страницы настоящим браузером (Playwright), только чтение.

Что проверяет (телефон и компьютер): title и description, теги h1-h4, картинки без alt и тяжёлые файлы,
время загрузки и число запросов, ссылки на мессенджеры / телефон / соцсети (куда ведут),
внутренние ссылки и их HTTP-статус (битые 404), встроенные карты и виджеты, формы, якоря,
плавающие кнопки (виджет обратного звонка). Формы НЕ отправляются, на кнопки с отправкой не нажимаем.

Результат: JSON и скриншоты в Статистика/<клиент>/site_audit_<дата>/ и краткая сводка в консоли.
Зачем: сверять страницу до и после правок (H1, title, alt, вес, ссылки) по ТЗ.

Использование:
    python site_page_audit.py --url https://jewelryfastsale.com/gold-silver --client-folder LuxeBrokers
    --no-links-check   не проверять статусы внутренних ссылок
"""
import argparse
import json
import re
import sys
import time
from datetime import date
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from _config import client_stats_dir

PAGE_JS = """() => {
  const txt = e => (e.innerText || '').replace(/\\s+/g, ' ').trim();
  const heads = [...document.querySelectorAll('h1,h2,h3,h4')].map(e => [e.tagName, txt(e).slice(0, 120)]).filter(x => x[1]);
  const imgs = [...document.images].map(i => ({src: i.currentSrc || i.src, alt: i.alt || '', w: i.naturalWidth, h: i.naturalHeight}));
  const links = [...document.querySelectorAll('a[href]')].map(a => ({text: txt(a).slice(0, 50), href: a.href,
      raw: a.getAttribute('href'), block: (a.closest('.t-rec') || {}).id || '-', y: Math.round(a.getBoundingClientRect().top + scrollY)}));
  const anchors = [...document.querySelectorAll('a[name]')].map(a => a.name);
  const fixed = [...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e); const r = e.getBoundingClientRect();
      return s.position === 'fixed' && r.width > 20 && r.width < 200 && r.right > innerWidth - 150 && r.bottom > innerHeight - 200; })
      .map(e => (e.className || '').toString().slice(0, 60));
  return {title: document.title, description: (document.querySelector('meta[name=description]') || {}).content || '',
          og_title: (document.querySelector('meta[property="og:title"]') || {}).content || '',
          headings: heads, images: imgs, links, anchors, forms: document.querySelectorAll('form').length,
          iframes: [...document.querySelectorAll('iframe')].map(f => f.src).filter(Boolean), fixed,
          height: document.body.scrollHeight};
}"""


def audit(page, url, label, out_dir):
    res = []
    page.on("response", lambda r: res.append((r.url, r.status, r.headers.get("content-type", ""), int(r.headers.get("content-length") or 0))))
    t0 = time.time()
    resp = page.goto(url, wait_until="load", timeout=60000)
    load_s = round(time.time() - t0, 2)
    page.wait_for_timeout(2500)
    h = page.evaluate("document.body.scrollHeight")
    for y in range(0, h, 500):
        page.evaluate(f"window.scrollTo(0,{y})")
        page.wait_for_timeout(100)
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(500)
    info = page.evaluate(PAGE_JS)
    page.screenshot(path=str(out_dir / f"{label}_first_screen.png"))
    total = sum(x[3] for x in res)
    heavy = sorted([(x[3], x[0]) for x in res if x[3] > 150_000], reverse=True)[:10]
    info.update(label=label, status=resp.status if resp else None, load_s=load_s,
                requests=len(res), total_kb=round(total / 1024), heavy=[(round(s / 1024), u) for s, u in heavy])
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--no-links-check", action="store_true")
    args = ap.parse_args()

    out_dir = client_stats_dir(args.client_folder) / f"site_audit_{date.today():%Y-%m-%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    host = urlparse(args.url).netloc

    with sync_playwright() as p:
        b = p.chromium.launch()
        desktop = audit(b.new_context(viewport={"width": 1366, "height": 900}, locale="en-US").new_page(), args.url, "desktop", out_dir)
        mobile = audit(b.new_context(**p.devices["Pixel 5"], locale="en-US").new_page(), args.url, "mobile", out_dir)

        broken = []
        if not args.no_links_check:
            ctx = b.new_context(locale="en-US")
            seen = {}
            for l in desktop["links"]:
                u = l["href"].split("#")[0]
                if urlparse(u).netloc.endswith(host) and u not in seen and u != args.url:
                    seen[u] = None
            for u in list(seen)[:30]:
                try:
                    r = ctx.request.get(u, timeout=20000)
                    seen[u] = r.status
                    if r.status >= 400:
                        broken.append((u, r.status))
                except Exception as e:  # noqa
                    seen[u] = str(e)[:40]
        b.close()

    result = {"url": args.url, "date": f"{date.today():%Y-%m-%d}", "desktop": desktop, "mobile": mobile, "broken_internal_links": broken}
    (out_dir / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    d = desktop
    print(f"Страница: {args.url}  (HTTP {d['status']})")
    print(f"Title: {d['title']!r}\nDescription: {d['description']!r}\nog:title: {d['og_title']!r}")
    h1 = [t for tag, t in d["headings"] if tag == "H1"]
    print(f"\nЗаголовки: H1 = {len(h1)} {h1}; всего h1-h4 с текстом: {len(d['headings'])}")
    noalt = [i for i in d["images"] if not i["alt"] and not i["src"].endswith(".svg")]
    print(f"Картинок: {len(d['images'])}, без alt (не svg): {len(noalt)}")
    for m in (desktop, mobile):
        print(f"{m['label']}: загрузка {m['load_s']} с, запросов {m['requests']}, вес по заголовкам {m['total_kb']} КБ, высота {m['height']} px")
    print("Тяжёлые (> 150 КБ):", d["heavy"])
    pat = re.compile(r"whatsapp|wa\.me|t\.me|sms:|instagram|facebook|twitter|tel:|mailto:")
    print("\nМессенджеры / телефон / соцсети (блок, y, куда ведёт):")
    for l in d["links"]:
        if pat.search(l["href"]):
            print(f"  {l['block']}  y={l['y']}  {l['href'][:100]}")
    print("\nФрейм-карты и виджеты:", d["iframes"], "| плавающие:", d["fixed"][:3], "| форм:", d["forms"])
    print("Якоря:", sorted(set(d["anchors"])))
    print("Битые внутренние ссылки (>= 400):", broken or "нет")
    print(f"\nФайлы: {out_dir}")


if __name__ == "__main__":
    main()
