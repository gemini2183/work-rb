---
name: project-landver-openai-car-truck-campaign
description: "Состояние OpenAI Ads кампании Landver car+truck на 2026-10-07 — ID, правила чтения результата, что осталось, как работать с ключом Ads API"
metadata:
  node_type: memory
  type: project
  originSessionId: 2f39a918-34d2-4b99-8809-66a15dd9035e
  modified: 2026-10-08T14:41:17.887Z
---

OpenAI Ads кампания "Landver Law - car+truck injuries - tilda" `cmpn_6ac654ebdf448199826b33648b3f1a89` создана через API 2026-10-07 и включена пользователем в кабинете; 4 группы (Early Offer / Case Value / Truck / Lawyer Cost), 8 объявлений approved, fixed_bid $5 (с 2026-10-08 — $7 у всех 4 групп, И-014), $40/день, 3 рынка DMA (LA/San Diego/Palm Springs). Детали и ID — `Клиенты/Andverpersonalinjury/Кампании/OpenAI_Ads/car-truck-tilda-2026-10-07.md`, `Журнал_изменений.md` (И-011…И-013), `Решения.md` 2026-10-07.

**Why:** старый ключ пользователь отозвал; 2026-10-08 он создал новый и положил в пользовательскую переменную Windows `OPENAI_ADS_API_KEY` (setx; в текущем процессе VS Code её нет до перезапуска).
**How to apply:** ключ брать из пользовательской области без вывода: `KEY=$(powershell.exe -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_ADS_API_KEY','User')" | tr -d '\r\n')`, запросы только через curl (urllib получает 403), в чат и файлы не писать; после работы напомнить отозвать. Формат Insights: `GET /ad_account/insights`, `aggregation_level`, `fields[]` (`ad_group.name`, `impressions`, `clicks`, `spend`, `ctr`, `cpc`), `time_ranges[]={"type":"date_range","since":..,"until":..}`, `filters[]={"field":"campaign.id","operator":"IN","value":[..]}`, `time_granularity` hourly/daily/none. Сначала прочитать Insights по группам за 3+ дня и применить правило: порог 1000 показов и 25 кликов на группу; <100 показов/день на группу → ставки всех групп до $7; CTR <0,3% на 1000 показов → выключать группу; читать по группе, не по объявлению. Не проверено и осталось: тестовый звонок на (888) 346-8106 в Ringostat, подстановка плейсхолдеров `{campaign_id}` (смотреть в GA4 Page location), приём целей Lead Created/phone_click, конверсии по старым объявлениям (`POST /conversions/insights`).
Про доступ: чтение и запись этим ключом классификатор Claude Code сначала блокировал ("Credential Exploration", затем запись); после явного «да» пользователя в чате (повторно) запись прошла. Использовать ключ только в рамках того, что пользователь разрешил, и показывать таблицу плана до записи. Связано: [[feedback-api-write-plan-table-then-approve]].

2026-10-08: ключ новый в переменной OPENAI_ADS_API_KEY; чтение/запись — `python Скрипты/openai_ads.py` (groups / insights / set-bid [--execute]); правило разрешения `Bash(python Скрипты/openai_ads.py:*)` выдано пользователем. За 07.10 было 4 показа на кампанию; следующая проверка 09.10 (показы после $7). Тестовый звонок на (888) 346-8106 не сделан.
