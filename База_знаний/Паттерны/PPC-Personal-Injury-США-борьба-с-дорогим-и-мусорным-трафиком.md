---
name: pattern-ppc-personal-injury-usa-cheap-and-clean-traffic
description: Лучшие практики контекстной рекламы (Google Ads) для personal injury юристов в США — как бороться с фрод-трафиком Search Partners и с высокой ценой клика на обычном поиске
status: частично проверено на аккаунте Andverpersonalinjury (раздел 1a)
updated: 2026-08-19
---

# PPC Personal Injury (США) — борьба с дорогим и мусорным трафиком

Собрано по запросу в контексте [[../Andverpersonalinjury/index|Andverpersonalinjury]]
(Andverpersonalinjury, landverpersonalinjury.com, "Landver Law") — жалоба: с
Search Partners идёт много трафика без единого обращения (подозрение на бот-
трафик), а на чистом Google Search цена конверсии от $60, что для текущего
бюджета клиента дорого. Источники — внешний поиск (WebSearch), см. ссылки в
конце каждого раздела. **Ничего из этого не проверено на кампаниях клиента** —
статус "не протестировано" до практической проверки.

## 1. Search Partners в Personal Injury — это известная, задокументированная проблема

Подозрение пользователя о боте/фроде — не паранойя, а совпадает с массовыми
жалобами PPC-сообщества за последний год:

- Google в августе 2025 добавил **полноценный Placement Report по Search
  Partner Network** (раньше такой прозрачности не было в принципе) —
  индустрия явно требовала этого именно из-за подозрений на мусорный трафик.
- Независимый разбор Seer Interactive: из **3785 проверенных плейсментов
  Search Partners — 3785 признаны мусором** (parked domains и подобное).
- В отдельном анализе 220 000+ плейсментов **до 30% расходов на Search
  Partners** в некоторых аккаунтах уходило на фродовый/невалидный трафик.
- Search Partners систематически более уязвимы к бот-трафику и клик-фроду,
  чем чистый Google Search, потому что Google слабее контролирует
  сторонние сайты-партнёры, через которые идёт показ.

**Практический вывод**: отключение Search Partners (и Display expansion) —
не экзотика, а стандартная рекомендованная практика именно для personal
injury PPC, где цена клика уже высока и каждый нецелевой клик особенно
болезненный. У клиента подозрение полностью укладывается в эту картину —
см. задачу на аудит в [[../../Клиенты/Andverpersonalinjury/Задачи|Задачи клиента]].

**Как проверить, а не просто выключить вслепую**: прежде чем отключать —
вытащить Search Partner Network Placement Report (доступен с августа 2025),
сегментировать по категориям доменов (parked/directory/video/...),
сопоставить с конверсиями (не только показами), приоритетно исключить
parked domains через Category Exclusions — это единственная категория,
которую можно исключать и в Search, и в Display одновременно. Если после
разбора всё равно решено оставить Search Partners включёнными — делать это
осознанно, а не по умолчанию.

Sources:
- [Google Search Partners Ad Fraud: How to Spot It, Stop It, and Save Your Budget](https://spideraf.com/articles/google-search-partners-ad-fraud-how-to-spot-it-stop-it-and-save-your-budget)
- [Of 3,785 Google Search Partner Placements Reviewed: 3,785 Were Garbage](https://www.seerinteractive.com/insights/search-partner-parked-domains-garbage)
- [Google Ads Search Partner Network Placement Report — ALM Corp](https://almcorp.com/blog/google-ads-search-partner-network-placement-report/)
- [Google Quietly Announces Search Partner Network Placement Visibility — Search Engine Journal](https://www.searchenginejournal.com/google-quietly-announces-search-partner-network-placement-visibility/554294/)
- [Complaints On Google Ads Search Partners Network Fraud — SE Roundtable](https://www.seroundtable.com/google-search-partners-ad-network-fraud-38063.html)

## 1a. Проверено на аккаунте Andverpersonalinjury (2026-08-19) — гипотеза подтвердилась

Написан скрипт `Скрипты/gads_search_partners_audit.py` (см. `Скрипты/README.md`)
и прогнан на customer_id `213-621-6123` за последние 30 дней
(2026-07-20 → 2026-08-18). Два реальных API-ресурса задействованы:
`segments.ad_network_type` на кампании (агрегат по сетям) и
`detail_content_suitability_placement_view` — новый ресурс от августа 2025,
дающий конкретные домены внутри Search Partners (только impressions, без
clicks/cost/conversions — ограничение самого API, см. docstring скрипта).

**Сводка по сетям за 30 дней (все кампании клиента вместе):**

| Сеть | Клики | Расход | Конверсии |
|---|---|---|---|
| SEARCH | 202 | $1258.56 | 32 |
| SEARCH_PARTNERS | 1084 | $1516.91 | 10 |
| CONTENT | 466 | $52.11 | 0 |

Search Partners даёт **в 5+ раз больше кликов**, чем чистый Search, почти
столько же денег (даже чуть больше!), но **в 3+ раза меньше конверсий** —
и большая часть даже этих немногих конверсий пришла не из Search-кампаний, а
из `pmax / ca` (Performance Max), где Search Partners неожиданно оказался
эффективнее ($19.75/конверсия против $31.03 у Search той же кампании).

**По чистым Search-кампаниям картина хуже**: в кампании
`search / car accident / ca - google search + network` (название буквально
содержит "+ network" — Search Partners включены сознательно) —
483 клика / $529.12 на Search Partners дали **0 конверсий**. В кампании
`search / all injuries` — 369 кликов / $524.83 на Search Partners дали
**1 конверсию** ($524.83 за неё). Это именно те кампании, где стоит
отключать Search Partners в первую очередь.

**Список площадок (detail_content_suitability_placement_view) подтверждает
подозрение на фрод/арбитраж, а не легитимных партнёров**: подавляющее
большинство показов в Search-кампаниях (не Display/PMax) уходит на кучку
малоизвестных "search feed"/arbitrage-доменов, а не на узнаваемые сайты:
`reviews.everydayxperts.com/search`, `bozuktus.com/blog/query`,
`wiseinmind.com/search`, `searchjobsplus.com/afs`, `infonowplus.com/afs`,
`selectanswers.com/topic/...`, `supremeinsights.com/topic/...`,
`selectadvise.com/topic/...`, `www.indiasite.com/get/result`,
`www.redesigndaily.com/dcg/search`, `search.savvyvita.com/serp`,
`gkinmarathi.in/wp-code` (индийский домен на языке маратхи — прямое
совпадение с подозрением пользователя об индийском бот-трафике). Общий
паттерн URL — искусственные "результаты поиска" (`/search`, `/serp`,
`/afs`, `/topic/<id>`, `/get/result`) без узнаваемого бренда/контента —
классический признак search arbitrage-сети, а не реального сайта с
органическим поисковым виджетом.

Полные данные — `Клиенты/Andverpersonalinjury/Статистика/gads_network_breakdown_2026-07-20_to_2026-08-18.csv`
и `gads_search_partner_placements_2026-07-20_to_2026-08-18.csv` (1081 площадка).

**Вывод**: гипотеза пользователя подтверждена данными, не только внешними
бенчмарками — трафик с Search Partners в Search-кампаниях этого клиента
реально идёт с площадок низкого качества и почти не конвертит. Ограничение:
сам список площадок даёт только impressions, не клики/деньги/конверсии по
каждому домену отдельно — точную "стоимость проблемы по домену" из API не
вытащить, но сопоставление "какие кампании показываются на этих доменах" +
агрегат по сети на уровне кампании (таблица выше) достаточно для решения.

**Точечное исключение конкретных площадок vs отключение сети целиком —
важное ограничение Google Ads (проверено 2026-08-19 по документации
поддержки, не в интерфейсе аккаунта):** Placement Exclusion Lists (Tools &
Settings → Shared Library) позволяют исключить конкретный домен, но **только
на уровне всего АККАУНТА**, не кампании — исключение действует сразу на ВСЕ
кампании, использующие Search Partners, включая Performance Max. Для этого
аккаунта это критично: `pmax / ca` — кампания, где Search Partners наоборот
эффективнее обычного Search ($19.75 за конверсию против $31.03, см. раздел
1a) — аккаунт-level исключение задело бы и её тоже. Дополнительно: исключение
домена НЕ распространяется на поддомены в Search Partners (в отличие от
Display/YouTube) — нужно вносить точный поддомен из списка площадок, не
базовый домен. Вступает в силу ~12 часов.

**Вывод по инструменту**: для проблемных Search-кампаний правильный уровень
воздействия — не placement exclusion (бьёт по всему аккаунту), а отключение
Search Partners на уровне САМОЙ КАМПАНИИ (campaign.network_settings,
доступно per-campaign) — это не затронет pmax/ca. Placement exclusions имеет
смысл держать в резерве как точечный инструмент, если в будущем конкретные
мусорные домены появятся именно в pmax/ca, которую полностью отключать от
Search Partners не хочется.

Sources:
- [Exclude placements at the account level — Google Ads Help](https://support.google.com/google-ads/answer/7331110?hl=en)
- [Google advertisers can now opt out of Search Network — Search Engine Land](https://searchengineland.com/google-advertisers-opt-out-search-partner-network-adalytics-435513)

## 1b. Механика "трафик из LA, но толку нет" — geo-masking через residential proxy

Уточнение пользователя (2026-08-19): у клиента в кампаниях выставлен таргетинг
**Presence** (не Presence-or-Interest/Interest) — то есть настройка гео сама
по себе корректная, не ошибка конфигурации. При этом отчёт по локациям в
Google Ads показывает трафик именно "из Лос-Анджелеса" — и всё равно 0
конверсий. Вопрос "как боты обходят гео-таргетинг, если стоит Presence" —
разобран отдельно, т.к. это не то же самое, что путаница Presence/Interest.

**Ответ — это не обход таргетинга, а подмена сигнала, на основе которого
Google принимает решение о таргетинге.** Presence определяется ТОЛЬКО по
IP-адресу запроса — никакой другой проверки физического местоположения нет.
Отдельная индустрия мошенничества использует **residential proxy сети** —
пулы реальных домашних/мобильных IP-адресов в США (арендованные легально
через proxy-провайдеров или полученные через заражённые устройства), через
которые прогоняется бот/клик-ферм-трафик. Google видит валидный
американский IP, привязанный к LA, и честно репортит рекламодателю "трафик
из LA" — потому что с точки зрения IP-геолокации это правда. Физически
источник трафика (человек за клик-фермой или скрипт) может находиться где
угодно, в т.ч. в Индии — IP-адрес просто взят "напрокат" у устройства в США.

Отдельный термин в индустрии — **geo-masking**: использование VPN/proxy/
residential proxy для маскировки реальной геолокации под целевой рынок
(US/UK/Germany и т.п.), чтобы низкоценный трафик выглядел как высокоценный
для рекламодателя. Встроенный фильтр невалидных кликов Google Ads это
ловит НЕ полностью — по независимым оценкам пропускает 5-22% такого
трафика, что и объясняет, почему в отчётах аккаунта клиента это выглядит
как обычный чистый трафик из нужного гео.

**Практическое следствие**: отличить такой клик от клика реального жителя
LA по данным, доступным в самом Google Ads (гео-отчёт, клики/показы/
конверсии), НЕЛЬЗЯ в принципе — оба выглядят идентично на уровне IP.
Единственный способ отличить — специализированный click-fraud инструмент
(см. раздел 2), который анализирует более глубокие сигналы (репутация IP —
известен ли он как datacenter/residential proxy, поведение на странице,
скорость клика, паттерны устройства), а не полагается на гео-отчёт Google
Ads как на источник истины.

Sources:
- [Residential Proxies and IP Masking Use In Ad Fraud — Fraudlogix](https://www.fraudlogix.com/blog/ad-fraud-101-understanding-the-role-of-residential-proxies-and-ip-masking/)
- [Geo-Masking: How Fraudsters Hide Their Real Location — Opticks Security](https://optickssecurity.com/fraud-types/geo-masking)
- [Can click fraud come through residential proxies? — ClickCease Blog](https://www.clickcease.com/blog/can-click-fraud-come-through-residential-proxies/)

## 2. Специализированные инструменты защиты от клик-фрода

Отраслевой стандарт для юр. ниши — не полагаться только на встроенную защиту
Google, а ставить отдельный инструмент, который блокирует источник по
паттернам (одно устройство, странные часы, скрытая геолокация, повторные
визиты без конверсии):

- **ClickCease** — самый широкий охват каналов (не только Google Ads),
  тарификация по визитам, годовые контракты; хороший дефолт при бюджете
  до ~$50k/мес.
- **ClickGuard** — специализация именно на Google Ads, 50+ настраиваемых
  правил, более гибкая кастомизация под конкретный кейс.
- Другие игроки того же класса: PPC Protect, TrafficGuard, Lunio, CHEQ,
  ClickPatrol, Fraud0.
- Дополнительно к автоматике — вручную блокировать IP конкурентов,
  найденные в логах, и раз в квартал подавать в Google запросы на возврат
  за невалидные клики (invalid click refunds).

Sources:
- [Best Click Fraud Protection Software 2026 — TrafficGuard](https://www.trafficguard.ai/blog/best-click-fraud-protection-software-protect-your-ppc-campaigns)
- [ClickGUARD vs ClickCease](https://cgnew.clickguard.com/clickguard-vs-clickcease/)
- [Click Fraud for Lawyers & Law Firms — Consultwebs](https://www.consultwebs.com/online-advertising/pay-per-click/click-fraud/)

## 3. Реалистичные бенчмарки CPC для personal injury в LA — $60 это ещё дёшево

Цифры из нескольких независимых источников сходятся: в крупных метро (LA,
NY, Chicago, Miami) высокоинтентные PI-запросы стоят кратно больше $60:

- "personal injury lawyer" в LA — от **~$158/клик**.
- Широкие ключи в LA/NY/Miami — от **$300+/клик**.
- Топовые high-intent запросы ("car accident lawyer near me", "motorcycle
  injury attorney", "personal injury lawyer [city]") в топовых метро —
  **$250–400/клик** по бенчмарку ROA Marketing на 2026 год.
- Общий разброс по нише — **$70–250/клик** в зависимости от гео и
  конкуренции; крупные метро дают множитель 1.5–3x к CPC пригородов за те
  же ключи.
- Заявленные месячные бюджеты, реально конкурирующие на топовых терминах в
  LA/NY/Chicago — **$20 000–100 000+/мес**.

**Вывод для клиента**: цена закрытия (или клика — уточнить у пользователя,
что именно измеряется под "$60") на чистом Google Search в LA — это НЕ
аномалия и не признак плохой настройки кампании, а рыночная реальность
самой дорогой рекламной ниши в США. При текущем уровне бюджета конкурировать
в лоб за широкие "personal injury lawyer" / "car accident lawyer" в
Лос-Анджелесе структурно не получится — нужна не столько оптимизация
имеющихся кампаний, сколько смена стратегии охвата (см. разделы 4–6).

Sources:
- [Personal Injury Lawyer PPC — Savvy Law Firm Marketing](https://savvylawfirmmarketing.com/blog/personal-injury-ppc/)
- [Personal Injury Law Firm Google Ads Cost 2026 — The Valley Marketing Group](https://thevalleymarketinggroup.com/blog/personal-injury-law-firm-google-ads-cost-2026/)
- [Cost Per Click Benchmarks for Personal Injury — Custom Legal Marketing](https://custom.legal/practice-areas/personal-injury-law-firm-marketing/cost-per-click-benchmarks-for-personal-injury/)
- [Google Ads for Personal Injury Lawyers: Beating the $300 CPC Problem — iMark Infotech](https://www.imarkinfotech.com/google-ads-for-personal-injury-lawyers-beating-the-300-cpc-problem/)

## 4. Google Local Services Ads (LSA) — вероятно, главная альтернатива для этого бюджета

Принципиально другая модель, снимающая именно ту проблему, с которой клиент
столкнулся (дорогой клик без гарантии обращения):

- **Pay-per-lead, не pay-per-click** — платишь Google не за клик, а за
  фактический звонок/сообщение. Это структурно устраняет риск "трафик без
  выхлопа", т.к. нецелевые клики/показы вообще не тарифицируются.
- Позиция — НАД обычными Search-объявлениями, тот же самый высокоинтентный
  сегмент запросов ("personal injury lawyer near me").
  В одном из разобранных кейсов конверсия звонков с LSA была **в 2.5 раза
  выше**, чем со стандартного PPC.
  Требует Google Screened (проверка лицензии, страховки, бэкграунд-чек
  адвоката/фирмы) — процесс не мгновенный, но это же и барьер для
  конкурентов с меньшим доверием.
- Хорошо ложится на цитируемую в вики методологию — платишь по факту лида,
  что снимает саму постановку вопроса "трафик есть, а обращений нет"
  (см. [[Сверка-конверсий-Директ-Метрика-Коллтрекинг]] — там тоже речь про
  то, что "нет обращений" по одному каналу измерения ещё не значит "канал
  не работает"; для LSA эта проблема просто не возникает, раз оплата идёт
  по лидам, а не по кликам).

**Рекомендация**: с учётом ограниченного бюджета клиента и уже
зафиксированной проблемы с нецелевым трафиком, LSA — первый кандидат на
пилот, до дальнейшей оптимизации Search-кампаний.

Sources:
- [Local Services Ads for Lawyers — LawRank](https://lawrank.com/local-services-ads-for-lawyers/)
- [LSAs vs Google Ads for Personal Injury Lawyers — Nifty Marketing](https://niftymarketing.com/lsas-vs-google-ads-for-personal-injury-lawyers/)
- [How Personal Injury Firms Can Use Google Local Services Ads — FWD Lawyer Marketing](https://fwd-lawyermarketing.com/how-personal-injury-firms-can-use-google-local-services-ads-to-drive-case-leads/)

## 5. Тактики снижения эффективной цены при ограниченном бюджете

- **Long-tail вместо широких терминов**: "motorcycle accident attorney
  Nashville" вместо "car accident lawyer" — конкретные фразы (гео + тип
  травмы + roles) конвертят лучше и стоят дешевле, чем родовые высокочастотные
  запросы. Это прямо согласуется с уже принятой структурой словаря тем
  клиента (см. [[../../Клиенты/Andverpersonalinjury/Решения|Решения — Юристы США]],
  записи 2026-08-18 про генератор семантики по темам) — можно распространить
  тот же подход глубже, комбинируя тему + район (не только LA целиком, но
  конкретные районы/пригороды с меньшей конкуренцией).
- **Гео-модификаторы ставок**: +30% в основном районе охвата, −50% за его
  пределами (пример из отраслевого источника) — сфокусировать бюджет там,
  где реально приходят клиенты, а не размазывать по всему Калифорнии.
- **Дневное расписание показов (dayparting)**: показывать объявления только
  в часы работы intake-команды — тратить бюджет тогда, когда реально можно
  ответить на звонок; вечер/выходные часто дают более качественные лиды при
  меньшей конкуренции по ставкам.
- **Call-only объявления** параллельно с текстовыми — для ниши, где именно
  звонок, а не переход на сайт, является реальным действием к конверсии.
- **Стратегия ставок при малом бюджете**: если бюджета не хватает на
  Target CPA (правило — бюджет должен быть минимум ×4 от целевого CPA),
  начинать с **Maximize Conversions без строгого CPA**, чтобы наработать
  историю конверсий и понять реальный диапазон CPA, прежде чем переходить
  на Target CPA. Это отдельная задача от вопроса Search Partners — просто
  общая рекомендация по биддингу в дорогой нише при малом бюджете.
- **SEO и информационные ключи как более дешёвый параллельный канал**:
  многие PI-фирмы вкладываются в органику и низкочастотные
  информационные запросы (блог, гайды) для привлечения на ранней стадии
  исследования — не решает проблему P PC напрямую, но снижает совокупную
  зависимость от дорогого клика.
- **Bing Ads как параллельный канал**: ощутимо дешевле Google Search,
  меньший охват, но и меньше конкуренции — вариант для докрутки бюджета,
  а не замена Google.

Sources:
- [PPC for Personal Injury Lawyers: Get More Cases — GrowLaw](https://growlaw.co/blog/ppc-guide-for-personal-injury-lawyers)
- [50 Personal Injury Keywords for SEO and PPC — RunSensible](https://www.runsensible.com/blog/personal-injury-keywords/)
- [Target CPA vs Maximize Conversions — Adsbot](https://adsbot.co/target-cpa-vs-maximize-conversions/)
- [Google Search Ads for Lawyers: How Much Should Your Firm Budget — Zahavian Legal Marketing](https://www.zahavianlegalmarketing.com/google-adwords-budget-lawyers/)

## 6. Открытые вопросы / не покрыто этим исследованием

- Раздел 1a (Search Partners) проверен на реальных данных аккаунта
  Andverpersonalinjury (2026-08-19) — остальное (LSA, click-fraud
  инструменты, гео/dayparting тактики) пока НЕ проверено на практике.
- Уточнено у пользователя (2026-08-19): "$60" — это цена клика (CPC), не
  CPA/цена лида. Пользователь ориентировался на подсказку Google Ads
  ("к показу на первой странице") по части ключей — то есть это
  оценка Google, требуемая для гарантированного топ-позиционирования по
  конкретным ключам, а не фактически уплаченная цена клика по всем
  кампаниям. Соответствует нижней границе рыночного диапазона раздела 3
  ($70-250/клик в среднем по нише, $150+ на топовых терминах в LA) — то
  есть $60 не завышена и не аномальна, но и не "дорого показалось",
  а близко к минимуму разумного порога для топ-позиций в этой нише/гео.
- LSA требует прохождения Google Screened — сроки и требования по
  конкретному штату/лицензии CA не проверялись в рамках этого поиска.
  Также LSA пока рассмотрен только на уровне общей механики, не проверено,
  насколько это применимо именно к бренду "Landver Law" / текущим
  practice areas сайта.
- Не рассмотрены отдельно Performance Max и Discovery — не факт, что
  подходят для этой ниши (высокий риск того же типа мусорного трафика,
  что и Search Partners, т.к. PMax по умолчанию включает Display/Partners).
- Меньшие города рядом с LA как отдельная гео-стратегия (не только модификаторы
  ставок, а прицельные кампании на менее конкурентные пригороды) —
  затронуто только вскользь, стоит разобрать отдельно вместе с
  actual search volume по каждому пригороду, если пользователь захочет
  развить это направление.

## Связанные записи

- [[../Andverpersonalinjury/index|Andverpersonalinjury — индекс]]
- [[../../Клиенты/Andverpersonalinjury/Решения|Решения — Юристы США]]
- [[Сверка-конверсий-Директ-Метрика-Коллтрекинг]]
- [[Google-Ads-RSA-динамические-вставки-лимит-символов]]
