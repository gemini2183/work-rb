---
name: project-brief-andverpersonalinjury
description: Бриф проекта Andverpersonalinjury (Landver Law) — Google Ads, борьба с дорогим/мусорным трафиком personal injury
status: черновик
updated: 2026-08-19
---

# Andverpersonalinjury (Landver Law) — бриф проекта

## Ниша / продукт

Юридические услуги в США — personal injury (травмы/несчастные случаи): car accident,
motorcycle, truck, 18 wheeler, bus, bicycle, pedestrian, slip and fall, dog bite,
catastrophic injury, wrongful death, rideshare (Uber/Lyft). Сайт landverpersonalinjury.com,
бренд в объявлениях "Landver Law". Гео — Калифорния, с фокусом на Los Angeles.

## ЛПР / контакты (роли, не личные данные, если не нужно)


## Цели сотрудничества


## Договорённости (бюджеты, KPI, отчётность — периодичность)


## Ограничения (что нельзя, чувствительные темы, брендбук)


## Технический контекст

Агентство Adwhite (Google Ads), не Redbird (Директ) — общая таблица клиентов
`SHEET_URLS["adwhite"]` в `Скрипты/_config.py` (см. [[../../Инфраструктура|Инфраструктура]]).
Клиент НЕ заведён строкой ни на вкладке "Adwords", ни на "Google_Ads_API" общей
таблицы Adwhite (проверено 2026-08-06) — customer_id пришлось искать в
прод-репозитории `google-cloud-jobs` напрямую.

customer_id `213-621-6123`, доступен через MCC `login_customer_id` `302-348-6398`
(источник: `google-cloud-jobs/adwhite/func/gads_andverpersonalinjury/main.py` —
per-client Cloud Function с захардкоженным customer_id, не через общую таблицу; см.
[[../../Инфраструктура|Инфраструктура]] про паттерн двух поколений job'ов). Локальный
скрипт вики `Скрипты/gads_ads_dump.py` принимает `--customer-id` напрямую, без похода
в таблицу — по этой же причине.

До 2026-08-19 объединён с [[../Desertinjurylaw/index|Desertinjurylaw]] в общей папке
"Юристы США" (см. [[../../Инфраструктура|Инфраструктура]] про причину разделения) —
общая история решений до этой даты осталась в архиве
[[../Юристы США/Решения-архив-до-разделения|Юристы США/Решения-архив-до-разделения]].

## История отношений (кратко, обновляется редко)
