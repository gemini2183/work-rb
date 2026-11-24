---
status: черновик
updated: 2026-11-24
---
# EkspertAgro: индекс in-market по аудитории покупателей (Audience insights) - 24.11

Только чтение. В кабинет не писал, --execute не запускал.

## Что открыл перед работой
- `База_знаний/Агенты/Каталог_операций.md` (поиск composition/insights): строка 107 - это `gads_audiences_audit.py --only-composition`, расшифровка состава Audience-объектов (названия), НЕ индекс аудитории; остальные совпадения - OpenAI Ads insights, не относятся.
- `Скрипты/README.md` (строки ~902-910: affinity/composition) - тот же аудит.
- `Скрипты/gads_audiences_audit.py` целиком в нужной части (строки 225-541): ни `AudienceInsightsService`, ни `GenerateAudienceCompositionInsights` нет; образец доступа: `GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)`, `get_ads_service(login)`, `run(ga, cid, gaql)`, `_lookup_names`.
- `Скрипты/*.py`: Grep по audience_insights/AudienceInsights/composition/index/affinity - совпадения только в `gads_audiences_audit.py` (composition = состав Audience) и README. Отдельных скриптов insights нет.
- `База_знаний/`: Grep по audience insights/AudienceInsights - только `Инструменты/Performance-Max-lead-gen-tCPA-и-сигнал-конверсий.md` (упоминание, не метод). `База_знаний/Проблемы/`: по insights/composition - только П-024 (OpenAI, не относится).
- `10_данные.md` этой папки (итоги разведки) прочитан.

## Размер списка 9475706784 (чтение 24.11, `gads_audiences_audit.py --only-composition --user-list-id 9475706784`)
CRM_BASED, display=12000, search=12000 (то же, что в разведке). Для insights размер достаточен по первому впечатлению, но минимум размера для Audience insights по списку в документации не нашёл: не проверено.

## Что принимает API (по прототипам установленной библиотеки google-ads, v23, файл `...\googleads\v23\services\types\audience_insights_service.py`; на практике НЕ запускал - не проверено на практике)
- `AudienceInsightsService.GenerateAudienceCompositionInsights(customer_id, audience, baseline_audience, data_month, dimensions, customer_insights_group)`.
- Допустимые dimensions: KNOWLEDGE_GRAPH, GEO_TARGET_COUNTRY, SUB_COUNTRY_LOCATION, YOUTUBE_CHANNEL, YOUTUBE_LINEUP, **AFFINITY_USER_INTEREST, IN_MARKET_USER_INTEREST**, LIFE_EVENT_USER_INTEREST, PARENTAL_STATUS, INCOME_RANGE, AGE_RANGE, GENDER.
- `InsightsAudience` содержит поле `user_list` (UserListInfo) - в v21+ (в v20 поля нет). Страна - `country_locations` (LocationInfo, Польша geoTargetConstants/2616). `baseline_audience` - население страны (только country_locations).
- Ответ: по каждой категории метрики состава (доля в аудитории, доля в базе, индекс) - точные имена полей в `AudienceCompositionMetrics` (v23, строка ~45131) скрипту читать из прототипа.
- Не установлено: принимает ли API CRM_BASED-список (ограничения по типу списка, по размеру и по политике данных) и вернёт ли он данные по списку 12 000 для Польши. Выяснится только запуском.

## Пробел: нет скрипта audience insights
Каталог операций, README и `Скрипты/*.py` способа не содержат; одноразовый код сам не пишу. Бриф для script-builder ниже. Альтернативы: см. раздел «Вручную».

## Бриф для script-builder
Задача: общий параметризованный скрипт `D:\GitHub\work-rb\Скрипты\gads_audience_insights.py`. Только чтение, режима записи нет. Привязок к клиенту/списку/стране в коде нет, всё аргументами.

Образец и что переиспользовать: `Скрипты/gads_audiences_audit.py` (импорты и доступ: `GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)`, `get_ads_service`, `run`, `client_stats_dir`, `_name`, `_id`, `_lookup_names` для названий user_interest по id; main/argparse как в audit). Сохранение CSV - как там, в `Клиенты/<клиент>/Статистика/`.

Аргументы:
- `--customer-id` (обязательно), `--client-folder` (обязательно, куда CSV).
- Основа аудитории (одно из): `--user-list-id` (id user_list; в запросе `InsightsAudience.user_list = UserListInfo(user_list="customers/<cid>/userLists/<id>")`), либо `--age`/`--gender` как простой демо-набор (для проверки), либо `--category-id` (user_interest) для «аудитория = in-market категория».
- `--country-geo-id` (по умолчанию 2616 Польша), `--baseline-user-list-id` (необязательно; по умолчанию baseline = вся страна: `country_locations` без других полей).
- `--dimensions` (список, по умолчанию IN_MARKET_USER_INTEREST AFFINITY_USER_INTEREST; допускать остальные из перечня выше).
- `--data-month yyyy-mm` (по умолчанию не задан = последние 30 дней), `--top N` (по умолчанию 15), `--min-share` (отсечь шум; по умолчанию 0, отсечку печатать вслух), `--customer-insights-group` (по умолчанию имя клиента-папки).
- `--api-version` - версия клиента: `user_list` в InsightsAudience есть с v21, в v20 нет; использовать ту версию, что стоит у остальных скриптов (v23); при отсутствии поля сказать ясно.
Вывод: таблица `Dimension | Категория | id user_interest | доля в аудитории | доля в базе | индекс (доля аудитории / доля базы) | in-market доступно для таргета в DG (да/нет по типу dimension)`; сортировка по индексу, топ N на dimension; печатать также размер выборки/размер списка (`size_for_search`), если API его отдаёт; в конец - строка «Ошибка API» дословно, если отказ. Не фильтровать молча: что отброшено по `--min-share` - показать числом.
Проверки: сухой прогон = ровно один вызов API на dimension-набор (read, квоту записывать в `gads_quota_ledger`, если так принято у соседних скриптов); синтаксис; прогон на списке 9475706784 клиента EkspertAgro (customer 8826134558, Польша) как приёмка, но в коде клиента нет. Если API отказывает по списку - вернуть дословный текст ошибки, не обходить (см. раздел «Вручную»).
Обновить: `Скрипты/README.md`, `База_знаний/Агенты/Каталог_операций.md` (одна строка: «Индекс in-market/affinity аудитории (список/категория) против страны» | Ч | `gads_audience_insights.py`), карточку области, если есть.
Оговорка для будущих анализов: индекс по списку - сравнение с населением; не заменяет решение по сигналу конверсий (метод - `Алгоритм_анализа_кампании`, не здесь).

## Ответ на пункты задачи 4 (топ-15 по индексу, пересечение с 6 использованными: 80237, 80253, 80483, 80494, 80501, 80896)
В данных этого нет: скрипта не было, API не вызывали. Таблица будет после запуска `gads_audience_insights.py`.

## Вручную (если скрипт не получится или API откажет)
Не проверено на практике, интерфейс может отличаться:
1. Google Ads, аккаунт 8826134558: Tools > Audience Manager > Audience lists (или Tools > Planning > Audience insights - название зависит от версии интерфейса).
2. Открыть Audience insights, выбрать «Your data» / список «Profimet ekspertagro.pl - уже купившие клиенты» (CRM, 12 000), страна - Польша, период - последние 30 дней.
3. Вкладка «Affinity & in-market» (Audience composition): отсортировать по «Index» (индекс), включить фильтр «In-market», выписать топ-15 с индексом и долей; таблицу «категория / доля / индекс» записать сюда.
4. Для таргета Demand Gen брать только те, что называются в списке In-market segments; id категории - из Audience Manager > Audience segments > Browse > In-market (id user_interest) или через `gads_audiences_audit.py --user-interest-id <id>` по названию.

## Вердикт (8-12 строк)
1. Размер: список 9475706784 CRM_BASED, display=12000, search=12000 (`gads_audiences_audit.py --only-composition --user-list-id 9475706784`, 24.11). Достаточен по размеру, минимум для insights не проверен.
2. Пробел: нет скрипта audience insights (проверено: Каталог_операций.md, README.md, Скрипты/*.py, База_знаний/, Проблемы/). `gads_audiences_audit.py` расшифровывает состав Audience-объектов, индекса не считает.
3. API подходит: `GenerateAudienceCompositionInsights`, dimensions IN_MARKET_USER_INTEREST и AFFINITY_USER_INTEREST, у `InsightsAudience` есть `user_list` (v21+; прототипы google-ads v23 на диске). Не проверено на практике.
4. Не установлено: примет ли API CRM-список и вернёт ли данные для Польши; нужен запуск после сборки скрипта.
5. Бриф для script-builder: `Скрипты/gads_audience_insights.py` (общий, параметры клиент/список/страна/dimensions), в этом файле выше.
6. Топ-15 индекса и пересечение с 6 использованными (80237, 80253, 80483, 80494, 80501, 80896): в данных этого нет, число будет после запуска скрипта.
7. Ручной обход: Audience Manager > Audience insights по списку, шаги в разделе «Вручную» (не проверено на практике).
8. До результата 2-3 категории для новой DG не выбирать: единственное, что есть сейчас - те 6 широких категорий из конфига (без индекса).
9. Новая проблема для реестра: нет способа получить индекс in-market по аудитории покупателей (Пробел, решается скриптом выше).

## Итог ручной проверки 24.11
Источник: скрины пользователя, Google Ads > Audience Manager > Audience insights, база Poland. Через API не получено (отказ для Польши, П-044). Значения - как показал интерфейс, не измерены агентом.

Сегмент «Google-engaged audiences - for Account 8826134558» (не покупатели; 65+ и мужчины):
- in-market: Manufacturing Jobs 4.9x, Lawn Care & Gardening Supplies 4.3x, Agriculture Jobs 4.0x, Pickup Trucks (Used) 3.7x, Pickup Trucks 3.6x, Business & Industrial Products 3.2x, Tools 3.1x, Outdoor Items 3.1x, Climate Control & Air Quality 3.0x, Landscape Design 3.0x
- affinity: Truck & SUV 1.9x, Folk music 1.5x, DIY 1.3x

Сегмент CRM «Profimet ekspertagro.pl - уже купившие клиенты» (9475706784):
- in-market: Lawn Care & Gardening Supplies 3.1x, Business & Industrial Products 2.6x, Outdoor Items 2.3x, Collision & Auto Body Repair 2.0x, Tools 2.0x, Landscape Design 1.8x, Fireplaces 1.7x, Wheels & Tires 1.7x, Electrician Services 1.6x, Plumbing Fixtures 1.6x
- affinity: DIY 1.4x, Truck & SUV 1.3x, Avid Local News Readers 1.2x, Outdoor Enthusiasts 1.2x

Демография CRM-сегмента (на глаз по скрину, не измерено): возраст 35-65+, родителей больше, чем по Польше.

Оговорка: в названии списка «Profimet», состав 12 000 записей не проверен (EkspertAgro или нет).

Основание решения пользователя (24.11, «да, по умолчанию»): обе аудитории дают в верхних in-market строках Lawn Care & Gardening Supplies, Outdoor Items, Tools. Business & Industrial Products тоже в верхах обоих сегментов (3.2x и 2.6x), но в решение не вошла - причина не записана (вопрос к пользователю).

Не проверено: принимает ли API CRM-список 9475706784; совпадает ли состав списка с EkspertAgro.
