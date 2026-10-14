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
## [2026-10-09] car+truck / минус-слова | снят broad «near me», добавлено 5 exact (insider accident lawyers, notourproblem org, sweetjames law, call big ike, accident defence attorney) после «да» | гипотеза: «near me» — крупнейший кластер, снятие даст показы; риск — нецелевые запросы | прочитано обратно: 1499 минусов, «near me» нет, 5 на месте; смотреть Search Terms с 10.10, см. Журнал_изменений И-017
## [2026-10-12] car+truck / точные группы + ручное CPC + минусы | созданы «Car Accident - Exact» (23 ключа) и «Truck Accident - Exact» (11), ставка $50, копии объявлений; ставки 4 фразовых групп $0,01 → $25; стратегия Maximize clicks ($50) → Manual CPC; снят broad «costa»/«mission»/«viejo», добавлен phrase «costa rica» | гипотеза: точные ключи дают приоритет идентичным запросам и сокращают мусор среди показов (чужие фирмы); не проверено на кабинете | прочитано обратно: все изменения на месте, 142 позитивных ключа (108 PHRASE + 34 EXACT), 1 497 кампанийных минусов; baseline 06–11.10: 123 показа, 5 кликов, $457,88, 0 конверсий; оценка 2026-10-19; см. Журнал_изменений И-021…И-023
## [2026-10-13] car+truck / гео и минусы | пользователь вручную добавил штат California (критерий 21137, PRESENCE; +30% у LA и Beverly Hills сохранены); после «да» сняты 10 широких минусов с городами (concord, fresno, visalia, redding, bakersfield, oakland, sacramento, chico, oxnard, palmdale), 1 497 → 1 487 | клиент разрешил всю Калифорнию, охват узкий (360 показов, 9 кликов за 06–12.10) | прочитано обратно: минусов 1 487, десяти слов нет | см. Журнал_изменений И-025, И-027; точные минусы с городами не трогали
## [2026-10-14] car+truck / срез 06–13.10 по API, ничего не менялось | после расширения на всю California (13.10) | гипотеза пользователя: фразовые ловят нерелевантное, точные надо расширить, ставку фразовых снизить; не проверено на конверсиях (0 конверсий в Ads, сверки с Ringostat нет) | по дням: 11.10 — 40 показов/4 клика/$88,58; 12.10 — 237/4/$118,64; 13.10 — 466/12/$391,18. За 06–13.10 всего 826 показов, 21 клик, $967,70, 0 конверсий; IS 15%, потеряно по рангу 85%, по бюджету 0%. В search_term_view видно 59% показов и 64% расхода (за 13.10 — 285 из 466 показов и $147 из $391). Видимые запросы: релевантные ДТП-запросы 304 показа/5 кликов/$167; имена и бренды чужих фирм 161 показ/3 клика/$426 (из них $369 — один клик 08.10 при снятом потолке); информационные и испанские 24 показа/1 клик/$25. Точные группы: CPC ~$49 при ставке $50; фразовые: CPC ~$24,5 при ставке $25. Предложения — в чате, на «да» не записывались
