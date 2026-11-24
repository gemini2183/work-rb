---
status: открыта
updated: 2026-11-24
---

# П-053: нет общего сборщика Demand Gen; `gads_demand_gen_builder.py` зашит под `dg_lookalike_test`

**Симптом:** `gads_demand_gen_builder.py` создаёт только `dg_lookalike_test`: имя, гео Польша, одна группа, карусель, мультиассет на готовых id картинок, группа ENABLED, гео PRESENCE_OR_INTEREST. Не умеет 2 группы с разными аудиториями и текстами, гео из списка id, загрузку новых картинок без карусели, цель CPA, группы на паузе. Validate_only 24.11 (с именем `dg_montaz_warm_lal`) упал: «Trying to modify the name of an active or paused campaign ... already assigned» (имя `dg_lookalike_test` занято) и 12 строк «Resource was not found» (каскад).

**Что известно:** `gads_dg_yt_builder.py` (только YouTube-видео), `gads_demand_gen_interest_builder.py` (правка констант), `gads_dg_search_segment_builder.py` (один сегмент) не подходят. Бриф script-builder - в `Клиенты\ProfiMet\Работы\2026-11-24_dg_montaz\30_план.md`, «Пробелы», бриф 1.

**Что НЕ установлено:** сохранена ли структура плана в боевом запуске - нет: 24.11 создан `gads_dg_image_builder.py` (новый, в `Скрипты/`), он на боевой задаче проверен только однажды (создание с --execute), повторной проверки нет.

**Обход:** `gads_dg_image_builder.py` (конфиг YAML, PAUSED, read-back) для DG-кампаний с 2 группами. Строка в `Скрипты/README.md` и `Каталог_операций.md` - не проверено, обновлять по плану.

**Найдено:** 24.11.2026, `Клиенты\ProfiMet\Работы\2026-11-24_dg_montaz\30_план.md`, Пробел 1; `40_запись.md`.

**Использовано:** —
