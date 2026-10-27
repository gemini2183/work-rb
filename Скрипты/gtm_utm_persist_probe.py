# Разовая диагностика: пишет ли живой GTM тег «UTM - сохранить в браузере» в localStorage.rb_utm. Отправки в GA/Supabase перехватываются.
import sys, io, json
from playwright.sync_api import sync_playwright
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
site = sys.argv[1]; scen = sys.argv[2]
URL = site + "/?utm_source=test&utm_medium=cpc&utm_campaign=probe&gclid=TESTCLID"
STATE = """(()=>{const o={};try{const e=window.google_tag_data&&google_tag_data.ics&&google_tag_data.ics.entries;if(e)for(const k in e){o[k]=e[k].default+'/'+e[k].update}}catch(x){o.err=String(x)}
let ls=null;try{ls=localStorage.getItem('rb_utm')}catch(x){ls='ERR '+x}
let dl=(window.dataLayer||[]).map(x=>{try{return Array.prototype.slice.call(x).join(':').slice(0,60)}catch(e){return String(x).slice(0,60)}}).filter(s=>/consent|gtm\.(js|load|dom)|cookie/i.test(s)).slice(0,12);
return JSON.stringify({consent:o,rb_utm:ls,dl:dl,cookies:document.cookie.slice(0,200)})})()"""
with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(locale="pl-PL", viewport={"width":1440,"height":900}); pg = ctx.new_page()
    gtmreq=[]
    def route(r):
        u=r.request.url
        if "/g/collect" in u or "/j/collect" in u or "mc.yandex" in u or "doubleclick" in u or "googleadservices" in u or "facebook" in u or "google-analytics" in u: return r.fulfill(status=204, body="")
        if "supabase.co" in u: return r.fulfill(status=201, body="")
        if "googletagmanager.com/gtm.js" in u: gtmreq.append(u)
        return r.continue_()
    ctx.route("**/*", route)
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(5000)
    print("1 после загрузки:", pg.evaluate(STATE))
    if scen == "update":   # как в gtm_test_version: gtag consent update после загрузки
        pg.evaluate("window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)};gtag('consent','update',{ad_storage:'granted',analytics_storage:'granted',ad_user_data:'granted',ad_personalization:'granted'})")
        pg.wait_for_timeout(3000); print("2 после consent update:", pg.evaluate(STATE))
        pg.goto(site + "/ofirmie", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(4000)
        print("3 после перехода на /ofirmie:", pg.evaluate(STATE))
    if scen == "banner":
        print("баннер:", pg.evaluate("(()=>{const b=document.getElementById('cookieConsentContainer');return b?b.innerText.slice(0,300)+' | кнопки: '+[...b.querySelectorAll('button,a')].map(x=>x.innerText.trim()).join(' / '):'нет баннера'})()"))
    if scen == "accept":
        pg.get_by_text("Zaakceptuj wszystkie").first.click(); pg.wait_for_timeout(3500)
        print("2 после клика «принять все» на стартовой:", pg.evaluate(STATE))
        pg.goto(site + "/ofirmie", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(4000)
        print("3 после перехода на /ofirmie (без меток в адресе):", pg.evaluate(STATE))
        print("баннер виден на /ofirmie:", pg.evaluate("!!document.getElementById('cookieConsentContainer')"))
    if scen == "accept2":  # принял на второй странице, метки были только на первой
        pg.goto(site + "/ofirmie", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(3000)
        pg.get_by_text("Zaakceptuj wszystkie").first.click(); pg.wait_for_timeout(3500)
        print("2 принял на 2-й странице:", pg.evaluate(STATE))
        pg.goto(site + "/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(4000)
        print("3 ещё одна страница после принятия:", pg.evaluate(STATE))
    if scen == "returning":  # согласился раньше, потом заходит по рекламной ссылке с метками
        pg.get_by_text("Zaakceptuj wszystkie").first.click(); pg.wait_for_timeout(3000)
        pg.evaluate("localStorage.removeItem('rb_utm')")
        pg.goto(site + "/ofirmie", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(2000)
        pg.goto(URL.replace("/?", "/ofirmie?"), wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(5000)
        print("2 вернулся с метками, согласие уже сохранено:", pg.evaluate(STATE))
    if scen == "events":
        DL="JSON.stringify((window.dataLayer||[]).map(x=>{try{return x.event?('EVENT '+x.event):Array.prototype.slice.call(x).map(y=>typeof y==='object'?JSON.stringify(y).slice(0,120):y).join(':')}catch(e){return '?'}}))"
        print("dataLayer до клика:", pg.evaluate(DL))
        pg.get_by_text("Zaakceptuj wszystkie").first.click(); pg.wait_for_timeout(3000)
        print("dataLayer после клика:", pg.evaluate(DL))
    print("gtm.js запросы:", [g[:120] for g in gtmreq])
    br.close()
