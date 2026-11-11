---
status: подготовка (в GTM, Tilda, кабинеты ничего не писалось); ждёт решения супервайзера
updated: 2026-11-11
---

# Испанская страница: форма -> GA4, `ldv_form_start`, план правки GTM

Страница: `https://landverpersonalinjury.tilda.ws/abogado-accidentes-auto-lawyer-california`. Контейнер GTM-KVLHDKJJ (аккаунт 6353362488, контейнер 261134482), живая версия 16, прочитана через API 11.11 ~11:05 (Варшава). Пояс времени: Варшава 11:21 = 02:21 по Лос-Анджелесу (ноябрь, PST = Варшава минус 9 ч); пояс ресурса GA4 549802233 — America/Los_Angeles.

## 1. Главный вывод: на испанской странице правка `ldv_form_start` не нужна

Гипотеза «слушатель ищет `form.t-form`, а у новых форм `t-form` — div-обёртка» верна для Motorcycle, но НЕ для испанской.

| Страница | Что у `<form>` в живом DOM (11.11 ~11:15 Варшава, Chrome, фокус в поле «имя») | `ldv_form_start` |
|---|---|---|
| Испанская | `id="vb-b2s-form"`, класс `vb-b2s__form t-form js-form-proccess`, `action="#"`, `button type="submit"`, 2 приёмника `.js-formaction-services` | **сработал** (1 событие в dataLayer после фокуса) |
| Motorcycle | `id="form5284565603_1"`, класс только `js-form-proccess` (`t-form` на div-обёртке), 0 приёмников, кнопка `type="button"` | **не сработал** (0) |
| Pedestrian & Bicycle | класс `ldv2__form t-form`, **`id` пустой, класса `js-form-proccess` нет**, `button type="submit"`, 2 приёмника | сработал (1); но см. риск ниже |

Источники: код тега 65 «ldv form start script» (живая версия 16): `t.closest('form.t-form')`; DOM — живые страницы (JS в Chrome пользователя); GA4: на испанской `lead_form_start` уже приходил 10.11 в час 07 (google / cpc) и в час 12 (`claude_form_test / test`) по поясу Лос-Анджелеса (Data API, `ga4_realtime_events.py --page-contains abogado`).

## 2. Как устроен путь «форма -> GA4» на испанской (прочитано из контейнера и кода Tilda)

1. Фокус в поле -> тег 65 (HTML, All Pages) пушит `ldv_form_start` -> триггер 53 -> тег 62 «GA4 - lead_form_start».
2. Отправка: Tilda (`tilda-forms-1.0.min.js`) после УСПЕШНОГО ответа сервера пушит `submit_<id формы>` = `submit_vb-b2s-form`.
3. Триггер 121 «submit vb form [topic pages]» (папка «Topic pages (vb)»): regex `^submit_(vb-.+-form|ldv-form-el)$` — `submit_vb-b2s-form` подходит. Старый триггер 4 (`submit_form*`) НЕ подходит (после `submit_` идёт `vb-`, не `form`), поэтому двойного счёта нет.
4. Триггер 121 запускает тег 125 «GA4 - form_submit [topic pages]» (`form_submit`, `form_place=inline`) и тег 126 «OpenAI Pixel - Lead Created [topic pages]» (`lead_created`).
5. Значит `form_submit` в GA4 появится только если сервер Tilda принял заявку (событие пушится в ветке успеха).

Технически проверено без отправки (JS на живой странице): `tildaForm` загружен, `tildaForm.validate` по пустой форме даёт `name:req`, `phone:req`, по заполненной (TEST, +1 (999) 999-9999) — 0 ошибок; кнопка `type="submit"`; 2 скрытых поля `formservices[]` (получатели) есть. Сама отправка и доставка получателям НЕ проверялись.

## 3. План правки GTM для «да» (таблица «Объект | Действие | Было -> Станет | Откуда факт»)

Для ИСПАНСКОЙ страницы правок нет: **0 изменений, версию не создавать**.

Необязательная страховка для будущих страниц на `-lawyer-california`, у которых `<form>` без класса `t-form` (сейчас это Motorcycle; после замены макета на настоящий блок формы Tilda `t-form` на `<form>`, скорее всего, появится сам, как у Car/Pedestrian/испанской). Делать только если после исправления Motorcycle событие всё ещё не приходит.

| Объект | Действие | Было -> Станет | Откуда факт |
|---|---|---|---|
| Тег HTML «ldv form start script [topic pages, без t-form]» (новый, папка «Topic pages (vb)» id 118) | создать | нет -> слушатель `focusin` для форм, которые НЕ `form.t-form` (`form.js-form-proccess`, `[data-vibeblock-form]`, `[id^="ldv-form"]`), пушит `ldv_form_start`; свой флаг `__ldvFormStartTP`, чтобы не пересечься с тегом 65 | тег 65 ищет только `form.t-form`; Motorcycle `form5284565603_1` без `t-form` (DOM 11.11) |
| Триггер запуска нового тега | использовать существующий 122 «topic pages pageview» (`-lawyer-california/?$`), новый не создавать | — | триггер 122 уже кормит теги 129 и др. |
| Тег 65, триггеры 53/121/122, теги 62/125/126 | не трогать | — | контейнер общий (решение пользователя 26.10) |

Код нового тега (условие `f.matches('form.t-form')` исключает формы, которые уже ловит тег 65, дублей `lead_form_start` не будет):

```html
<script>(function(){if(window.__ldvFormStartTP)return;window.__ldvFormStartTP=true;var seen={};document.addEventListener('focusin',function(e){var t=e.target;if(!t||!t.closest||t.type==='hidden')return;var f=t.closest('form');if(!f||f.matches('form.t-form'))return;if(!(f.matches('.js-form-proccess')||f.hasAttribute('data-vibeblock-form')||f.matches('[id^="ldv-form"]')))return;var id=f.id||f.name||'form';if(seen[id])return;seen[id]=1;(window.dataLayer=window.dataLayer||[]).push({event:'ldv_form_start',form_place:f.closest('.t-popup')?'popup':'inline'});},true);})();</script>
```

Допущения (проверить): Motorcycle получит настоящий блок формы (П-013) — тогда страховка не нужна; `form_place` для всех этих форм `inline`.

Порядок, если решат делать: новая рабочая область от ЖИВОЙ версии 16 (ловушка плейбука: рабочая область строится от последней версии, а не от живой) -> `gtm_apply_plan.py` (проверка) -> `gtm_test_version.py` на Motorcycle и испанской (`--eval` фокус в поле; ожидание: на испанской `lead_form_start` ровно 1, не 2) + регрессия на Car (число событий равно живой версии) -> «опубликуй» только от пользователя.

## 4. Риски, найденные по пути (не относятся к правке GTM)

1. **Pedestrian & Bicycle:** в живом DOM у формы нет `id` и нет класса `js-form-proccess` (на 10.11 в отчёте `page_tracking_check` был `form5673505903_1`; после вечерней пересборки иначе). Обработчик Tilda привязывается к `.js-form-proccess`; без него отправка, возможно, не работает, а событие было бы `submit_` без id и не попало бы ни в триггер 4, ни в 121. Не проверено отправкой — вынести в тест перед включением рекламы на эту страницу.
2. **Motorcycle:** 0 получателей и `type="button"` — форма мёртвая (П-013); `ldv_form_start` тоже не идёт.
3. Получатели испанской формы (2 значения `formservices[]`) заданы в коде страницы исполнителем; верны ли они (почта / интеграция колл-центра), видно только по живой заявке.

## 5. Сценарий живой тестовой отправки (ТОЛЬКО по «да» супервайзера/пользователя: заявка уходит получателям формы, возможно в колл-центр клиента)

Подготовка (до «да»): предупредить колл-центр/получателя, что придёт заявка «TEST, do not call».

1. Замерить «до»: `python Скрипты\ga4_realtime_events.py --property 549802233 --realtime --events lead_form_start form_submit` (запомнить числа и время; считает весь ресурс за 30 минут, поэтому делать сразу перед шагом 2 и сразу после).
2. В Chrome пользователя открыть: `https://landverpersonalinjury.tilda.ws/abogado-accidentes-auto-lawyer-california?utm_source=claude_form_test&utm_medium=test&utm_campaign=claude_form_test`. Подождать 5 с (GTM загрузится).
3. Консоль (F12), проверка: `window.dataLayer.filter(e=>e.event).map(e=>e.event)` — запомнить длину.
4. Заполнить: имя `TEST`; телефон `9999999999` (маска сама даст `+1 (999) 999-9999`); «¿Usted o un pasajero resultó herido?» — «No estoy seguro»; «¿Qué tipo de accidente fue?» — «Otro»; «Cuéntenos…» — `TEST, do not call`.
5. Нажать «Solicitar mi consulta gratuita». Зафиксировать время (Варшава и Лос-Анджелес). Ожидание: зелёный блок «Gracias. Recibimos su solicitud…» вместо формы; в Network запрос к `forms.tildacdn.com` (статус 200); в консоли в dataLayer появилось `submit_vb-b2s-form`.
6. Если успеха нет, но кнопка «не реагирует»: скопировать сообщение об ошибке над формой и вкладку Network; не жать больше двух раз (Tilda блокирует по IP, П-014).
7. Через 1-2 минуты: `ga4_realtime_events.py --realtime --events lead_form_start form_submit` — ожидание: `form_submit` +1 (и `lead_form_start` +1, если страница была загружена заново).
8. Через несколько часов (задержка стандартных отчётов): `python Скрипты\ga4_realtime_events.py --property 549802233 --from 2026-11-11 --to 2026-11-11 --page-contains abogado --events lead_form_start form_submit` — искать строку с источником `claude_form_test / test` и час по поясу Лос-Анджелеса (учесть: утро по Варшаве = вчерашняя дата по Лос-Анджелесу, если время до 09:00 Варшава).
9. Побочные эффекты теста: сработает тег 126 (OpenAI Pixel `lead_created`) и GA4 `form_submit` (ключевое событие/импорт в Ads, если настроен, но без gclid в Ads не засчитается). Это тестовые данные; в отчётах исключать по источнику `claude_form_test`.
10. Результат записать в Хронику («форма -> GA4», минута Варшава и Лос-Анджелес, получатель получил / не получил) и закрыть П-013-ветку по испанской.

Критерий «готово»: на экране сообщение об успехе + запрос к `forms.tildacdn.com` 200 + `form_submit` в GA4 realtime (или в дневном отчёте) + получатель подтвердил, что заявка пришла.
