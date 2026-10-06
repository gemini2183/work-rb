---
status: подготовлена, не запущена (Paused)
updated: 2026-10-06
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
