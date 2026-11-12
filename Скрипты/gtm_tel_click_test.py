#!/usr/bin/env python
# coding: utf-8
"""Тест тега «Клик по номеру - rngst и клик в Supabase» на версии контейнера ДО публикации (2026-11-12). В Supabase и аналитику ничего не уходит.

Как: временная среда GTM на указанной версии (`gtm_preview`), Playwright с мобильным экраном открывает сайт по ссылке (реальный формат
utm_content PMax, gclid тестовый), ждёт подмену номера Ringostat, нажимает на ссылку `tel:`. Запросы GA/Ads/Facebook/Яндекс перехватываются (204),
запросы в Supabase перехватываются и ПЕЧАТАЮТСЯ (201), Ringostat и сайт идут как обычно (иначе не будет cookie `rngst` и подмены).
Сценарии: (1) заход с gclid, нажатие; (2) второе нажатие через 3 с (две разные строки, ts_ms разные); (3) заход без gclid и без utm, нажатие
(строка с пустым click_key); (4) заход с gclid БЕЗ нажатия — записей нет. Проверяется: поля строки, совпадение rngst_client_id с cookie,
номер в phone_href равен показанному на странице, тег 17 (клик по номеру в Ads) сработал как раньше (запрос Ads виден), записей в *_leads нет.

    PYTHONUTF8=1 python gtm_tel_click_test.py --version 23 [--url https://ekspertagro.pl] [--client EkspertAgro]
"""
import argparse
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from playwright.sync_api import sync_playwright

from gtm_tel_click_tag import CLIENTS

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]
QUERY_CLICK = ("utm_source=google&utm_medium=cpc&utm_campaign=shop_pmax&utm_content=rb_cid_24230255260_%7Cgid_%7Caid_%7Cpos_%7Cdev_m"
               "%7Cplc_youtube.com%7Cregion_id_1011430%7Ctargetid_%7Cgclid_TESTTELCLICK_AbC123&gclid=TESTTELCLICK_AbC123")
COOKIE_JS = "(()=>{const m=document.cookie.match(/(?:^|; )rngst=([^;]*)/);if(!m)return null;try{return JSON.parse(decodeURIComponent(m[1])).clientId}catch(e){return 'ERR'}})()"
TEL_JS = "Array.from(document.querySelectorAll('a[href^=\"tel:\"]')).map(a=>({href:a.getAttribute('href'),text:(a.textContent||'').trim().slice(0,40),vis:!!(a.offsetWidth||a.offsetHeight)}))"


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:400]}")
    return r.json() if r.text else {}


def scenario(br, site, gtm_id, env_id, code, table, scen):
    ctx = br.new_context(locale="pl-PL", viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                         user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
    pg = ctx.new_page()
    taps, leads, ads, other = [], [], [], []

    def route(r):
        u = r.request.url
        low = u.lower()
        host = urlparse(u).netloc
        if "supabase.co" in host:
            body = r.request.post_data or ""
            (taps if table in u else leads).append(body)
            return r.fulfill(status=201, body="")
        if "googletagmanager.com/gtm.js" in u and f"id={gtm_id}" in u:
            return r.continue_(url=f"{u}&gtm_preview=env-{env_id}&gtm_auth={code}&gtm_cookies_win=x")
        if any(k in low for k in ("googleadservices", "/pagead/", "doubleclick")):
            ads.append(u[:120])
            return r.fulfill(status=204, body="")
        if any(k in low for k in ("/g/collect", "google-analytics", "facebook", "fbevents", "mc.yandex")):
            other.append(host)
            return r.fulfill(status=204, body="")
        return r.continue_()

    ctx.route("**/*", route)
    out = {"сценарий": scen}
    qs = QUERY_CLICK if scen != "no_utm" else ""
    pg.goto(f"{site}/{('?' + qs) if qs else ''}", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    out["cookie rngst.clientId"] = pg.evaluate(COOKIE_JS)
    tel = pg.evaluate(TEL_JS)
    out["ссылки tel: на странице (после подмены)"] = tel
    if scen == "no_tap":
        out["записей без нажатия (должно быть 0)"] = len(taps)
    else:
        vis = [t for t in tel if t["vis"]] or tel
        if not vis:
            out["ошибка"] = "на странице нет ссылок tel:"
        else:
            n_taps = 2 if scen == "double" else 1
            for i in range(n_taps):
                ads_before = len(ads)
                try:
                    pg.evaluate("""(h)=>{const a=Array.from(document.querySelectorAll('a[href^="tel:"]')).find(x=>x.getAttribute('href')===h&&(x.offsetWidth||x.offsetHeight))
                        ||Array.from(document.querySelectorAll('a[href^="tel:"]')).find(x=>x.getAttribute('href')===h); a.addEventListener('click',e=>e.preventDefault(),{once:true}); a.click();}""", vis[0]["href"])
                except Exception as e:
                    out["ошибка нажатия"] = str(e)[:200]
                pg.wait_for_timeout(3000)
                out[f"нажатие {i + 1}: запросов Ads (тег 17)"] = len(ads) - ads_before
            rows = [json.loads(b) for b in taps]
            out["строк в таблице нажатий"] = len(rows)
            out["строки"] = rows
            if rows:
                out["проверки"] = {
                    "rngst_client_id = cookie": all(r["rngst_client_id"] == out["cookie rngst.clientId"] for r in rows),
                    "phone_href = показанный номер": all(r["phone_href"] == vis[0]["href"] for r in rows),
                    "ts_ms разные": len({r["ts_ms"] for r in rows}) == len(rows),
                    "gclid/utm из адреса": [r["mark_source"] for r in rows],
                }
    out["записей в *_leads из-за теста (должно быть 0)"] = len(leads)
    ctx.close()
    return out


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--client", default="EkspertAgro", choices=list(CLIENTS))
    ap.add_argument("--url", default="https://ekspertagro.pl")
    ap.add_argument("--scen", nargs="*", default=["single", "double", "no_utm", "no_tap"])
    a = ap.parse_args()
    c = CLIENTS[a.client]
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{c['account']}/containers/{c['container']}"
    gtm_id = call(s, "GET", cont)["publicId"]
    env = call(s, "POST", cont + "/environments", json={
        "accountId": c["account"], "containerId": c["container"], "name": f"test-telclick-v{a.version}", "type": "user",
        "containerVersionId": a.version, "description": "временная среда для проверки тега клика по номеру, удаляется скриптом"})
    env_id, code = env["environmentId"], env["authorizationCode"]
    print(f"среда {env['name']} id {env_id} на версии {a.version}; контейнер {gtm_id}")
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for scen in a.scen:
                try:
                    r = scenario(br, a.url.rstrip("/"), gtm_id, env_id, code, c["table"], scen)
                except Exception as e:
                    r = {"сценарий": scen, "ошибка": str(e)[:300]}
                print("=" * 70)
                print(json.dumps(r, ensure_ascii=False, indent=1))
            br.close()
    finally:
        call(s, "DELETE", f"{cont}/environments/{env_id}")
        print(f"\nсреда {env_id} удалена")


if __name__ == "__main__":
    main()
