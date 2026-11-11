---
name: project-landver-three-pages-intake-form-2026-11-10
description: "Landver 10.11: три страницы под Search (Motorcycle, Pedestrian & Bicycle, испанская) со сжатым первым экраном и формой приёма вместо квиза; без юриста клиента; бюджет Google 10 000 $ со слов"
metadata:
  node_type: memory
  type: project
  originSessionId: 166147d6-073c-4d1b-8a7b-85b064ccec5c
  modified: 2026-11-10T12:10:53.485Z
---

Решения пользователя 10.11.2026: EN — Motorcycle отдельно и «Pedestrian & Bicycle» одной страницей; ES — одна общая «abogado de accidentes» с упором на легковые; квиз отменён, вместо него форма приёма (имя, телефон, радио «травма», 1 доп. вопрос по теме, необязательный текст). Испанский утверждён (колл-центр принимает на испанском, со слов) — не переспрашивать и не просить проверок.

**Why:** квиз для тяжёлых дел может выглядеть уловкой (опасение пользователя), независимых данных, что он конвертирует лучше формы, нет. Юристу клиента не отправляем: клиент уже «задрачивает», страницы идут без юридической сверки, как 28.10; берём только формулировки, уже стоящие на живых Car/Motorcycle.
**How to apply:** сборка — `Клиенты/Andverpersonalinjury/Кампании/Search/build_topic_pages.py` (темы motorcycle, pedestrian_bicycle, spanish); адреса страниц обязаны оканчиваться на `-lawyer-california` (условие GTM «Topic pages (vb)»); испанская — метки `es_…` и свои правила Ringostat. Бюджет Google Ads на ноябрь 10 000 $ — со слов пользователя (в таблице «Цели2» строка 9 000, не сверено). Задачи и состояние — `Клиенты/Andverpersonalinjury/Задачи.md`, `Хроника_2026-11.md` 10.11. Связано: [[feedback_decide_as_consultant_when_math_adequate]].
