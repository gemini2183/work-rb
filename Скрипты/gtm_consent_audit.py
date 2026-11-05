# Аудит согласий на cookie: сценарий выбора в баннере -> состояние Consent Mode, localStorage.rb_utm,
# cookie баннера, события dataLayer, какие внешние запросы пытались уйти (GA/Ads/Facebook) и что ушло бы в Supabase.
# Только чтение: все отправки перехватываются (GA/Ads/FB -> 204, Supabase -> 201, тело печатается), форма не отправляется.
# Запуск: PYTHONUTF8=1 python -I gtm_consent_audit.py https://mocnaszklarnia.pl [сценарий ...]
# Сценарии: none | all | essential | analytics | marketing | both_off   (без аргумента — все).
# Банер ProfiMet (Tilda, самописный): кнопки «Zaakceptuj wszystkie» / «Zaakceptuj tylko niezbędne» / «Dostosuj zgody».
import sys, io, json, re
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
site = sys.argv[1].rstrip("/")
SCEN = sys.argv[2:] or ["none", "all", "essential", "analytics", "marketing", "both_off"]
UTM = "utm_source=test&utm_medium=cpc&utm_campaign=audit&utm_content=audit_c&gclid=TESTCLID&fbclid=TESTFB&gbraid=TESTGB&wbraid=TESTWB"

STATE = r"""(()=>{const c={};try{const e=window.google_tag_data&&google_tag_data.ics&&google_tag_data.ics.entries;
if(e)for(const k in e){if(/^(ad_|analytics)/.test(k))c[k]=e[k].default+'/'+e[k].update}}catch(x){c.err=String(x)}
let ls=null;try{ls=localStorage.getItem('rb_utm')}catch(x){ls='ERR'}
const ck=n=>{const m=document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'));return m?m[1]:null};
const ev=(window.dataLayer||[]).map(x=>{try{return x.event&&!/^gtm\./.test(x.event)?x.event+(x.setReactionType?'('+x.setReactionType+')':''):(Array.prototype.slice.call(x)[0]==='consent'?'consent:'+Array.prototype.slice.call(x)[1]+':'+JSON.stringify(Array.prototype.slice.call(x)[2]).slice(0,110):null)}catch(e){return null}}).filter(Boolean);
return JSON.stringify({consent:c,rb_utm:ls,setTypeAccept:ck('setTypeAccept'),acceptBanner:ck('acceptBanner'),ls_keys:Object.keys(localStorage),events:ev})})()"""


def run(scen):
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(locale="pl-PL", viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        sent, supa = [], []

        def route(r):
            u = r.request.url
            low = u.lower()
            if "supabase.co" in low:
                if r.request.method == "POST":
                    supa.append(r.request.post_data or "")
                return r.fulfill(status=201, body="")
            kind = None
            if "/g/collect" in low or "google-analytics" in low:
                kind = "GA4"
                m = re.search(r"[?&]en=([^&]+)", u)
                if m: kind += ":" + m.group(1)
            elif "doubleclick" in low or "googleadservices" in low or "/pagead/" in low:
                kind = "GoogleAds"
            elif "facebook" in low or "fbevents" in low:
                kind = "Facebook"
            elif "mc.yandex" in low:
                kind = "Metrika"
            if kind:
                sent.append(kind)
                return r.fulfill(status=204, body="")
            return r.continue_()

        ctx.route("**/*", route)
        out = {"сценарий": scen}
        pg.goto(site + "/?" + UTM, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        out["1 после загрузки (метки в адресе)"] = json.loads(pg.evaluate(STATE))
        out["1 запросы"] = sorted(set(sent)); sent.clear()
        if scen == "all":
            pg.get_by_text("Zaakceptuj wszystkie").first.click()
        elif scen == "essential":
            pg.get_by_text("Zaakceptuj tylko niezbędne").first.click()
        elif scen in ("analytics", "marketing", "both_off"):
            pg.get_by_text("Dostosuj zgody").first.click(); pg.wait_for_timeout(800)
            an = scen == "analytics"; ad = scen == "marketing"
            if not an: pg.evaluate("document.getElementById('analyticsSwitch').click()")
            if not ad: pg.evaluate("document.getElementById('advertisingSwitch').click()")
            pg.get_by_text("Zapisz ustawienia").first.click()
        if scen != "none":
            pg.wait_for_timeout(3500)
            out["2 после выбора"] = json.loads(pg.evaluate(STATE))
            out["2 запросы"] = sorted(set(sent)); sent.clear()
        pg.goto(site + "/ofirmie", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        out["3 другая страница, меток в адресе нет"] = json.loads(pg.evaluate(STATE))
        out["3 запросы"] = sorted(set(sent)); sent.clear()
        out["3 баннер виден"] = pg.evaluate("(()=>{const b=document.getElementById('cookieConsentContainer');return !!b&&getComputedStyle(b).display!=='none'})()")
        pg.evaluate("window.dataLayer.push({event:'submit_form'})")
        pg.wait_for_timeout(3000)
        out["4 после submit_form: тело в Supabase"] = supa[:]
        out["4 запросы"] = sorted(set(sent))
        br.close()
        return out


for s in SCEN:
    try:
        r = run(s)
    except Exception as e:
        r = {"сценарий": s, "ошибка": str(e)[:300]}
    print("=" * 70)
    print(json.dumps(r, ensure_ascii=False, indent=1))
