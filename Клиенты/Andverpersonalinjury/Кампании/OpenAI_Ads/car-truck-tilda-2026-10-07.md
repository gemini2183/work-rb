---
status: создана через API, на паузе, объявления на модерации
updated: 2026-10-07
---

# OpenAI Ads — Landver Law - car+truck injuries - tilda

Страница: https://landverpersonalinjury.tilda.ws/california-car-truck-accident. Обоснование — [[../../Решения]], записи 2026-10-07.
Кампания `cmpn_6ac654ebdf448199826b33648b3f1a89`: paused, bidding_type clicks, дневной лимит $40, гео рынки LA 3000192 / San Diego 3000201 / Palm Springs 3000193. Цели: Lead Created (`6a7b00c61a64819497dd47dc068f53e1`), phone_click (`6a7f1cfe4a98819490c7c60ed51c7cba`).
Группы: fixed_bid $5, шаблон `campaign_id={campaign_id}&ad_group_id={ad_group_id}&ad_id={ad_id}` на уровне группы. Тексты hints — `ad-groups-cartruck-round1.csv`, объявления — `ads-cartruck-round1.csv` (метки utm_content = early_offer_o1/o2, case_value_v1/v2, truck_t1/t2, lawyer_cost_l1/l2).

| Группа | ad_group_id | Объявления |
|---|---|---|
| Early Offer | adgrp_6ac654ef08248199b6a567f3866f78d9 | CT-O1 Early Offer After Your Crash? / CT-O2 The Adjuster Called Already? |
| Case Value | adgrp_6ac654f0932081998816375be152d3c0 | CT-V1 What Is Your Crash Case Worth? / CT-V2 CA Car Crash Injury Lawyers (Free Review) |
| Truck Liability and Evidence | adgrp_6ac654f2c3e88199a8f5fe2e84170886 | CT-T1 CA Truck Accident Injury Lawyers (Free Review) / CT-T2 Truck Crash? Preserve the Evidence |
| Lawyer Cost | adgrp_6ac654f453dc8199917493af0aab84e1 | CT-L1 Hurt in a Crash? No Fee Unless We Win / CT-L2 Worried About Lawyer Costs? |

Правило чтения: порог 1000 показов и 25 кликов на группу; группа с CTR ниже 0,3% на 1000 показов выключается; через 3 дня после включения при <100 показов в день на группу поднять ставки всех групп до $7. Читать по группе, не по объявлению (кликов мало).

## Лог действий (append-only)
## [2026-10-07] кампания/структура | создана через API, объявления in_review | гипотеза в Решения 2026-10-07 | не включена
