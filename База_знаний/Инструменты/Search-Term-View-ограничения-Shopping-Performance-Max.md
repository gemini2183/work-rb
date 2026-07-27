---
name: search-term-view-ограничения-shopping-performance-max
description: Ограничения ресурса search_term_view Google Ads API для Shopping и Performance Max кампаний
status: протестировано
updated: 2026-07-26
---

# search_term_view — ограничения для Shopping и Performance Max

## Проверенный факт №1: keyword-поля в SELECT молча обнуляют Shopping-строки

`search_term_view` в принципе отдаёт данные по Shopping-кампаниям (таргетинг по
товарному фиду, без ключевых слов) — это не то же самое, что "Shopping вообще
не поддерживается". Но если в GAQL-запросе к `search_term_view` в `SELECT`
одновременно с `search_term_view.search_term` присутствуют поля
`segments.keyword.info.text` и/или `segments.keyword.info.match_type`, то
**все строки Shopping-кампаний исчезают из ответа целиком**, без ошибки и без
предупреждения — просто 0 строк по этим кампаниям, будто там нет данных.

Проверено эмпирически: один и тот же запрос (тот же customer_id, тот же
период) к кампании `Merchant_Shopping` дал:
- **13 848 строк** — без `segments.keyword.info.*` в SELECT
- **0 строк** — с этими полями в SELECT

Причина — Shopping-таргетинг не привязан к ключевому слову, а `segments.keyword`
— обязательный сегмент, требующий непустого значения для попадания строки в
выборку; для Search-кампаний (где ключевые слова есть) те же поля работают
нормально и строки не пропадают.

## Проверенный факт №2: Performance Max не отдаёт search_term_view вообще

Для кампаний `advertising_channel_type = PERFORMANCE_MAX` ресурс
`search_term_view` возвращает 0 строк независимо от состава SELECT — это
задокументированное ограничение API, не связанное с фактом №1. Поисковые
запросы по PMax доступны только через раздел "Insights" в веб-интерфейсе
Google Ads, программного доступа к ним через отчётный API нет.

## Как распознать на практике

- Кампания `advertising_channel_type` = `SHOPPING` (4) и в запросе к
  `search_term_view` есть `segments.keyword.info.*` → подозревать факт №1,
  убрать эти поля и перепроверить.
- Кампания `advertising_channel_type` = `PERFORMANCE_MAX` (10) и
  `search_term_view` пуст независимо от полей → факт №2, это ограничение API,
  не чинится.
- `campaign.advertising_channel_type` и `advertising_channel_sub_type` удобно
  проверить отдельным запросом к ресурсу `campaign`, если непонятно, с каким
  типом кампании имеем дело.

## Что делать

- Не включать `segments.keyword.info.*` в запросы `search_term_view`, если
  среди кампаний могут быть Shopping — использовать только
  `campaign.name`/`ad_group.name`/`search_term_view.search_term` + метрики.
- Если нужно сопоставление поискового запроса с загруженным ключевым словом —
  делать отдельным шагом на своей стороне (сравнение текста запроса со списком
  ключей из `keyword_view`), не одним комбинированным GAQL-запросом.
- Для PMax-кампаний не пытаться получить поисковые запросы через API — явно
  проговаривать пользователю, что это ограничение Google, а не отсутствие
  данных или брак нашего скрипта.

## Статус
Проверено 2026-07-26 в контексте разбора [[../../Клиенты/Корогва/index|Корогва]]
(кампании `Merchant_Shopping` и `Merchant_Performance Max-1`, один аккаунт
845-234-6433). Реализация — [[../../Скрипты/gads_semantics|Скрипты/gads_semantics.py]],
`fetch_search_terms`. См. также [[../../Клиенты/Корогва/Решения|Решения]].
