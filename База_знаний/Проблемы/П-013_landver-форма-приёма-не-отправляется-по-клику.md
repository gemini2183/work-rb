---
status: решена
updated: 2026-11-12
---

# П-013. Landver: на новой странице форма приёма не отправляется по клику

**Система:** Tilda / страницы Motorcycle (`landverpersonalinjury.tilda.ws/motorcycle-accident-lawyer-california`); на Pedestrian и испанской не проверялось.

**Симптом (10.11, Chrome через расширение, метки `utm_source=claude_form_test`):** поля заполнены (имя TEST, телефон 9999999999, радио «Yes, I was hurt», текст «TEST, do not call»), три клика по кнопке «Get My Free Case Review» — запроса на отправку формы нет (ни в сети, ни XHR/fetch/beacon), сообщения об успехе нет, ошибок валидации нет (`tildaForm.validate` вернул пустой список). Событие клика до кнопки доходит. В GA4 ушёл только автоматический `form_start` (расширенные измерения), нет `ldv_form_start`.

**Что известно:**
- Форма `form5284565603_1`, класс `js-form-proccess`, `data-formactiontype=2`, кнопка `<button type="button" class="t-submit">`; `window.tildaForm` загружен; jQuery на странице нет.
- Событие `submit` по клику не возникает (кнопка type=button).
- Первый клик был ДО установки перехватчиков, но запроса к серверу в журнале сети нет и после него.

**Причина для Motorcycle (установлена 10.11 по опубликованному HTML, пользователь подтвердил, что вручную тоже не отправляется):** вся страница опубликована ОДНОЙ записью Tilda типа 1370 (HTML-блок «Vibe»), а в ней лежит нарисованный макет формы из `0_maket_prosmotr.html` (в коде комментарий `<!-- NATIVE FORM -->`, `<form>` без action, кнопка `type="button"`). Настоящего блока формы Tilda (с полями, почтой и интеграциями), который по `ИНСТРУКЦИЯ_сборка_в_Tilda.md` ставится между блоками 2 и 3, на странице нет. Тот же класс сбоя, что П-010.

**Три страницы собраны по-разному (по опубликованному HTML, поведение отправки проверено только на Motorcycle):**
| Страница | Что в коде формы |
|---|---|
| Motorcycle | макет: `<form>` без action, `button type="button"`, мёртвая |
| Pedestrian & Bicycle | своя форма `form.ldv2__form`, `button type="submit"`, без `t-submit`, без правил Tilda — не проверена |
| Испанская | форма с правилами и маской Tilda (`vb-b2s__*`, `js-tilda-rule`, `t-submit`) — не проверена |

**Что НЕ установлено:** это дефект страницы или артефакт клика через расширение; как Tilda привязывает обработчик к этой кнопке; как ведут себя Pedestrian и испанская. Отправку «вручную» человеком не проверяли.

**Обход / как проверить:** пользователь один раз вручную заполняет форму и жмёт кнопку на Motorcycle (метка `claude_form_test` в адресе); есть запрос `forms.tildacdn.com` или окно успеха — это был артефакт. Нет — дефект: Задача по Tilda исполнителю (кнопка должна быть `type="submit"` или инициализироваться Tilda).

Связано: [[П-010_tilda-сборка-исполнителем-не-по-инструкции]], задача «ldv_form_start» в `Клиенты/Andverpersonalinjury/Задачи.md`.

## Решение (12.11)
Исполнитель заменил макет на настоящую форму Tilda: `<form id="ldv-moto-form" class="t-form js-form-proccess">`, кнопка `type="submit"` (проверено `page_tracking_check.py` и разбором HTML 12.11 09:50). Тест-заявка пользователя (имя TEST) 12.11: окно «Thank you», письмо получателям пришло, GA4 `form_submit` дошёл. Сопутствующая проблема: событие `submit_ldv-moto-form` не ловилось триггерами GA4 `form_submit` — исправлено в GTM v17 (И-144), проверка до публикации — `gtm_form_event_check.py`.
**Как проверить:** `python Скрипты/page_tracking_check.py --url <адрес> --client-folder Andverpersonalinjury` — в «Формы» `t-form js-form-proccess`; `python Скрипты/gtm_form_event_check.py --account 6353362488 --container 261134482 --form-id ldv-moto-form` — «ЛОВИТСЯ».

