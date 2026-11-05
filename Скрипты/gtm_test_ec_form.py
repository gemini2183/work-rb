#!/usr/bin/env python
# coding: utf-8
"""Проверить расширенные конверсии (телефон в теге конверсии Google Ads) на версии контейнера GTM ДО публикации.
Ничего не уходит наружу: временная среда GTM (удаляется), ответ Tilda на отправку формы подменяется («успех» без отправки лида
клиенту), запросы конверсий Google Ads и GA4 перехватываются и разбираются локально.

Сценарий: открыть страницу, дать согласие, ввести тестовый телефон в форму, нажать отправку (или, если Tilda не сработала,
отправить событие `submit_formNNN` в dataLayer), напечатать: что стало с полем после «успешной» отправки, значение переменной
телефона, и все перехваченные запросы конверсий с параметрами em / pn / ec_mode (хэш пользовательских данных).

    python gtm_test_ec_form.py --account 6240500366 --container 190366786 --version 14 --url https://jewelryfastsale.com/ \
        --form form772276664 --phone 3105551234
"""
import argparse
import io
import sys
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
ALLOWED = ("tildacdn", "tilda.ws", "tilda.cc", "googletagmanager.com", "jewelryfastsale.com", "fonts.g", "fonts.googleapis")
CONV_MARKERS = ("pagead/conversion", "pagead/1p-conversion", "ccm/conversion", "ccm/collect", "/rmkt/collect")


def call(s, method, path, **kw):
    r = s.request(method, BASE + path, **kw)
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"GTM API {method} {path}: {r.status_code} {r.text[:400]}")
    return r.json() if r.text else {}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--form", required=True, help="id формы Tilda, например form772276664")
    ap.add_argument("--phone", default="3105551234")
    ap.add_argument("--name", default="Test Test")
    ap.add_argument("--js-fill", action="store_true", help="не печатать мышью и не жать кнопку (форма скрыта, например виджет): значение вводится JS с событием input")
    ap.add_argument("--clear", action="store_true", help="перед событием отправки очистить поля телефона (проверка запасного номера из кэша при вводе)")
    ap.add_argument("--no-mobile", action="store_true")
    ap.add_argument("--keep-env", action="store_true")
    a = ap.parse_args()
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    cont = f"accounts/{a.account}/containers/{a.container}"
    gtm_id = call(s, "GET", cont)["publicId"]
    env = call(s, "POST", cont + "/environments", json={
        "accountId": a.account, "containerId": a.container, "name": f"claude-ec-v{a.version}", "type": "user",
        "containerVersionId": a.version, "description": "временная среда проверки EC, удаляется скриптом"})
    env_id, code = env["environmentId"], env["authorizationCode"]
    print(f"среда {env_id} на версии {a.version}; контейнер {gtm_id}")
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(locale="en-US", viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            conv, tilda_posts = [], []

            def route(r):
                u = r.request.url
                host = urlparse(u).netloc
                if "/g/collect" in u or "/j/collect" in u:
                    return r.fulfill(status=204, body="")
                if any(m in u for m in CONV_MARKERS):
                    conv.append(dict(parse_qsl(urlsplit(u).query)) | {"_url": u.split("?")[0], "_post": (r.request.post_data or "")[:300]})
                    return r.fulfill(status=204, body="")
                if "/procces" in u or ("tildacdn" in host and r.request.method == "POST"):
                    tilda_posts.append((u, (r.request.post_data or "")[:300]))
                    return r.fulfill(status=200, content_type="application/json",
                                     body='{"results":["1:1:0"]}')
                if "googletagmanager.com/gtm.js" in u and f"id={gtm_id}" in u:
                    return r.continue_(url=f"{u}&gtm_preview=env-{env_id}&gtm_auth={code}&gtm_cookies_win=x")
                if any(k in host for k in ALLOWED):
                    return r.continue_()
                return r.abort()
            ctx.route("**/*", route)
            pg.goto(a.url, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(4000)
            pg.evaluate("window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)};"
                        "gtag('consent','update',{ad_storage:'granted',ad_user_data:'granted',ad_personalization:'granted',analytics_storage:'granted'})")
            pg.wait_for_timeout(1500)
            form = pg.locator(f"#{a.form}")
            fields_js = f"[...document.querySelectorAll('#{a.form} input')].filter(i=>i.type=='tel'||i.name=='Phone').map(i=>i.name+':'+i.type+'='+i.value)"
            if a.js_fill:
                pg.evaluate("""([f,ph])=>{const t=document.querySelector('#'+f+' input[type=tel]');t.value=ph;
                    t.dispatchEvent(new Event('input',{bubbles:true}));t.dispatchEvent(new Event('change',{bubbles:true}))}""", [a.form, a.phone])
                evs = []
                print("поля (JS-ввод):", pg.evaluate(fields_js))
            else:
                tel = form.locator('input[type="tel"]').first
                tel.scroll_into_view_if_needed(timeout=8000)
                tel.click()
                tel.press_sequentially(a.phone, delay=60)
                nm = form.locator('input[name="name"]')
                if nm.count():
                    nm.first.fill(a.name)
                print("поля до отправки:", pg.evaluate(fields_js))
                pg.evaluate("window.__evs=[];(window.dataLayer=window.dataLayer||[]);var _p=window.dataLayer.push;window.dataLayer.push=function(){for(var i=0;i<arguments.length;i++){var x=arguments[i];if(x&&x.event)window.__evs.push(x.event)}return _p.apply(this,arguments)}")
                form.locator('button[type="submit"], .t-submit').first.click()
                pg.wait_for_timeout(6000)
                try:
                    evs = pg.evaluate("window.__evs")
                    if evs is None:
                        raise ValueError("страница перешла")
                except Exception:
                    evs = ["(страница перешла — Tilda сделала редирект на " + pg.url + ")", "submit_form"]
                print("события dataLayer после нажатия:", evs)
                print("запросов Tilda перехвачено:", len(tilda_posts), [t[0][:80] for t in tilda_posts])
                try:
                    print("поля после отправки:", pg.evaluate(fields_js))
                except Exception:
                    print("поля после отправки: страница уже перешла на", pg.url)
            if a.clear:
                pg.evaluate(f"document.querySelectorAll('#{a.form} input').forEach(i=>{{if(i.type=='tel'||i.name=='Phone')i.value=''}})")
                print("поля очищены:", pg.evaluate(fields_js))
            try:
                print("кэш номера (window.__rbPhoneEc):", pg.evaluate("window.__rbPhoneEc"))
            except Exception:
                pass
            if not any(e.startswith("submit_form") for e in evs):
                num = a.form.replace("form", "")
                print(f"Tilda событие не отправила — шлю submit_form{num} вручную (поле уже очищено или нет)")
                pg.evaluate(f"window.dataLayer.push({{event:'submit_form{num}'}})")
                pg.wait_for_timeout(5000)
            print(f"\nперехвачено запросов конверсий: {len(conv)}")
            for c in conv:
                keys = {k: v for k, v in c.items() if k in ("em", "pn", "ec_mode", "label", "tiba", "gtm", "ecsid", "_url", "ec_uid", "tid", "ph")}
                print("  ", keys)
            ctx.close()
            br.close()
    finally:
        if not a.keep_env:
            call(s, "DELETE", f"{cont}/environments/{env_id}")
            print(f"\nсреда {env_id} удалена")


if __name__ == "__main__":
    main()
