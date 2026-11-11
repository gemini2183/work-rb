---
name: google-lsa-правила-лидов-и-рисков
description: Правила Google Local Services Ads (LSA) — оспаривание лидов, оплата пропущенных звонков, расписание показа, переход на Performance Max
status: не протестировано
updated: 2026-08-19
---

# Google Local Services Ads (LSA) — правила лидов и рисков

Собрано из официальных источников Google (support.google.com) 2026-08-19 по
запросу для [[../../Клиенты/Andverpersonalinjury/index|Andverpersonalinjury]]
(верификация LSA завершена в этот же день, канал только что запущен, см.
[[../../Клиенты/Andverpersonalinjury/Решения|Andverpersonalinjury/Решения]]).
Статус "не протестировано" — из внешних источников, не проверено на практике
на аккаунтах вики.

## Оспаривание нецелевых/невалидных лидов

Ручного оспаривания больше нет — заменено на **Auto Crediting System**:
- лид оценивается ML-моделью в момент первого контакта; невалидный сразу не
  тарифицируется
- уже оплаченный лид может быть переоценён позже, кредит начисляется
  автоматически (обычно в течение 30 дней)
- **лиды "job type not serviced" / "geo not serviced" НЕ кредитуются вообще**
  — ни автоматически, ни по запросу
- дополнительно credits недоступны для health care вертикалей, tax
  specialists, рекламодателей EMEA
- единственный оставшийся канал влияния — форма "Rate this lead" на странице
  лида (не гарантия возврата, сигнал алгоритму на будущее)

**Пошагово, что сделать с нецелевым лидом (проверено по тексту справки 2026-11-03, на практике не проверено):**
1. LSA-кабинет → меню (три полоски слева вверху) → **Leads** → открыть нужный лид.
2. **Rate this lead** (справа вверху) → **Open** → заполнить опрос и отправить. Это единственный подтверждённый в справке путь; возврат не гарантирован, Google решает сам. То же можно отправить через Google Ads API.
3. Окно — 30 дней с даты лида; после него кредит не рассматривается (по сторонним источникам; в справке 15100654 написано «credits typically appear within 30 days»).
4. Статус лида смотреть в отчёте: Not charged / Charged / In review / Credited. Кредит приходит на баланс, в счёте исходная строка остаётся.
5. Если нужен человек — «Contact us» из справки LSA (страница gethelp требует входа в аккаунт, содержимое не прочитано). Старая справка 7435486 («dispute within 30 days») описывает ручной процесс, который сторонние источники считают отключённым с июля 2024; справка 11444536 до сих пор говорит «you can dispute… US and Canada», страницу шагов «How to dispute charges» прочитать не удалось. Противоречие не снято.
5а. **Наблюдение 2026-11-03 (Landver):** в карточке лида со статусом «In review» (Archive) кнопки «Rate this lead» нет. Справка 7195435 говорит про опрос «на странице Leads в Google Ads», точный путь не даёт. Искать в списке лидов (строка / три точки), при отсутствии — Contact us. Почему кнопка скрыта — не подтверждено.
5б. **Как выглядит опрос «Rate this lead» (наблюдение 2026-11-04, Landver, лид со статусом Charged — кнопка появилась в карточке, пока был «In review» её не было):** шаг 1 — «How satisfied are you with the quality of this lead?», 5 смайлов; шаг 2 — «Which of the following best describes why you are not satisfied… Select all that apply»: не в зоне обслуживания / услуга, которой бизнес не оказывает / «The person calling was not ready to book services» / спам / дубль / работа или продажа / Other (текст, без персональных данных) + Submit. **Подвох:** по факту клик по пункту сразу отправил опрос, выбрать два пункта и дописать Other не удалось. Если нужны и пункт, и комментарий — вводить текст в Other и выбирать пункт одним ответом, либо отдельно писать в Contact us. Принимается ли повторная отправка — не проверено.
5в. **Ответ поддержки по обращению (Landver, лид 349650808, 05.11, наблюдение — один случай):** обращение через Contact us → Email закончилось отказом: лид «good lead», потому что в звонке обсуждалась информация о бизнесе, а звонивший сказал, что перезвонит в рабочие часы (Google читает это как намерение обратиться к рекламодателю). Дословно просят: если звонят по услуге, которой нет, вежливо сказать, что не помогаете, и быстро закончить звонок без сбора контактов (сообщение — отклонить); не направлять к другим исполнителям, иначе повторные случаи «могут оплачиваться». Следствие: «скрытый номер, телефон не дал, обещал перезвонить» довод не работает; решает то, что говорилось в звонке. Ответ пришёл через 1 день после подтверждения обращения.
6. Не кредитуются: «job type not serviced», «geo not serviced». Юристы в списке исключений справки не названы (названы health care, tax, EMEA).

Источники: [About Automated Local Services Ads lead credits](https://support.google.com/localservices/answer/15100654),
[Local Services Ads Deprecates Lead Disputes — Blue Corona](https://www.bluecorona.com/blog/google-local-service-ads-lead-dispute-deprecation)

**Следствие**: раз "не та услуга" не возвращается в принципе, единственная
защита — превентивная (таргетинг категорий услуг), не постфактум-оспаривание.
В LSA нет ключевых слов/минус-слов, как в обычном Search — таргетинг только
через чекбоксы "сфер деятельности и услуг".

## Оплата пропущенных звонков

Валидным (оплачиваемым) лидом официально считается:
- звонок, на который ответили и поговорили с клиентом
- звонок, оставленный на голосовую почту (даже без ответа)
- пропущенный звонок БЕЗ голосового сообщения — становится оплачиваемым,
  только если бизнес сам перезвонил/написал в ответ и состоялся контакт

Источник: [How leads work — Local Services Help](https://support.google.com/localservices/answer/7195435)

Отдельно от оплаты — пропущенные звонки официально снижают показатель
отзывчивости (responsiveness), а он влияет на ранжирование/частоту показа
объявления ("Missed calls may negatively affect your responsiveness").

Источники: [About ad rankings — Local Services Help](https://support.google.com/localservices/answer/7527305),
[Google LSA Missed Calls Cost You Twice — Tradesly AI](https://www.tradesly.ai/blog/google-lsa-missed-calls-ranking-penalty)

## Расписание показа объявления (Ad Scheduling)

Штатный инструмент, три режима:
1. круглосуточно (24/7)
2. по часам работы бизнеса (синхронизировано с профилем)
3. индивидуальное расписание (вручную дни недели + часы)

Вне выбранного расписания платное объявление не показывается — может
отображаться бесплатная версия профиля компании.

Источник: [About ad scheduling — Local Services Help](https://support.google.com/localservices/answer/9251526)

Прямой инструмент против риска "оплаченный лид в нерабочее время, когда
некому ответить" — сузить расписание под реальные часы доступности.

## Переход LSA на Performance Max (2026-2027)

Google поэтапно переводит LSA в модель Performance Max pay-per-lead внутри
основной платформы Google Ads:
- август 2026 — старт для отдельных категорий США (сантехники, HVAC,
  электрики); юридическая ниша не в первой волне
- конец 2026 — расширение на более широкий круг категорий
- 2027 — международные аккаунты и остальные категории

Не меняется (по заявлению Google): оплата только за валидные лиды,
размещение в Search/Maps, отсутствие ключевых слов в таргетинге.

Меняется: недельные бюджеты → дневные, отключается ручная максимальная цена
за лид, отменяются BBB-значки. **Отчёты о производительности НЕ переносятся
автоматически при миграции** — рекомендуется заранее сохранять историю.

Источник: [Local Services Ads transition to Performance Max — Google Ads Help](https://support.google.com/google-ads/answer/17213585)

## Номер телефона в LSA и колл-трекинг (добавлено 2026-10-14, не проверено на практике)

Запрос по [[../../Клиенты/Andverpersonalinjury/index|Andverpersonalinjury]]: заменить номер в LSA на статический номер Ringostat.

**Официально (Google, Local Services Help):**
- В объявлении показывается не бизнес-номер, а динамический Google forwarding number; выбрать его нельзя («There is no way to choose your tracking number»). Он пересылает звонок на «business phone number» из профиля LSA. [Manage leads and jobs](https://support.google.com/localservices/answer/6224859)
- Смена business phone number — в списке правок, которые делает только поддержка LSA, с верификацией (документы: DBA, регистрация бизнеса). В кабинете (Profile & Budget) поля для самостоятельной правки нет. [Edit your ad or business information](https://support.google.com/localservices/answer/7435507)
- В том же разделе: «Note that your business phone number must not be a tracking number» — прямое противоречие идее ставить туда номер колл-трекера.
- Business Profile привязывается (linking). **Уточнение 2026-10-14 по скриншоту кабинета Landver (раздел Business Verification → Google Business Profile):** Google пишет «When your Google Business Profile gets linked or updated for this Google Ads Account, certain business information will be sourced directly from your Google Business Profile and apply to your Google Local Services Ad». Список полей не назван; номер в карточке GBP (+1 310-461-3737) совпадает с номером в профиле LSA, где у телефона нет кнопки правки. Вывод: с высокой вероятностью телефон LSA берётся из Business Profile; формально поле не подтверждено Google. Справка 7435507 (правка телефона только через поддержку) описывает старый поток и в новом интерфейсе может не работать.

**Неофициально (практики, вендоры колл-трекинга):** номер колл-трекера в LSA ставят, меняя его через поддержку Google (WhatConverts, CallRail, ветка Local Search Forum); двойная пересылка (Google → трекер → офис) работает; возможна повторная верификация. Конверсии в Google Ads не вернутся, если не настроены Enhanced Conversions. Источники: [WhatConverts](https://www.whatconverts.com/help/docs/using-whatconverts/lead-tracking/call-tracking/add-a-phone-number-to-track-google-local-service-ads-calls/), [CallRail](https://support.callrail.com/hc/en-us/articles/41591539899277-How-to-set-up-Google-Local-Services-Ads-with-CallRail), [Local Search Forum](https://localsearchforum.com/threads/call-tracking-for-local-service-ads.57124/).

**Как увидеть звонки на уже существующий номер из Business Profile (2026-10-14, не проверено на практике):** два пути. (а) Переадресация у владельца номера (его оператор/АТС, не в Ringostat): номер → номер Ringostat → реальный приёмник; в Ringostat назначением указывать НЕ сам номер из профиля, иначе петля. (б) Перенос номера в Ringostat: у вендора «Port Existing Numbers» значится в функциях ([G2](https://g2.com/products/ringostat/features)), условия для США (LOA, сроки) не найдены. Оба пути дают один общий номер для всех источников (GBP, сайт, LSA): отдельно LSA по нему не выделить.

**Отдельная история (не путать):** сентябрь 2026 — в Google Ads объявления с локациями показывают номер Business Profile вместо номера из call asset; Google ответил, что при location+call assets звонок может идти на номер локации. Это про Google Ads, не доказательство, что LSA берёт номер из Business Profile. [SERoundtable](https://www.seroundtable.com/google-lsa-phone-number-42160.html)

## Бюджет LSA и показы (добавлено 2026-11-06, Landver; внешние источники не проверены на практике)
- По Google: порядок объявлений определяет аукцион из ставки и качества профиля, учитывается вероятность лида ([How bidding works](https://support.google.com/localservices/answer/10125017), [About ad rankings](https://support.google.com/localservices/answer/7527305)). Бюджет — верхний предел расхода, а не рычаг показов; точных весов Google не публикует.
- Стратегии LSA в справке: Maximize leads (рекомендована), Target CPL, Max per lead. В API у нашей кампании тип `MAXIMIZE_CONVERSIONS` — по `lsa_state.py` это «максимум заявок»; название в интерфейсе не сверено.
- Наши данные (`lsa_state.py`, Landver, 24.10–06.11): бюджет 428,57 $/день, с 06.11 00:20 — 600 $/день (правка с аккаунта adwhitemcc@gmail.com). 238 показов за 14 дней; расход только в 3 дня (28.10, 29.10, 02.11) — день с лидом стоит ≈ $300–430 на лид. Показы упали с 59 (02.11) до 2–10 в день после снятия услуги с нападениями вечером 02.11 (совпадение по времени, другие причины не исключены).
- Вывод: бюджет не был ограничением, повышение показов не даст; лимит — рейтинг и набор услуг.

## Business Profile и фото в LSA (добавлено 2026-11-06; справка Google прочитана, на аккаунте Landver не проверено)
- Для LSA нужен публичный проверенный Business Profile (GBP), связь через приглашение в Google Ads. Название, адрес и тип места идут из GBP в LSA и правятся только в GBP; изменения в LSA в GBP не возвращаются, синхронизируются только проверенные данные ([Manage your business details between GBP and LSA](https://support.google.com/localservices/answer/15683105)). В этой справке про фото, отзывы, телефон и зону обслуживания ничего нет.
- Фото в объявлении LSA берутся из профиля LSA («Profile and Budget»), не из GBP: «if you have photos in your Google Business Profile, you need to add them to your LSA profile» ([About Local Services Ads with photos](https://support.google.com/localservices/answer/15202088)). Фото проходят проверку качества до показа. Как Google выбирает, какие показывать, справка не объясняет; по сообщению 2024 года (Search Engine Land) выбор идёт по вероятности вовлечения — не из справки.
- Отзывы после связки ведутся в GBP и показываются в обоих местах — по стороннему источнику (Justia Onward), в справке не найдено. Влияние связки на ранжирование в найденных источниках не описано.
- Практика: фото из GBP (в том числе нерабочие) в рекламе LSA не появятся, пока их не загрузили в LSA, но показываются в карточке на Картах и в поиске. Проверять оба места.

## Требования к фото LSA и как достать оригиналы (добавлено 2026-11-10; требования прочитаны, в кабинете Landver проверен только интерфейс, статус «не протестировано» по правилам фото)
- Политика Local Services ([Google Ads Policy](https://support.google.com/adspolicy/answer/6245891)): от 640×640, JPEG/PNG/BMP/ICO, до 10 МБ, до 100 фото на аккаунт. Пропорции не заданы, квадрат не обязателен. Нельзя: телефон, почта, адрес на фото; скриншоты; размытые или тёмные; дубликаты; чужой водяной знак. С 02.08.2026 нельзя ИИ-обработанные и ИИ-фото в ЕС и штате Нью-Йорк (в Калифорнии в политике не оговорено).
- BrightLocal пишет про обложку «не меньше 1440×810, 16:9» со ссылкой на справку 9091766; справка отдаёт 404, в кабинете Landver отдельного поля «cover photo» нет — **не подтверждено**.
- Кабинет (Landver 10.11.2026): `ads.google.com/localservices` → аккаунт → меню → **Profile & budget** → карточка **Photos** (Add, View all photos: All / Pending review / Needs attention); отдельно **Headshot for your ad** и **Professionals**. Новые фото сначала в статусе Pending review.
- Превью из Google Карт (`=w203-h152-k-no` в конце адреса `lh3.googleusercontent.com/...`) — не оригинал. Замена суффикса на `=s0` отдаёт файл в полном размере (проверено 10.11.2026 на Landver: 203×152 → 1600×1200). Нейро-апскейл крошечных превью не нужен и для фото людей нежелателен (дорисовывает лица).
- Свои фото фирмы берутся с сайта (wp-content/uploads, оригиналы без суффикса `-WxH`), стоковые картинки сайта для LSA не использовать («original, not copied»).

## «Фото для объявления» (Headshot for your ad) vs карточка «Фотографии» (добавлено 2026-11-11; не протестировано)
- Два разных блока в Profile & budget. **«Фотографии» (Photos)** — галерея: загрузка пачкой (справка: «bulk upload, multi-select, bulk delete»), Google рекомендует 3–5+ и сам выбирает, какие показать в объявлении; потолок 100 на аккаунт (политика). **«Фото для объявления» (Headshot)** — один главный портрет, в интерфейсе Landver стоит «Сейчас показано» с одним снимком и карандаш для замены.
- Официальная формулировка (старая версия справки 9091766, цитата через marketingdr.co): «Select verticals on Local Services including law, real estate, and finance may have a main business headshot for their ad. They also optionally have headshots for individual professionals» — главный headshot в единственном числе (юристы, недвижимость, финансы), отдельно необязательные headshots отдельных специалистов. Требования к кадру: только голова и плечи, лицо по центру, смотрит в камеру, **один человек в кадре**, не логотип/здание, без текста, нейтральный фон, не ч/б и без сильных фильтров. Размер/пропорции в этой цитате нет (marketingdr), Dagmar 2023 пишет квадрат 1:1, от 500 px — вторично.
- Живая страница справки 9091766 (прочитана 11.11.2026 целиком, curl): раздел «Headshots requirements» есть только в оглавлении, тела раздела нет — убран. Сходится с in-account уведомлением октября 2026 (Search Engine Roundtable): «featured professionals will no longer show on your ads. Headshot is optional and won't affect ad serving. The rest of your ad, including photos, reviews, and more, won't change.» Про главный headshot отдельно ничего не сказано. Явного «только одно» в официальном тексте нет; единственное число в формулировке + одно фото в интерфейсе Landver.
- Clio (help.clio.com, 403, не прочитано) по пересказу пишет «до 5 headshots» — не подтверждено, вероятно про специалистов.
- Справка Google (15202088) про headshot ничего не говорит.
- 11.11.2026 прочитаны целиком (curl) «как заполнять разделы» — [Edit your ad or business information](https://support.google.com/localservices/answer/7435507), [Local Services Ads overview](https://support.google.com/localservices/answer/7549347), [Improve your LSA performance](https://support.google.com/localservices/answer/12492201): слов headshot / «фото для объявления» нет ни в одной. Разделы по справке: Business hours и Ad scheduling, Service area, Job types, Photos (только «personally identifying photos shouldn't be uploaded»), Budget, Business Bio (до 6 стандартных highlights), Insurance, Message leads, Link Business Profile; для юристов упомянуты featured professionals и Education. Официальной инструкции по полю headshot нет — подсказку смотреть в самом окне карандаша в кабинете. Вторичные источники (techwyse, miraflow, 2026) пишут, что Google убирает «featured professionals» и делает headshot необязательным (не влияет на показ) — официально не подтверждено, смотреть уведомления в кабинете.
