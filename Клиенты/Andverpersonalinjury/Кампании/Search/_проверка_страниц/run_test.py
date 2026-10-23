import sys, json, pathlib
from playwright.sync_api import sync_playwright
src = pathlib.Path(r"D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search\settlement_quiz_t123.html").read_text(encoding="utf-8")
html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>body{margin:0;background:#0d151b}</style></head><body>""" + src + """
<div style="background:#f6f2ea;padding:30px 16px"><form id="f1" class="t-form"><input type="text" name="name" placeholder="First name"><input type="tel" name="phone" placeholder="Phone"><button>Send</button></form></div>
</body></html>"""
out = pathlib.Path(__file__).parent
(out/"page.html").write_text(html, encoding="utf-8")

Q1={'head':0,'spine':1,'fracture':2,'soft':3,'other':4}
Q2={'hospital':0,'ongoing':1,'surgery':2,'none':3,'diagnosing':4}
Q3={'none':0,'days':1,'weeks':2,'cant':3}
Q4={'other':0,'shared':1,'unsure':2}
Q5={'none':0,'statement':1,'offer':2,'signed':3}
P={'offer':'An offer is on the table','statement':'They asked for a statement','signed':'You already signed','nocontact':'The insurer may call soon','notreat':"Treatment hasn't started"}
T={'serious':'serious injury situation','moderate':'moderate injury situation','developing':'still developing'}
cases=[
 ('head','ongoing','none','other','none','serious','nocontact'),
 ('soft','ongoing','days','other','none','moderate','nocontact'),
 ('spine','ongoing','none','other','offer','serious','offer'),
 ('spine','hospital','weeks','shared','statement','serious','statement'),
 ('soft','hospital','none','unsure','none','moderate','nocontact'),
 ('fracture','surgery','weeks','other','signed','serious','signed'),
 ('soft','surgery','none','other','none','serious','nocontact'),
 ('soft','ongoing','cant','other','none','serious','nocontact'),
 ('soft','none','none','other','none','developing','notreat'),
 ('head','none','none','other','offer','developing','offer'),
 ('other','diagnosing','days','shared','statement','developing','statement'),
 ('other','diagnosing','none','unsure','none','developing','nocontact'),
]
fails=[]
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(viewport={'width':390,'height':844},device_scale_factor=2,is_mobile=True,has_touch=True)
    pg=ctx.new_page()
    errs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)))
    pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None)
    pg.goto((out/"page.html").as_uri()); pg.wait_for_timeout(1500)
    pg.screenshot(path=str(out/'m_q1.png'))
    for c in cases:
        pg.goto((out/"page.html").as_uri())
        for qi,(val,m) in enumerate(zip(c[:5],[Q1,Q2,Q3,Q4,Q5])):
            pg.locator('.ldvq__opt').nth(m[val]).click(); pg.wait_for_timeout(260)
        txt=pg.locator('#ldvq-card').inner_text()
        ok_t=T[c[5]] in txt; ok_p=P[c[6]] in txt
        if not(ok_t and ok_p): fails.append((c,ok_t,ok_p,txt[:200]))
        # others must be absent
        for k,v in P.items():
            if k!=c[6] and v in txt and not (k=='nocontact' and False): fails.append((c,'extra line',k))
    # detailed run
    pg.goto((out/"page.html").as_uri())
    for qi,(val,m) in enumerate(zip(('spine','ongoing','weeks','other','offer'),[Q1,Q2,Q3,Q4,Q5])):
        if qi==2:
            pg.screenshot(path=str(out/'m_q3.png'))
            # back test
            pg.get_by_text('Back').click(); pg.wait_for_timeout(100)
            assert 'question 2 of 5' in pg.inner_text('#ldvq-card').lower(), 'back failed'
            assert pg.locator('.ldvq__opt.is-picked').count()==1, 'picked state lost'
            pg.locator('.ldvq__opt').nth(1).click(); pg.wait_for_timeout(260)
        pg.locator('.ldvq__opt').nth(m[val]).click(); pg.wait_for_timeout(260)
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(out/'m_result_top.png'))
    pg.locator('#ldvq-card').screenshot(path=str(out/'m_result_card.png'))
    dl=pg.evaluate('window.dataLayer')
    print('dataLayer:',json.dumps(dl,ensure_ascii=False))
    hid=pg.evaluate("Array.from(document.querySelectorAll('#f1 input[type=hidden]')).map(i=>i.name+'='+i.value)")
    print('hidden fields:',hid)
    print('tel link:',pg.locator('#ldvq-card a.ldvq-phone').get_attribute('href'),'| form anchor:',pg.locator('#ldv-form').count())
    pg.locator('#ldvq-card .ldvq__btn--primary').click(); pg.wait_for_timeout(500)
    print('after cta hidden cta_source:',pg.evaluate("document.querySelector('#f1 input[name=cta_source]').value"))
    pg.get_by_text('Change my answers').click(); pg.wait_for_timeout(300)
    print('restart ->', 'question 1 of 5' in pg.inner_text('#ldvq-card').lower())
    # desktop
    ctx2=b.new_context(viewport={'width':1366,'height':900}); d=ctx2.new_page()
    d.goto((out/"page.html").as_uri()); d.wait_for_timeout(1200); d.screenshot(path=str(out/'d_q1.png'))
    for val,m in zip(('spine','ongoing','weeks','other','offer'),[Q1,Q2,Q3,Q4,Q5]):
        d.locator('.ldvq__opt').nth(m[val]).click(); d.wait_for_timeout(260)
    d.wait_for_timeout(600); d.locator('#ldvq-card').screenshot(path=str(out/'d_result_card.png'))
    # overflow check on mobile
    ow=pg.evaluate("document.documentElement.scrollWidth>document.documentElement.clientWidth")
    print('horizontal overflow mobile:',ow)
    b.close()
print('page errors:',errs)
print('FAILS:',json.dumps(fails,ensure_ascii=False,indent=1) if fails else 'none',' | cases',len(cases))
