---
status: ВКЛЮЧЕНА 2026-10-28, все 6 объявлений approved
updated: 2026-10-28
---

# OpenAI Ads — Landver Law - topics (wrongful death, brain injury, rideshare) - tilda

Кампания `cmpn_435f7d14eb548191b41e1924fc2de71b`: clicks/click, лимит $50 в день, гео и цели как у car+truck (`cmpn_6ac654ebdf448199826b33648b3f1a89`). План — `topics_groups_2026-10-28.json`. Журнал И-111, эксперимент Э-15.

| Группа | ad_group_id | Страница | Объявления |
|---|---|---|---|
| Wrongful Death | adgrp_d1ce8909a8788191a412acd87d7f784f | /wrongful-death-lawyer-california | WD1 «Lost a Loved One? Wrongful Death Lawyer», WD2 «Insurer Called After a Fatal Accident?» |
| Brain Injury | adgrp_bdc248b7bbe88191a99b1449cd4ece76 | /brain-injury-lawyer-california | BI1 «Head Injury After a Crash or Fall?», BI2 «Insurer Says It Was Just a Concussion?» |
| Rideshare | adgrp_8322863e365081918edf42e1b2c8fa30 | /uber-lyft-accident-lawyer-california | RS1 «Hurt in a Crash With an Uber or Lyft?», RS2 «Who Pays After an Uber or Lyft Crash?» |

Правило чтения: по группе, не по объявлению (кликов мало); пороги и стоп — Э-15 ($60 на группу без обращения, CTR < 0,3% на 1 000 показов).

## Лог действий (append-only)
## [2026-10-28] кампания/структура | создана, 3 группы fixed $20, 6 объявлений (`openai_ads.py create-campaign`, `create-groups`) | гипотеза в Э-15 | прочитано обратно: paused, in_review
## [2026-10-28] включение | объявления approved за 1–2 минуты, группы и кампания paused → active (`openai_ads.py activate`, `campaign --status active`, по «сразу запускай») | — | прочитано обратно: active/approved у всех, serving_issues пусто, подмена номера на страницах 6 из 6 по каждой
## [2026-11-12] кампания/структура | созданы 4 лидогенные группы и 8 объявлений на паузе (`openai_ads.py create-groups --execute`, план `lead_groups_2026-11-12.json`) | гипотеза в Э-20 (подсказки «ищет юриста», объявления-утверждения) | прочитано обратно: группы paused fixed_bid $20, hints 3; объявления paused/in_review; И-147. Pedestrian и Bicycle — отдельные группы на общую страницу `pedestrian-bicycle-accident-lawyer-california`
## [2026-11-12] кампания/структура | старые 5 групп на паузу, 4 лидогенные группы включены (И-148); создана «Spanish - Lawyer» на паузе (И-149) | гипотеза в Э-20 | кампания paused с 06.11 (кто — неизвестно), показов нет
