# Правила подмены Ringostat для https://landverpersonalinjury.tilda.ws/california-car-accident-settlement
Дата: 2026-10-26 10:43. Только чтение.
Скрипт Ringostat: https://script.ringostat.com/v4/4c/4c28b51a7504aa7cdf1789ee697a219f17ccbd8b.js; действующих правил проекта: 23
Ссылок tel: 5; основной номер на странице tel:+18444529465
  действующее правило #18 (//a[@data-ldv-cta="header_call"]) покрывает ссылок: 1
  действующее правило #19 (//a[@data-ldv-cta="hero_call" or @data-ldv-cta="how_call" or @data-ldv-cta="fee_call" or @) покрывает ссылок: 3
  действующее правило #22 (//a[@data-ldv-cta="footer_call"]) покрывает ссылок: 1
Уже покрыто действующими правилами: 5 из 5

## План: 0 правил(а) на 0 непокрытых ссылок

Итого покрыто: 5 из 5 ссылок tel: — ВСЕ
Не охвачено по построению: ссылки, создаваемые скриптом страницы после загрузки (кнопки результата квиза и т.п.), номер картинкой, номер без ссылки tel:.

## JS для консоли страницы «XPaths» проекта в Ringostat (после «да»; затем «Применить настройки»)
```js
(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const set=(n,v)=>{const e=document.querySelector('[name="'+n+'"]');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
const rules=[];
for(const r of rules){[...document.querySelectorAll('button')].find(e=>/Добавить XPath/.test(e.textContent)).click();await sleep(1500);
set('data[Xpath][type]','manual');set('data[Xpath][text]',r.xpath);set('data[Xpath][name]',r.name);set('data[Xpath][mask]',r.mask);set('data[Xpath][geo_group]',r.geo);
[...document.querySelectorAll('.modal button[type=submit]')].filter(b=>b.textContent.trim()==='Сохранить').pop().click();await sleep(3500);}
return document.querySelectorAll('table tbody tr').length;})()
```