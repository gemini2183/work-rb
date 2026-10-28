# Правила подмены Ringostat для https://landverpersonalinjury.tilda.ws/uber-lyft-accident-lawyer-california
Дата: 2026-10-28 15:30. Только чтение.
Скрипт Ringostat: https://script.ringostat.com/v4/4c/4c28b51a7504aa7cdf1789ee697a219f17ccbd8b.js; действующих правил проекта: 23
Ссылок tel: 8; основной номер на странице tel:+18444529465
Уже покрыто действующими правилами: 0 из 8

## План: 5 правил(а) на 8 непокрытых ссылок
1. rideshare 1 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-track']
   XPath: //a[@data-vb-track="q4n_header_call"]
   Маска: <small>FREE CONSULTATION · 24/7</small>(###) ###-####
   Ссылки: [{'data-vb-track': 'q4n_header_call'}]
2. rideshare 2 | совпадений 4 из 4 OK | признак: ['data-атрибут data-vb-track']
   XPath: //a[@data-vb-track="c9r_call" or @data-vb-track="m2w_call" or @data-vb-track="q4n_hero_call" or @data-vb-track="w2t_call"]
   Маска: <span class="t-btnflex__text">Call (###) ###-#### · 24/7</span>
   Ссылки: [{'data-vb-track': 'q4n_hero_call'}, {'data-vb-track': 'c9r_call'}, {'data-vb-track': 'm2w_call'}, {'data-vb-track': 'w2t_call'}]
3. rideshare 3 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-track']
   XPath: //a[@data-vb-track="q4n_sticky_call"]
   Маска: Call now · 24/7<span style="display:none;">+###########</span>
   Ссылки: [{'data-vb-track': 'q4n_sticky_call'}]  (номера в тексте нет: добавлен скрытый span)
4. rideshare 4 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-track']
   XPath: //a[@data-vb-track="y8f_call"]
   Маска: <span class="t-btnflex__text">Call (###) ###-####</span>
   Ссылки: [{'data-vb-track': 'y8f_call'}]
5. rideshare 5 | совпадений 1 из 1 OK | признак: ['data-атрибут data-vb-track']
   XPath: //a[@data-vb-track="e5j_footer_call"]
   Маска: (###) ###-####
   Ссылки: [{'data-vb-track': 'e5j_footer_call'}]

Итого покрыто: 8 из 8 ссылок tel: — ВСЕ
Не охвачено по построению: ссылки, создаваемые скриптом страницы после загрузки (кнопки результата квиза и т.п.), номер картинкой, номер без ссылки tel:.

## JS для консоли страницы «XPaths» проекта в Ringostat (после «да»; затем «Применить настройки»)
```js
(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const set=(n,v)=>{const e=document.querySelector('[name="'+n+'"]');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
const rules=[{"name": "rideshare 1", "xpath": "//a[@data-vb-track=\"q4n_header_call\"]", "mask": "<small>FREE CONSULTATION · 24/7</small>(###) ###-####", "geo": "1"}, {"name": "rideshare 2", "xpath": "//a[@data-vb-track=\"c9r_call\" or @data-vb-track=\"m2w_call\" or @data-vb-track=\"q4n_hero_call\" or @data-vb-track=\"w2t_call\"]", "mask": "<span class=\"t-btnflex__text\">Call (###) ###-#### · 24/7</span>", "geo": "1"}, {"name": "rideshare 3", "xpath": "//a[@data-vb-track=\"q4n_sticky_call\"]", "mask": "Call now · 24/7<span style=\"display:none;\">+###########</span>", "geo": "1"}, {"name": "rideshare 4", "xpath": "//a[@data-vb-track=\"y8f_call\"]", "mask": "<span class=\"t-btnflex__text\">Call (###) ###-####</span>", "geo": "1"}, {"name": "rideshare 5", "xpath": "//a[@data-vb-track=\"e5j_footer_call\"]", "mask": "(###) ###-####", "geo": "1"}];
for(const r of rules){[...document.querySelectorAll('button')].find(e=>/Добавить XPath/.test(e.textContent)).click();await sleep(1500);
set('data[Xpath][type]','manual');set('data[Xpath][text]',r.xpath);set('data[Xpath][name]',r.name);set('data[Xpath][mask]',r.mask);set('data[Xpath][geo_group]',r.geo);
[...document.querySelectorAll('.modal button[type=submit]')].filter(b=>b.textContent.trim()==='Сохранить').pop().click();await sleep(3500);}
return document.querySelectorAll('table tbody tr').length;})()
```