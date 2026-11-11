---
name: reference-metrika-profimet
description: Яндекс.Метрика ProfiMet (счётчик 75073231): id целей баннера согласия и как её читать; токен НЕ хранится
metadata:
  type: reference
---

Счётчик Метрики mocnaszklarnia.pl: `75073231`, аккаунт `redbird.analytics`. Читать через API Метрики (`api-metrika.yandex.net/stat/v1/data`, заголовок `Authorization: OAuth <токен>`). **Токен в память/вики не сохранён** — пользователь вставлял его в чат 2026-10-06 (лучше спросить заново или взять из рабочей таблицы клиентов; напомнить, что токен лежит в истории чата).

Цели баннера согласия (самописный баннер, GTM-контейнер GTM-TKGN4NT шлёт `ym(75073231,'reachGoal',...)`): `show_popup` 326188549, `must_have_cookies` 326189789, `all_cookies` 326190412, `settings` 326191579, `confirmed` 326191580. Для долей брать `ym:s:goalNvisits` (визиты с целью), не `goalNreaches`: один визит даёт несколько показов баннера. Метрика грузится ДО согласия, поэтому видит всех посетителей — подходит как знаменатель.

**How to apply:** для оценки доли принявших cookie и сверки с GA4. Связано: [[reference-ga4-access-profimet]].
