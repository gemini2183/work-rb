---
name: google-ads-editor-bulksheet-csv-format
description: Формат колонок bulksheet CSV для импорта в Google Ads Editor — типы строк, особенности минус-слов
status: протестировано
updated: 2026-08-19
---

# Google Ads Editor — формат Bulksheet CSV

Собранные на практике особенности формата CSV для импорта через Google Ads Editor
(Account -> Import -> From File). Дополняется по мере того, как всплывают новые
Row Type/поля в проектах вики (см. [[../../Клиенты/Andverpersonalinjury/index|Andverpersonalinjury]] —
основной источник, скрипты `Скрипты/gads_geo_ad_group_builder.py`,
`Скрипты/gads_ad_adapter.py`, `Скрипты/gads_campaign_builder.py`).

## Минус-слова (Negative Keyword) — частая ошибка формата

**Протестировано, найден баг 2026-08-19** (см.
[[../../Клиенты/Andverpersonalinjury/Решения|Andverpersonalinjury/Решения]]):
обычная логика "как позитивный keyword, только Row Type другой" НЕ работает.

Неправильно (Editor молча импортирует как ОБЫЧНЫЙ позитивный ключ, без ошибки,
без явного предупреждения — заметно только post-factum по составу группы):
```
Row Type: Negative keyword   (строчная k)
Match Type: BROAD
```

Правильно:
```
Row Type: Negative Keyword   (заглавная K)
Match Type: Negative Broad   (не BROAD — специальное значение)
```

Match Type для минус-слов — отдельный набор значений, не переиспользует
обычные: `Negative Broad` / `Negative Phrase` / `Negative Exact` (а не
`BROAD`/`PHRASE`/`EXACT`).

**Практическое следствие**: если Editor после импорта показывает ключевые
слова из CSV вперемешку без разделения на позитивные/минус (нет визуального
отличия по типу, у группы жёлтый предупреждающий значок) — в первую очередь
проверить именно эти два поля, не Ad group/Campaign.

## Источники

Не протестировано напрямую (внешние источники, использованы для диагностики
бага выше): [Adobe Advertising bulksheet reference](https://experienceleague.adobe.com/en/docs/advertising/search-social-commerce/campaign-management/management/bulksheets/bulksheet-data-formats/bulksheet-data-google),
[Karooya — bulk negative keyword upload guide](https://www.karooya.com/blog/bulk-negative-keyword-addition-with-google-ads-editor/).
