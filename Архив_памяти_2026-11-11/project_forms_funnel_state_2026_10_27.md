---
name: project-forms-funnel-state-2026-10-27
description: Сверка форм Tilda→Supabase→GA4→CRM за октябрь, опубликованные GTM v89/v21, что дальше (ProfiMet: метки из браузера не подставляются)
metadata:
  type: project
---

Сверка форм 1–27.10.2026 (скрипт `Скрипты/forms_funnel_reconcile.py`, страница `База_знаний/Паттерны/Потери-форм-Tilda-Supabase-GA4-CRM.md`): ProfiMet Tilda 72 / CRM 71 / GA4 49 / Supabase 64 пар по времени; ExpertAgro Tilda 64 / CRM 65 / GA4 58 сеансов (события ×2 из-за автособытия form_submit) / Supabase 58. Метки: ExpertAgro 16 из 58 потеряны в CRM, ProfiMet 17 заявок без метки в CRM, но реклама по GA4/Supabase.

Опубликовано 27.10: GTM ProfiMet v89 (И-094) и ExpertAgro v21 (Э-016): в Supabase добавлены `gclid`, `utm_content`, `page_url` (колонки добавил пользователь). Откат: v88 / v20.

**Why:** у ProfiMet в Tilda нет полей меток; метка в Supabase — запасной источник.

**How to apply:** следующий шаг — отдельная сессия по ProfiMet: тег «UTM - сохранить в браузере» в тесте не пишет `localStorage.rb_utm` (у ExpertAgro пишет, конфиг тега тот же, с v62 не менялся) — проверить на живом сайте в браузере (зайти с метками, уйти на другую страницу, `localStorage.rb_utm`), потом замер новых колонок через 3–5 дней, выключение «Взаимодействий с формами» в GA4 ExpertAgro делает пользователь (срок 02.11). См. [[feedback-discrepancy-tool-must-flag-lost-labels]].
