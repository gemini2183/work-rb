---
name: п-007-tilda-canonical-lang
description: Страницы Motorcycle и Pedestrian & Bicycle: пустой lang, у Motorcycle canonical на 404
status: открыта
system: Tilda / страницы
first_seen: 2026-11-10
updated: 2026-11-10
---

# П-007. Страницы Motorcycle и Pedestrian & Bicycle: пустой lang, у Motorcycle canonical на 404

**Статус:** открыта  |  **Система:** Tilda / страницы

## Симптом (дословно)
10.11 17:18: `lang=«»` у Motorcycle и Pedestrian & Bicycle; canonical Motorcycle = `https://landverpersonalinjury.com/motorcycle-accident-lawyer-california` (404). Испанская: `lang=es`, свой canonical — в порядке.

## Причина
Исполнитель не выставил атрибут `lang` и адрес canonical в настройках страницы Tilda.

## Решение / обход
Исполнителю: выставить `lang="en"` и canonical на свой адрес страницы Tilda (задача на 12.11). На рекламу не влияет (не проверено), влияет на индексацию.

## Как проверить
`page_tracking_check.py` показывает `lang=«en»` и свой canonical.

## Как не допустить
Включить пункты в контрольные числа инструкции для исполнителя.

## Связано
[[Задачи]] Landver 12.11

## Использовано (когда решение применили повторно)
- —
