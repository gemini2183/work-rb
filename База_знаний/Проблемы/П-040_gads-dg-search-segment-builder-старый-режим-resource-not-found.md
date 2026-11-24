---
name: п-040-gads-dg-search-segment-builder-старый-режим-resource-not-found
description: Скрипт создания поискового сегмента в старом режиме падает на validate_only с «Resource was not found» по ad_group; режим --segment-only работает
status: открыта
system: Скрипты / Google Ads
first_seen: 2026-11-23
updated: 2026-11-23
---

# П-040. Скрипт gads_dg_search_segment_builder.py: старый режим падает на validate_only

**Статус:** открыта  |  **Система:** Скрипты / Google Ads  |  **Пометка:** скрипт

## Симптом (дословно)
`Скрипты/gads_dg_search_segment_builder.py` в старом режиме (клиент Landver, customer 213-621-6123), validate_only: `Resource was not found` по ad_group (временные id).

## Что известно
- Оригинал из git HEAD падает так же: дефект существовал до правок 23.11.
- Режим `--segment-only` отработал на EkspertAgro (customer 8826134558) 23.11: создан сегмент 1038964620 (И-003), прочитано обратно: участников 29, все KEYWORD.

## Что НЕ установлено
Причина падения в старом режиме (какой вызов и почему не находит ad_group по временным id) не найдена.

## Обход
Для поисковых сегментов использовать `--segment-only` (validate_only, затем `--execute` по «да»).

## Как проверить
- Старый режим на Landver в validate_only: ожидать ту же ошибку, пока не исправлено.
- `--segment-only` на тестовом сегменте: validate_only, затем чтение обратно.
- Решённым считать, когда старый режим проходит validate_only без ошибки и обход больше не нужен.
