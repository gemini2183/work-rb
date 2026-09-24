---
name: google-ads-bidding-strategies-shopping-vs-pmax
description: Какие стратегии назначения ставок доступны в Standard Shopping vs Performance Max — и почему PMax не может работать на клики
status: протестировано
updated: 2026-09-24
---

# Google Ads: доступные стратегии ставок — Shopping vs Performance Max

Источники: официальная документация Google Ads Help + несколько
профильных PPC-статей (megadigital, GoDataFeed, jyll.ca — см. ссылки
внизу) + скриншот реального кабинета. Статус — "протестировано": список
для Shopping подтверждён и скриншотом реального кабинета EkspertAgro
(кампания `shop_search`, 2026-09-24), и независимо несколькими профильными
источниками, которые прямо пишут "Target CPA is not available for Shopping
campaigns". Текущая выбранная стратегия конкретных кампаний клиента
проверена через API отдельно, см.
[[../../Клиенты/EkspertAgro/Мерчант/Решения|Решения EkspertAgro — Мерчант]],
запись 2026-09-24.

## ⚠️ Урок: общая документация Google описывает Target CPA неточно применительно к Shopping

Первая версия этой страницы ошибочно включала Target CPA в список для
Standard Shopping — это было взято из общей формулировки официальной
документации Google Ads Help без поправки на конкретный тип кампании.
Скриншот реального диалога "Select your bid strategy" кампании
`shop_search` (EkspertAgro — Мерчант) показал: **Target ROAS, Maximize
clicks, Maximize conversion value (automated) + Manual CPC (manual)** —
без Target CPA. Дальнейшая сверка с профильными PPC-источниками
(megadigital.ai, godatafeed.com, learn.jyll.ca) подтвердила: это не
устаревший UI и не A/B-вариант, а системное ограничение формата — **Target
CPA в принципе не поддерживается для Shopping-кампаний**, только для
Search/Performance Max/Display и др.

Отдельно от этого вопроса: с августа 2026 Google менял механику
target-based стратегий (как они ведут себя при ограниченном бюджете, не
факт наличия/отсутствия) и переименовал ярлыки в июне 2026 ("Maximize
conversions with a Target CPA" → "Target CPA") — эти изменения касаются
Search/PMax/Display/Demand Gen, а не факта отсутствия Target CPA у
Shopping, который был так всегда.

**Урок на будущее:** при вопросах о конкретных опциях интерфейса — не
подавать формулировку из общей документации Google как факт для
конкретного типа кампании без сверки: (1) скриншотом реального кабинета
клиента, если доступен, и/или (2) независимыми профильными
статьями/видео практиков, а не одной страницей поддержки. Тот же паттерн
ошибки уже был с Final URL в feed-only PMax (см.
[[Performance-Max-feed-only|Performance Max feed-only]]).

## Standard Shopping — доступные стратегии (подтверждено скриншотом + профильными источниками)

- **Maximize Clicks** (в Google Ads API — `TARGET_SPEND`) — простая smart
  bidding стратегия, автоматически подбирает ставки, чтобы получить
  максимум кликов в рамках заданного бюджета.
- **Manual CPC** — ручное управление ставками, рекомендуется профильными
  источниками при менее 15 конверсий/мес на кампанию.
- **Target ROAS** — держит средний ROAS на заданном уровне (max. CPC
  бид с оптимизацией под ценность конверсии), рекомендуется при
  достаточном объёме конверсионных данных.
- **Target CPA — недоступен для Shopping-кампаний в принципе**, не путать
  с Performance Max (см. ниже), где это одна из двух базовых стратегий.

## Performance Max — доступные стратегии (жёсткое ограничение)

Только две, обе конверсионные/ценностные:

- **Maximize Conversions** — опционально с Target CPA.
- **Maximize Conversion Value** — опционально с Target ROAS.

**Кликовых стратегий (Maximize Clicks) и Manual CPC в Performance Max нет
вообще** — это архитектурное ограничение формата, PMax в принципе не
работает на кликовых/трафиковых целях, только на конверсионных. Если цель
кампании — объём кликов/трафика, а не конверсии/ценность заказа,
Performance Max для этого не подходит независимо от прочих настроек
(включая feed-only, см. [[Performance-Max-feed-only|Performance Max feed-only]]).

## Важное обновление терминологии (с июня 2026)

Google переименовал ярлыки в интерфейсе, поведение стратегий не
изменилось:
- "Maximize conversions with a Target CPA" → **"Target CPA"**
- "Maximize conversion value with a Target ROAS" → **"Target ROAS"**

Если в интерфейсе клиента видно просто "Target CPA"/"Target ROAS" без
слова Maximize — это тот же механизм, не новая стратегия.

## Как проверить текущую стратегию кампании через API

```
SELECT campaign.name, campaign.bidding_strategy_type
FROM campaign
WHERE campaign.name = "..."
```

Возвращает enum `BiddingStrategyType` (`TARGET_SPEND`, `MANUAL_CPC`,
`MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_CPA`,
`TARGET_ROAS` и др.) — не даёт список ВСЕХ доступных для выбора опций,
только фактически применённую.

## Источники

Официальная документация:
- [About Maximize conversions bidding](https://support.google.com/google-ads/answer/7381968?hl=en)
- [About Maximize conversion value bidding](https://support.google.com/google-ads/answer/7684216?hl=en)
- [Determine a bid strategy based on your goals](https://support.google.com/google-ads/answer/2472725?hl=en)
- [Changes to target based bid strategies](https://support.google.com/google-ads/answer/17061251?hl=en)
- [About Target ROAS bidding](https://support.google.com/google-ads/answer/6268637?hl=en)
- [About Target CPA bidding](https://support.google.com/google-ads/answer/6268632?hl=en)
- [FAQ: changes to Target-based bid strategies](https://support.google.com/google-ads/answer/17125145?hl=en)
- [About automated bidding for Shopping campaigns](https://support.google.com/google-ads/answer/6309029?hl=en)

Профильные PPC-источники (подтверждают отсутствие Target CPA у Shopping):
- [The Best Google Shopping Bid Strategy and Tips to Boost ROAS — megadigital](https://megadigital.ai/en/blog/google-shopping-bid-strategy/)
- [Guide to Google Shopping Bidding Strategies — GoDataFeed](https://www.godatafeed.com/blog/google-shopping-bidding-strategies)
- [Manual vs. Smart Bidding in Google Shopping — jyll.ca](https://learn.jyll.ca/blog/should-you-use-manual-or-automated-bidding-in-google-shopping-campaigns)

Про изменения target-based стратегий 2026 года (терминология/механика, не
факт наличия Target CPA у Shopping):
- [Google Ads Target Bid Strategy Changes: August 2026 — PPC Hero](https://ppchero.com/google-ads-target-bid-strategy-changes/)
- [Google brings back Target CPA and Target ROAS as standalone bidding strategies — PPC Land](https://ppc.land/google-brings-back-target-cpa-and-target-roas-as-standalone-bidding-strategies/)
