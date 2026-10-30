---
name: youtube-реклама-через-demand-gen-что-нужно-для-старта
description: Как рекламироваться на YouTube через Google Ads в 2026 (Demand Gen вместо Video action), что нужно для старта, требования к видео, бюджетные пороги Google против 1000 €, риски; факты справки отдельно от мнений практиков
status: не протестировано (справка и статьи, прочитано 2026-10-30; на наших кабинетах YouTube-only не запускался)
updated: 2026-10-30
---

# YouTube-реклама через Demand Gen: что нужно для старта

Поводом был ProfiMet (ноябрь 2026, ≈1000 €, отдельная статья оплаты). Решения по клиенту — в `Клиенты/ProfiMet/Решения.md`.

## 1. Где и как это покупается (справка Google)
- Реклама YouTube идёт через **Google Ads**. Video action campaigns (VAC, «видео под конверсии») **заменены Demand Gen**: создание VAC убрано в апреле 2025, остатки переведены автоматически до апреля 2026. Старые инструкции по VAC устарели. Источник: [Video Action Campaigns are being upgraded to Demand Gen](https://support.google.com/google-ads/answer/15110871?hl=en).
- Для заявок на YouTube — **Demand Gen, цель «Конверсии»** (не «Клики» и не «Просмотры»), ставка «Максимум конверсий» (по умолчанию) или целевая цена. Каналы выбираются на уровне группы объявлений: YouTube in-stream, in-feed, Shorts (можно оставить только YouTube). Источники: [Channel controls](https://support.google.com/google-ads/answer/15973205), практик [Inceptly: как повторить VAC в Demand Gen](https://inceptly-agency.beehiiv.com/p/you-miss-vac-here-s-how-to-recreate-it-in-demand-gen-step-by-step).
- Остальные кампании «Просмотры» (VVC) и «Охват» (VRC) покупают просмотры/показы, а не заявки: плата за просмотр (30 секунд или взаимодействие; Shorts — 10 секунд) или за 1000 показов. Для заявок не подходят. Источник: [About video ad formats](https://support.google.com/google-ads/answer/2375464?hl=en).
- **Тип «Video» при цели «Leads» (проверено в кабинете ProfiMet 2026-10-30):** плитка «Video — Generate leads on YouTube» есть, но по «Continue» открывает **тот же мастер Demand Gen** (URL `/new/demandgen?fromVideo=true`) с баннером «You can no longer create new video conversion campaigns because they're being upgraded to Demand Gen campaigns». Отдельной видеокампании под заявки создать нельзя. Справка Google при этом противоречит сама себе: [Create a Video action campaign](https://support.google.com/google-ads/answer/10146226?hl=en) пишет «upgraded to Demand Gen as of May 2026», но тут же описывает шаги и подтип «Drive conversions»; кабинету верить больше.
- В мастере Demand Gen вкладка загрузки видео есть (Upload; лимит в подсказке 1 GiB, длительность до 60.00); в библиотеке ассетов ProfiMet уже 9 видео (10–15 с).
- Форматы: skippable in-stream (пропуск через 5 с, без максимума длины, до 3 мин рекомендовано), in-feed (плата за клик), Shorts (до 60 с рекомендовано). Bumper и non-skippable — только в «Охвате», для заявок не наш вариант.

## 2. Что нужно для запуска (чек-лист)
1. **Доступ к каналу YouTube клиента.** Канал нужен для ролика (ссылка на YouTube-видео) и для списков ремаркетинга (зрители канала). Приглашение менеджером должно быть принято со стороны нашего аккаунта (на скриншоте 30.10 «Ожидает подтверждения»).
2. **Связка канал ↔ Google Ads.** YouTube Studio → Настройки → Канал → Расширенные настройки → Связать аккаунт Google Ads; ссылку подтверждает владелец аккаунта Ads; без связки списки зрителей не строятся ([справка](https://support.google.com/google-ads/answer/2545661?hl=en-GB)). Google заявлял автосвязку каналов с аккаунтами после 10.06.2026 с возможностью отказа ([SEL](https://searchengineland.com/google-to-auto-link-youtube-channels-and-google-ads-accounts-465110)); в нашем кабинете не проверено. Какая именно роль канала достаточна для связки (менеджер или владелец) — в официальной справке не нашёл, проверить.
3. **Видео на канале YouTube** (Demand Gen берёт ссылку на YouTube-ролик). Лежат в Drive-папке клиента, на канал нужно загрузить; будет ли подходить «не в списке» — не проверено.
4. **Конверсии**: тег Google, цели Ads, Ringostat — как у остальных кампаний (одна категория цели, см. [[Demand-Gen-бюджет-цели-ставки-и-почему-нет-показов]]).
5. **Номер Ringostat под YouTube** и проверка подмены `phone_swap_check.py` (запись в `Пул_номеров.yaml`). Ringostat не отдаёт разбивку по сети показа, поэтому без отдельного канала звонки с YouTube не отличить ([[../../Клиенты/ProfiMet/Решения]] 2026-10-07).
6. **Объявление Demand Gen**: ≥1 видео, финальный URL, до 5 заголовков и 5 описаний, кнопка действия, название бизнеса, логотип (по Inceptly и справке).
7. **Исключения площадок** уровня аккаунта (детские каналы, 726 шт., [[Performance-Max-площадки-инвентарь-и-исключения]]) действуют на все кампании аккаунта.

## 3. Требования к видео (справка [Demand Gen asset specifications](https://support.google.com/google-ads/answer/13704860?hl=en))
- Форматы: 16:9 (1920×1080), 1:1 (1080×1080), 4:5 (1080×1350), 9:16 (1080×1920, рекомендован для Shorts).
- Минимум 5 секунд; **ролики короче 10 с не показываются в in-stream**.
- Рекомендация Google: хотя бы одно видео каждого формата (вертикальное, квадратное, горизонтальное) ([Best practices](https://support.google.com/google-ads/answer/14693848)).
- Структура по практикам (агентские блоги, **гипотеза для A/B, не норма**): зацепка в первые 5 секунд с указанием, кому ролик, одна кнопка действия, цена/доказательство; длинные ролики — in-stream, короткие с сильной миниатюрой — in-feed, вертикальные до 60 с — Shorts; длинный ролик на Shorts — ошибка.

## 4. Бюджетные пороги Google против малого бюджета
- Две официальные страницы дают **разные** пороги (прочитаны дословно 2026-10-30):
  - [The YouTube Performance Four](https://support.google.com/google-ads/answer/14693848) (общий гайд по YouTube, не страница только про Demand Gen), раздел «Set Sufficient Budgets»: «Maximize Strategies (Maximize Conversions/Maximize Conversion Value): Set a daily budget of $100 or more»; «Target Strategies (tCPA/tROAS): … at least 10x your target CPA»; «Do not evaluate performance until the campaign has generated at least 50 conversions»; менять ставки/бюджет на 5–10% в неделю, не более 15%.
  - [Fix Demand Gen campaigns not running or low traffic](https://support.google.com/google-ads/answer/14718973), раздел про низкий бюджет: для конверсионных стратегий «at least 20 times your average target CPA»; для Maximize Clicks минимума нет, «a good practice is to use at least $100 USD per day, per ad group»; симптом нехватки бюджета — статус «Eligible (Limited)», «your ads may not serve as often».
  - $100 — рекомендация («recommend/good practice»), а не запрет; последствия ниже порога в справке описаны только как реже показы и статус Eligible (Limited). Про срыв обучения или отказ запустить справка не пишет.
- На ProfiMet кабинет сам порекомендовал не менее 25 €/день и предупредил про смешанные цели ([[Demand-Gen-бюджет-цели-ставки-и-почему-нет-показов]]).
- Там же, [та же страница 14718973](https://support.google.com/google-ads/answer/14718973), «Budget tips for Demand Gen»: «at least $500 USD per ad group, per day will help drive effective and efficient performance» (и $100 — чтобы «avoid a cold start»). Прочитано 2026-10-30.
- Жёсткий технический порог: **5 $ в день** на кампанию Demand Gen через API с 01.04.2026, ошибка `BUDGET_BELOW_DAILY_MINIMUM`; Google объясняет его «cold start» ([ppc.land по блогу Google Ads Developers от 27.02.2026](https://ppc.land/google-to-enforce-5-minimum-daily-budget-on-demand-gen-campaigns-from-april/)).
- Продуктовый менеджер Google по Demand Gen Alejandro Osio (подкаст Ads Decoded, 01.10.2026): «a hundred dollars daily budget, which is bare minimum best practice»; что бывает ниже — не сказано ([ppc.land](https://ppc.land/google-pm-calls-100-a-day-the-floor-for-a-demand-gen-campaign/)). Пересказ издания, не первоисточник.
- Практики (мнения, данных не приводят): Lysible — 30–50 €/день для отслеживаемых заявок, 10–15× цели конверсии для выхода из обучения, меньше 15–20 конверсий в неделю = бюджет ниже критического ([статья](https://www.lysible.com/en/blog/google-ads-demand-gen)); Amir Gomez — 10–20 $/день только для «направленных данных», для лидгена 1500–3000 $/мес ([статья](https://www.amirgomez.com/blog/youtube-ads-minimum-budget-2026)); Fospha по программе с Google (25 ретейл-брендов, Q4 2025) — около 130 $/день на кампанию и не меньше 9 ассетов ([страница](https://www.fospha.com/fospha-academy-lessons/how-much-of-your-google-budget-should-go-to-demand-gen)). Слова Aleric Heck про 25–50 $/день на in-stream подтвердить не удалось (страница подкаста про бюджет молчит), в основу не брать.
- Итого 1000 €/мес ≈ 33 €/день — ниже $100 из первой страницы, но выше 25 € из подсказки нашего кабинета; 50 конверсий за месяц при цене заявки 30–60 € недостижимы (17–33 заявки).

## 5. Что известно о результатах (мнения и кейсы, не наши данные)
- Кейс [Getuplead](https://getuplead.com/?p=6776) (B2B, Demand Gen только YouTube, янв–май 2026): холодная аудитория — заявка 826 $ (in-stream) и 3137 $ (in-feed); ретаргетинг — 303 $ (in-feed); Gmail давал 19 449 кликов и 0 конверсий; автор не называет канал надёжным после 4 месяцев. Не наша ниша.
- Практики советуют: сначала убрать Gmail/Discover/Google TV, холодный трафик — in-stream, тёплый — in-feed, считать по заявке/продаже, а не по просмотрам; оптимизация на «Просмотры» привлекает дешёвые случайные просмотры.
- В Demand Gen много конверсий YouTube приходится на **engaged-view** (просмотр без клика): они завышают отчёты и их нужно сверять с реальными звонками/формами (Best practices, «Prioritize PII or IP identifiers»).

## 6. Что уже есть по ProfiMet (наши данные)
- YouTube внутри PMax (`pmax1_test`, 01.09–08.10): 27% расхода, 11% конверсий, **CPA 88 €** по Ads; показы в основном детские ролики (Э-03).
- Demand Gen на Discover/Gmail: `dg_lookalike_test` 67.8 € → 0 заявок, `dg_interest_nodiscover` 29 € → 0 заявок; нулевые показы лечились целью (одна категория), бюджетом 25 € ([[Demand-Gen-каналы-и-миграция-Display]]).
- YouTube-only Demand Gen на ProfiMet **не запускался**: гипотезы ниже не проверены.

## 7. Видео: где лежит ролик и «служебный канал» (30.10.2026)
- Файл с компьютера в объявление не вставить: [Demand Gen video assets](https://support.google.com/google-ads/answer/17141078?hl=en) — «You can't upload an offline video»; ролик должен быть на YouTube, для показа без публикации годится unlisted.
- В мастере кампании есть вкладка **Upload** (в кабинете ProfiMet проверено 30.10, без загрузки файла): подсказка «длительность 0.01–60.00, до 1 GiB». Справка [Create a Demand Gen campaign](https://support.google.com/google-ads/answer/13695389?hl=en) на шаге загрузки даёт выбор места: **«Your video ad storage channel, created by YouTube»** или **«Your own channel»**. В интерфейсе этот выбор до выбора файла не появился; куда реально попадёт ролик — не проверено.
- Служебный канал (по [Upload videos, Google Ads API](https://developers.google.com/google-ads/api/docs/assets/upload-videos), про API, не про интерфейс): «Google-managed YouTube channel associated with the Google Ads account», только unlisted, название/описание/канал не меняются, переноса на свой канал в документации нет. «Реклама от имени бренда» задаётся полями объявления: название бизнеса (до 25 знаков) и квадратный логотип (в YouTube-форматах берётся логотип из объявления, не канала).
- Канал клиента нужен только для списков зрителей (связка канал ↔ Ads). Ролики короче 11 с (Shorts — 10 с просмотра) в такие списки не попадают; bumper и non-skippable не идут в списки вовсе.
- В библиотеке ассетов ProfiMet уже 9 видео (10–15 с); два около 10 с — на границе показа в in-stream.

## 8. Частота показов (проверено в кабинете ProfiMet 2026-10-30)
- В мастере Demand Gen **нет настройки частоты** ни на уровне кампании (Location and language, Devices, Ad schedule, Third-party measurement, Campaign URL options, IP exclusions), ни группы. Лимит частоты есть у Видео-кампаний (in-stream/bumper, [Use frequency capping](https://support.google.com/google-ads/answer/6034106)), создавать которые больше нельзя. Сторонний блог пишет, что в Demand Gen он есть — кабинет не подтверждает.
- Косвенно: размер бюджета против размера списка, шире аудитория, исключение конвертировавшихся/CRM-клиентов; частоту оценивать как показы ÷ размер списка и по падению CTR/доли досмотров ролика. Метрика частоты в отчётах Demand Gen — проверить после запуска.

## 9. Как менять ролики: данные, а не календарь (30.10.2026)
- «14 дней» — единственная цифра Google ([Best practices](https://support.google.com/google-ads/answer/14693848): «only pause those that are low-performing and have had at least 14 days to ramp up»); обоснования и определения «ramp up» на странице нет. Соседние правила: «add new assets before removing old ones», менять небольшую часть, новые материалы массово — в новой кампании (новое обучение), 50 конверсий до оценки кампании.
- Google (Ads Decoded, по пересказу из выдачи) активно заменять предлагает, когда достигнут лимит ассетов в объявлении и конкретный ассет заметно просел относительно собственного старта; срока нет. Статус «Learning» у ассета в API — «статистика недостаточно значима для оценки».
- Календарные сроки у практиков (7–14 дней, 4–6 недель, квартал) разнятся в разы, исследований нет; частота 2–6 показов на человека в неделю — тоже из блогов.
- Критерий должен быть по объёму: показов на ролик для различения при 5% ошибке и мощности 80% (расчёт 30.10, формула разности долей; базовые CTR — допущение): CTR 0.5% → +50% ≈ 15 600; 1% → +50% ≈ 7 750; 1% → +30% ≈ 19 800; 2% → +50% ≈ 3 800. Доля досмотров 20% → 26% ≈ 770. Клик→заявка 3% → 4.5% ≈ 2 500 кликов (при малом бюджете недостижимо — судить по заявкам по ролику нельзя, только по кампании).
- Рабочая схема (предложение, не норма): не оценивать ролик меньше ≈ 5 000 показов и ≈ 100 досмотров; пауза — если досмотры и CTR ниже лучшего ролика группы за пределами доверительного интервала при достаточном объёме; усталость — частота растёт, а CTR/досмотры падают относительно собственного старта; новый ролик добавлять, а не заменять.
- A/B встроенный (Asset uplift experiment, ноябрь 2025): одна переменная, не править кампанию в ходе теста, срок 4–6 недель, бюджет ≈ 100 $/день на группу ([Create A/B experiments for Demand Gen](https://support.google.com/google-ads/answer/13719071), [SEL](https://searchengineland.com/measure-demand-gen-creative-impact-asset-uplift-tests-474868)) — для 33 €/день не подходит.

## 10. Структура и учёт для малого бюджета (30.10.2026)
- Порог продажи 30 € ÷ доля заявок, дошедших до продажи = допустимая цена заявки (60% → 18 €, 40% → 12 €, 30% → 9 €).
- Замер ProfiMet (звонки с рекламы Google/Facebook, 126 номеров, 01.08–09.09): до продажи дошло 36.5%; в день звонка 19%, за 7 дн. 27%, за 14 дн. 30%, за 30 дн. 33%; среди купивших 74% за неделю, 83% за две, 91% за месяц ([[../../Клиенты/ProfiMet/Хроника_2026-10]]). Прежнее «созревает 2–3 недели» было словами клиента и замером не подтвердилось.
- Одна группа на кампанию; несколько близких аудиторий не дробить (Google: объединять группы с < 30 конверсиями за 30 дней).
- Просмотры без клика: engaged-view (10 с in-stream; 5 с in-feed/Shorts) идут в колонку «Конверсии»; view-through — отдельная колонка, окно настраивается, оптимизация под них для YouTube-only Demand Gen по умолчанию выключена; люди, взаимодействовавшие с другими объявлениями, из view-through исключаются ([About view-through conversions](https://support.google.com/google-ads/answer/16542520?hl=en)). Связь «просмотр YouTube → Brand → заявка» в Ads, Ringostat, Supabase не видна; косвенно — Brand до/во время/после и вопрос «откуда узнали».

Связано: [[Demand-Gen-пользовательские-сегменты-по-поисковым-запросам]], [[Demand-Gen-look-alike-уровень-охвата-и-список-основы]].
