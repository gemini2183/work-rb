---
name: П-028
description: profimet_sources_dashboard.py падает на GA4 Data API (429 Too Many Requests, один раз 502) — дашборд «По источникам» за период не собирается
status: открыта
updated: 2026-11-13
---

# П-028: GA4 Data API 429 роняет `profimet_sources_dashboard.py`

- **Симптом (дословно):** `requests.exceptions.HTTPError: 429 Client Error: Too Many Requests for url: https://analyticsdata.googleapis.com/v1beta/properties/349001266:runReport` в `ga4_forms_daily` (строка 119), вызов `client_like_daily(ringo, ga4_forms_daily(...))`. Первый запуск 13.11 дал `502 Server Error: Bad Gateway`, второй и третий — 429. Команда: `python profimet_sources_dashboard.py --from 2026-11-01 --to 2026-11-12 --no-open`.
- **Что известно:** «Наш» режим успел посчитать (265 рекламных продаж из 445 с 01.08), падение на режиме «как у клиента»; CSV не записан.
- **НЕ установлено:** чей квоту выбрали (другие сессии/скрипты на том же ключе `ga4-analytics`), почему запрос не повторяется.
- **Обход:** цены продажи — `profimet_price_per_sale_by_campaign.py` (не ходит в GA4), заявки — `state_digest.py`.
- **Идея решения:** в `ga4_forms_daily` повтор с паузой (экспоненциально) и режим «без GA4» для «Нашего» режима. Правка скрипта — через `script-builder`.
- **Как проверить:** запуск за 01.11–12.11 доходит до записи CSV.
