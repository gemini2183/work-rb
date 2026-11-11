---
status: открыта
updated: 2026-11-11
---

# П-015. Landver Pedestrian & Bicycle: у формы в живом DOM нет `id` и класса `js-form-proccess`

**Система:** Tilda / страница `pedestrian-bicycle-accident-lawyer-california`, форма приёма.

**Симптом (11.11 ~11:17 Варшава = 02:17 Лос-Анджелес, JS в Chrome через расширение, 3 с после загрузки):** `<form class="ldv2__form t-form">`, `id=""`, класса `js-form-proccess` нет, кнопка `type="submit"`, 2 скрытых `formservices[]`. На 10.11 17:19 `page_tracking_check.py` видел `form5673505903_1` (форма до пересборки).

**Что известно:** обработчик Tilda (`tilda-forms-1.0.min.js`) привязывается к `.js-form-proccess` (`t_forms__onSubmit`, `t_forms__initBtnClick`); событие для GTM = `submit_` + `id` формы; для форм в блоке `.t1370` без класса и без `action` Tilda сама добавляет класс и id `form<recId>_<n>` (`t_forms__initVibeForms`) — здесь этого не произошло. `ldv_form_start` на этой странице работает (есть `t-form`).

**Что НЕ установлено:** отправляется ли форма вообще; какое событие уйдёт в `dataLayer` (при пустом id — `submit_`, которого нет ни в триггере 4 `submit_form*`, ни в 121 `^submit_(vb-.+-form|ldv-form-el)$`). Отправку не проверяли (заявка уходит получателям).

**Обход / как проверить:** до включения рекламы на страницу — тестовая заявка по сценарию из `Клиенты/Andverpersonalinjury/GTM_план_ldv_form_start_spanish.md` (раздел 5, подставить адрес Pedestrian): успех на экране + `forms.tildacdn.com` 200 + `form_submit` в GA4. Если события нет — исполнителю Tilda: у формы `id` вида `ldv-form-el` (подходит под триггер 121) и класс `js-form-proccess`, либо настоящий блок формы Tilda.

Связано: [[П-013_landver-форма-приёма-не-отправляется-по-клику]], [[П-010_tilda-сборка-исполнителем-не-по-инструкции]].
