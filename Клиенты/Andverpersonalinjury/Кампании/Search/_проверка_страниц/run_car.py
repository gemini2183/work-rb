import pathlib, json
from playwright.sync_api import sync_playwright
prev=pathlib.Path(r"D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Tilda_страница_Car\0_maket_prosmotr.html")
out=pathlib.Path(__file__).parent
Q1={'head':0,'spine':1,'fracture':2,'soft':3,'other':4};Q2={'hospital':0,'ongoing':1,'surgery':2,'none':3,'diagnosing':4}
Q3={'none':0,'days':1,'weeks':2,'cant':3};Q4={'other':0,'shared':1,'unsure':2};Q5={'none':0,'statement':1,'offer':2,'signed':3}
with sync_playwright() as p:
    b=p.chromium.launch(); errs=[]
    for name,vp,mob in (('cm',{'width':390,'height':844},True),('cd',{'width':1366,'height':900},False)):
        c=b.new_context(viewport=vp,device_scale_factor=1,is_mobile=mob,has_touch=mob); pg=c.new_page()
        pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None)
        pg.goto(prev.as_uri()); pg.wait_for_timeout(2000)
        h=pg.evaluate('document.documentElement.scrollHeight'); ow=pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth')
        print(name,'height',h,'overflow',ow,'h1',pg.locator('h1').count(),'h2',pg.locator('h2').count())
        # форма A на первом экране?
        top=pg.evaluate("document.getElementById('formA').getBoundingClientRect()"); 
        print(name,'форма A: top',round(top['top']),'bottom',round(top['bottom']),'экран',vp['height'])
        pg.screenshot(path=str(out/f'{name}_first.png'))
        pg.screenshot(path=str(out/f'{name}_full.png'),full_page=True)
        # квиз
        for val,m in zip(('spine','ongoing','weeks','other','offer'),[Q1,Q2,Q3,Q4,Q5]):
            pg.locator('#ldvq-card .ldvq__opt').nth(m[val]).click(); pg.wait_for_timeout(260)
        txt=pg.locator('#ldvq-card').inner_text()
        print(name,'квиз результат:', 'serious injury situation' in txt, 'An offer is on the table' in txt)
        print(name,'кнопка к форме B:', pg.locator('#ldvq-card .ldvq__btn--primary').get_attribute('href'))
        hid=pg.evaluate("Array.from(document.querySelectorAll('#formA input[type=hidden],#formB input[type=hidden]')).map(i=>i.closest('form').id+':'+i.name).slice(0,16)")
        print(name,'hidden:',len(hid), [x for x in hid if 'quiz_summary' in x])
        print(name,'headings:',pg.evaluate("Array.from(document.querySelectorAll('h1,h2')).map(h=>h.tagName+' '+h.innerText.replace(/\s+/g,' ').slice(0,60))"))
    b.close()
print('errors',errs)
