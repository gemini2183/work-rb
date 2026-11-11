---
name: project-lead-standard-ringostat-supabase-2026-11-05
description: "Единый стандарт «заявка Google Ads» = Ringostat + Supabase + call_view; сторож, сводка и план месяца считают по нему, конверсии Ads — только справка"
metadata:
  type: project
---

Решение пользователя 05.11: заявки для сторожей, `state_digest.py` и плана месяца — только уникальные звонки Ringostat (Google Ads) + формы Supabase (без пачек-мусора, телефон за день один раз; Google по `utm_source` или `gclid`). Звонки из объявлений: кампания из `call_view` Google Ads по времени ±3 мин (ProfiMet 13 из 13, EkspertAgro 5 из 5 совпали). Формы без метки не приписываются Google, показываются отдельно с верхней оценкой. Код: `Скрипты/leads_standard.py`; сторож переведён 05.11 11:16.

**Why:** раньше сторож, сводка и план считали по-разному (Ads-конверсии против Ringostat/Supabase), решения по кампаниям нельзя было сравнивать.

**How to apply:** цифры заявок брать из `leads_standard.py`/раздела [4] сводки, не из конверсий Ads; не называть пропуск Supabase без сверки с CRM (ошибка 05.11: часовой пояс Tilda в `forms_funnel_reconcile.py` определяется неверно, Tilda-таблица ProfiMet кончается 27.10). Отдельные номера Ringostat на кампанию отложены. См. [[feedback-numbers-only-from-scripts]].
