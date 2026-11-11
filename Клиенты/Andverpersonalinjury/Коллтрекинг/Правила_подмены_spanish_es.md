---
status: ВНЕСЕНО в кабинет 2026-11-11 (6 правил, 33 -> 39, «Применить» ~12:00, И-133); проверка подмены 11:54 - см. раздел «Результат проверки»
updated: 2026-11-11
---

# Правила подмены Ringostat `es_*` — испанская страница `landverpersonalinjury.tilda.ws/abogado-accidentes-auto-lawyer-california`

Заменяет черновик [[Правила_подмены_abogado_tilda]] (там маски без обёртки кнопки и без правила на FAQ — см. «Что изменено против черновика»). Закрывает П-006 после ввода и проверки. Механизм — [[../../../База_знаний/Инструменты/Ringostat-механизм-подмены-номера]], порядок — [[../../../База_знаний/Агенты/Запуск_трекинга_новой_посадочной]], шаг 6.

## Что установлено (чтение, 2026-11-11)
- **Конфиг Ringostat (11:15):** `https://script.ringostat.com/v4/4c/4c28b51a7504aa7cdf1789ee697a219f17ccbd8b.js` → `"xpaths"`: **33 правила, ни одного с `es_`**; ни одно из 33 не совпадает ни с одним элементом испанской страницы (проверено по HTML страницы, снятому в 11:16). Проект Ringostat — `project_id=234843`.
- **Страница (HTML 11:16, один запрос, 200):** 8 ссылок `tel:` с `data-ldv-cta="es_*"`; пять кнопок («как работает», оплата, первый экран, адвокат, финал) имеют внутри `<span class="t-btnflex__text">…</span>` (класс `t-btnflex`, собрано исполнителем в Tilda).
- **Номер текстом вне ссылок (кроме 8 `tel:`):** (1) FAQ «¿Atienden en español?» — `<details><p>Sí. Puede llamar al (844) 452-9465, las 24 horas, y hablar en español.</p>` — видимый; (2) сообщение после отправки формы `div.vb-b2s__success` (скрыто, П-008).
- **Проверка «до» (`phone_swap_check.py`, 11:17, `Статистика/phone_swap_check_2026-11-11_1117.csv`):** без меток (десктоп и мобильный) OK, номер (844) 452-9465; с метками Google и ChatGPT — 4 случая MISMATCH: все 8 `tel:` на (844), плюс текст FAQ и скрытый текст сообщения формы. Итог «4 из 6 не прошли».

## Правила (Manual mode, ГЕО группа **All**, не «not set»)
XPath — на сам `<a>`; номер из пула выбирает сервер по каналу (Google Ads — 3 номера, ChatGPT — 1, см. `Пул_номеров_spanish_tilda.yaml`), поэтому в правилах «какой номер по какой метке» не задаётся: правило только говорит, где и в какой форме показывать подставленный номер. `href` у найденной ссылки Ringostat ставит сам.

| # | Название правила | Элемент | XPath | Совпадений (по HTML 11:16) | Маска |
|---|---|---|---|---|---|
| 1 | `abogado header` | Шапка (десктоп) | `//a[@data-ldv-cta="es_header_call"]` | 1 | `<small>CONSULTA GRATIS · 24/7</small>(###) ###-####` |
| 2 | `abogado call 24/7` | Первый экран, «как работает», «оплата», финал | `//a[@data-ldv-cta="es_hero_call" or @data-ldv-cta="es_how_call" or @data-ldv-cta="es_fee_call" or @data-ldv-cta="es_final_call"]` | 4 | `<span class="t-btnflex__text">Llame al (###) ###-#### · 24/7</span>` |
| 3 | `abogado attorney` | Кнопка у блока адвоката | `//a[@data-ldv-cta="es_attorney_call"]` | 1 | `<span class="t-btnflex__text">Llame al (###) ###-####</span>` |
| 4 | `abogado sticky` | Нижняя плашка на телефоне (номера в тексте нет) | `//a[@data-ldv-cta="es_sticky_call"]` | 1 | `Llame ahora · 24/7<span style="display:none;">+###########</span>` |
| 5 | `abogado footer` | Подвал | `//a[@data-ldv-cta="es_footer_call"]` | 1 | `(###) ###-####` |
| 6 | `abogado faq` | Ответ FAQ про звонок (видимый текст) | `//details/p[contains(.,"Puede llamar al")]` | 1 | `Sí. Puede llamar al (###) ###-####, las 24 horas, y hablar en español.` |
| 7 (по желанию) | `abogado success` | Сообщение после формы (скрыто, П-008) | `//div[contains(@class,"vb-b2s__success")]` | 1 | `Gracias. Recibimos su solicitud y nos comunicaremos con usted para programar su consulta gratuita. Mientras tanto, si aún no lo ha hecho, reciba atención médica y no dé declaraciones grabadas ni firme ofertas de una aseguradora. ¿Prefiere hablar ahora? Llame al (###) ###-#### · 24/7.` |

Знак `·` — U+00B7 (как на странице). Не набирать руками: брать JS ниже, символы в нём записаны кодами `\u00b7`, `\u00ed`, `\u00f1`. Маска заменяет весь текст/внутренности найденного узла, поэтому в правилах 6 и 7 она содержит весь текст целиком.
Правило 7 не проверялось на поведение: Tilda может перезаписать текст окна успеха при отправке формы. Без него решение 10.11 по П-008 остаётся в силе (звонок оттуда пойдёт на основной номер). Вводить правило 7 или нет — решение пользователя; для критерия ниже оно не обязательно.

## Что изменено против черновика `Правила_подмены_abogado_tilda.md`
1. Маски правил 2 и 3 теперь с `<span class="t-btnflex__text">…</span>`: на живой странице внутри кнопок этот span есть, маска без него его бы стёрла. Тот же приём уже работает на Pedestrian & Bicycle и Motorcycle (правила №24, 26, 30, 32 в конфиге; проверка 10.11 показала подмену там).
2. Добавлено правило 6 (FAQ): без него критерий «все случаи OK» недостижим, строка `text … ldv-faq` останется несовпадением.
3. Правило 7 вынесено как необязательное.
4. Адрес в черновике был `abogado-de-accidentes-lawyer-california` (404); рабочий — `abogado-accidentes-auto-lawyer-california`, он же в пул-файле.

## Результат проверки (11.11, после внесения)
Публичный js Ringostat 11:53: 39 правил, 6 новых (индексы 33-38), XPath и маски как в таблице выше, ГЕО 1. `phone_swap_check.py` 11:54 (`Статистика/phone_swap_check_2026-11-11_1154.csv`): без меток OK (десктоп, мобильный); Google десктоп — все 8 `tel:` и FAQ на +18883783267; ChatGPT десктоп и мобильный — все на +18883468106; Google мобильный — все на (877) 403-8698, номера нет в `Пул_номеров_spanish_tilda.yaml` (подмена работает, пул-файл неполный: нужно подтвердить пул в кабинете и дописать номер). Остаток `!!` в четырёх случаях с метками — скрытое окно успеха (П-008). Осталось: скриншоты мест номера, живой звонок.

## Пошаговая инструкция (ручной ввод, ~10 минут)
Выполнять в браузере, где уже выполнен вход в Ringostat. Запись в кабинет — только по этой инструкции, API для правил нет.
1. Открыть `https://app.ringostat.com/project/dashboard?project_id=234843`, затем `https://app.ringostat.com/project/script_settings/xpaths?project_id=234843`. В таблице должно быть **33** строки (`document.querySelectorAll('table tbody tr').length`).
2. Открыть консоль (F12 → Console), вставить код из блока ниже (он только определяет функции) и вызывать `await esFill(0)`, нажимать «Сохранить» мышью, потом `esFill(1)` и так до пятого. 
3. Проверить: в таблице **39** строк (33 + 6; если вводили правило 7 — 40), и в названиях есть все `abogado header | call 24/7 | attorney | sticky | footer | faq`. Если одно правило не сохранилось (бывало: «одно из пяти») — повторить только его (форма «Добавить XPath»: тип Manual mode, XPath, название, маска, ГЕО группа All).
4. Нажать зелёную кнопку «Применить настройки» (справа сверху); должно появиться «Действие выполнено успешно».
5. Подождать 2–5 минут (скрипт Ringostat кэшируется) и убедиться без Tilda: `curl -s https://script.ringostat.com/v4/4c/4c28b51a7504aa7cdf1789ee697a219f17ccbd8b.js | grep -o 'es_header_call'` — должно найтись.
6. Запустить проверку (команда ниже), потом посмотреть глазами скриншоты.

**Код для консоли (v2, 11.11 ~12:00).** Первая версия (один цикл) в консоли пользователя ничего не добавила, причина не установлена: консоль возвращает `{}`, пока цикл идёт, и результат нужно смотреть через ~40 секунд. Форма кабинета проверена по живой странице: окно `#ev_modal`, форма `#xpath_add_form`, поля `data[Xpath][type|text|name|mask|geo_group]`, кнопки «Отмена» и «Сохранить» (`.ev_add_xpath`, обработчик на `.modal` с проверкой `validationEngine` и ajax, после успеха строка добавляется в таблицу без перезагрузки). Сухой прогон 11.11: все 6 правил заполняют поля, значения читаются обратно без искажений (`·` = код 183), проверка формы проходит, после «Отмена» строк 33, ничего не сохранено. Код ниже только определяет функции, пока вы не вызовете их.

Вставить код один раз (он ничего не записывает), затем:
- **Рабочий порядок:** `await esFill(0)` — откроет окно «Добавить XPath», заполнит поля, проверит форму и остановится. После этого ПОЛЬЗОВАТЕЛЬ (или вводящий кликом мыши в браузере) нажимает настоящую кнопку «Сохранить»; потом `await esFill(1)` … `await esFill(5)` (0-5 = header, call 24/7, attorney, sticky, footer, faq). Так внесены правила 11.11.
- **`esAll()` НЕ использовать:** клик «Сохранить», сделанный кодом (`.click()`), Ringostat не принимает (проверено 11.11: «НЕ сохранилось», строка не добавляется); сохраняет только настоящий клик мышью (в расширении Chrome — клик по координатам кнопки). Функция оставлена в коде для справки.
- Если что-то заполнилось не так: «Отмена» в окне, ничего не сохраняется.
- После каждого сохранения проверять `esNames().filter(n=>/^abogado/.test(n))`; в конце строк 39, «Применить настройки».

```js
window.ES_RULES=[{"name":"abogado header","xpath":"//a[@data-ldv-cta=\"es_header_call\"]","mask":"<small>CONSULTA GRATIS · 24/7</small>(###) ###-####"},{"name":"abogado call 24/7","xpath":"//a[@data-ldv-cta=\"es_hero_call\" or @data-ldv-cta=\"es_how_call\" or @data-ldv-cta=\"es_fee_call\" or @data-ldv-cta=\"es_final_call\"]","mask":"<span class=\"t-btnflex__text\">Llame al (###) ###-#### · 24/7</span>"},{"name":"abogado attorney","xpath":"//a[@data-ldv-cta=\"es_attorney_call\"]","mask":"<span class=\"t-btnflex__text\">Llame al (###) ###-####</span>"},{"name":"abogado sticky","xpath":"//a[@data-ldv-cta=\"es_sticky_call\"]","mask":"Llame ahora · 24/7<span style=\"display:none;\">+###########</span>"},{"name":"abogado footer","xpath":"//a[@data-ldv-cta=\"es_footer_call\"]","mask":"(###) ###-####"},{"name":"abogado faq","xpath":"//details/p[contains(.,\"Puede llamar al\")]","mask":"Sí. Puede llamar al (###) ###-####, las 24 horas, y hablar en español."}];
window.esSleep=ms=>new Promise(r=>setTimeout(r,ms));
window.esNames=()=>[...document.querySelectorAll('table tbody tr')].map(r=>r.cells[2].textContent.trim());
window.esFill=async(i)=>{
  const r=ES_RULES[i];
  if(!document.querySelector('#ev_modal.in')){document.querySelector('.ev_modal_add_xpath').click();await esSleep(2000);}
  const m=document.querySelector('#ev_modal');
  const set=(n,v)=>{const e=m.querySelector('[name="'+n+'"]');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
  const get=n=>m.querySelector('[name="'+n+'"]').value;
  set('data[Xpath][type]','manual');await esSleep(300);
  set('data[Xpath][text]',r.xpath);set('data[Xpath][name]',r.name);set('data[Xpath][mask]',r.mask);set('data[Xpath][geo_group]','1');
  const same=get('data[Xpath][type]')==='manual'&&get('data[Xpath][text]')===r.xpath&&get('data[Xpath][name]')===r.name&&get('data[Xpath][mask]')===r.mask&&get('data[Xpath][geo_group]')==='1';
  const valid=window.jQuery('#xpath_add_form').validationEngine('validate');
  const res=(same&&valid)?('OK: поля заполнены ('+r.name+'), нажмите «Сохранить» в окне'):('ОШИБКА: same='+same+' valid='+valid);
  console.log(res);return same&&valid;
};
window.esAll=async()=>{
  for(let i=0;i<ES_RULES.length;i++){
    if(esNames().includes(ES_RULES[i].name)){console.log('уже есть: '+ES_RULES[i].name);continue;}
    const ok=await esFill(i);if(!ok){console.log('СТОП на правиле '+i);return;}
    document.querySelector('#ev_modal .ev_add_xpath').click();
    for(let t=0;t<20&&!esNames().includes(ES_RULES[i].name);t++)await esSleep(500);
    console.log(esNames().includes(ES_RULES[i].name)?('сохранено: '+ES_RULES[i].name):('НЕ сохранилось: '+ES_RULES[i].name));
    await esSleep(1500);
  }
  console.log('строк в таблице: '+document.querySelectorAll('table tbody tr').length+' (ожидается 39); abogado: '+esNames().filter(n=>/^abogado/.test(n)).join(', '));
};
```
Правило 7 в код не включено (необязательное).

## Команда проверки (только чтение; шесть загрузок Tilda — не повторять серией, П-014)
```
cd D:\GitHub\work-rb\Скрипты
$env:PYTHONUTF8=1; python phone_swap_check.py --client-folder "Andverpersonalinjury" --pool-file "Коллтрекинг/Пул_номеров_spanish_tilda.yaml"
```
Отчёт сохраняется в `Статистика/phone_swap_check_<дата>_<время>.csv`. Между повторами — не менее 30–60 минут (гипотеза Хроники 10.11: проверки занимают номера пула и новым сеансам отдаётся основной; не проверено).

## Ожидаемый результат и критерий «готово»
- Без меток (десктоп и мобильный): OK, основной (844) 452-9465 (как сейчас).
- Google Ads (десктоп и мобильный): все 8 `tel:` и FAQ-текст на номере из пула (+18883783267 / +18883448725 / +18883025461), по одному номеру на визит; тексты «Llame al (888) … · 24/7», «Llame al (888) …» (адвокат), «(888) …» (подвал, шапка с «CONSULTA GRATIS · 24/7»), «Llame ahora · 24/7» (плашка).
- ChatGPT: те же места на +18883468106.
- Строка `split … ldv-footer` исчезает вместе с заменой номера в ссылке (сейчас это «24/7» из соседнего `<small>`, склеенное с (844)).
- **Критерий «6 из 6»:** все шесть случаев `[OK]`. Без правила 7 останется одна строка `!! … text … vb-b2s__success … скрыт` в случаях Google и ChatGPT — по счёту скрипта это 4 из 6 «не прошли», но это принятое П-008; считаем готовым, если **других `!!` нет** (так же, как Pedestrian & Bicycle, 10.11). С правилом 7 и подтверждённой подменой окна успеха — ровно 6 из 6.
- Глазами (десктоп и мобильный, метки Google): нет «Llame al Llame al» и «Call …», кнопки не потеряли оформление (span `t-btnflex__text` на месте), нет вложенных `<a>`, плашка внизу на телефоне, шапка с подписью «CONSULTA GRATIS · 24/7».

## Ручные шаги (итог)
1. Ввод 6 правил (7 по желанию) в кабинет Ringostat + «Применить настройки» — пользователь или Chrome-расширение по «да».
2. Запуск `phone_swap_check.py` через 2–5 минут и разбор результата.
3. Скриншоты мест номера с метками Google (десктоп + мобильный).
4. Тестовый живой звонок (не делался): номер из пула на странице → журнал Ringostat с `utm_campaign`.
5. Рекламу на испанскую страницу не включать до пунктов 2–3.

## Откат
Удалить в кабинете строки `abogado header | call 24/7 | attorney | sticky | footer | faq` (и `success`, если вводили) → «Применить настройки». Остальные 33 правила не затрагиваются.

## Не проверено
Живая подмена (правил в кабинете ещё нет); поведение правила 7; вид кнопок после подмены (ожидается по аналогии с Pedestrian & Bicycle, не по скриншоту этой страницы); отдельный номер/канал Ringostat для испанского трафика не заведён (решение пользователя: общий пул Google Ads).
