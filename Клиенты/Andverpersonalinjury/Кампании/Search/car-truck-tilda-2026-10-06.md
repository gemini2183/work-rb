---
status: ВКЛЮЧЕНА с 2026-10-06 (потолок цены клика $30 с 2026-10-09)
updated: 2026-10-09
---

# search / car+truck injuries / s / lp - tilda — подготовка к запуску

Посадочная: https://landverpersonalinjury.tilda.ws/california-car-truck-accident
Источник правды по текстам/ключам/минусам: `car-truck-tilda-генератор.py` в этой же папке (перегенерирует CSV в `Статистика/`).
Стратегическое обоснование — [[../../Решения]], записи 2026-10-06. Паттерн — [[../../../../База_знаний/Паттерны/Google-Ads-Search-юристы-только-пострадавшие-структура-и-фильтрация]].

## Структура (4 группы, все PHRASE)
- Car Accident (25 ключей), Auto Accident (24; auto/automobile/vehicle/motor vehicle/traffic), Truck Accident (28; вкл. commercial/trucking/delivery), 18 Wheeler and Semi (31; 18 wheeler/semi/big rig/tractor trailer). В каждой LA/Beverly Hills варианты.
- Почему так, а не по старым "Injury"-группам: объёмы Keyword Planner (California, не проверено на аккаунте) — `Статистика/gads_keyword_ideas_car_truck_2026-10-06.csv`.

## Объявления
- Закреплены: H1–H3 (все содержат слово про травму: "Injury"/"Injured"/"Hurt"), D1 = "Injured/Hurt in …? We represent injury victims only. …". Остальное не закреплено.
- Только факты со страницы-назначения (20+ лет, 4.8, contingency, defense-side, trial-focused). НЕ используем: "45 years"/"$38.5M" (с основного сайта), "$35.2M…" и т.п. (кейсы библиотеки чужие), "24/7" (клиент работает днём, расписание 08:00–23:00), "Top-Rated".

## Файлы импорта (`Статистика/`)
`gads_bulksheet_car_truck_tilda.csv` (объявления+ключи), `..._campaign_negatives.csv` (49 фраз), `..._group_negatives.csv`, `..._sitelinks.csv`. Формат негативов/sitelinks в Editor не проверен — при отказе вставлять вручную.

## Состояние на 2026-10-06 (конец сессии)
- Сделано пользователем: Norwalk Connecticut → California; лимит Max CPC $25 (решали $30, оставил $25, ежедневный просмотр).
- Коллтрекинг: правила Ringostat внесены, строгая проверка OK на этой странице и dog-bite — [[../../Коллтрекинг/Правила_подмены_car_truck_tilda]].
- НЕ сделано: удалить кампанийный broad-минус "near me" (в gen / init его нет); импорт файлов в Editor, удаление 4 старых групп (Auto/Car/Truck/18 wheeler Injury) с их callouts/snippet; callouts/structured snippet вручную (тексты ниже); Business name asset Disapproved; живой звонок с header; визуальная проверка кнопок.
- Callouts (до 25 знаков): Free Case Review / No Fee Unless We Win / 20+ Years in California / Trial-Focused Preparation / Beverly Hills Office / Contingency Fee Basis / Defense-Side Experience. Structured snippet "Types": Car Accidents, Truck Accidents, 18-Wheeler Crashes, Semi-Truck Crashes, Big Rig Crashes, Delivery Truck Crashes, Rear-End Collisions, Rideshare Crashes.

## Лог действий (append-only)
## [2026-10-06] car+truck / структура | пересобраны 4 группы по словарю запроса | см. Решения 2026-10-06 | не запущена
## [2026-10-09] car+truck / срез по API за 06–09.10 | состояние прочитано через API, ничего не менялось | гипотеза «потолок $25–30 ниже цены аукциона» не подтверждена и не опровергнута | всего 81 показ, 1 клик, $369,30, 0 конверсий. По дням: 06.10 — 2 показа; 07.10 — 0 (с 09:12 до 23:58 пауза); 08.10 — 79 показов, клик за $369,30 при снятом потолке; 09.10 до 14:57 — 0. Показы по группам: Auto Accident 78, Car Accident 3, Truck 0, 18 Wheeler 0. IS 13,7%, потеряно по рангу 86,3%, по бюджету 0%. Все 108 ключей ELIGIBLE, 4 объявления approved. Потолок: $25 → снят 07.10 05:34 → $30 с 09.10 00:36; стратегия всё время Maximize clicks (смены на Maximize conversions в истории нет). На кампании 1495 минус-слов (856 broad, 590 exact, 49 phrase), в т.ч. broad «near me»; из 108 ключей блокируют 2: «rear end collision lawyer» (exact-минус) и «delivery van accident lawyer» (broad «van»). Запросы 08.10 с показами: «insider accident lawyers» (клик $369,30), «notourproblem org», «sweetjames law», «call big ike», «accident defence attorney»
