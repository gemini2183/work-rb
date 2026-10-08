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
