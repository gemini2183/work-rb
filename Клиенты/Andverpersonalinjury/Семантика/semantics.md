---
name: client-semantics-yuristy-usa
description: Мастер-список семантики со статусом проработки — Юристы США
updated: 2026-08-18
---

# Семантика — Юристы США

| Ключ/группа | Статус | Кампания | Комментарий |
|---|---|---|---|
| Гео-варианты LA (243 ключа, 6 групп: Bicycle/Dog Bite/Motorcycle/Pedestrian/Slip and Fall/Bus Injury LA) | в проработке | search / all injuries / la | Сгенерировано `gads_geo_ad_group_builder.py`, CSV одобрен, ждёт правки 8 строк объявлений + импорта. См. [[../Решения|Решения]] 2026-08-18 |
| Broad/phrase-семантика по Словарь-тем.yaml (258 ключей, 11 групп) | в проработке | search / all injuries / broad (новая, ещё не создана в аккаунте) | Сгенерировано `gads_campaign_builder.py` искусственно из словаря — НЕ гео-дубль существующих ключей. CSV одобрен, ждёт правки 12 строк + бюджета/таргетинга + импорта. См. [[../Решения|Решения]] 2026-08-18 |
| Dog Bite — семантика для отдельной кампании (156 строк Keyword Planner, California+LA гео; 37 ключей отобрано для запуска) | готов к импорту | новая отдельная кампания "dog bite" (ещё не создана) | Собрано вручную (Google Autocomplete) + Keyword Planner API (`Скрипты/gads_keyword_ideas.py --geo-id 21137 --geo-id 1013962`, id California/Los Angeles — см. [[../Решения|Решения]] 2026-09-04). Итоговый bulksheet для импорта: `Статистика/gads_bulksheet_dog_bite.csv` (1 объявление + 37 ключей PHRASE). Полные данные: `Статистика/gads_keyword_ideas.csv`. См. кластеры и минус-слова ниже |

См. также [[Словарь-тем|Словарь-тем.yaml]] — источник модификаторов/суффиксов
для генерации broad-семантики по темам, используется обоими скриптами выше.

## Dog Bite — разбор семантики (2026-09-04)

Собрано в два прохода: (1) вручную через Google Autocomplete/WebSearch —
кластеры формулировок; (2) через реальный Keyword Planner API с гео-фильтром
California (id 21137) + Los Angeles (id 1013962) — оба ID подтверждены из
фактического таргетинга ENABLED/PAUSED-кампаний аккаунта (`--list-campaign-geo`),
не взяты из примера в докстринге скрипта. Старый `gads_keyword_ideas.csv` (2291
строк) был собран без гео-фильтра — там фигурировали нерелевантные города вне
Калифорнии, оценка объёма по нему была занижена на порядок. Актуальный CSV
перезаписан.

**Топ по объёму (California+LA, шт./мес):**

| Ключ | Объём | Конкуренция |
|---|---|---|
| dog bite lawyer | 2400 | LOW |
| dog bite lawyer near me | 1900 | LOW |
| dog bite attorney | 1000 | LOW |
| dog bite lawyer california | 880 | LOW |
| dog bite lawyer los angeles | 720 | LOW |
| abogado de mordedura de perro (испанский) | 320 | LOW |
| dog bite attorney riverside ca | 320 | LOW |

Вывод: ниша НЕ низковолюмная (в отличие от предварительной оценки по
нефильтрованному CSV, где "dog bite lawyer" показывал 50/мес) — реальный
объём по Калифорнии на два порядка выше. Испанский сегмент существен (320/мес
на одну фразу) — сопоставим с "dog bite lawyer los angeles", ранее в фокус
не попадал явно для этого направления.

**Кластеры (по итогам обоих проходов):**
1. Базовые транзакционные — dog bite lawyer/attorney(s), near me, California,
   Los Angeles + отдельные города CA (Riverside, Fresno, San Bernardino,
   Anaheim, Bakersfield, Beverly Hills, Huntington Beach, Victorville — все
   всплыли в API-расширении, не были в исходном seed-списке)
2. По типу ответчика/ситуации — neighbor's dog bit me, landlord liability dog
   bite, dog attacked my child/baby, dog bite at work, dog bit me again
3. Информационные "нужен ли юрист" — do i need a lawyer for a dog bite,
   bitten/attacked by a dog what to do
4. Информационные "деньги" — settlement calculator/amounts, claim, compensation
5. Породы — pit bull/pitbull, german shepherd, rottweiler, husky, doberman,
   cane corso, xl bully, bully breed — все валидны как фразы (Google их не
   отклонил), но объём по Калифорнии практически нулевой (0-10/мес) —
   годятся только для broad/phrase хвоста, не для отдельных групп
6. Испанский — abogado de mordedura de perro (320/мес), abogados perros.
   **Отменено для этого запуска** (2026-09-04, не отложено): у
   landverpersonalinjury.tilda.ws/dog-bite нет испаноязычной версии страницы
   и нигде не заявлено "hablamos español" — вести испаноязычный клик на
   англоязычный лендинг создаёт разрыв доверия в момент, когда человек уже
   кликнул. Если тема всплывёт снова — сначала нужна испаноязычная версия
   лендинга, это отдельная более крупная задача, не просто перевод
   объявления. Ключи остаются в CSV как справочные данные (реальный объём
   спроса подтверждён), просто не используются в текущей кампании

**Минус-слова (подтверждено по автокомплиту и по факту API-расширения):**
- медицина/укус как физический феномен: rabies, antibiotic, ICD-10, dog bite
  arm, "bite work" и весь его хвост (K9/protection dog training/sport —
  schutzhund, malinois, sleeve, harness — совершенно другая ниша, всплыла
  из-за расширения по слову "bite"). **Важно: минус-фраза именно "bite
  work" целиком** (или "schutzhund"/"sleeve"/"harness" как отдельные
  однозначные термины) — НЕ обрезанные породные варианты вида "german
  shepherd bite"/"cane corso bite"/"doberman bite" без слова "work": без
  "work" эти фразы теряют единственный отличительный признак нецелевого
  запроса и рискуют срезать реальные позитивные запросы жертв (напр. "german
  shepherd bite lawyer", "bitten by a german shepherd") — ошибка найдена и
  исправлена 2026-09-04, три такие обрезанные строки убраны из
  рекомендованного списка
- поп-культура/иное: dream/dream meaning, manhwa/манга, awareness
  month/stamp, конкретные знаменитости (Chris Brown, Cesar Millan)
- не та юрисдикция: другие штаты/страны (Chicago, Brooklyn, UK, Canada,
  Jamaica, Australia, South Africa, Haryana, Ontario)
- не та сторона: "dog bite lawyer defense" (защита владельца собаки, не
  жертвы), "do i need a lawyer if my dog bites someone" (тоже владелец)
- не про человека: "cat attacked by a dog"
- зоология/статистика, не юруслуги: breed statistics, bite force/strength,
  breed chart

Не проверено: остаточный объём "one bite rule" (устаревший термин, не
действует в CA, но могут гуглить по инерции) — не включён в seed-список этого
прохода, добавить отдельным прогоном при необходимости.

## Match type и минус-слова на бренды конкурентов

**Match type: только PHRASE/EXACT, НЕ broad.** Пользователь явно отклонил
broad match для этой темы — даже phrase/exact иногда расширяются Google на
близкие варианты, если в тексте есть общие слова ("dog bite lawyer"), и
показывают объявление по факту брендового запроса конкурента (человек ищет
конкретную контору, а не услугу вообще) — broad усилил бы этот риск
многократно. Согласуется с остальной семантикой аккаунта — там везде PHRASE,
broad нигде не используется.

**Минус-слова — бренды конкурентов (LA/CA dog bite, из выдачи Google по
запросу "Los Angeles dog bite lawyer"/"California dog bite lawyer"), найдены
2026-09-04:**

- bisnar chase
- schuerger shunnarah
- west coast trial lawyers
- dog bite law group
- selarz law
- darwish law
- mandell law
- ehline law
- easton and easton (только полной фразой — "easton" одним словом слишком
  общее, риск случайно срезать целевой трафик)
- morgan (одним словом — пользователь явно решил жёстко: любая комбинация со
  словом "morgan" считается нецелевой, риск показа по бренду Morgan & Morgan/
  forthepeople важнее, чем потеря единичных случайных совпадений)
- dominguez firm
- bestattorney
- panish
- wilshire law firm
- farzam law
- kornberg law
- kjt law group
- dogsbite.org (справочник по укусам, не фирма — тоже нецелевой клик)

**Минус-слова — агрегаторы/директории юристов** (там сравнивают фирмы, не
ищут прямой контакт с конкретным адвокатом — нецелевой лид для Landver Law):
- lawinfo
- expertise.com / expertise
- superlawyers
- avvo
- justia

Список не исчерпывающий — при разборе Search Terms после запуска кампании
пополнять по факту просачивания (та же практика, что уже применялась к
harassment/discrimination для темы Personal Injury, см. [[../Решения|Решения]]
2026-08-19).

## Финальный список ключей для запуска — только LA (2026-09-04)

Из 128 фраз с ненулевым объёмом сначала вручную отфильтрован мусор (K9/protection
dog training кластер "bite work" и хвост — 29 фраз, чужие юрисдикции вне
Калифорнии Chicago/Brooklyn/Providence/Greenville/Cumming — 6 фраз включая
Cumming, GA, ошибочно принятый за калифорнийский город, абстрактные "юрист по
животным вообще" не про собак конкретно — ~15 фраз, испанский — 2 фразы,
странные обрывки без ясного смысла) — осталось 64 чистых ключа по теме.

**Дальше пользователь указал на конкретику самого лендинга**: страница
landverpersonalinjury.tilda.ws/dog-bite прямо в тексте говорит "укусили В
ЛОС-АНДЖЕЛЕСЕ" — то есть страница сейчас заточена конкретно под LA, не под
Калифорнию в целом. Приводить клик по запросу с другим городом ("dog bite
lawyer bakersfield", "victorville dog bite lawyer" и т.п.) на страницу,
явно говорящую про другой город, создаёт разрыв доверия в момент клика — та
же логика, что уже применена к отмене испанского варианта (текст объявления/
семантика должны соответствовать тому, что человек увидит на посадочной
странице).

**Решение: из 64 ключей для ПЕРВОГО запуска берутся только 37** — LA/Beverly
Hills-специфичные + общие безгеографические (которые Google и так покажет
физически LA-аудитории благодаря гео-таргетингу кампании). Остальные 27
(Riverside, Fresno, San Bernardino, Bakersfield, Anaheim, Victorville,
Huntington Beach, Moreno Valley, Costa Mesa, Sherman Oaks, San Juan
Capistrano, Inland Empire, Marin County, San Luis Obispo, Santa Ana) —
отложены, не удалены: вернуться к ним при расширении лендинга/кампании на
всю Калифорнию.

**Финальные 37 ключей для запуска (PHRASE, кампания dog bite, final_url
landverpersonalinjury.tilda.ws/dog-bite):**

animal attack lawyer los angeles, attorney dog, best dog bite attorney near me,
best dog bite lawyers near me, beverly hills dog bite attorney, beverly hills
dog bite lawyer, bitten by a dog what to do, can a landlord be held responsible
for a tenants dog, can a landlord be responsible for a tenants dog, dangerous
dog lawyers, do i need a lawyer for a dog bite, dog attorney, dog attorney near
me, dog bite accident attorney, dog bite accident lawyer, dog bite at work, dog
bite attorney, dog bite claim, dog bite claim compensation, dog bite
compensation, dog bite injury lawyer near me, dog bite lawyer, dog bite lawyer
california, dog bite lawyer los angeles, dog bite lawyer near me, dog bite
settlement amounts california, dog bite settlement calculator, dog injury
lawyer, dog lawyer, dog lawyer near me, landlord liability dog bite, lawyer
dogs, lawyers that handle dog bites, lawyers that handle dog cases, neighbors
dog bit me, pit bull attack lawyer, pit bull lawyer

**Структура групп:** одна общая группа (не дробить на LA/Beverly Hills — см.
[[../Решения|Решения]] 2026-09-04, решение про объём слишком маленький для
дробления на старте).

**Отложенные 27 гео-ключей других городов CA** (для будущего расширения, НЕ
включать в текущий импорт): dog bite attorney riverside ca, fresno dog bite
lawyer, san bernardino dog bite lawyers/lawyer, dog bite lawyer anaheim,
riverside dog bite lawyers, bakersfield dog bite lawyer, dog bite lawyer
bakersfield, dog bite attorney bakersfield, victorville dog bite
lawyers/lawyer/attorney, huntington beach dog bite lawyer, dog bite lawyer
moreno valley, costa mesa dog bite lawyer/attorney, dog bite lawyer sherman
oaks, dog bite lawyer san juan capistrano, fresno dog bite injury attorney,
inland empire dog bite attorneys/attorney/lawyers/lawyer, marin county dog
bite lawyer, san luis obispo dog bite lawyer/dog bites attorney, santa ana
dog bites lawyer.

## Требование к будущему объявлению: разделить жертву и владельца собаки

Минус-слово "dog bite lawyer defense" закрывает только явные запросы
владельца собаки (со словом "defense" в тексте) — но большая часть базовых
широких запросов ("dog bite lawyer", "dog attack lawyer", "dog bite attorney
near me") двусмысленна: их с равной вероятностью может гуглить и жертва
укуса, и владелец собаки, которого укушенный собирается судить (или уже
подал в суд), и который ищет защиту. Минус-слова здесь бессильны — у самого
запроса нет отличительного слова. Единственный способ отсечь нецелевого
владельца до клика — сам текст объявления должен явно и многократно
сигнализировать, что предложение адресовано ИМЕННО пострадавшему (жертве
укуса), не владельцу собаки.

**Требование на этап составления объявления (следующий шаг, не выполнено
здесь):** в тексте будущего объявления (заголовки, описания, sitelinks,
уточнения/callouts) явно и НЕСКОЛЬКО раз в разных местах подчеркнуть адресата
— "injured", "victim", "bitten", "were you bitten" и т.п. формулировки со
стороны пострадавшего, избегать нейтральных формулировок вида "dog bite
legal help", которые одинаково читаются с обеих сторон. Зафиксировано по
прямому требованию пользователя 2026-09-04 — учесть при следующем шаге
(составление объявлений).
