---
name: luxebrokers-gold-qs-tz
description: ТЗ на поднятие оценки качества (Quality Score) ключей gold_ — посадочная /gold-silver и тексты объявлений
status: черновик — ждёт ответов клиента по фактам (раздел 7)
updated: 2026-10-13
---

# ТЗ: поднять оценку качества ключей gold_ (LuxeBrokers)

Кому: тот, кто правит сайт (Tilda) и объявления. Страница: https://jewelryfastsale.com/gold-silver.
Что проверено 13.10.2026: кабинет Google Ads через API (оценки по ключам за 15.09–12.10), страница через браузер Chrome (мобильный и десктоп), поисковые запросы за 60 дней.

## 1. Что говорит Google (по ключам с трафиком)

Оценка ключа состоит из трёх частей. Каждая — «выше среднего / средняя / ниже среднего» относительно других рекламодателей на тот же запрос.

| Ключ (группа) | Показы | QS | Ожидаемый CTR | Релевантность объявления | Посадочная |
|---|---|---|---|---|---|
| We Buy Gold (Gold Buyer) | 804 | 3 | ниже | выше | **ниже** |
| Gold Buyer (Gold Buyer) | 631 | 2 | ниже | средняя | **ниже** |
| Sell Gold Near Me (Gold Near Me) | 478 | 1 | ниже | **ниже** | **ниже** |
| Gold Buyers Near Me (Gold Near Me) | 447 | 1 | ниже | **ниже** | **ниже** |
| Cash For Gold (Cash For Gold) | 360 | 2 | ниже | средняя | **ниже** |
| Sell Gold Jewelry (Gold Jewelry) | 266 | 5 | средний | выше | **ниже** |

Вывод: у **всех шести** ключей с трафиком «посадочная ниже среднего» — это общее для всех, и это правится один раз на странице. «Ожидаемый CTR ниже среднего» — у пяти из шести (правится текстами и расширениями, часть сделана 12.10). «Релевантность объявления ниже среднего» — только у группы «Gold Near Me» (правится заголовками этой группы).

Важно: оценку 1–10 Google называет диагностикой, а не целью. В аукционе работают сами три оценки в реальном времени. Практический смысл: сейчас gold_ теряет 65% показов по рейтингу (бюджет не ограничивает, тратится ≈ 47 $ из 250 $), и лучшая страница и тексты — единственный способ вернуть показы без роста цены клика.

## 2. Страница /gold-silver: что есть → что сделать

Что на странице сейчас (проверено в браузере):
- Главный экран: «WE BUY GOLD AND SILVER», телефон, часы, кнопка «Get a free online appraisal». **Нет слов «Beverly Hills» и «near me»**, адрес только в подвале.
- **Ни одного тега заголовка h1–h4 с текстом** (заголовки сделаны оформлением, а не тегами) — поисковая система и Google не видят структуру.
- Title: «Jewelry Fast Sale — Purchase/Repurchase of Gold and Silver»; description повторяет то же самое («Purchase/Repurchase of Gold and Silver»).
- 54 картинки, ни у одной нет alt. Картинки PNG весят ≈ 1,5 МБ (самые тяжёлые 482 / 304 / 288 КБ), всего ≈ 2,9 МБ и 124 запроса; на быстром канале в браузере страница грузится 2,2 с на мобильном. На реальном мобильном 4G — медленнее (PageSpeed получить не удалось, квота; пользователю прогнать https://pagespeed.web.dev для /gold-silver).
- Блоки: Types of products (шесть карточек), How to sell (4 шага), Gallery, 8 отзывов (без источника и звёзд), форма «Free online appraisal» с загрузкой файлов, адрес, телефон.
- Якоря #home, #types, #how, #gallery, #form на странице есть (проверено).
- Лишнее и противоречия: фраза «I'm available for business trips to other cities for projects lasting a month or longer» (от первого лица, уводит от «приезжайте»); выплата в шапке «cash or to a bank account», в шаге 3 «check or bank transfer».

### Правки (по приоритету)

| № | Что сделать | Где | Зачем | Нужно от клиента |
|---|---|---|---|---|
| 1 | Сделать главный заголовок настоящим H1 с ключевой фразой: «Gold Buyers in Beverly Hills: We Buy Gold, Scrap & Broken Gold» (62 знака). Под ним подзаголовок: «Sell gold near you. Free evaluation, paid in cash or bank transfer, deals in up to 10 minutes.» | Главный экран, первый блок | Страница должна отвечать словами запроса «gold buyers near me / sell gold near me / we buy gold» | нет |
| 2 | Переписать title: «Sell Gold in Beverly Hills \| Cash for Gold Buyers» (49 знаков) и description: «We buy gold jewelry, scrap, broken chains, coins and bars in Beverly Hills. Free evaluation, cash or bank transfer. Open daily 10 AM–7 PM.» (≈ 140 знаков) | Настройки страницы Tilda → SEO | Сейчас они повторяют друг друга и не содержат ни «sell gold», ни города | нет |
| 3 | На главном экране рядом с телефоном вывести адрес и часы одной строкой: «131 N Robertson Blvd, Beverly Hills, CA 90211 · Daily 10 AM–7 PM» и кнопку «Call now» (ссылка `tel:`) | Шапка и главный экран | Тот, кто ищет «near me», должен видеть, где вы, не дойдя до подвала | **Какой адрес верный:** 131 N Robertson Blvd (на сайте) или 8308 Wilshire Blvd (в брифе) |
| 4 | Добавить блок «How we calculate your offer» (3–4 строки): оценка по пробе (karat) и весу, по текущей цене золота; пробу проверяем при вас. Рядом таблица проб 10K / 14K / 18K / 22K / 24K. **Проценты и коэффициент выплаты — не писать, пока клиент не даст** | После блока Types of products | Прозрачность — часть оценки посадочной; сейчас на странице нет ни слова о том, как формируется цена | Как именно считают оффер, что можно публиковать |
| 5 | Добавить блок FAQ из 6–8 вопросов (см. раздел 4) | Перед формой | Закрывает запросы вроде «do you buy broken gold», «what do I need to bring» | Ответы на пункты, помеченные «подтвердить» |
| 6 | Отзывы: подписать источник («Google» / «Yelp») и дать ссылку; добавить общий рейтинг и число отзывов, если есть | Блок Customer reviews | Доверие | Откуда взяты отзывы, рейтинг |
| 7 | Убрать фразу про выезды «I'm available for business trips…» и привести выплату к одной формулировке: «Paid in cash or bank transfer» | Главный экран, шаг 3 «Get paid» | Расхождение подрывает доверие; фраза уводит от «приезжайте» | Подтвердить, что чек («check») тоже возможен |
| 8 | Заполнить alt у картинок: минимум у карточек Types of products и галереи («Gold chains we buy in Beverly Hills», «Gold coins and bars bought for cash» и т.п.) | Tilda: у каждого блока с картинкой → «Alt» | 54 картинки без описаний | нет |
| 9 | Сжать картинки: четыре самых тяжёлых PNG (482 / 304 / 300 / 288 КБ) → WebP или JPEG ≤ 150 КБ; общий вес страницы ≤ 1,5 МБ | Tilda → загрузить заново | Скорость на мобильном — часть посадочной | нет |
| 10 | На мобильном: закреплённая нижняя кнопка «Call» + «Free appraisal»; форма не длиннее трёх полей (имя, телефон, фото/описание) | Мобильная версия | Простота действия | нет |

Второй этап (не сейчас): отдельные страницы или чётко названные разделы под группы «Gold Coins», «Gold Bars», «Scrap & Broken Gold» с якорями `#scrap`, `#coins`, `#bars`, `#jewelry` и своими заголовками; в группах объявлений потом ставить URL на эти разделы. Делать, только если после пунктов 1–10 «посадочная» останется «ниже среднего» у нескольких ключей.

## 3. Объявления: что добавить в заголовки по группам

Принцип Google для «релевантности объявления»: фраза из ключа должна быть в заголовке слово в слово. Сейчас новые RSA gold_ (12.10) общие на 5 групп, и в них нет «Near Me». Добавить в заголовки RSA **своей группы** (по 2–3 строки, до 30 знаков):

| Группа объявлений | Ключи | Добавить заголовки (знаков) |
|---|---|---|
| Gold Near Me | Sell Gold Near Me, Gold Buyers Near Me, Sell Gold Nearby | Gold Buyers Near Me (19), Sell Gold Near Me (17), We Buy Gold Near You (20) |
| Cash For Gold | Cash For Gold | Cash for Gold Near Me (21), Cash for Gold Today (20) |
| Gold Buyer | Gold Buyer, We Buy Gold | Gold Buyer in Beverly Hills (27), We Buy Gold Near You (20) |
| Gold Bars | Sell Gold Bars, Sell Gold Bars Nearby | Sell Gold Bars Near Me (22), Gold Bar Buyers Near You (25) |
| Gold Coins | Sell Gold Coins, Gold Coin Buyer, Cash For Gold Coins | Gold Coin Buyers Near Me (24), Sell Gold Coins for Cash (26) |
| Gold Jewelry | Sell Gold Jewelry | Sell Gold Jewelry Near Me (25) |
| Gold Chain / Gold Ring | Sell Gold Chain / Sell Gold Ring | Sell Gold Chain for Cash (24) / Sell Gold Ring for Cash (23) |

Закрепление не нужно: пусть Google подбирает. «Near Me» в заголовке не нарушает правил, но в тексте не повторять одну и ту же фразу в нескольких заголовках одного объявления.

Ожидаемый CTR: уже сделано 12.10 — сайтлинки, выноски, сниппет «Types»; ещё стоит добавить в объявление конкретику, которой нет у конкурентов (то, что подтвердит клиент): «Test and weigh in front of you», «Same-day payment».

## 4. Текст FAQ (черновик на английском)

Пункты «подтвердить» — публиковать только после ответа клиента.

1. **Do you buy broken or scrap gold?** Yes. We buy broken chains, single earrings, damaged pieces and mixed lots. *(есть на странице)*
2. **Do you buy gold coins and bars?** Yes, priced by purity, weight and market conditions. *(есть на странице)*
3. **How much will I get for my gold?** The offer depends on karat, weight and the current gold price. We test and weigh your items and explain the calculation. *(подтвердить: «test and weigh in front of you»)*
4. **Do I need an appointment?** Подтвердить.
5. **What should I bring?** Подтвердить: нужен ли документ с фото (ID), нужны ли чеки.
6. **How fast do I get paid?** The average transaction takes up to 10 minutes. *(на странице так)*
7. **Is the evaluation free?** Yes, free evaluation with no obligation to sell. *(на странице так)*
8. **Can I send photos first?** Yes, use the form for a free online appraisal. *(форма есть)*

## 5. Чего не делать

- Не писать проценты выплаты, акции, сроки и условия, которых нет в материалах клиента.
- Не вставлять в текст «near me» десятки раз (это ухудшит читаемость и не помогает).
- Не гнаться за цифрой QS: цель — показы по рейтингу и цена клика.

## 6. Как проверим и когда

- Сделать правки, отдельным отчётом зафиксировать дату.
- Через 7 дней: посмотреть в кабинете три оценки по тем же шести ключам и показы по рейтингу (потеря показов по рейтингу была 65%).
- Через 14 дней: решить про второй этап (отдельные разделы по группам).
- Быстрого пересчёта не обещаю: Google оценивает по накопленным данным; **оценки на странице пересчитываются не мгновенно**.
- Эффект на заявки читать вместе с этапом 2 (целевая цена 40 → 50 $) и кольцом 1 по гео, поэтому дату правок страницы записать в [[Журнал_изменений]].

## 7. Вопросы клиенту (ответы нужны для пунктов 3, 4, 5, 6, 7)

1. Какой адрес верный: 131 N Robertson Blvd или 8308 Wilshire Blvd?
2. Нужна ли запись заранее? Что взять с собой (документ с фото)?
3. Как формируется оффер: по пробе и весу, по текущей цене золота? Что из этого можно публиковать?
4. Откуда отзывы (Google / Yelp), какой рейтинг?
5. Чек («check») — возможен или только наличные / перевод?
6. Что подтверждает «пробу и вес при вас» (проверка на месте)?

Источники по практике: [[../../База_знаний/Инструменты/Google-Ads-Quality-Score-компоненты-и-как-поднять]].
