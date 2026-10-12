---
name: luxebrokers-campaign-gold
description: Лог кампании Search «gold_» (Google Ads 953-486-5605) — переработка 2026-10 (проект, ждёт «да» по этапам)
status: этап 1 выполнен 2026-10-12 (harvest-группа на паузе); этапы 2–4 ждут согласования
updated: 2026-10-12
---

# Кампания `gold_` — лог и план переработки

Контекст — [[../../Решения]] (запись 2026-10-12), общий план — [[../../План_наращивания_объёма_2026-10]].

## Состояние на 2026-10-12 (до правок)
- Search, Maximize Conversions с целевым CPA **40 $**, бюджет **250 $/день** (расход ≈ 47 $/день), сети: поиск Google, партнёры выкл.
- Гео: Beverly Hills, West Hollywood + 12 районов + радиус 5 км; расписание 09:30–19:30; AI Max не включался.
- 10 групп, 19 ключей (все PHRASE), 20 объявлений (10 «старых» с 6 из 13 закреплёнными и 10 «новых» с 13 из 13 закреплёнными).
- Общие списки минусов: «Negative init» (457) и «Temp» (16); кампанийных минусов 96; в группах — 16–118 точных и широких.
- База 28.09–11.10 (14 дней): 127 показов, 6,4 клика, 47 $, 0,79 заявки в день; цена заявки 60 $; всего 11 заявок.
- Активы кампании: 6 сайтлинков (с якорями #s1–#s6, которых нет на странице), 3 выноски, 1 сниппет, 12 картинок, lead form на паузе.

## План (по этапам; каждый этап — своё «да»)

### Этап 1 — день 0 (после «да»): списки, объявления, активы, harvest
| № | Объект | Действие | Было → Станет | Откуда факт | Откат |
|---|---|---|---|---|---|
| 1.1 | Общие списки минусов | Создать «Negative gold_ v2» (460 слов); подключить к gold_; отключить от gold_ «Negative init» и «Temp» (на остальных 6 кампаниях они остаются) | 473 слова → 460: убраны `scrap`, `broken`, `appraisal`, `appraise`, `apprisal`, `apprise`, `estate`, `worth`, `seller`, `vintage`, `angeles`, `la`, `burbank`, `free`, `how`, `online`, `brokers`, `broker`, `real`, `antique`; добавлены `bag(s)`, `purse(s)`, `handbag(s)`, `wallet(s)` | `shared_criterion` 12.10; сайт: «scrap gold, broken chains…»; Keyword Planner | подключить обратно «Negative init» и «Temp», отключить v2 |
| 1.2 | Кампанийный минус `hollywood` (BROAD, id 10383511) | Удалить | блокирует запросы с «Hollywood» внутри текущего гео (район в целях) | `campaign_criterion` 12.10 | создать заново |
| 1.3 | Группа «gold_ / harvest 10-26» | Создать **на паузе**, 18 фраз PHRASE, без групповых минусов | см. список ниже | запросы 12.08–11.10; Keyword Planner | удалить / оставить на паузе |
| 1.4 | Объявления RSA | Добавить новое (тексты ниже) в harvest + «Gold Near Me», «Gold Buyer», «Cash For Gold», «Gold Jewelry», «Gold Beverly Hills» (6 шт.) | — → новое; финальный URL `/gold-silver`, путь «Beverly Hills», трекинг-шаблон кампании | аудит объявлений 12.10 | пауза нового |
| 1.5 | Объявления с 13 из 13 закреплённых | Пауза 4 шт.: 781839748709 (Gold Jewelry), 781839748712 (Cash For Gold), 781839748718 (Gold Near Me), 781839748721 (Gold Buyer) | ENABLED → PAUSED | CTR ниже парного старого в 4 группах из 4: 4,0 vs 5,8%; 3,2 vs 4,8%; 2,3 vs 5,4%; 3,2 vs 4,8% | включить |
| 1.6 | Сайтлинки | Создать 5, привязать к gold_; отвязать от gold_ 6 старых (сами ассеты остаются у silver) | см. таблицу ниже | якоря #form, #types, #how есть на `/gold-silver` (проверено 12.10); #s1–#s6 нет | привязать старые |
| 1.7 | Выноски | Добавить 5 к 3 существующим | +Paid in Cash or Transfer, Open Daily 10 AM to 7 PM, Free Evaluation, Scrap & Broken Gold OK, Beverly Hills Location | сайт /gold-silver | отвязать новые |
| 1.8 | Сниппет | Создать «Types: Gold Jewelry, Scrap Gold, Gold Coins, Gold Bars, Silver, Platinum», привязать; отвязать старый (id 151684357895) от gold_ | Jewelry / Watches / Diamonds / Coins and Bars → золото | сайт: «Cash for Gold, Gold Jewelry, Scrap & Broken Gold, Gold Coins, Gold Bars, Silver & Platinum» | привязать старый |
| 1.9 | Группа harvest | Включить | PAUSED → ENABLED | отдельное «да» после чтения обратно | пауза |

### Этап 2 — день 3: целевой CPA
- **2.1** Кампания gold_: целевой CPA 40 → 50 $. Откуда: потеря IS по рейтингу 61%; цена заявки за 28 дней 48 $, с 01.10 — 67 $; нужная на остаток месяца 79 $. Откат: вернуть 40 $ при цене заявки 7 дней > 95 $ два раза подряд.

### Этап 3 — день 6: кольцо 1 гео (в ту же кампанию, радиус 5 км не трогаем)
- **3.1** Добавить гео отдельными критериями, без корректировок ставок: Culver City (1013714), Koreatown (9230076), Westwood — район LA (9061122), Downtown Los Angeles (9060325), Santa Monica (1014255). Откат: удалить критерий или −100% по конкретному гео.
- **3.2** Удалить минус `santa monica` (BROAD): кампанийный id 10320971 и групповой в 10 группах.

### Этап 4 — день 13, только если кольцо 1 окупилось: кольцо 2
Sherman Oaks (1014273), Glendale (1013819), Burbank (1013622), Inglewood (1013880); удалить минусы `glendale` (кампанийный 11501891 + 10 групповых), `inglewood` (11843200).

## Фразы harvest (PHRASE, 18)
who buys gold near me; who buys gold; sell my gold near me; sell my gold; who pays the most for gold; who pays the most for gold near me; gold cash near me; cash for gold near me; where can i sell my gold; where to sell gold jewelry; sell gold jewelry near me; best place to sell gold; gold exchange near me; sell scrap gold; scrap gold buyers; sell broken gold jewelry; sell broken gold chain; free gold appraisal near me.
Исключена «gold coin buyers» — дубль существующего «gold coin buyer». Проверено: не блокируются кампанийными минусами и списком v2, точных дублей текста нет. Часть фраз пересекается по смыслу с существующими ключами («sell gold jewelry near me» ↔ «sell gold jewelry») — внутри кампании выигрывает ключ с лучшим рейтингом.

## Правила чтения (оценка 14 дней после каждого этапа)
- Кольца: строки `location_view` по каждому гео против строк старых гео в тот же период; решение по гео при ≥ 60 кликов или ≥ 3 заявках.
- Оставить гео: цена заявки ≤ 79 $. Исключить (−100%): расход ≥ 120 $ при 0 заявок.
- Целевой CPA: потеря IS по рейтингу ≤ 50%, ≥ +0,4 заявки в день, цена заявки 7 дней ≤ 79 $.
- Harvest: ≥ 30 кликов за 14 дней, ≥ 0,2 заявки в день, цена ≤ 79 $.
- Отчёт по запросам через 7 дней после этапа 1: слова из списка v2 вернуть точечно, если принесли мусор.

## Допущения (проверить до «да»)
1. Формулировка выплаты «Paid in Cash or Bank Transfer»: на странице в шапке «Payment in cash or to a bank account», в шаге 3 — «check or bank transfer».
2. «Same Visit» (H3) и «Up to 10 Minutes» — со страницы («immediate payment», «average transaction time up to 10 minutes»).
3. Часы «Open Daily 10 AM to 7 PM» — со страницы; расписание показа 09:30–19:30 не меняем.
4. Для золота убраны не все «брендовые» слова списка (`pre`, `owned`, `second`, `hand`, `unused` оставлены).
5. Бюджет 250 $/день не меняем (расход ≈ 47 $).

## Журнал действий (дописывать после каждого этапа)
### 2026-10-12 — этап 1 записан (скрипт `Скрипты/gads_campaign_rework.py`, план `gold_stage1_plan.json`, снимок «до» `Статистика/gold_stage1_plan_before.json`)
Пакет из 523 операций одним атомарным запросом; проверка `validate_only` прошла, затем запись, чтение обратно:
- список «Negative gold_ v2» подключён (459 слов; план 460 — `gemstone` был дублем), «Negative init» и «Temp» отвязаны от gold_ (на остальных 6 кампаниях остались); кампанийный минус `hollywood` удалён (96 → 95);
- группа «gold_ / harvest 10-26»: PAUSED, 18 ключей PHRASE, 1 объявление;
- 4 объявления с 13 из 13 закреплений на паузе (781839748709, …712, …718, …721); новых RSA 6 (5 групп + harvest), статус модерации «на проверке», Ad strength PENDING;
- сайтлинки: 5 новых (URL с UTM до якоря, шаблон `{lpurl}` на уровне ассета), 6 старых отвязаны; выноски 3 + 5; сниппет «Types: Gold Jewelry, Scrap Gold, Gold Coins, Gold Bars, Silver, Platinum»; новые ассеты на модерации.
Отклонение от таблицы: URL сайтлинков содержат `?utm_source=google&utm_medium=cpc&utm_campaign={campaignid}&utm_content=sitelink` до якоря и шаблон `{lpurl}` на уровне ассета — иначе параметры шаблона кампании дописываются после `#` и теряются (документация Google о параметрах URL). utm_content у сайтлинков отличается от кампании («sitelink» вместо «rb|campaign_…»). Два пары сайтлинков ведут на один URL (#form: S1 и S5; #types: S2 и S3) — разные тексты; показ дублей Google может ограничить.
Дальше: проверить модерацию 13.10, затем включить harvest (отдельное «да»); этап 2 — 16.10.

