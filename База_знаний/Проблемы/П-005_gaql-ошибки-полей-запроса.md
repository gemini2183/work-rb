---
name: п-005-gaql-ошибки-полей-запроса
description: GAQL: `Unrecognized fields` и `campaign.id must be present in SELECT`
status: решена
system: Google Ads API
first_seen: 2026-11-10
updated: 2026-11-10
---

# П-005. GAQL: `Unrecognized fields` и `campaign.id must be present in SELECT`

**Статус:** решена  |  **Система:** Google Ads API

## Симптом (дословно)
`ad_group_asset.policy_summary.*`, `campaign.url_expansion_opt_out`, `campaign.start_date` — «Unrecognized fields»; при фильтре `WHERE campaign.id = …` — «The following field must be present in SELECT clause: campaign.id»; в API v23 у `campaign_criterion` атрибут типа называется `type_`, а не `type`.

## Причина
Особенности схемы GAQL v23.

## Решение / обход
Политику ссылок читать через `asset.policy_summary.approval_status` и `ad_group_asset.primary_status`/`primary_status_reasons`; в SELECT добавлять `campaign.id` (или `ad_group.id`) при фильтре по нему; в Python обращаться `c.type_`.

## Как проверить
Запрос возвращает строки.

## Как не допустить
Перед новым запросом — сверить поле по готовым скриптам (`gads_campaign_state_dump.py`).

## Связано
[[Хроника_2026-11]]

## Использовано (когда решение применили повторно)
- —
- 2026-11-11: `gads_clone_plan.py` — `The following field must be present in SELECT clause: 'campaign.id'` при фильтре `WHERE campaign.id` у `campaign_asset`, `ad_group_asset`, `ad_group_criterion`; функция `q` теперь подставляет `campaign.id` в SELECT сама.
