---
name: project-profimet-dashboard-youtube-row-2026-11-10
description: "ProfiMet 10.11: в дашборде «По источникам» отдельная строка YouTube (признак yt_), второй после Google Ads; пояснения режима «как у клиента» подробно; правило отмены"
metadata:
  node_type: memory
  type: project
  originSessionId: af038b81-a779-4552-8728-385739323c17
  modified: 2026-11-10T09:01:55.445Z
---

Решение пользователя 10.11: YouTube в дашборде отдельной строкой, признак — название кампании (и `utm_campaign`) начинается с `yt_`, строка на втором месте (после Google Ads, как у клиента). Реализовано в `Скрипты/profimet_sources_dashboard.py` (+ `profimet_our_leads.py`), живая таблица обновлена `--update-sheet` 10.11; «Итого» до/после совпало.

**Why:** YouTube (кампания `yt_warm`, с 04.11) оценивается отдельно, порог 30 € за продажу; в Google Ads его смешивать нельзя.
**How to apply:** новые источники добавлять в `SOURCES`/`AD_SRC`, раскладка листа «Дашборд» идёт из `ROW`/`table_cells`/`notes_formulas` (пояснения в A17:A28). В CRM строк с `yt_` пока 0 — продажи YouTube 0 по нашим данным, сверить при появлении. Режим «как у клиента» описан по пунктам под таблицей и на листе «Как считается» (`CLIENT_TEXT`; правка текстов — `--patch-client-notes`). Правило отмены клиента (отмена до даты продажи → заказ действует) подтверждено одним заказом 94230110, пять других заказов вне периода списков клиента. Связано: [[project-profimet-our-mode-one-ladder-forms-check-2026-11-09]], [[project-profimet-youtube-launch-2026-11-04]].
