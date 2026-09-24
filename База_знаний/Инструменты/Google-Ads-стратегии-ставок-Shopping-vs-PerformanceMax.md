---
name: google-ads-bidding-strategies-shopping-vs-pmax
description: Какие стратегии назначения ставок доступны в Standard Shopping vs Performance Max — и почему PMax не может работать на клики
status: частично протестировано
updated: 2026-09-24
---

# Google Ads: доступные стратегии ставок — Shopping vs Performance Max

Источник: официальная документация Google Ads Help (см. ссылки внизу) —
**разошлась с реальным интерфейсом**, см. предупреждение ниже. Статус —
"частично протестировано": список для Shopping сверен со скриншотом
реального кабинета EkspertAgro (кампания `shop_search`, 2026-09-24), список
для Performance Max — пока только из документации, не проверен на
скриншоте (текущая выбранная стратегия конкретных кампаний проверена через
API, см. [[../../Клиенты/EkspertAgro/Мерчант/Решения|Решения EkspertAgro — Мерчант]],
запись 2026-09-24).

## ⚠️ Расхождение документации с реальным UI

Документация Google Ads Help описывает Target CPA как отдельную доступную
стратегию для Standard Shopping. **На практике, на скриншоте реального
диалога выбора стратегии кампании `shop_search` (EkspertAgro — Мерчант,
2026-09-24), Target CPA в списке НЕТ.** Реальный список в диалоге "Select
your bid strategy":

- Automated bid strategies: **Target ROAS**, **Maximize clicks**,
  **Maximize conversion value**
- Manual bid strategies: **Manual CPC**

Причина расхождения не выяснена — возможно, Target CPA как отдельный пункт
убран Google из этого диалога (доступен только через другой путь
настройки конверсий), либо это A/B-вариант интерфейса, либо документация
просто устарела. **Урок: не доверять списку стратегий из документации без
проверки скриншотом конкретного кабинета** — тот же паттерн ошибки, что
уже был с Final URL в feed-only PMax (см.
[[Performance-Max-feed-only|Performance Max feed-only]]).

## Standard Shopping — доступные стратегии (по скриншоту реального кабинета)

- **Maximize Clicks** (в Google Ads API — `TARGET_SPEND`) — простая smart
  bidding стратегия, автоматически подбирает ставки, чтобы получить
  максимум кликов в рамках заданного бюджета.
- **Manual CPC** — ручное управление ставками.
- **Target ROAS** — держит средний ROAS на заданном уровне (max. CPC
  бид с оптимизацией под ценность конверсии).
- ~~Target CPA~~ — заявлен в документации Google, но отсутствует в
  реальном диалоге выбора стратегии (см. предупреждение выше).

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

- [About Maximize conversions bidding](https://support.google.com/google-ads/answer/7381968?hl=en)
- [About Maximize conversion value bidding](https://support.google.com/google-ads/answer/7684216?hl=en)
- [Determine a bid strategy based on your goals](https://support.google.com/google-ads/answer/2472725?hl=en)
- [Changes to target based bid strategies](https://support.google.com/google-ads/answer/17061251?hl=en)
- [About Target ROAS bidding](https://support.google.com/google-ads/answer/6268637?hl=en)
- [About Target CPA bidding](https://support.google.com/google-ads/answer/6268632?hl=en)
