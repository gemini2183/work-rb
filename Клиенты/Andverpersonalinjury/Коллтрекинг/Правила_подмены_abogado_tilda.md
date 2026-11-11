---
status: УСТАРЕЛ 2026-11-11 — актуальные правила и инструкция в [[Правила_подмены_spanish_es]] (маски кнопок с t-btnflex__text, правило на FAQ, верный адрес); в кабинет Ringostat НЕ внесено
updated: 2026-11-11
---

# Правила подмены Ringostat — испанская страница «abogado de accidentes» (ожидаемый адрес `landverpersonalinjury.tilda.ws/abogado-de-accidentes-lawyer-california`)

Зачем отдельные правила: английские правила (`car-lawyer …`, см. [[Правила_подмены_car_accident_lawyer_tilda]]) привязаны к `data-ldv-cta` и переписывают внутренности ссылки маской «Call (###) ###-#### · 24/7». На испанской странице метки с префиксом `es_` (ставит сборщик `build_topic_pages.py`), поэтому английские правила её не трогают, а испанские кнопки получают свои маски. Принцип тот же: XPath на сам `<a>`, маска только из внутренностей, ГЕО группа All; `href` Ringostat ставит сам.

| # | Место | XPath | Совпадений | Маска (внутренности ссылки) |
|---|---|---|---|---|
| 1 | Шапка (десктоп) | `//a[@data-ldv-cta="es_header_call"]` | 1 | `<small>CONSULTA GRATIS · 24/7</small>(###) ###-####` |
| 2 | Кнопки «Llame al … · 24/7»: первый экран, «как работает», «оплата», финал | `//a[@data-ldv-cta="es_hero_call" or @data-ldv-cta="es_how_call" or @data-ldv-cta="es_fee_call" or @data-ldv-cta="es_final_call"]` | 4 | `Llame al (###) ###-#### · 24/7` |
| 3 | Кнопка у блока адвоката | `//a[@data-ldv-cta="es_attorney_call"]` | 1 | `Llame al (###) ###-####` |
| 4 | Нижняя плашка на телефоне | `//a[@data-ldv-cta="es_sticky_call"]` | 1 | `Llame ahora · 24/7<span style="display:none;">+###########</span>` |
| 5 | Подвал | `//a[@data-ldv-cta="es_footer_call"]` | 1 | `(###) ###-####` |

Знак `·` — U+00B7 (как на странице), копировать отсюда. Названия правил: `abogado header`, `abogado call 24/7`, `abogado attorney`, `abogado sticky`, `abogado footer` (Manual mode, ГЕО All), потом «Применить настройки».

Порядок (по `База_знаний/Агенты/Запуск_трекинга_новой_посадочной.md`, шаг 6): страница опубликована → `ringostat_xpath_plan.py --url … --client-folder Andverpersonalinjury --name-prefix abogado` сверить число совпадений (ожидается 1/4/1/1/1 = 8 из 8) → таблица плана → «да» → ввод через Chrome → `phone_swap_check.py` с `Пул_номеров_spanish_tilda.yaml`, затем скриншоты ВСЕХ мест номера с метками Google (десктоп и мобильный): должно быть «Llame al …», не «Call …» и не «Llame al Llame al».
Откат: удалить 5 строк `abogado …` и «Применить настройки».

Не проверено: живая подмена на этой странице; отдельный номер/канал Ringostat для испанского трафика не заведён (решение пользователя).
