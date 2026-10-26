# Правила подмены Ringostat для https://landverpersonalinjury.tilda.ws/california-car-accident-lawyer
Дата: 2026-10-26 10:05. Только чтение.
Скрипт Ringostat: https://script.ringostat.com/v4/4c/4c28b51a7504aa7cdf1789ee697a219f17ccbd8b.js; действующих правил проекта: 23
Ссылок tel: 8; основной номер на странице tel:+18444529465
  действующее правило #18 (//a[@data-ldv-cta="header_call"]) покрывает ссылок: 1
  действующее правило #19 (//a[@data-ldv-cta="hero_call" or @data-ldv-cta="how_call" or @data-ldv-cta="fee_call" or @) покрывает ссылок: 4
  действующее правило #20 (//a[@data-ldv-cta="attorney_call"]) покрывает ссылок: 1
  действующее правило #21 (//a[@data-ldv-cta="sticky_call"]) покрывает ссылок: 1
  действующее правило #22 (//a[@data-ldv-cta="footer_call"]) покрывает ссылок: 1
Уже покрыто действующими правилами: 0 из 8

## План: 5 правил(а) на 8 непокрытых ссылок
1. car-lawyer 1 | совпадений 1 из 1 OK | признак: ['data-атрибут data-ldv-cta']
   XPath: //a[@data-ldv-cta="header_call"]
   Маска: <small>FREE CONSULTATION · 24/7</small> (844) 452-9465<span style="display:none;">+###########</span>
   Ссылки: [{'data-ldv-cta': 'header_call'}]  (номера в тексте нет: добавлен скрытый span)
2. car-lawyer 2 | совпадений 4 из 4 OK | признак: ['data-атрибут data-ldv-cta']
   XPath: //a[@data-ldv-cta="fee_call" or @data-ldv-cta="final_call" or @data-ldv-cta="hero_call" or @data-ldv-cta="how_call"]
   Маска: Call (844) 452-9465 · 24/7<span style="display:none;">+###########</span>
   Ссылки: [{'data-ldv-cta': 'hero_call'}, {'data-ldv-cta': 'how_call'}, {'data-ldv-cta': 'fee_call'}, {'data-ldv-cta': 'final_call'}]  (номера в тексте нет: добавлен скрытый span)
3. car-lawyer 3 | совпадений 1 из 1 OK | признак: ['data-атрибут data-ldv-cta']
   XPath: //a[@data-ldv-cta="sticky_call"]
   Маска: Call now · 24/7<span style="display:none;">+###########</span>
   Ссылки: [{'data-ldv-cta': 'sticky_call'}]  (номера в тексте нет: добавлен скрытый span)
4. car-lawyer 4 | совпадений 1 из 1 OK | признак: ['data-атрибут data-ldv-cta']
   XPath: //a[@data-ldv-cta="attorney_call"]
   Маска: Call (844) 452-9465<span style="display:none;">+###########</span>
   Ссылки: [{'data-ldv-cta': 'attorney_call'}]  (номера в тексте нет: добавлен скрытый span)
5. car-lawyer 5 | совпадений 1 из 1 OK | признак: ['data-атрибут data-ldv-cta']
   XPath: //a[@data-ldv-cta="footer_call"]
   Маска: (844) 452-9465<span style="display:none;">+###########</span>
   Ссылки: [{'data-ldv-cta': 'footer_call'}]  (номера в тексте нет: добавлен скрытый span)

Итого покрыто: 8 из 8 ссылок tel: — ВСЕ
Не охвачено по построению: ссылки, создаваемые скриптом страницы после загрузки (кнопки результата квиза и т.п.), номер картинкой, номер без ссылки tel:.

## JS для консоли страницы «XPaths» проекта в Ringostat (после «да»; затем «Применить настройки»)
```js
(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const set=(n,v)=>{const e=document.querySelector('[name="'+n+'"]');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
const rules=[{"name": "car-lawyer 1", "xpath": "//a[@data-ldv-cta=\"header_call\"]", "mask": "<small>FREE CONSULTATION · 24/7</small> (844) 452-9465<span style=\"display:none;\">+###########</span>", "geo": "1"}, {"name": "car-lawyer 2", "xpath": "//a[@data-ldv-cta=\"fee_call\" or @data-ldv-cta=\"final_call\" or @data-ldv-cta=\"hero_call\" or @data-ldv-cta=\"how_call\"]", "mask": "Call (844) 452-9465 · 24/7<span style=\"display:none;\">+###########</span>", "geo": "1"}, {"name": "car-lawyer 3", "xpath": "//a[@data-ldv-cta=\"sticky_call\"]", "mask": "Call now · 24/7<span style=\"display:none;\">+###########</span>", "geo": "1"}, {"name": "car-lawyer 4", "xpath": "//a[@data-ldv-cta=\"attorney_call\"]", "mask": "Call (844) 452-9465<span style=\"display:none;\">+###########</span>", "geo": "1"}, {"name": "car-lawyer 5", "xpath": "//a[@data-ldv-cta=\"footer_call\"]", "mask": "(844) 452-9465<span style=\"display:none;\">+###########</span>", "geo": "1"}];
for(const r of rules){[...document.querySelectorAll('button')].find(e=>/Добавить XPath/.test(e.textContent)).click();await sleep(1500);
set('data[Xpath][type]','manual');set('data[Xpath][text]',r.xpath);set('data[Xpath][name]',r.name);set('data[Xpath][mask]',r.mask);set('data[Xpath][geo_group]',r.geo);
[...document.querySelectorAll('.modal button[type=submit]')].filter(b=>b.textContent.trim()==='Сохранить').pop().click();await sleep(3500);}
return document.querySelectorAll('table tbody tr').length;})()
```