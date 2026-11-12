---
name: openai-ads-ставки-target-cpc-вместо-max-cpc
description: Что значит кнопка «Задать ставку tCPC» в Ads Manager OpenAI и как она соотносится с нашим fixed_bid $20; сроки отключения Max CPC
status: не протестировано
updated: 2026-11-12
---

# OpenAI Ads: Target CPC (tCPC) вместо Max CPC

Внешний источник, в кабинете не проверено; факты по нашим группам — из API.

## Что пишут
- С 9 ноября 2026 в Ads Manager для кликовых кампаний вместо Max Bid / Max CPC появляются Target CPA и Target CPC; существующие кампании остаются на прежней стратегии, пока их не переключат ([relevantaudience.com](https://www.relevantaudience.com/ai/chatgpt-ads-target-cpa-target-cpc-replace-max-bid/), пересказ письма OpenAI рекламодателям).
- Max CPC ограничивает каждую ставку; Target CPC позволяет системе в каждом аукционе ставить выше или ниже цели, стремясь к заданной средней цене клика ([seroundtable](https://seroundtable.com/openai-updates-chatgpt-ads-bidding-options-42470.html)).
- Max Bid и Max CPC отключаются **1 января 2027**; оставшиеся кликовые кампании переведут на Target CPC, значение цели в анонсе не названо (relevantaudience).
- Документация OpenAI: стратегии не гарантируют показ при заданной цене.

## У нас (API 12.11)
- Группы кампании «topics» — `bidding_config.strategy = fixed_bid`, `max_bid_micros = 20 000 000` ($20, потолок цены клика). Кнопка «Задать ставку tCPC» в списке групп — это предложение включить новую стратегию, к нашему $20 она отношения не имеет (в интерфейсе не проверено).
- Включать tCPC без нужды не стоит: у Target CPC нет жёсткого потолка, а у fixed_bid $20 есть (политика риска: не сливать бюджет).
- До 01.01.2027 надо решить, чем заменять fixed_bid в рабочих группах, и поставить осознанную цель, а не дать системе перевести автоматически.
