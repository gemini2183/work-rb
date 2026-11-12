---
status: версия-черновик 97 создана и проверена во временной среде; НЕ опубликована, живая версия 96
updated: 2026-11-12
---
# Запись в GTM: ProfiMet, страница /montaz-szklarni (GTM-TKGN4NT)

Исполнитель: агент «Исполнитель записи в GTM». Дата: 2026-11-12. Основание: `12_gtm.md`, план `D:\GitHub\work-rb\Клиенты\ProfiMet\Трекинг\gtm_plan_montaz_2026-11-12.json`.
Цитата «да» (12.11.2026, чат): на вопрос «3. GTM: черновик по вашему "ок" из плана (4 тега, 3 триггера, 4 переменные в папке "pm montaz"), затем проверка в среде предпросмотра … Публикации не будет, живая версия 96 остаётся … "Да" на все три пункта сразу?» пользователь ответил: «да». Публикация не разрешена и не выполнялась.

## Резюме
- Создана версия-черновик 97 (аккаунт 6003760261, контейнер 44158621): 4 переменные, 3 триггера, 4 тега, папка «pm montaz». Теги 56 → 60, триггеры 53 → 56. Старые объекты не правились.
- Живая версия осталась 96 (проверено чтением после записи, 12.11.2026).
- Проверка во временной среде (analytics_storage дано, utm_campaign=gtm_test): версия 97 даёт `montaz_calc` (model, length, price_table_open) ×3, `montaz_order_click` (order) ×1 и `block_time` с `montaz_hero/catalog/self_or_us/calculator/faq`; версия 96 (контроль) — только `block_time` с `top`.
- Не проверено: живая отправка формы, событие в отчётах GA4 на живом сайте (до публикации невозможно), мобильный режим, места номера.
- Откат: публиковать ничего не нужно, живая 96; черновик 97 можно не публиковать/удалить. Откат после возможной будущей публикации: `gtm_publish_version.py --account 6003760261 --container 44158621 --version 96 --execute`.

## Версии
- «До» (живая): 96 «Удалён тег «visitsToServer»», тегов 56, триггеров 53.
- Создана: 97 «montaz page: calculator events, block_time», тегов 60, триггеров 56. Рабочая область `pm-montaz-tracking` (id 100).
- «После» (живая): 96, не изменилась.

## Команды и вывод

### 1. Проверка без записи (`gtm_apply_plan.py --plan … `)
```
Живая версия до: 96 «Удалён тег «visitsToServer»», тегов 56, триггеров 53
План: переменных 4, триггеров 3, новых тегов 4, правок тегов 0
  + тег pm montaz calc script <- ['pm montaz page']
  + тег pm montaz block_time script <- ['pm montaz page']
  + тег GA4 - montaz_calc <- ['pm event montaz_calc']
  + тег GA4 - montaz_order_click <- ['pm event montaz_order_click']
Проверка пройдена. Ничего не изменено (нужен --execute).
```
Совпадает с `12_gtm.md`.

### 2. Запись (`gtm_apply_plan.py --plan … --execute`, без --publish)
```
Рабочая область: pm-montaz-tracking 100
Встроенные переменные включены: ['pagePath']
  папка pm montaz 283
  переменная dlv calc_action / dlv calc_model / dlv calc_length / dlv calc_total
  триггер pm montaz page 288
  триггер pm event montaz_calc 289
  триггер pm event montaz_order_click 290
  тег pm montaz calc script 291
  тег pm montaz block_time script 292
  тег GA4 - montaz_calc 293
  тег GA4 - montaz_order_click 294
Версия создана: 97, тегов 60, триггеров 56
Не опубликовано (нужен --publish). Живая версия прежняя.
```

### 3. Проверка версии 97 во временной среде
Команда: `python gtm_test_version.py --account 6003760261 --container 44158621 --version 97 --url "https://mocnaszklarnia.pl/montaz-szklarni?utm_source=google&utm_medium=cpc&utm_campaign=gtm_test" --grant analytics_storage --no-prevent --no-tel-places --no-mobile --click 'label.pm-model[data-model="went"]' 'label.pm-len[data-len="6"]' 'details.pm-prices summary' '[data-pm="order"]' --eval "1"`
Среда claude-test-v97 (id 295), удалена скриптом после проверки. Перехвачено запросов GA4: 11; в Supabase запросов 0 (формы не отправлялись).
```
block_time: 7  (block_name: montaz_calculator ×2, montaz_catalog, montaz_faq, montaz_hero, montaz_self_or_us, top)
montaz_calc: 3  (calc_action: length, model, price_table_open; calc_model=went ×3; calc_length=4 ×1 и 6 ×2; calc_total=1100 ×2, 900 ×1)
montaz_order_click: 1  (calc_action=order, calc_model=went, calc_length=6, calc_total=1100)
```
Ожидание из задания выполнено: montaz_calc (model, length, price_table_open), montaz_order_click (order), block_time с montaz_*.
Замечание: `calc_length=4` один раз и `calc_total=900` — вероятно, состояние калькулятора на момент выбора модели (до выбора длины 6); это предположение по выводу, не проверено отдельно; один прогон.

Контроль, версия 96 (среда claude-test-v96 id 296, удалена):
```
запросов GA4 перехвачено: 1
block_time: 1 (block_name=top, block_seconds=30)
```
montaz_calc и montaz_order_click отсутствуют. Условие «новая версия даёт события, прежняя нет» выполнено.

### 4. Чтение обратно (`gtm_read_container.py --version 97 --summary`, фильтр montaz)
```
Версия 97 (montaz page: calculator events, block_time): тегов 60, триггеров 56
  тег  291 html     pm montaz calc script  <- триггеры ['288']
  тег  292 html     pm montaz block_time script  <- триггеры ['288']
  тег  293 gaawe    GA4 - montaz_calc  <- триггеры ['289']
  тег  294 gaawe    GA4 - montaz_order_click  <- триггеры ['290']
  триггер  288 pageview       pm montaz page
  триггер  289 customEvent    pm event montaz_calc
  триггер  290 customEvent    pm event montaz_order_click
```
Живая (`--summary` без версии): `Версия 96 (Удалён тег «visitsToServer»): тегов 56, триггеров 53`.
Переменные (4) и папка 283 созданы по выводу `--execute`; в сводке `--summary` переменные не перечисляются, отдельным чтением не проверялись.

## Откат
Публикации не было, откат живой версии не нужен (живая 96). Если версию 97 когда-нибудь опубликуют и понадобится вернуться: `python gtm_publish_version.py --account 6003760261 --container 44158621 --version 96 --execute`.
Внимание: следующая рабочая область GTM строится от ПОСЛЕДНЕЙ версии (97), не от живой (96); если черновик не нужен, удалить версию 97 и сделать `versions/96:set_latest` (см. плейбук «Запуск_трекинга_новой_посадочной», ловушки).

## Не проверено
- Живой отправки формы не было (по условию задания); `form_submit` для окон заказа этим прогоном не проверялся (работает на общих тегах контейнера, см. `12_gtm.md`).
- События в GA4 (DebugView/отчёты) на живом сайте: до публикации их нет. После публикации проверять отдельно.
- Мобильный режим (`--no-mobile`) и места номера (`--no-tel-places`) не проверялись.
- Клики по FAQ и дополнительным опциям (extra_*, with_greenhouse, bar_summary, shop_link) не кликались: проверены только model, length, price_table_open, order.
- Регистрация измерений GA4 (`calc_action`, `calc_model`, `calc_length`, `calc_total`) не делалась.
- Режим Manual сессии не проверялся агентом технически; запись прошла без блокировок.

## Публикация 12.11.2026 (по слову пользователя «опубликуй»)
- `gtm_publish_version.py --account 6003760261 --container 44158621 --version 97 --execute`: живая версия 96 → 97 («montaz page: calculator events, block_time»; тегов 60, переменных 18, триггеров 56); прочитано обратно, ОК. Откат: `--version 96 --execute`.
- Проверка на живой странице (Playwright, запросы аналитики и пикселей заблокированы, формы не отправлялись): в dataLayer пришли `montaz_calc` (model/went/4/900; length/went/6/1100; price_table_open/went/6/1100), контейнер GTM-TKGN4NT. Первый `calc_length=4, calc_total=900` — длина по умолчанию у модели `went` до выбора 6 м (расхождение из отчёта агента закрыто).
- Не проверено: фактическая доставка событий в GA4 (нужны согласие и DebugView), регистрация параметров GA4, мобильный режим, тестовая заявка.

## Проверка после тестовой заявки пользователя (12.11.2026, ~15:50-16:00 Варшава)
- Тест: страница с `utm_source=test&utm_medium=test&utm_campaign=test`, согласие «Принять все», калькулятор, окно «Zamów montaż», имя TEST.
- GA4 realtime (`ga4_realtime_events.py --property 349001266 --realtime`, 30 минут по всему ресурсу): `montaz_calc` 3, `montaz_order_click` 2, `form_start` 1, `form_submit` 1. События дошли.
- Не проверено: значения параметров `calc_*` (новые определения появляются в отчётах до 24–48 ч; realtime их не показывает), доходит ли тестовая заявка в CRM и Supabase (проверка по номеру — отдельно); `montaz_order_click` 2 против одной отправки — не разобрано (возможен повторный клик по кнопке).
- Тестовую заявку фильтровать по `utm_campaign=test` и имени TEST.
