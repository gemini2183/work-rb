---
name: scripts-readme
description: Как пользоваться скриптами сбора статистики
updated: 2026-07-24
---

# Скрипты

Один общий скрипт на источник данных для клиентов без спец-условий — разница
между ними только в логине/токене/номерах целей, структура запроса одна и та же.

Если у клиента есть спец-условия для сверки/анализа (например, кампанию нужно
исключать по UTM, как letnie у ЕГЭ Merlin — см. `conditions` на вкладке
"Metrika" общей таблицы) — под него заводится **отдельный** скрипт
(`<источник>_stats_<клиент>.py`), который использует функцию сбора из общего
скрипта, но добавляет свою фильтрацию поверх. Не зашивать клиент-специфичные
условия в общий скрипт — это 1:1 повторяет архитектуру прод-пайплайна
(`google-cloud-jobs`), где под такими клиентами тоже отдельные job'ы со своим
`apply_client_filters`, а не общая логика для всех.

## Два агентства — две отдельные таблицы

В этой вике ведутся клиенты двух разных агентств:
- **Redbird** — контекстная реклама Яндекс.Директ (Директ/Метрика/Callibri
  и т.п.), таблица `SHEET_URLS["redbird"]` в `_config.py`.
- **Adwhite** — контекстная реклама Google Ads (Google Ads API/Merchant
  Center), таблица `SHEET_URLS["adwhite"]` в `_config.py`.

Обе таблицы одинаковы по паттерну (клиент — строка на вкладке источника,
`status=active`), но разные по адресу и структуре вкладок. `get_client_row(...,
agency="redbird"|"adwhite")` — по умолчанию `"redbird"`, для Adwhite-клиентов
передавать `agency="adwhite"` явно.

Логин/токен/счётчик/client_id **не хранятся в этой вики** — берутся напрямую
из соответствующей общей Google-таблицы, той же, что питает продовый
BigQuery-пайплайн в `E:/PythonProjects/RedBird/google-cloud-jobs`. Это единый
источник правды: если токен клиента поменялся, обновляется в одном месте, а не
дублируется в нескольких проектах. Здесь только облегчённая локальная версия
сбора — без BigQuery, снапшот сразу кладётся в `Клиенты/<клиент>/Статистика/`
для анализа агентом.

## Установка

```
pip install -r requirements.txt
```

## Требование к таблице

Клиент должен быть заведён строкой на нужной вкладке общей таблицы своего
агентства (`Директ`/`Metrika`/`Calibri` для Redbird, `Google_Ads_API` для
Adwhite), с `status=active`, и значением колонки `client`, которое передаётся
скриптам как `--client`.

Доступ — через service account `Скрипты/secrets/rb_cloud_service.json` (не в
git, скопирован из `google-cloud-jobs`; тот же service account, что использует
продовый пайплайн, доступ read-only к обеим таблицам).

Для Google Ads API (Adwhite) дополнительно нужен `Скрипты/secrets/google-ads.yaml`
(developer_token/OAuth/MCC login_customer_id — не в git, скопирован из
`google-cloud-jobs/adwhite/func/<любой gads-job>/google-ads.yaml`, общий для
всего аккаунта Adwhite, не per-клиент).

## Запуск — Redbird (Директ/Метрика/Callibri)

```
python direct_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" --days 30
python metrika_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" --days 30 --goals 123456,789012
python callibri_stats.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" --days 30
```

`callibri_stats.py` тянет звонки (колл-трекинг) с вкладки "Calibri" общей
таблицы — сырые данные без дедупликации и без вычисления источника трафика.
Использовать напрямую только для клиентов без спец-условий; для ЕГЭ Merlin —
см. клиент-специфичный скрипт ниже.

### Клиент-специфичные скрипты (ЕГЭ Merlin)

```
python metrika_stats_ege_merlin.py --date-from 2026-06-01 --date-to 2026-07-17
```

Поверх сбора `metrika_stats.py` фильтрует только рекламный трафик, схлопывает
Source в YaDirect, исключает letnie по UTM Content и исключает трафик
неактивного проекта "Merlin - Курсы Python" по UTM Content (1:1 логика
прод-job `ym2_merlin_ege`).

```
python callibri_stats_ege_merlin.py --date-from 2026-06-01 --date-to 2026-07-17
```

Поверх сбора `callibri_stats.py` (`fetch_callibri_calls`) классифицирует
Source (Контекст/YaDirect по traffic_type+utm_source), исключает letnie по
utm_content и дедуплицирует звонки по (phone, месяц) — 1:1 логика прод-job
`callibri2_merlin_ege`. Использовать вместо общего `callibri_stats.py` для
этого клиента — общий не делает ни классификацию, ни дедупликацию.

```
python reconcile.py --client "ЕГЭ Merlin" --client-folder "ЕГЭ Merlin" \
    --date-from 2026-06-01 --date-to 2026-07-17
```

Общий скрипт сверки конверсий по кампаниям (Директ vs Метрика+Callibri) —
реализация методологии
`База_знаний/Паттерны/Сверка-конверсий-Директ-Метрика-Коллтрекинг.md`.
Сопоставление идёт по `CampaignId` — UTM-метки устроены одинаково во всех
проектах (Директ отдаёт CampaignId готовым числом, Метрика — в UTM Campaign,
Callibri — как `cid_<id>` в utm_content), так что это общая логика без
клиентских вариаций. `goal_id`/`ct_goal_id` (какая колонка direct-файла —
форма, какая звонок) берутся не флагом, а с вкладки "Metrika" по `--client`.
Не собирает данные сам — сначала нужно прогнать `direct_stats.py`,
`metrika_stats*.py` и `callibri_stats*.py` за тот же период.

## Запуск — Adwhite (Google Ads / Merchant Center)

```
python gads_stats.py --client "Клиент - Google Ads" --client-folder "Клиент" --days 30
```

Тянет трафик (Cost/Clicks/Impressions) и конверсии одним проходом через
Google Ads API (не REST+токен, как у Директа/Метрики — используется
библиотека `google-ads`, OAuth через `google-ads.yaml`). Конверсии
разбиваются по `segments.conversion_action_name` — не суммируются в одну
цифру, чтобы не терять смену основной цели конверсии во времени (если у
клиента конверсия была переопределена в середине периода, в снапшоте видно
оба названия отдельными строками).

### Клиент-специфичные скрипты (Корогва)

```
python gads_stats_korogva.py --date-from 2026-06-01 --date-to 2026-07-17
```

Один аккаунт Google Ads (client_id 845-234-6433), разбитый на два подпроекта
по названию кампании, не по отдельному customer_id (1:1 логика прод-job'ов
`gads_korogva_gads`/`gads_korogva_merchant`):
- "Корогва - Google Ads" — обычные кампании
- "Корогва - Merchant Center" — товарные кампании (название содержит "Sales"
  или "Merchant_")

Собирает оба подпроекта за один запуск, сохраняет раздельно (`gads_korogva-gads_*`
и `gads_korogva-merchant_*`, плюс `*-goals_*` для конверсий каждого).

`--client` — как записано в колонке `client` таблицы (может отличаться от имени
папки в `Клиенты/`, поэтому `--client-folder` — отдельный параметр).

Результат — TSV/CSV файл в `Клиенты/<клиент>/Статистика/` с диапазоном дат в имени.
Номера целей для `--goals` берутся из `Клиенты/<клиент>/Цели/goals.md`.
