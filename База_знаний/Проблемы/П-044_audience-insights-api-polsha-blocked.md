---
status: обходится
updated: 2026-11-24
---

# П-044: Audience insights API отказывает для Польши

**Система:** Google Ads API, `Скрипты/gads_audience_insights.py` (сервис `AudienceInsightsService.GenerateAudienceCompositionInsights`).
**Клиент:** EkspertAgro, customer 8826134558, список CRM 9475706784.
**Найдено:** 24.11.2026, ~10:07 (по данным пользователя).

## Симптом (дословно)
`Request validation error: Location [2616] is not supported for insights`, BLOCKED_VALUE, INVALID_ARGUMENT, request_id `yag2gxR-JZNXbhF_ohwPHw`. Отказ и для audience, и для baseline_audience (страна 2616 = Польша).

## Что известно
- Скрипт при отказе печатает текст ошибки дословно, таблицу не получили.
- Ручной путь в интерфейсе работает: Audience Manager > Audience insights, база Poland. Проверено пользователем 24.11 (скрины).

## Что НЕ установлено
- Принимает ли API CRM-список 9475706784 (до него запрос не дошёл).
- Поддерживаются ли другие страны (`--country-geo-id`) - не пробовали.

## Обход
Audience Manager > Audience insights в интерфейсе Google Ads. Результат записан в `Работы/2026-11-24_DG_YT_inmarket_lookalike/15_insights.md`.

## Как проверить
Повторить `gads_audience_insights.py --customer-id 8826134558 --client-folder EkspertAgro --user-list-id 9475706784` (только чтение); если отказ тот же - обход остаётся. Другая страна: `--country-geo-id <id>`.

## Использовано
- 24.11: обход через интерфейс, индекс получен вручную (см. выше).
