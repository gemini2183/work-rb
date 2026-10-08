---
name: performance-max-площадки-инвентарь-и-исключения
description: Как ограничить мусорный трафик PMax на YouTube/Discover/Display: типы инвентаря, исключения площадок, отчёт по каналам, как снять разбивку через API
status: частично протестировано (разбивка по каналам и площадкам через API на ProfiMet 2026-10-08; сами исключения не применялись)
updated: 2026-10-08
---

# PMax: каналы, площадки, типы инвентаря и исключения

## Что нельзя
По справке Google ([channel performance report](https://support.google.com/google-ads/answer/16260130?hl=en), проверено 2026-10-08): "you can't directly control budget allocation per channel"; исключить канал целиком или урезать бюджет на YouTube/Display нельзя. Влиять можно ассетами, сигналами аудиторий и конверсиями.

## Типы инвентаря (Content suitability, уровень аккаунта)
Источник: [How to use brand suitability features in Performance Max](https://support.google.com/google-ads/answer/13607727?hl=en), проверено 2026-10-08.
- **Maximum inventory** — весь доступный инвентарь; самое чувствительное отсекается автоматически.
- **Moderate inventory** — убирает сильную брань, драматизированное насилие и сексуально откровенные темы.
- **Limited inventory** — ещё умеренную брань и откровенное даже в обычном контенте; Google рекомендует только брендам со строгими требованиями.
Действует на YouTube, Display и видеопартнёров. **Про детский контент в справке ничего нет** — тип инвентаря детские ролики не убирает.

## Что убирает конкретные площадки
- **Исключения площадок на уровне аккаунта** (Tools → Content suitability): YouTube-каналы, ролики, сайты, приложения; PMax их соблюдает; до 20 000 за раз, всего до 65 000 ([Exclude placements at the account level](https://support.google.com/google-ads/answer/7331110?hl=en), из выдачи). Действуют на **все кампании аккаунта**.
- **Минус-слова** в PMax — только Search и Shopping; для Display и видео используются исключаемые ключевые слова контента (Content Suitability).

## Как снять разбивку через API (ProfiMet, google-ads 29, API v23)
- По каналам: `FROM campaign` с `segments.ad_network_type` (значения SEARCH, DISCOVER, YOUTUBE, CONTENT, SEARCH_PARTNERS, MIXED), метрики расход, клики, конверсии.
- По площадкам: `FROM performance_max_placement_view`, в SELECT обязателен `campaign.id`; поля `display_name`, `placement_type`, `placement`, метрика показы (сортировка по показам).
- Конверсии по действию в разрезе канала: `segments.ad_network_type` вместе с `segments.conversion_action_name`.

## Что нашли на ProfiMet (`pmax1_test`, 2026-10-08, конверсии Ads)
01.09–08.10: Search 42% расхода, 68% конверсий, CPA 23 €; Discover 31%, 21%, 57 €; YouTube 27%, 11%, 88 €. YouTube-показы — в основном детские ролики («Śpiewające Brzdące», «Baby Shark», «Peppa» и т. п.) и новостные клипы. Полная таблица — [[../../Клиенты/ProfiMet/Кампании/РСЯ_КМС/pmax1_test]]. Гипотеза: исключения площадок снизят долю YouTube; не проверено.

## Видео в PMax и автогенерация ассетов (ProfiMet, API, 2026-10-08)
- Видео в группах ассетов видны через `asset_group_asset` (`field_type = YOUTUBE_VIDEO`). В `pmax1_test` во всех 6 включённых группах по 2 видео; в `pmax01` в единственной включённой группе тоже 2.
- Настройки автоматизации ассетов кампании: `campaign.asset_automation_settings` (типы `TEXT_ASSET_AUTOMATION`, `GENERATE_IMAGE_ENHANCEMENT`, `GENERATE_IMAGE_EXTRACTION`, `GENERATE_ENHANCED_YOUTUBE_VIDEOS`, `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION`; статусы OPTED_IN / OPTED_OUT). В `pmax1_test`: автогенерация YouTube-видео выключена, расширение URL для текстов выключено.
- По справке Google (страница про группы ассетов): «Our system is able to automatically generate videos based on the assets provided» — без своих видео Google может создать их сам, если автогенерация включена. Будет ли PMax без видео и с выключенной автогенерацией показываться на YouTube — не проверено, это и есть предмет теста.

## Как собрать список детских YouTube-каналов для исключения (метод, ProfiMet, 2026-10-08)
1. Выгрузить площадки PMax: `performance_max_placement_view` (`placement` = id видео, `display_name` = название; метрика только показы; сортировать по показам).
2. По видео найти канал: `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=<id>&format=json` → `author_name`, `author_url` (@handle). Быстро и без ключа; для удалённых видео ответ 401/403/404.
3. Идентификатор канала (UC…, 24 знака) со страницы `@handle` — брать из `<link rel="canonical" href=".../channel/UC…">`, **не** из первого `"channelId"` в коде страницы (там бывают чужие каналы); проверять уникальность ID.
4. Расширить заранее: поиск YouTube по детским запросам на разных языках (`results?search_query=…&sp=EgIQAg%3D%3D`, фильтр «каналы»), брать каналы от 50 тыс. подписчиков; результат вычитывать вручную — попадаются сельхозканалы, религиозные, музыка для сна.
5. Записать в исключения аккаунта: `customer_negative_criterion` с `youtube_channel.channel_id`, пачками по 100, сначала `validate_only`. Скрипт — `Скрипты/gads_exclude_youtube_channels.py`.
6. Результат ProfiMet: 726 каналов; топ-4000 видео выборки (88.8 тыс. показов) на 66% приходятся на эти каналы (по показам, не по расходу). Эффект на долю расхода YouTube — измерять через 2 недели (`segments.ad_network_type`).
