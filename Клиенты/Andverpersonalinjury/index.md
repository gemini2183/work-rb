---
name: client-index-andverpersonalinjury
description: Точка входа по клиенту Andverpersonalinjury (Landver Law, Google Ads)
status: активный
updated: 2026-08-19
---

# Andverpersonalinjury (Landver Law) — индекс

Текущий статус одной строкой: агентство Adwhite (Google Ads), customer_id
`213-621-6123`, сайт landverpersonalinjury.com. 2026-08-19 выделен в отдельную папку
из бывшей объединённой "Юристы США" (см. [[../../Инфраструктура|Инфраструктура]]) —
общая история до этой даты в архиве
[[../Юристы США/Решения-архив-до-разделения|Юристы США/Решения-архив-до-разделения]].
Составлено полное описание источников трафика — см. [[Источники-трафика]]. Ключевая
находка (аудит 2026-08-19): Search Partners в чистых Search-кампаниях ("search / car
accident / ca - google search + network", "search / all injuries") даёт много кликов
почти без конверсий с search-arbitrage доменов — решение об отключении на уровне
кампании ждёт пользователя, см. [[Задачи]]. Параллельно идёт верификация Google Local
Services Ads (LSA) как альтернативного pay-per-lead канала — почти пройдена (блокер:
"Lawyer license" всё ещё "Processing"), см. [[Решения]], записи 2026-08-19.

- [[_project]] — бриф
- [[Источники-трафика]] — полная карта источников трафика (Search/Search Partners/PMax/Display/Discover/YouTube/Maps/LSA)
- [[Цели/goals]] — цели аналитики
- Семантика/ — статус проработки ключей + [[Семантика/Словарь-тем|Словарь-тем.yaml]] (тема → синонимы/модификаторы для `Скрипты/gads_semantics_generator.py` и `gads_campaign_builder.py`)
- Аудитории/ — сегменты ретаргетинга
- Кампании/Search/ — логи по кампаниям + [[Кампании/Search/Эталонное-объявление-и-sitelinks|Эталонное-объявление-и-sitelinks.yaml]] (шаблон RSA-объявления для `Скрипты/gads_ad_adapter.py`)
- Коллтрекинг/Пул_номеров.yaml — пул номеров и правила подмены Ringostat, для `Скрипты/phone_swap_check.py`
- Статистика/ — снапшоты
- [[Решения]] — стратегический лог
- [[Задачи]] — to-do список по клиенту
