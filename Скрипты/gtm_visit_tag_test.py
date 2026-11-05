#!/usr/bin/env python
# coding: utf-8
"""Тест тега «Визит - rngst и клик в Supabase» на версии контейнера ДО публикации (2026-11-05). Ничего не отправляет в аналитику и Supabase.

Как: временная среда GTM на указанной версии (`gtm_preview`), Playwright открывает сайт со ссылкой, где есть gclid; запросы GA/Ads/Facebook/Яндекс
перехватываются (204), запросы в Supabase перехватываются и ПЕЧАТАЮТСЯ (201), Ringostat и сайт идут как обычно (иначе не появится cookie `rngst`).
Сценарии баннера: none (без выбора), all, essential. Проверяется: ушла ли запись в profimet_visits, совпал ли `rngst_client_id` с cookie `rngst`,
что в `consent` и `mark_source`; визит без клика (адрес без gclid) не должен писаться; при «all» повторный заход той же ссылкой даёт consent=granted.

    PYTHONUTF8=1 python gtm_visit_tag_test.py --version 95 [--url https://mocnaszklarnia.pl]
"""
import argparse
import io
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from playwright.sync_api import sync_playwright

KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.edit.containers",
          "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
          "https://www.googleapis.com/auth/tagmanager.publish"]
ACCOUNT, CONTAINER = "6003760261", "44158621"
QUERY = "utm_source=google&utm_medium=cpc&utm_campaign=pmax01_visit_test&utm_content=visit_test&gclid=TESTVISITGCLID_AbC123"
COOKIE_JS = "(()=>{const m=document.cookie.match(/(?:^|; )rngst=([^;]*)/);if(!m)return null;try{return JSON.parse(decodeURIComponent(m[1])).clientId}catch(e){return 'ERR'}})()"


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:400]}")
    return r.json() if r.text else {}


def scenario(br, site, gtm_id, env_id, code, scen):
    ctx = br.new_context(locale="pl-PL", viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    visits, leads, other = [], [], []

    def route(r):
        u = r.request.url
        low = u.lower()
        host = urlparse(u).netloc
        if "supabase.co" in host:
            body = r.request.post_data or ""
            (visits if "profimet_visits" in u else leads).append((r.request.method, body))
            return r.fulfill(status=201, body="")
        if "googletagmanager.com/gtm.js" in u and f"id={gtm_id}" in u:
            return r.continue_(url=f"{u}&gtm_preview=env-{env_id}&gtm_auth={code}&gtm_cookies_win=x")
        if any(k in low for k in ("/g/collect", "google-analytics", "doubleclick", "googleadservices", "/pagead/", "facebook", "fbevents", "mc.yandex")):
            other.append(host)
            return r.fulfill(status=204, body="")
        return r.continue_()

    ctx.route("**/*", route)
    out = {"сценарий": scen}
    pg.goto(f"{site}/?{QUERY}", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    out["1 cookie rngst.clientId"] = pg.evaluate(COOKIE_JS)
    out["1 записей в profimet_visits"] = [json.loads(b) for _, b in visits]
    visits.clear()
    if scen == "all":
        pg.get_by_text("Zaakceptuj wszystkie").first.click()
    elif scen == "essential":
        pg.get_by_text("Zaakceptuj tylko niezbędne").first.click()
    if scen != "none":
        pg.wait_for_timeout(3000)
        out["2 после выбора: новых записей"] = len(visits)
        visits.clear()
    pg.goto(f"{site}/ofirmie", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(6000)
    out["3 другая страница без gclid в адресе: записи"] = [json.loads(b) for _, b in visits]
    visits.clear()
    if scen == "all":
        pg.goto(f"{site}/?{QUERY}", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(7000)
        out["4 повторный заход по той же ссылке (согласие уже дано)"] = [json.loads(b) for _, b in visits]
        visits.clear()
    pg.goto(f"{site}/?utm_source=google&utm_medium=cpc&utm_campaign=x_no_click", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(6000)
    out["5 заход с utm, но без клика Google: записей"] = len(visits)
    out["заявок в profimet_leads из-за теста (должно быть 0)"] = len(leads)
    ctx.close()
    return out


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--url", default="https://mocnaszklarnia.pl")
    ap.add_argument("--scen", nargs="*", default=["none", "all", "essential"])
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{ACCOUNT}/containers/{CONTAINER}"
    gtm_id = call(s, "GET", cont)["publicId"]
    env = call(s, "POST", cont + "/environments", json={
        "accountId": ACCOUNT, "containerId": CONTAINER, "name": f"claude-visit-test-v{a.version}", "type": "user",
        "containerVersionId": a.version, "description": "временная среда для проверки тега визитов, удаляется скриптом"})
    env_id, code = env["environmentId"], env["authorizationCode"]
    print(f"среда {env['name']} id {env_id} на версии {a.version}; контейнер {gtm_id}")
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for scen in a.scen:
                try:
                    r = scenario(br, a.url.rstrip("/"), gtm_id, env_id, code, scen)
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
