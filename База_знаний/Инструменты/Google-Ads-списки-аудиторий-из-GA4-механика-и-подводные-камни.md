---
name: google-ads-ga4-audience-lists-mechanics
description: Как аудитории GA4 попадают в Google Ads как списки, чем размеры отличаются, что происходит при удалении, какие списки бывают
status: проверено на проекте ProfiMet 2026-10-07 (Google Ads API v23, GA4 Admin API, GTM); пункты «не проверено» помечены
updated: 2026-10-07
---

# Списки аудиторий Google Ads из GA4: механика и подводные камни

Выводы получены на практике на ProfiMet (см. [[../../Клиенты/ProfiMet/Аудитории/Справочник_списков]]), не из документации. Что взято из общих знаний — помечено.

## Откуда берутся списки в аккаунте

- **Аудитория GA4 → список Ads.** Если ресурс GA4 связан с Ads, аудитории GA4 выгружаются в Ads как списки «Website visitors», тип REMARKETING, **только для чтения** (`read_only = True`). Срок жизни списка равен сроку аудитории. Определение условий в Ads не видно, читать его надо в GA4 (Admin API `audiences.list`, с ключом, у которого есть доступ к ресурсу; интерфейс GA4 → Admin → Аудитории).
- **Customer Match (CRM)** — тип CRM_BASED, редактируемый, ключ — контактные данные; в описании списка можно записать, как он обновляется.
- **Системные Google** (RULE_BASED): `All visitors (AdWords)` с копиями `(system-defined)`, `All Converters`; LOGICAL: `AdWords optimized list`.
- **Видны только в интерфейсе** (в API `user_list` не отдаются): автосписки «Conversion-based» (по типам конверсий) и «Google-engaged audiences».
- **Похожие аудитории (Similar)** остались в аккаунте пустыми; API их не удаляет (ошибка «read-only user list types»), в интерфейсе в нашем случае не нашлись. Что формат закрыт Google в 2023 — из общих знаний, не проверено.

## Почему размер в Ads меньше, чем в GA4

Ads считает только тех, кого сопоставил с рекламным профилем; нужно согласие (на ProfiMet GA4 стартует только после «принять все» на cookie-баннере) и GA client id. По корзине: 2 289 пользователей GA4 → 960 на Display (~42%). События, отправляемые серверно без браузера (Ringostat для звонков на статические номера), создают в GA4 отдельных «пользователей» без профиля — в Ads они не доходят: «Лиды» 1 692 в GA4 и 24 в Ads. Размеры в Ads округлены и показываются отдельно по сетям (Search, YouTube, Display, Gmail), маленькие помечены «Too small to serve».

## Операции через API (проверено 2026-10-07)

- Удаление списка: `UserListService.mutate_user_lists` с `remove`; Google принимает и для `read_only` списков из GA4 (`validate_only` и реальное удаление); отклоняет типы Similar и Look-alike.
- **Критерии подключения при удалении списка не удаляются.** Остаются критерии, ссылающиеся на удалённый список. Порядок: сначала снять подключения (`CampaignCriterionService`/`AdGroupCriterionService` с `remove`), потом удалять списки.
- Исключения на уровне кампании — `campaign_criterion` типа USER_LIST с `negative = True`; режим группы объявлений Targeting/Observation — в `ad_group.targeting_setting.target_restrictions` (`bid_only`).
- Автосписки «Conversion-based» через API `user_list` не видны, но их критерии в кампаниях есть и снимаются обычным удалением критерия.
- Пробные (trial) кампании экспериментов нельзя ставить на паузу напрямую (ошибка «Cannot modify … status of a trial campaign»); для кампаний, у которых эксперимент остановлен, можно вешать ярлык.
- Удалённые из Ads списки GA4 может создать заново, пока аудитория существует в GA4 — **не проверено** (проверка на ProfiMet 2026-10-08).

## Диагностика «почему список не копится»

1. Прочитать определение аудитории в GA4 (Admin API).
2. Сравнить число пользователей аудитории в GA4 (Data API, измерение `audienceName`, метрика `totalUsers`) с размером списка в Ads: ~40% — норма для событий из браузера с согласием; в разы меньше — признак событий без браузера (серверные, Measurement Protocol).
3. Профилировать событие по `deviceCategory` и `sessionDefaultChannelGroup`: 100% «desktop» и «Unassigned» — безличные серверные события.
4. Проверить, не обвалилось ли само событие по неделям (при смене сайта или GTM).

## Метки «Customer Type» (тип клиента) у списков

Источник: официальная справка Google «About audience customer types» (support.google.com/google-ads/answer/14443483) и профильные PPC-новости; **в наших кампаниях не перепроверено.** Метки («Purchasers», «Cart abandoners», «Qualified leads», «Disengaged customers», «High value customers» и др.) ставятся на собственные списки вручную в Audience Manager или автоматически (при настройке целей жизненного цикла, при синхронизации некоторых аудиторий GA4). Используются целью «привлечение новых клиентов»: «Purchasers» определяют существующих клиентов (режимы «ставить выше за новых», «только новые»).

Проверено через API (ProfiMet 2026-10-07): ресурс `user_list_customer_type` (список + категория; PURCHASERS = 3), цель по кампаниям — `campaign_lifecycle_goal.customer_acquisition_goal_settings.optimization_mode` (TARGET_ALL_EQUALLY / TARGET_NEW_CUSTOMER; в запросе `campaign.name` вместе с этим ресурсом даёт ошибку, брать `campaign_lifecycle_goal.campaign` и сопоставлять отдельно), ценности — `customer_lifecycle_goal`. **Подводный камень:** метка «Purchasers» на широком списке (все посетители) при режиме «только новые клиенты» может отсекать всех бывавших на сайте.
