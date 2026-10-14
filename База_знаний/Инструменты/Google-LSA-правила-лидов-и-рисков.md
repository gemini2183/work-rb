---
name: google-lsa-правила-лидов-и-рисков
description: Правила Google Local Services Ads (LSA) — оспаривание лидов, оплата пропущенных звонков, расписание показа, переход на Performance Max
status: не протестировано
updated: 2026-08-19
---

# Google Local Services Ads (LSA) — правила лидов и рисков

Собрано из официальных источников Google (support.google.com) 2026-08-19 по
запросу для [[../../Клиенты/Andverpersonalinjury/index|Andverpersonalinjury]]
(верификация LSA завершена в этот же день, канал только что запущен, см.
[[../../Клиенты/Andverpersonalinjury/Решения|Andverpersonalinjury/Решения]]).
Статус "не протестировано" — из внешних источников, не проверено на практике
на аккаунтах вики.

## Оспаривание нецелевых/невалидных лидов

Ручного оспаривания больше нет — заменено на **Auto Crediting System**:
- лид оценивается ML-моделью в момент первого контакта; невалидный сразу не
  тарифицируется
- уже оплаченный лид может быть переоценён позже, кредит начисляется
  автоматически (обычно в течение 30 дней)
- **лиды "job type not serviced" / "geo not serviced" НЕ кредитуются вообще**
  — ни автоматически, ни по запросу
- дополнительно credits недоступны для health care вертикалей, tax
  specialists, рекламодателей EMEA
- единственный оставшийся канал влияния — форма "Rate this lead" на странице
  лида (не гарантия возврата, сигнал алгоритму на будущее)

Источники: [About Automated Local Services Ads lead credits](https://support.google.com/localservices/answer/15100654),
[Local Services Ads Deprecates Lead Disputes — Blue Corona](https://www.bluecorona.com/blog/google-local-service-ads-lead-dispute-deprecation)

**Следствие**: раз "не та услуга" не возвращается в принципе, единственная
защита — превентивная (таргетинг категорий услуг), не постфактум-оспаривание.
В LSA нет ключевых слов/минус-слов, как в обычном Search — таргетинг только
через чекбоксы "сфер деятельности и услуг".

## Оплата пропущенных звонков

Валидным (оплачиваемым) лидом официально считается:
- звонок, на который ответили и поговорили с клиентом
- звонок, оставленный на голосовую почту (даже без ответа)
- пропущенный звонок БЕЗ голосового сообщения — становится оплачиваемым,
  только если бизнес сам перезвонил/написал в ответ и состоялся контакт

Источник: [How leads work — Local Services Help](https://support.google.com/localservices/answer/7195435)

Отдельно от оплаты — пропущенные звонки официально снижают показатель
отзывчивости (responsiveness), а он влияет на ранжирование/частоту показа
объявления ("Missed calls may negatively affect your responsiveness").

Источники: [About ad rankings — Local Services Help](https://support.google.com/localservices/answer/7527305),
[Google LSA Missed Calls Cost You Twice — Tradesly AI](https://www.tradesly.ai/blog/google-lsa-missed-calls-ranking-penalty)

## Расписание показа объявления (Ad Scheduling)

Штатный инструмент, три режима:
1. круглосуточно (24/7)
2. по часам работы бизнеса (синхронизировано с профилем)
3. индивидуальное расписание (вручную дни недели + часы)

Вне выбранного расписания платное объявление не показывается — может
отображаться бесплатная версия профиля компании.

Источник: [About ad scheduling — Local Services Help](https://support.google.com/localservices/answer/9251526)

Прямой инструмент против риска "оплаченный лид в нерабочее время, когда
некому ответить" — сузить расписание под реальные часы доступности.

## Переход LSA на Performance Max (2026-2027)

Google поэтапно переводит LSA в модель Performance Max pay-per-lead внутри
основной платформы Google Ads:
- август 2026 — старт для отдельных категорий США (сантехники, HVAC,
  электрики); юридическая ниша не в первой волне
- конец 2026 — расширение на более широкий круг категорий
- 2027 — международные аккаунты и остальные категории

Не меняется (по заявлению Google): оплата только за валидные лиды,
размещение в Search/Maps, отсутствие ключевых слов в таргетинге.

Меняется: недельные бюджеты → дневные, отключается ручная максимальная цена
за лид, отменяются BBB-значки. **Отчёты о производительности НЕ переносятся
автоматически при миграции** — рекомендуется заранее сохранять историю.

Источник: [Local Services Ads transition to Performance Max — Google Ads Help](https://support.google.com/google-ads/answer/17213585)

## Номер телефона в LSA и колл-трекинг (добавлено 2026-10-14, не проверено на практике)

Запрос по [[../../Клиенты/Andverpersonalinjury/index|Andverpersonalinjury]]: заменить номер в LSA на статический номер Ringostat.

**Официально (Google, Local Services Help):**
- В объявлении показывается не бизнес-номер, а динамический Google forwarding number; выбрать его нельзя («There is no way to choose your tracking number»). Он пересылает звонок на «business phone number» из профиля LSA. [Manage leads and jobs](https://support.google.com/localservices/answer/6224859)
- Смена business phone number — в списке правок, которые делает только поддержка LSA, с верификацией (документы: DBA, регистрация бизнеса). В кабинете (Profile & Budget) поля для самостоятельной правки нет. [Edit your ad or business information](https://support.google.com/localservices/answer/7435507)
- В том же разделе: «Note that your business phone number must not be a tracking number» — прямое противоречие идее ставить туда номер колл-трекера.
- Business Profile привязывается (linking). **Уточнение 2026-10-14 по скриншоту кабинета Landver (раздел Business Verification → Google Business Profile):** Google пишет «When your Google Business Profile gets linked or updated for this Google Ads Account, certain business information will be sourced directly from your Google Business Profile and apply to your Google Local Services Ad». Список полей не назван; номер в карточке GBP (+1 310-461-3737) совпадает с номером в профиле LSA, где у телефона нет кнопки правки. Вывод: с высокой вероятностью телефон LSA берётся из Business Profile; формально поле не подтверждено Google. Справка 7435507 (правка телефона только через поддержку) описывает старый поток и в новом интерфейсе может не работать.

**Неофициально (практики, вендоры колл-трекинга):** номер колл-трекера в LSA ставят, меняя его через поддержку Google (WhatConverts, CallRail, ветка Local Search Forum); двойная пересылка (Google → трекер → офис) работает; возможна повторная верификация. Конверсии в Google Ads не вернутся, если не настроены Enhanced Conversions. Источники: [WhatConverts](https://www.whatconverts.com/help/docs/using-whatconverts/lead-tracking/call-tracking/add-a-phone-number-to-track-google-local-service-ads-calls/), [CallRail](https://support.callrail.com/hc/en-us/articles/41591539899277-How-to-set-up-Google-Local-Services-Ads-with-CallRail), [Local Search Forum](https://localsearchforum.com/threads/call-tracking-for-local-service-ads.57124/).

**Отдельная история (не путать):** сентябрь 2026 — в Google Ads объявления с локациями показывают номер Business Profile вместо номера из call asset; Google ответил, что при location+call assets звонок может идти на номер локации. Это про Google Ads, не доказательство, что LSA берёт номер из Business Profile. [SERoundtable](https://www.seroundtable.com/google-lsa-phone-number-42160.html)
