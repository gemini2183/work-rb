---
name: кейс-anthropic-growth-marketing-claude-code
description: Сырая выжимка внешнего кейса Anthropic (Growth Marketing team) — агентная генерация RSA-объявлений через Claude Code, slash-команда /rsa, два саб-агента, лог экспериментов
updated: 2026-07-29
---

# Кейс Anthropic: Growth Marketing team + Claude Code (генерация объявлений)

Неизменяемый сырой материал — собран из официального поста Anthropic и нескольких
независимых пересказов (кросс-проверено, детали совпадают). Один нетехнический
маркетолог (Austin Lau) в одиночку выстроил на Claude Code весь Growth Marketing
процесс за счёт агентных workflow, без единой строчки кода, написанной вручную.

## Источники

- Официальный пост: https://claude.com/blog/how-anthropic-teams-use-claude-code
- Официальный PDF (whitepaper, "How Anthropic teams use Claude Code"):
  https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf
  (не удалось распарсить содержимое напрямую — PDF отдаёт бинарные потоки)
- Разбор с наибольшей технической детализацией (подтверждён независимо):
  https://cc4.marketing/blog/anthropic-growth-marketing-claude-code/
  и https://blog.coupler.io/claude-code-for-marketing/
- Дополнительно (числа/результаты): https://www.gend.co/blog/anthropic-claude-ad-creation-30-seconds,
  https://gigazine.net/gsc_news/en/20260225-how-anthropic-uses-claude-marketing/

## Итоговые результаты (заявлены Anthropic)

- Время создания одного объявления: 2 часа → 15 минут.
- Другая метрика в том же материале: 30 минут → 30 секунд (вероятно, для более
  узкой операции внутри процесса, не для полного цикла — источники не разводят
  однозначно, какая цифра к какому шагу относится).
- 10-кратный рост объёма выпускаемых креативов.
- Отдельно — Figma-плагин, который находит фреймы и генерирует до 100 визуальных
  вариаций перестановкой заголовков/описаний (не относится к текстовой генерации
  как таковой, отдельная часть workflow).

## Архитектура: slash-команда `/rsa`

Custom slash-команда `/rsa` — единая точка входа. Дословно (cc4.marketing /
coupler.io, независимо совпадает):

> "A custom slash command pulls in campaign data, existing copy, and keywords,
> then cross-references against predefined skills containing Anthropic's brand
> voice and Google Ads best practices."

То есть на вход команда получает:
- данные кампании,
- существующий копирайт (текущие объявления),
- ключевые слова,

и сверяется с заранее сохранёнными **Agent Skills**, которые содержат голос
бренда и best practices конкретной площадки (в их случае — Google Ads RSA).

## Два саб-агента — разделение по формальному ограничению, не по смысловой роли

Дословно:

> "Two specialized sub-agents split the work: one writes headlines (30-character
> limit), the other writes descriptions (90-character limit). Splitting by
> constraint means fewer edge-case failures."

Важный нюанс: разделение сделано **по формальному полю RSA-формата** (headline
30 символов / description 90 символов), а не по смысловой роли ("хук" vs
"оффер"). Обоснование в источнике — так меньше ошибок на граничных случаях
(агент не путает лимиты разных типов текста, если у него всегда один лимит).

## Experiment memory system (лог экспериментов)

Дословно:

> "The experiment memory system. It logs hypotheses and test results from each
> round of ad iteration. When launching new variants, Claude pulls all prior
> test data so the next round builds on what already worked."

То есть: после каждого раунда фиксируются гипотеза + результат теста. При
следующем раунде генерации весь предыдущий лог подтягивается в контекст, чтобы
не повторять неудачные ходы и опираться на подтверждённо успешные.

## Выход

Дословно: "The system packages results into a CSV ready for upload." —
валидированный по длине текста CSV, готовый к ручной загрузке в кабинет.
Никакой автоматической публикации — человек проверяет перед загрузкой.

## Что осталось непрояснённым даже после кросс-проверки нескольких источников

- Точный текст системных промптов саб-агентов — нигде не процитирован дословно.
- Точная структура файла/файлов Agent Skills (как физически организован голос
  бренда + best practices площадки).
- Точный формат/схема лога экспериментов (JSON? Markdown? база?).
- Критерий, по которому Selection-шаг (упомянут в пересказах вскользь как
  "identifies underperformers") определяет "слабое" объявление — метрика и
  порог нигде не названы.

Это ограничения источника, а не нашего анализа — если появится более подробный
разбор (например, если whitepaper удастся прочитать целиком), эту страницу
нужно дополнить, не переписывая.
