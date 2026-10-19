#!/usr/bin/env python
# coding: utf-8
"""Проверить версию контейнера GTM в браузере ДО публикации — без вреда для данных. Пишет только временную среду GTM (и удаляет её).

Как: создаёт среду GTM на указанной версии (type=user), открывает сайт в Playwright, подменяя `gtm.js` на версию из среды
(`gtm_preview=env-N`, `gtm_auth=<код>`), блокирует всё, кроме сайта, Tilda и GTM, запросы GA4 (`/g/collect`) ПЕРЕХВАТЫВАЕТ,
разбирает и обрывает — в аналитику ничего не уходит; форма сайта не отправляется. Согласие задаётся из командной строки.
Сценарий: плавная прокрутка всей страницы (блоки), клик по каждой видимой ссылке `tel:` (место номера), затем отчёт —
какие события GA4 ушли и с какими параметрами. Повтор в мобильном окне. В конце среда удаляется.

    python gtm_test_version.py --account 6003760261 --container 44158621 --version 64 --url https://mocnaszklarnia.pl/ \\
        --grant analytics_storage [--events block_view block_time click_tel] [--no-mobile] [--keep-env]
    python gtm_test_version.py ... --grant none     # контроль: без согласия события не должны уходить
"""
import argparse
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlsplit

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from playwright.sync_api import sync_playwright

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]
ALLOWED = ("tildacdn", "tilda.ws", "tilda.cc", "googletagmanager.com", "mocnaszklarnia.pl", "fonts.g", "fonts.googleapis")


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:400]}")
    return r.json() if r.text else {}


def parse_collect(request):
    """Все события из одного запроса /g/collect (одно в URL, остальные — строками тела)."""
    base = dict(parse_qsl(urlsplit(request.url).query))
    out = []
    body = request.post_data or ""
    lines = [l for l in body.splitlines() if l.strip()]
    if lines:
        for l in lines:
            d = dict(base); d.update(dict(parse_qsl(l))); out.append(d)
    else:
        out.append(base)
    return out


def run_scenario(pg, grant, wait_s):
    gtag = "window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}"
    if grant != ["none"]:
        state = {k: ("granted" if k in grant else "denied")
                 for k in ("ad_storage", "ad_user_data", "ad_personalization", "analytics_storage")}
        pg.evaluate(gtag + f";gtag('consent','update',{state!r})".replace("'granted'", "'granted'"))
    pg.wait_for_timeout(1500)
    height = pg.evaluate("document.documentElement.scrollHeight")
    vh = pg.evaluate("window.innerHeight")
    y = 0
    while y < height:
        pg.mouse.wheel(0, vh * 0.6)
        pg.wait_for_timeout(1700)
        y += vh * 0.6
    pg.wait_for_timeout(wait_s * 1000)
    pg.evaluate("""()=>{document.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('a[href^="tel:"]');if(a)e.preventDefault()},true)}""")
    n = pg.evaluate("document.querySelectorAll('a[href^=\"tel:\"]').length")
    clicked = 0
    for i in range(n):
        try:
            loc = pg.locator('a[href^="tel:"]').nth(i)
            loc.scroll_into_view_if_needed(timeout=3000)
            pg.wait_for_timeout(400)
            loc.click(timeout=3000, force=True, no_wait_after=True)
            clicked += 1
            pg.wait_for_timeout(900)
            pg.reload(wait_until="domcontentloaded") if False else None
        except Exception as e:  # невидимые ссылки пропускаем
            print(f"    tel #{i}: пропуск ({str(e).splitlines()[0][:60]})")
    pg.wait_for_timeout(2500)
    return n, clicked


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--gtm-id", default=None, help="публичный id контейнера GTM-XXXX (по умолчанию из API)")
    ap.add_argument("--grant", nargs="+", default=["analytics_storage"], help="типы согласия или none")
    ap.add_argument("--events", nargs="*", default=[], help="показывать только эти события")
    ap.add_argument("--no-mobile", action="store_true")
    ap.add_argument("--wait", type=int, default=8)
    ap.add_argument("--keep-env", action="store_true")
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{a.account}/containers/{a.container}"
    gtm_id = a.gtm_id or call(s, "GET", cont)["publicId"]
    env = call(s, "POST", cont + "/environments", json={
        "accountId": a.account, "containerId": a.container,
        "name": f"claude-test-v{a.version}", "type": "user", "containerVersionId": a.version,
        "description": "временная среда для проверки в браузере, удаляется скриптом"})
    env_id, code = env["environmentId"], env["authorizationCode"]
    print(f"среда {env['name']} id {env_id} на версии {a.version}; контейнер {gtm_id}; согласие: {a.grant}")
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for name, kw in (("desktop", dict(viewport={"width": 1440, "height": 900})),
                             ("mobile", dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True))):
                if name == "mobile" and a.no_mobile:
                    continue
                ctx = br.new_context(locale="pl-PL", **kw)
                pg = ctx.new_page()
                hits = []

                def route(r):
                    u = r.request.url
                    host = urlparse(u).netloc
                    if "/g/collect" in u or "/j/collect" in u:
                        hits.extend(parse_collect(r.request))
                        return r.abort()
                    if "googletagmanager.com/gtm.js" in u and f"id={gtm_id}" in u:
                        return r.continue_(url=f"{u}&gtm_preview=env-{env_id}&gtm_auth={code}&gtm_cookies_win=x")
                    if any(k in host for k in ALLOWED):
                        return r.continue_()
                    return r.abort()
                ctx.route("**/*", route)
                pg.goto(a.url, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(3000)
                n, clicked = run_scenario(pg, a.grant, a.wait)
                print(f"\n=== {name}: ссылок tel: {n}, кликов {clicked}; запросов GA4 перехвачено событий: {len(hits)}")
                cnt, params = Counter(), defaultdict(Counter)
                for h in hits:
                    en = h.get("en", "?")
                    if a.events and en not in a.events:
                        continue
                    cnt[en] += 1
                    for k in ("ep.block_name", "epn.block_seconds", "ep.click_place"):
                        if k in h:
                            params[en][f"{k.split('.', 1)[1]}={h[k]}"] += 1
                for en, c in cnt.most_common():
                    print(f"  {en}: {c}")
                    for pv, pc in sorted(params[en].items()):
                        print(f"      {pv} ×{pc}")
                ctx.close()
            br.close()
    finally:
        if not a.keep_env:
            call(s, "DELETE", f"{cont}/environments/{env_id}")
            print(f"\nсреда {env_id} удалена")


if __name__ == "__main__":
    main()
