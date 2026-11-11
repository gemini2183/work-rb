---
name: project_landver_dg_search_segment_2026_10_26
description: Landver Demand Gen dg_search_segment (Э-10) на 26.10 — включена, цель клика $1, объявления A/B на проверке, что смотреть 27.10
metadata:
  type: project
---

Landver (customer 213-621-6123) Demand Gen `dg_search_segment`, ID 24399007403, создан 26.10 скриптом `Скрипты/gads_dg_search_segment_builder.py` (И-079, Э-10). Сегмент типа SEARCH («искали на Google») из 12 ключей про юриста по ДТП, каналы только Discover и Gmail (YouTube и Display выключены по решению пользователя), бюджет $50 в день, гео как у Search, страница `/california-car-accident-lawyer`. Объявление A со словом injury («Injury Victims Only»), B-страховка без injury, hurt, victim. Пользователь включил кампанию, поставил расписание 08–18 (время кабинета, Лос-Анджелес), «Целевая цена клика» $1 (было $0,50, И-080/И-081), выключил автосоздание видео.

**Why:** в Search клик $25–103, 55 кликов и 0 заявок за 06–22.10; нужна дешёвая проверка другого канала. Потолок цены клика API Demand Gen не принимает (ни при создании, ни правкой) — только в интерфейсе.

**How to apply:** 27.10 первым делом `gads_dg_search_segment_builder.py --customer-id 213-621-6123 --read-back-only` и сводка: одобрены ли A и B (на 26.10 REVIEW_IN_PROGRESS), показы, цена клика, расход. Нет показов при $1 — решает пользователь ($2, $3 шагами). Стоп-правило Э-10: $250 без звонка и формы; промежуточный взгляд на $100; если A отклонено — идём на B, A в обход правил не переписывать. Пороги по CTR и цене клика зафиксировать после первого чистого дня. Связано: [[project_landver_state_2026_10_23]], [[feedback_negate_ambiguous_intent_hard_when_traffic_enough]].
