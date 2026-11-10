---
name: п-002-политика-health-in-personalized-ads-на-ключах
description: Ключи про травмы отклоняются политикой HEALTH_IN_PERSONALIZED_ADS при создании
status: решена
system: Google Ads API
first_seen: 2026-11-10
updated: 2026-11-10
---

# П-002. Ключи про травмы отклоняются политикой HEALTH_IN_PERSONALIZED_ADS при создании

**Статус:** решена  |  **Система:** Google Ads API

## Симптом (дословно)
Мутация падает: `A policy was violated … [ad_group_criterion_operation > create > keyword > text]`; `policy_violation_details`: `HEALTH_IN_PERSONALIZED_ADS`, `is_exemptible = True` (ключи `car accident lawyer`, `car accident lawyer los angeles`).

## Причина
Google считает юридические запросы о травмах чувствительным здоровьем; ограничивает персонализацию (статус ключей и ссылок «APPROVED_LIMITED»), показ по ключу в поиске по справке не блокирует (на кабинете не проверено).

## Решение / обход
На операции (не на критерии) добавить `exempt_policy_violation_keys` с `policy_name = "HEALTH_IN_PERSONALIZED_ADS"`, `violating_text = <ключ>`: `kop = new_op().ad_group_criterion_operation; k = kop.exempt_policy_violation_keys.add()`. Реализовано в `Скрипты/gads_landver_search_rebuild.py` (`KEYWORD_POLICY_EXEMPT`). Сначала validate_only: он показывает, какие ключи помечены.

## Как проверить
validate_only проходит; после записи ключ в кабинете со статусом ENABLED.

## Как не допустить
При каждом создании ключей по травмам гнать validate_only и добавлять исключение только для помеченных.

## Связано
[[Журнал_изменений]] Landver И-127

## Использовано (когда решение применили повторно)
- —
