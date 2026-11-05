---
name: ringostat-gclid-и-client-id-статика-против-динамики
description: Что реально отдаёт Ringostat API по звонкам разных типов пулов (gclid, client_id, utm_*), что ставит на сайте (cookie rngst) и схема «визит с rngst → Supabase → звонок по client_id» для возврата gclid статическим пулам
status: не протестировано (данные Ringostat API проверены на ProfiMet 05.11.2026; равенство client_id звонка и cookie rngst не проверено, ждёт реальных звонков)
updated: 2026-11-05
---

# Ringostat: gclid и client_id у звонков статических и динамических пулов

## Что проверено (ProfiMet, Ringostat API `calls/list`, входящие Google, 01.08–04.11.2026)
| Пул | Звонков | gclid в `utm_content` | `client_id` |
|---|---|---|---|
| Google CPC_dyn (динамический) | 416 | 416 (формат `rb_cid_…\|gid_…\|…\|gclid_<значение>`) | uuid у всех |
| Google CPC_pmax (статический, номер на сайте по метке) | 13 | 0 (в полях шаблон канала `.*`) | uuid у всех |
| Google CPC_demand_gen (статический) | 5 | 0 (шаблон `,*`) | uuid у всех |
| Google CPC calls from ads (номер в объявлении) | 67 | 2 | uuid у всех, 18 повторов |

- **Статические пулы с визитом** (pmax, demand_gen, YouTube, ретаргет): посетитель на сайт заходит, номер показан по метке, но gclid Ringostat в звонок не кладёт. Причину документация не объясняет (вывод из данных).
- **«Calls from ads»** — ассет звонка в объявлении, визита нет; два звонка с gclid оказались динамическими (`utm_campaign=pmax1_…`), попавшими в этот пул (причина неизвестна). `client_id` у таких звонков, вероятно, присваивает сам Ringostat (гипотеза).
- Ключевое: **API отдаёт по умолчанию только `calldate, caller, n_alias`**; остальные поля надо запрашивать в `fields`. Наша выгрузка `profimet_ringostat_full_export.py` не запрашивала `utm_content` и `client_id`, поэтому «gclid нет» в ней было следствием набора полей, а не данных.

## Что Ringostat ставит при визите (Playwright, 05.11.2026)
- Cookie `rngst` = `{"clientId":"<uuid>"}` (~1 год), `rngst2` (utmz и id сессии), `rngst1`, `rngst_callback`, `rngstHash`; ставятся без согласия на баннер.
- Адрес страницы **с gclid** уходит на серверы Ringostat (`analytics.ringostat.net/changed_number`, `/collect`, `callback.ringostat.net`). Адресная строка не меняется. В cookie gclid не сохраняется.
- Объекты `window.ringostatAnalytics`, `ringostatAPI`, `ringostatRestartSubstitution`.

## Схема возврата gclid статическим звонкам (внедрена на ProfiMet 05.11, GTM v95, не проверена)
Тег GTM на All Pages читает `clientId` из `rngst` и клик (`gclid`/`gbraid`/`wbraid`) из адреса или `rb_utm`, пишет в Supabase `profimet_visits` с уникальным индексом (`rngst_client_id`, `click_key`). Звонок сопоставляется по `client_id`. Тег без условия согласия (решение пользователя; правовая оценка — клиенту); `consent` пишется в таблицу. Скрипты: `Скрипты/gtm_visit_tag.py`, `gtm_visit_tag_test.py`, `visit_call_join.py`.
- **Не проверено:** что `client_id` звонка = `rngst.clientId` (совпадает формат). Контроль метода — динамический пул (gclid звонка против gclid визита); для статики — совпадение `utm_campaign` звонка и визита.
- Расхождение со старой записью: поддержка Ringostat (06.10, раздел 13 страницы про передачу звонков в GA4) называла `client_id` «GA client id»; в API он в формате uuid, как `rngst.clientId`. Перепроверить по первым парам.
- Старая попытка (тег GTM `visitsToServer`, сервер `ringostat-webhook.onrender.com`, ключ — GA client id из `_ga`) работала только после согласия на аналитику, для кампаний с `pmax`; удалена 05.11 (И-101).

## Ограничения Supabase Free для такого хранилища
База 500 МБ, трафик 5 ГБ, 2 проекта, пауза после 7 дней без активности; на странице Billing: при превышении квоты проекты «могут перестать отвечать» (остановит и запись заявок). Визиты хранить 90 дней (столько принимает Google для офлайн-конверсии) и чистить. Цифры по лимитам — из сторонних обзоров, не из официальной страницы.

Связано: [[Ringostat-Google-Ads-интеграция-и-нехватка-номеров-искажают-атрибуцию]], [[Ringostat-механизм-подмены-номера]], `Инфраструктура.md` 2026-11-05.
