---
name: п-011-windows-кодировка-вывода-python
description: UnicodeEncodeError cp1251 при печати кириллицы и символов (★)
status: решена
system: Окружение
first_seen: 2026-11-10
updated: 2026-11-10
---

# П-011. UnicodeEncodeError cp1251 при печати кириллицы и символов (★)

**Статус:** решена  |  **Система:** Окружение

## Симптом (дословно)
`UnicodeEncodeError: 'charmap' codec can't encode character '\u2605'`.

## Причина
Консоль Windows в cp1251.

## Решение / обход
Запускать `PYTHONUTF8=1 python …` (или `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`).

## Как проверить
Вывод без ошибок.

## Как не допустить
Всегда `PYTHONUTF8=1`.

## Связано
[[CLAUDE]]

## Использовано (когда решение применили повторно)
- —
