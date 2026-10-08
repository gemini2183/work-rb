---
name: demand-gen-каналы-и-миграция-display
description: Управление каналами в Demand Gen (можно выключить YouTube) и перевод Display-кампаний Google в Demand Gen в 2026 году; что теряется и что добавляется
status: не протестировано (по официальным страницам, проверено 2026-10-08)
updated: 2026-10-08
---

# Demand Gen: каналы и миграция Display

## Управление каналами (Channel controls)
Источник: [Channel controls in Demand Gen campaigns](https://support.google.com/google-ads/answer/15973205?hl=en), проверено 2026-10-08.
- Настройка на уровне **группы объявлений**.
- Ручной режим «Let me choose»: YouTube (in-stream, in-feed, Shorts), Discover, Gmail, Maps, Google Display Network. YouTube можно исключить целиком.
- Google рекомендует «All Google channels» для большинства рекламодателей (автораспределение бюджета); не все каналы совместимы с каждым типом объявления и аудитории.
- Сравнение: в Performance Max каналом управлять нельзя ([[Performance-Max-площадки-инвентарь-и-исключения]]).

## Display переезжает в Demand Gen
Источник: [Google display ads campaigns have a new home in Demand Gen](https://support.google.com/google-ads/answer/17051545?hl=en-GB), проверено 2026-10-08.
- С июня 2026 — инструмент миграции; позже в 2026 новые Display-кампании можно создавать только внутри Demand Gen; позже — автоматический перевод оставшихся подходящих кампаний.
- Старые Display-кампании получают статус Removed (остаются для отчётов до 5 лет), откатить нельзя.
- Теряется: ручной CPC, оптимизация по видимым показам, модель оплаты за конверсии, корректировки ставок и сезонности, комбинированные аудитории, часть исключений на уровне группы.
- Добавляется: YouTube, Discover, Gmail, Maps (бета), карусели, видеоформаты, lookalike-сегменты, Target CPC (не то же, что ручной CPC), отчёт по форматам.
- Таргетинг по площадкам и исключения контента сохраняются.
- Что это значит для ProfiMet: Display-кампании `dspl_rtg_basket`, `dspl_rtg_engage_mid` используют Maximize clicks с потолком цены клика (не ручной CPC); сохранится ли потолок после миграции — не проверено.
