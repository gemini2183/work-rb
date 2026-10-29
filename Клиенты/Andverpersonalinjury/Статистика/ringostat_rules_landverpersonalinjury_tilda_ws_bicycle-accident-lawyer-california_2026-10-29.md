# Правила подмены Ringostat для https://landverpersonalinjury.tilda.ws/bicycle-accident-lawyer-california
Дата: 2026-10-29 16:08. Только чтение.
Скрипт Ringostat: https://script.ringostat.com/v4/4c/4c28b51a7504aa7cdf1789ee697a219f17ccbd8b.js; действующих правил проекта: 28
Ссылок tel: 8; основной номер на странице tel:+18444529465
Уже покрыто действующими правилами: 0 из 8

## План: 5 правил(а) на 8 непокрытых ссылок
1. bicycle 1 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-cta']
   XPath: //a[@data-vb-cta="header_call"]
   Маска: <small>Free consultation · 24/7</small><span>(###) ###-####</span>
   Ссылки: [{'data-vb-cta': 'header_call'}]
2. bicycle 2 | совпадений 4 из 4 OK | признак: ['data-атрибут data-vb-cta']
   XPath: //a[@data-vb-cta="fee_call" or @data-vb-cta="final_call" or @data-vb-cta="hero_call" or @data-vb-cta="how_call"]
   Маска: <span class="t-btnflex__text">Call (###) ###-#### · 24/7</span>
   Ссылки: [{'data-vb-cta': 'hero_call'}, {'data-vb-cta': 'how_call'}, {'data-vb-cta': 'fee_call'}, {'data-vb-cta': 'final_call'}]
3. bicycle 3 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-cta']
   XPath: //a[@data-vb-cta="sticky_call"]
   Маска: Call now · 24/7<span style="display:none;">+###########</span>
   Ссылки: [{'data-vb-cta': 'sticky_call'}]  (номера в тексте нет: добавлен скрытый span)
4. bicycle 4 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-cta']
   XPath: //a[@data-vb-cta="attorney_call"]
   Маска: <span class="t-btnflex__text">Call (###) ###-####</span>
   Ссылки: [{'data-vb-cta': 'attorney_call'}]
5. bicycle 5 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-cta']
   XPath: //a[@data-vb-cta="footer_call"]
   Маска: (###) ###-####
   Ссылки: [{'data-vb-cta': 'footer_call'}]

Итого покрыто: 8 из 8 ссылок tel: — ВСЕ
Не охвачено по построению: ссылки, создаваемые скриптом страницы после загрузки (кнопки результата квиза и т.п.), номер картинкой, номер без ссылки tel:.

## JS для консоли страницы «XPaths» проекта в Ringostat (после «да»; затем «Применить настройки»)
```js
(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const set=(n,v)=>{const e=document.querySelector('[name="'+n+'"]');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
const rules=[{"name": "bicycle 1", "xpath": "//a[@data-vb-cta=\"header_call\"]", "mask": "<small>Free consultation · 24/7</small><span>(###) ###-####</span>", "geo": "1"}, {"name": "bicycle 2", "xpath": "//a[@data-vb-cta=\"fee_call\" or @data-vb-cta=\"final_call\" or @data-vb-cta=\"hero_call\" or @data-vb-cta=\"how_call\"]", "mask": "<span class=\"t-btnflex__text\">Call (###) ###-#### · 24/7</span>", "geo": "1"}, {"name": "bicycle 3", "xpath": "//a[@data-vb-cta=\"sticky_call\"]", "mask": "Call now · 24/7<span style=\"display:none;\">+###########</span>", "geo": "1"}, {"name": "bicycle 4", "xpath": "//a[@data-vb-cta=\"attorney_call\"]", "mask": "<span class=\"t-btnflex__text\">Call (###) ###-####</span>", "geo": "1"}, {"name": "bicycle 5", "xpath": "//a[@data-vb-cta=\"footer_call\"]", "mask": "(###) ###-####", "geo": "1"}];
for(const r of rules){[...document.querySelectorAll('button')].find(e=>/Добавить XPath/.test(e.textContent)).click();await sleep(1500);
set('data[Xpath][type]','manual');set('data[Xpath][text]',r.xpath);set('data[Xpath][name]',r.name);set('data[Xpath][mask]',r.mask);set('data[Xpath][geo_group]',r.geo);
[...document.querySelectorAll('.modal button[type=submit]')].filter(b=>b.textContent.trim()==='Сохранить').pop().click();await sleep(3500);}
return document.querySelectorAll('table tbody tr').length;})()
```