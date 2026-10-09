---
status: ВКЛЮЧЕНА (переключено в кабинете 2026-10-07), все объявления approved
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
## [2026-10-07] кампания | включена (active) пользователем в кабинете, 8 объявлений approved | см. Журнал_изменений | ждём первых 3 дней показов
## [2026-10-08] кампания/первое чтение Insights | чтение через API (новый ключ в переменной окружения пользователя) | гипотеза не менялась | за 07.10 (время кабинета, PT): 4 показа, 0 кликов, $0 на всю кампанию — Truck 3, Lawyer Cost 1, Early Offer 0, Case Value 0; показы шли в 12:00, 14:00, 18:00, 21:00. Все 4 группы active, fixed_bid $5, 8 объявлений approved. Старая кампания paused, показов с 01.10 нет. Выборка ничтожна (порог 1000 показов не достигнут в 250 раз), по CTR выводов нет; уровень показов на порядки ниже порога 100/день на группу — вопрос поднятия ставок до $7 вынесен пользователю
## [2026-10-08] ставки групп | fixed_bid $5 → $7 во всех 4 группах (скрипт openai_ads.py, после «да») | на $5 за сутки 4 показа на кампанию; ставка ниже рынка (гипотеза) | прочитано обратно: $7 у всех; смотреть показы с 09.10, см. Журнал_изменений И-014
## [2026-10-09] кампания/чтение Insights 07–09.10 | чтение через `openai_ads.py insights`, ничего не менялось | гипотеза «$7 вернёт показы» пока не подтверждена | по группам: 07.10 — 4 показа (Truck 3, Lawyer Cost 1); 08.10 — 6 (Truck 4, Early Offer 1, Lawyer Cost 1); 09.10 до 14:57 — 1 (Truck); итого 11 показов, 0 кликов, $0. Все 4 группы active, fixed_bid $7. Для сравнения, старая dog bite (`cmpn_6a7b1758f9508192b009ef9839299108`, ставка $8, 20.09–09.10): 6 498 показов, 22 клика, $232,41, CPC $9,43, CTR 0,35% (~325 показов в день на кампанию против ~4 здесь); у dog bite те же 3–4 hints на группу, гео не сверялось
