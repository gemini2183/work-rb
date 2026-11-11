---
name: reference-ga4-access-profimet
description: "Как читать GA4 ProfiMet (property 349001266) — какой сервисный аккаунт/ключ работает, что включено, что нет"
metadata:
  node_type: memory
  type: reference
  originSessionId: fa3c5c1f-5ec5-48e6-a0cc-ddf801dd299b
  modified: 2026-10-06T08:09:23.759Z
---

GA4 ProfiMet (mocnaszklarnia.pl): property `349001266`. Рабочий ключ — сервисный аккаунт `ga4-analytics@redbird-196813.iam.gserviceaccount.com`, файл `E:/PythonProjects/RedBird/google-cloud-jobs/adwhite/func/ga4_profimet/redbird-196813-ga4.json` (читать по месту, в вики не копировать). GA4 **Data API работает** (событие по минуте `dateHourMinute`, кампании, `conversions`). **Admin API включён пользователем 2026-10-07** (проект 971181496802): чтение аудиторий работает (`analyticsadmin.googleapis.com/v1alpha/properties/349001266/audiences`, scope analytics.readonly, 30 аудиторий); запись не проверена — нужна роль «Редактор» у `ga4-analytics`. Ключ `rb-cloud-admin` (`Скрипты/secrets/rb_cloud_service.json`) к ресурсу НЕ допущен (403).

Событие GA4 от Ringostat приходит со временем окончания звонка (старт + duration) — так звонок сопоставляется с событием по минуте.

**How to apply:** для сверки Ringostat → GA4 → Ads использовать этот ключ; результаты первой сверки — в [[project-campaign-analyzer-state]] и `База_знаний/Инструменты/Ringostat-передача-звонков-в-GA4-события-и-типы.md`.

Готовые скрипты (2026-10-06, `Скрипты/`): `ringostat_ga4_delivery_profimet.py` (сверка звонков Ringostat с событиями GA4), `metrika_consent_profimet.py` (цели баннера в Метрике, токен из `YM_TOKEN`). Описание — `Скрипты/README.md`.
