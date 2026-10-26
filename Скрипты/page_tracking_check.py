#!/usr/bin/env python
# coding: utf-8
"""Трекинг и работоспособность посадочной страницы одной командой. ТОЛЬКО ЧТЕНИЕ: формы не отправляются,
запросы GA4 перехватываются (в аналитику клиента ничего не уходит), пиксели рекламных систем блокируются.

Зачем: перед запуском рекламы на новую страницу (Landver, 2026-10-24) то же самое делалось пачкой разовых скриптов. Здесь собрано в одно место:
  1. Страница: title/description/lang/canonical/robots, h1, картинки без alt, ошибки консоли и запросы с ошибкой, грубая скорость на мобильном.
  2. Трекеры: id контейнера GTM, версия, Ringostat (скрипт и число XPath-правил), Clarity, пиксели, gtag.
  3. Телефон: каждая ссылка tel: (текст, класс, data-атрибуты, видимость), подменяется ли она при метках google/cpc против страницы без меток.
  4. Формы: id, имена полей, скрытые поля, находятся ли они в окне (popup) и какой у окна хук.
  5. Кнопки и якоря: куда ведёт каждая ссылка «#…»: есть ли цель, не пуста ли она (высота 0), не хук ли окна;
     «мёртвые» якоря (цель есть, но ничего не показывает) помечаются.
  6. События, которые страница сама пушит в dataLayer (разбор inline-скриптов) и что реально лежит в dataLayer.
  7. Сценарий (прокрутка, клики по --click, клики по номерам и почте, раскрытие FAQ) и список событий GA4, которые ушли бы с ТЕКУЩИМ контейнером GTM, с параметрами.
Результат: отчёт в консоль и в Статистика/<клиент>/page_tracking_check_<домен>_<дата>.md.

    python page_tracking_check.py --url https://site/page --client-folder Andverpersonalinjury \\
        [--click "#quiz button.opt" --click "#quiz button.opt" ...] [--faq "details summary"] [--no-mobile]
Что не покрывает: реальную отправку формы, живой звонок, согласие на cookie, конверсии в Google Ads.
"""
import argparse
import io
import json
import re
import sys
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

from _config import client_stats_dir

UTM = "utm_source=google&utm_medium=cpc&utm_campaign=page_tracking_check"
BLOCK_HOSTS = ("bzr.openai.com", "bzrcdn.openai.com", "clarity.ms", "doubleclick.net", "facebook.net", "connect.facebook.com",
               "googleadservices.com", "analytics.tiktok.com", "px.ads.linkedin.com")

COLLECT_JS = r"""()=>{
  const out = {};
  const q = s => document.querySelector(s);
  out.title = document.title; out.lang = document.documentElement.lang || '';
  out.description = (q('meta[name=description]')||{}).content || '';
  out.canonical = (q('link[rel=canonical]')||{}).href || '';
  out.robots = (q('meta[name=robots]')||{}).content || '';
  out.viewport = (q('meta[name=viewport]')||{}).content || '';
  out.h1 = [...document.querySelectorAll('h1')].map(h => h.innerText.trim().split(String.fromCharCode(10))[0].slice(0,100));
  const imgs = [...document.images]; out.imgs = imgs.length; out.noAlt = imgs.filter(i => !i.hasAttribute('alt')).length;
  const scripts = [...document.scripts];
  const srcs = scripts.map(s => s.src).filter(Boolean);
  const inline = scripts.filter(s => !s.src).map(s => s.textContent);
  const all = srcs.join('\n') + '\n' + inline.join('\n');
  out.gtm = [...new Set((all.match(/GTM-[A-Z0-9]{5,8}/g)||[]))];
  out.ga = [...new Set((all.match(/\bG-[A-Z0-9]{8,12}\b/g)||[]))];
  out.aw = [...new Set((all.match(/\bAW-\d{6,12}\b/g)||[]))];
  out.ringostat = srcs.filter(s => /ringostat/.test(s));
  out.clarity = [...new Set((all.match(/clarity\.ms\/tag\/([a-z0-9]+)|"clarity","script","([a-z0-9]+)"/g)||[]))].slice(0,3);
  out.pixels = ['fbq','ttq','_linkedin_partner_id','oaiq','hj','ym'].filter(k => typeof window[k] !== 'undefined');
  // события, которые страница пушит сама
  const ev = new Set();
  inline.forEach(t => {
    (t.match(/event\s*:\s*['"]([\w.-]+)['"]/g)||[]).forEach(m => ev.add(m.replace(/event\s*:\s*['"]/,'').replace(/['"]$/,'')));
    (t.match(/track\(\s*['"]([\w.-]+)['"]/g)||[]).forEach(m => ev.add(m.replace(/track\(\s*['"]/,'').replace(/['"]$/,'')));
  });
  ['gtm.js','gtm.start','gtm.dom','gtm.load'].forEach(e => ev.delete(e));
  out.pageEvents = [...ev];
  // телефоны
  out.tel = [...document.querySelectorAll('a[href^="tel:"]')].map(a => {
    const d = {}; [...a.attributes].filter(x => x.name.startsWith('data-')).forEach(x => d[x.name] = x.value);
    const r = a.getBoundingClientRect();
    return {href: a.getAttribute('href'), text: a.textContent.replace(/\s+/g,' ').trim().slice(0,70), html: a.innerHTML.replace(/\s+/g,' ').trim().slice(0,200),
            cls: String(a.className).slice(0,70), data: d, visible: !!(a.offsetWidth||a.offsetHeight), nested: a.querySelectorAll('a').length};
  });
  out.mailto = [...document.querySelectorAll('a[href^="mailto:"]')].map(a => a.getAttribute('href'));
  // формы и окна
  out.forms = [...document.querySelectorAll('form')].map(f => ({
    id: f.id, popup: !!f.closest('.t-popup'), visible: !!(f.offsetWidth||f.offsetHeight),
    fields: [...f.querySelectorAll('input,textarea,select')].filter(i => i.type !== 'hidden').map(i => i.name + ':' + i.type),
    hidden: [...f.querySelectorAll('input[type=hidden]')].map(i => i.name).filter(n => n && !/^(formservices|tildaspec)/.test(n))}));
  out.popupHooks = [...document.querySelectorAll('[data-tooltip-hook]')].map(e => e.getAttribute('data-tooltip-hook'));
  // якоря
  const anchors = {};
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    const h = a.getAttribute('href'); if (h.length < 2) return;
    const id = h.slice(1);
    const el = document.getElementById(id) || document.querySelector('[name="'+id+'"]');
    const hook = out.popupHooks.includes(h);
    let state;
    if (hook) state = 'открывает окно';
    else if (!el) state = 'ЦЕЛИ НЕТ';
    else {
      const r = el.getBoundingClientRect();
      if (r.height === 0 && !el.querySelector('*')) {
        let n = el, nxt = null;
        while (n && !nxt) { let s = n.nextElementSibling; while (s) { if (s.getBoundingClientRect().height > 0) { nxt = s; break; } s = s.nextElementSibling; } n = n.parentElement; }
        const ar = el.getBoundingClientRect().top + window.scrollY;
        const near = [...document.querySelectorAll('form')].filter(f => !f.closest('.t-popup') && f.getBoundingClientRect().height > 0).map(f => f.getBoundingClientRect().top + window.scrollY - ar).filter(d => d >= -50 && d <= 900).sort((x, y) => x - y)[0];
        state = 'якорь высотой 0 -> дальше: ' + (nxt ? (nxt.tagName.toLowerCase() + (nxt.id ? '#' + nxt.id : '')) : 'ничего') + '; ближайшая форма ниже: ' + (near === undefined ? 'НЕТ в пределах 900 px (кнопка «к форме» никуда не ведёт?)' : 'через ' + Math.round(near) + ' px');
      } else state = 'ведёт к блоку' + ((el.tagName === 'FORM' || el.querySelector('form')) ? ' (с формой)' : '');
    }
    const cta = a.getAttribute('data-ldv-cta') || [...a.attributes].filter(x => x.name.startsWith('data-') && /cta|goal|track|event/i.test(x.name)).map(x => x.value)[0] || a.textContent.trim().slice(0,30);
    (anchors[h+' | '+state] = anchors[h+' | '+state] || []).push(cta);
  });
  out.anchors = anchors;
  out.sections = [...document.querySelectorAll('[id]')].filter(e => ['SECTION','FOOTER','HEADER','DIV','FORM','ASIDE'].includes(e.tagName) && e.getBoundingClientRect().height > 80 && !/^rec\d+/.test(e.id))
    .map(e => e.id + ':' + Math.round(e.getBoundingClientRect().height)).slice(0, 40);
  out.faq = (document.querySelectorAll('details summary').length) ? 'details/summary: ' + document.querySelectorAll('details summary').length : '';
  out.dl = (window.dataLayer||[]).map(x => x.event).filter(Boolean);
  return out;
}"""


def parse_collect(route_request):
    q = parse_qs(urlparse(route_request.url).query)
    base = {k: v[0] for k, v in q.items()}
    body = route_request.post_data or ""
    lines = [l for l in body.splitlines() if l.strip()]
    evs = []
    if lines:
        for l in lines:
            d = dict(base); d.update({k: v[0] for k, v in parse_qs(l).items()}); evs.append(d)
    else:
        evs.append(base)
    return evs


def run_viewport(p, name, ctx_kw, a, report):
    br = p.chromium.launch()
    ctx = br.new_context(**ctx_kw)
    hits, bad, console = [], [], []

    def route(r):
        u = r.request.url
        if "/g/collect" in u or "/j/collect" in u:
            hits.extend(parse_collect(r.request))
            return r.fulfill(status=204, body="")
        if any(h in u for h in BLOCK_HOSTS):
            return r.abort()
        r.continue_()
    ctx.route("**/*", route)
    pg = ctx.new_page()
    pg.on("console", lambda m: console.append(m.text[:150]) if (m.type == "error" and "ERR_FAILED" not in m.text and "ERR_BLOCKED" not in m.text) else None)
    pg.on("response", lambda r: bad.append(f"{r.status} {r.url[:110]}") if r.status >= 400 else None)
    pg.add_init_script("window.__lcp=0;new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});")
    sep = "&" if "?" in a.url else "?"
    pg.goto(a.url + sep + UTM, wait_until="load", timeout=90000)
    pg.wait_for_timeout(5000)
    info = pg.evaluate(COLLECT_JS)
    lcp = pg.evaluate("Math.round(window.__lcp)")
    # та же страница без меток: подмена номера?
    ctx2 = br.new_context(**ctx_kw)  # чистый профиль: Ringostat запоминает метки визита внутри одного профиля
    ctx2.route("**/*", lambda r: r.abort() if ("/g/collect" in r.request.url or any(h in r.request.url for h in BLOCK_HOSTS)) else r.continue_())
    pg2 = ctx2.new_page()
    pg2.goto(a.url, wait_until="load", timeout=90000)
    pg2.wait_for_timeout(5000)
    plain = [t["href"] for t in pg2.evaluate(COLLECT_JS)["tel"]]
    ctx2.close()
    # сценарий: прокрутка
    h = pg.evaluate("document.documentElement.scrollHeight")
    y = 0
    while y < h:
        y += 500
        pg.evaluate(f"window.scrollTo(0,{y})")
        pg.wait_for_timeout(420)
    pg.wait_for_timeout(1200)
    for sel in a.click:
        try:
            loc = pg.locator(sel).first
            loc.scroll_into_view_if_needed(timeout=3000)
            pg.wait_for_timeout(250)
            loc.click(timeout=3000, no_wait_after=True)
        except Exception as e:
            report.append(f"  клик не удался: {sel} ({str(e).splitlines()[0][:60]})")
        pg.wait_for_timeout(600)
    if a.faq:
        try:
            pg.locator(a.faq).first.scroll_into_view_if_needed(timeout=3000)
            pg.locator(a.faq).first.click(timeout=3000, no_wait_after=True)
            pg.wait_for_timeout(800)
        except Exception as e:
            report.append(f"  FAQ не раскрылся: {a.faq} ({str(e).splitlines()[0][:60]})")
    for i, t in enumerate(info["tel"]):  # клик по каждой ссылке tel: (без перехода в телефонную программу — в браузере без обработчика ничего не происходит)
        try:
            loc = pg.locator('a[href^="tel:"]').nth(i)
            if t["visible"]:
                loc.scroll_into_view_if_needed(timeout=2500)
                loc.click(timeout=2500, no_wait_after=True)
            else:
                loc.dispatch_event("click")
        except Exception:
            pass
        pg.wait_for_timeout(450)
    for i in range(len(info["mailto"])):
        try:
            loc = pg.locator('a[href^="mailto:"]').nth(i)
            loc.scroll_into_view_if_needed(timeout=2500)
            loc.click(timeout=2500, no_wait_after=True)
        except Exception:
            pass
        pg.wait_for_timeout(450)
    pg.wait_for_timeout(5000)  # события уходят с задержкой
    dl_after = pg.evaluate("(window.dataLayer||[]).map(x=>x.event).filter(Boolean)")
    br.close()

    report.append(f"\n## {name}")
    report.append(f"- Страница: «{info['title']}», lang=«{info['lang']}», h1: {info['h1']}, canonical: {info['canonical'] or 'нет'}, robots: {info['robots'] or 'нет'}")
    report.append(f"- description: {info['description'][:170] or 'НЕТ'}")
    report.append(f"- Картинок {info['imgs']}, без alt {info['noAlt']}; LCP {lcp} мс (шумно, без замедления; решение по скорости — PageSpeed Insights); ошибок консоли {len(console)}; запросов с ошибкой {len(bad)}")
    for m in console[:5]:
        report.append(f"    консоль: {m}")
    for m in [b for b in bad if not any(x in b for x in ("collect", "clarity"))][:8]:
        report.append(f"    {m}")
    report.append(f"- Трекеры: GTM {info['gtm']}, GA4 {info['ga']}, AW {info['aw']}, Ringostat {len(info['ringostat'])} скрипт(а), Clarity {info['clarity']}, пиксели (глобальные объекты) {info['pixels']}")
    swapped = sum(1 for t, pl in zip(info["tel"], plain) if t["href"] != pl) if len(plain) == len(info["tel"]) else None
    report.append(f"- Телефон: ссылок tel: {len(info['tel'])}; с метками Google отличаются от страницы без меток: {swapped if swapped is not None else 'сравнить нельзя (число ссылок разное)'}")
    for t in info["tel"]:
        flag = "" if t["nested"] == 0 else f" ВЛОЖЕННЫХ <a>: {t['nested']}"
        report.append(f"    {t['href']} | «{t['text']}» | {'видна' if t['visible'] else 'скрыта'} | data={t['data'] or '—'} | class={t['cls']}{flag}")
    report.append(f"- Почта: {info['mailto'] or 'нет'}")
    report.append(f"- Формы: {len(info['forms'])}")
    for f in info["forms"]:
        report.append(f"    {f['id'] or '(без id)'} | {'ОКНО' if f['popup'] else 'на странице'} | {'видна' if f['visible'] else 'скрыта'} | поля {f['fields']} | скрытые {f['hidden']}")
    report.append(f"- Хуки окон: {info['popupHooks'] or 'нет'}")
    report.append("- Якоря «#…» (куда ведут кнопки):")
    for k, v in info["anchors"].items():
        report.append(f"    {k}  <- {sorted(set(v))}")
    report.append(f"- Блоки с id (высота): {info['sections']}")
    report.append(f"- FAQ: {info['faq'] or 'не найден'}")
    report.append(f"- События, которые страница пушит сама (разбор кода): {info['pageEvents'] or 'нет'}")
    report.append(f"- dataLayer после сценария: {sorted(set(dl_after))}")
    en = {}
    for h_ in hits:
        e = h_.get("en", "?")
        en.setdefault(e, [])
        pr = {k.split('.', 1)[1]: v for k, v in h_.items() if k.startswith(("ep.", "epn."))}
        if pr and pr not in en[e] and len(en[e]) < 6:
            en[e].append(pr)
        elif e not in en:
            en[e] = []
    cnt = {}
    for h_ in hits:
        cnt[h_.get("en", "?")] = cnt.get(h_.get("en", "?"), 0) + 1
    report.append(f"- События GA4, которые ушли бы с текущим контейнером ({len(hits)}): {cnt}")
    for e, prs in en.items():
        if prs and e not in ("block_view", "block_time"):
            report.append(f"    {e}: {prs[:4]}")
    pe = set(info["pageEvents"])
    missing = sorted(x for x in pe if x not in cnt and x not in sorted(set(dl_after)))
    if pe:
        report.append(f"- События страницы, на которые в GA4 не ушло событие с тем же именем: {sorted(x for x in pe if x not in cnt)} (имя в GA4 может отличаться, например ldv_cta -> cta_click: сверить с триггерами контейнера)")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--client-folder", default=None)
    ap.add_argument("--click", action="append", default=[], help="CSS-селектор для клика по порядку (квиз: повторить несколько раз)")
    ap.add_argument("--faq", default=None, help="CSS-селектор вопроса FAQ")
    ap.add_argument("--no-mobile", action="store_true")
    a = ap.parse_args()
    report = [f"# Проверка трекинга страницы {a.url}", f"Дата: {datetime.now():%Y-%m-%d %H:%M}. Метки: {UTM}. Только чтение; GA4 перехвачен, пиксели заблокированы."]
    with sync_playwright() as p:
        run_viewport(p, "Десктоп 1366×850", dict(viewport={"width": 1366, "height": 850}), a, report)
        if not a.no_mobile:
            run_viewport(p, "Мобильный (iPhone 13)", dict(p.devices["iPhone 13"]), a, report)
    text = "\n".join(report)
    print(text)
    if a.client_folder:
        host = urlparse(a.url).netloc.replace(".", "_") + "_" + urlparse(a.url).path.strip("/").replace("/", "_")[:40]
        f = client_stats_dir(a.client_folder) / f"page_tracking_check_{host}_{datetime.now():%Y-%m-%d}.md"
        f.write_text(text, encoding="utf-8")
        print("\nСохранено:", f)


if __name__ == "__main__":
    main()
