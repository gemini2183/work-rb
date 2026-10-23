import pathlib, json
from playwright.sync_api import sync_playwright
prev=pathlib.Path(r"D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search\settlement_page_preview.html")
out=pathlib.Path(__file__).parent
with sync_playwright() as p:
    b=p.chromium.launch()
    errs=[]
    for name,vp,mob in (('m',{'width':390,'height':844},True),('d',{'width':1366,'height':900},False)):
        c=b.new_context(viewport=vp,device_scale_factor=1,is_mobile=mob,has_touch=mob)
        pg=c.new_page(); pg.on('pageerror',lambda e:errs.append(str(e)))
        pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None)
        pg.goto(prev.as_uri()); pg.wait_for_timeout(2500)
        h=pg.evaluate('document.documentElement.scrollHeight'); ow=pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth')
        img=pg.evaluate("(()=>{const i=document.querySelector('.ldvp__atty img');return i.complete&&i.naturalWidth>0})()")
        print(name,'height',h,'overflow',ow,'attorney img loaded',img)
        pg.screenshot(path=str(out/f'{name}_full.png'),full_page=True)
        # sticky/anchors
        if mob:
            pg.screenshot(path=str(out/'m_first.png'))
            pg.locator('.ldvs__form').click(); pg.wait_for_timeout(700)
            print('after sticky click scrollY',pg.evaluate('Math.round(scrollY)'),'form A top',pg.evaluate("Math.round(document.getElementById('formA').getBoundingClientRect().top)"))
        # faq open
        pg.locator('.ldvp__faq summary').first.click(); pg.wait_for_timeout(200)
        print(name,'faq open',pg.locator('.ldvp__faq details[open]').count())
        dl=pg.evaluate('window.dataLayer'); print(name,'dl',json.dumps(dl))
    b.close()
print('errors',errs)
