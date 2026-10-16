---
status: не протестировано
updated: 2026-10-15
---

# Google Ads Search: корректировка ставки по местоположению — только на уровне кампании

**Не проверено на практике** в кабинете (не пробовали поставить на группу через интерфейс или API); факт из официальной справки, подтверждён профильными источниками.

## Факт
- В поисковых кампаниях корректировка ставки по местоположению (location bid adjustment, −90%…+900%) задаётся **только для кампании**: в справке Google «About bid adjustments» в разделе «Where you can use them» для Location указано только «Campaigns». Для устройств — кампания и группа.
- Значит, повышение +X% для города действует на **все группы** кампании (фразовые, точные, тематические), исключить из него отдельную группу нельзя.
- В API location-модификатор — `campaign_criterion.bid_modifier` у критерия location; `AdGroupBidModifier` для location не используется (старые ответы команды AdWords API на форуме: на уровне группы — только платформа/устройство).
- На Smart Bidding (tCPA/tROAS/Max conversions) ручная корректировка по местоположению не применяется (кроме −100%), см. [[Google-Ads-Smart-Bidding-и-корректировки-ставок]]; на Manual CPC — применяется.

## Как получить «повышение только для точных/городских групп»
1. Ставка группы: поднять ставку конкретной группы (например, группы с городом в запросе) — она действует только на её ключи.
2. Убрать или уменьшить корректировку по местоположению кампании и компенсировать ставками групп. Цена: генерические ключи (например «car accident lawyer» без города) теряют повышение для людей, которые физически в этом городе — а большинство ищет без названия города.
3. Если не хочется двойного повышения (ставка группы под город × корректировка по городу) — ставку такой группы задавать как «целевая ставка ÷ (1 + корректировка)».
4. Отдельная кампания под гео — единственный способ иметь разные гео-повышения для разных наборов ключей; минус: делятся бюджет и минус-слова.

## Пример
Landver car+truck 2026-10-15: +30% у Los Angeles и Beverly Hills на уровне кампании, группа «Car Accident - LA/BH Exact» $70 → для людей из LA до $91. Вопрос пользователя «повышение только на точные, не на фразовые» — см. [[../../Клиенты/Andverpersonalinjury/Решения|Решения]] 2026-10-15.

## Источники
- [Google Ads Help — About bid adjustments](https://support.google.com/google-ads/answer/2732132)
- [Google Ads Help — Edit bid adjustments (hotel campaigns): locations only at campaign level](https://support.google.com/google-ads/answer/9263007)
- [KlientBoost — Google Ads bid adjustments](https://klientboost.com/google/bid-adjustments/)
- [Karooya — set bid adjustments: location, device, ad scheduling](https://www.karooya.com/blog/set-bid-adjustments-adwords-location-device-ad-scheudling)
- [AdWords API forum — bid adjustments (location через CampaignCriterion)](https://groups.google.com/d/msg/adwords-api/AEN5oxE3m9E/tEp8dUDmb3EJ)
