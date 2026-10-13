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

## 2. Страница /gold-silver: задачи для исполнителя

Как устроена страница (проверено в браузере 13.10): 19 блоков Tilda, почти все — Zero Block. Ни в одном нет тега заголовка h1–h4 с текстом. Блоки названы по id из кода страницы (rec…), чтобы их можно было найти: в редакторе Tilda у каждого блока виден такой номер в настройках блока.
Названия пунктов меню Tilda ниже даны по общему знанию (настройки страницы → SEO; у текстового элемента Zero Block выбор тега) — **у меня нет доступа к редактору, пункты не проверены в вашем кабинете, названия могут отличаться**.

### Задача 1. Сделать заголовок первого экрана настоящим H1
- **Где:** Zero Block `rec4298993003` (первый экран, большой «WE BUY / GOLD AND SILVER»).
- **Сейчас:** «WE BUY GOLD AND SILVER» оформлено крупным текстом без тега заголовка; слов «Beverly Hills» и «near me» на экране нет.
- **Сделать:** текст заголовка заменить на «Gold Buyers in Beverly Hills: We Buy Gold, Scrap & Broken Gold» (62 знака) и поставить тег H1 (на странице должен быть ровно один H1). Если на телефоне уходит в 4+ строки — короткий вариант: H1 «Gold Buyers in Beverly Hills» (28), а «We Buy Gold, Scrap & Broken Gold» вынести в подзаголовок.
- **Под H1 добавить строку:** «Sell gold near you. Free evaluation, paid in cash or bank transfer, deal in up to 10 minutes.»
- **Проверка:** в коде страницы поиск `<h1` находит один тег с этим текстом.

### Задача 2. Title и description страницы
- **Где:** настройки страницы → SEO.
- **Сейчас:** title «Jewelry Fast Sale — Purchase/Repurchase of Gold and Silver»; description «Purchase/Repurchase of Gold and Silver» (то же самое, одной фразой).
- **Сделать:** title «Sell Gold in Beverly Hills | Cash for Gold Buyers» (49 знаков); description «We buy gold jewelry, scrap, broken chains, coins and bars in Beverly Hills. Free evaluation, cash or bank transfer. Open daily 10 AM–7 PM.» (≈ 140 знаков). Если в настройках отдельно задан заголовок для соцсетей (og:title) — поставить тот же title (сейчас он повторяет старый).

### Задача 3. Адрес и часы на первом экране
- **Где:** тот же `rec4298993003`, под подзаголовком из задачи 1.
- **Сейчас:** в шапке телефон «+1 (213) 794-76-66» и «Daily 10 am to 7 pm»; адрес есть только в нижнем блоке `rec4298994203`.
- **Сделать:** добавить строку «131 N Robertson Blvd, Beverly Hills, CA 90211 · Open daily 10 AM – 7 PM». **Адрес подтверждён пользователем 13.10:** 131 N Robertson Blvd, Beverly Hills, CA 90211 (как и на сайте) — публиковать можно.
- **Номер:** не вписывать вручную другой; использовать тот же номер/элемент, что в шапке (подмену делает Ringostat). После правки сделать тестовый звонок и убедиться, что звонок виден в Ringostat.

### Задача 4. Одна формулировка про оплату
- **Где (3 места):** первый экран `rec4298993003` («Payment in cash or to a bank account»); блок How to sell `rec4298993603`, шаг 04 («Receive immediate payment by check or bank transfer.»); будущий FAQ.
- **Сделать:** везде «Paid in cash or bank transfer» (в шаге 04: «Receive immediate payment in cash or by bank transfer.»). Если клиент подтвердит, что чек тоже возможен — везде «cash, check or bank transfer».

### Задача 5. Фраза про выезды в боковом меню (низкий приоритет, можно не делать)
- **Где:** блок `rec4298993103` — боковая панель меню (Tilda T450), открывается по значку меню. Фраза лежит в правой колонке панели.
- **Проверено 13.10 в браузере:** после нажатия на значок меню видны только четыре пункта (Types of products, How to Sell, Gallery, Online appraisal). Фраза остаётся **за краем экрана и посетителю не видна** ни на телефоне, ни на десктопе; она есть только в коде страницы.
- **Что это за текст:** «I'm available for business trips to other cities for projects lasting a month or longer.» По смыслу совпадает с брифом клиента (выездные консультации в другие города для крупных проектов от месяца).
- **Сделать:** по желанию убрать из панели или перенести в видимую часть страницы, если клиент хочет это показывать. На оценку качества и на посетителей влияет мало: человек её не видит, поисковик читает как посторонний текст про «поездки».

### Задача 6. Новый блок «How we calculate your offer»
- **Где:** между блоком Types of products `rec4298993403` и How to sell `rec4298993603`.
- **Текст:** заголовок «How we calculate your offer». Абзац: «Your offer is based on three things: the karat (purity) of your gold, its weight, and the current gold price. We test and weigh your items and explain how the offer is calculated before you decide.» *(«test and weigh» — подтвердить у клиента; в отзыве написано «tested my scrap jewelry … right in front of me»).*
- **Таблица проб:** 10K — 41,7%, 14K — 58,3%, 18K — 75,0%, 22K — 91,7%, 24K — 99,9% (чистота золота по пробе — общая арифметика). Процент выплаты и коэффициенты **не писать**.

### Задача 7. Блок FAQ
- **Где:** после отзывов, перед формой `rec4298994203`.
- **Публикуем сразу (по тексту страницы):**
  1. «Do you buy broken or scrap gold?» — «Yes. We buy broken chains, single earrings, damaged pieces and mixed lots.»
  2. «Do you buy gold coins and bars?» — «Yes. Pricing depends on type, purity, weight and market conditions.»
  3. «How fast do I get paid?» — «The average transaction takes up to 10 minutes.»
  4. «Is the evaluation free?» — «Yes, a free evaluation with no obligation to sell.»
  5. «Can I send photos first?» — «Yes. Use the form for a free online appraisal.»
- **После ответа клиента:** «Do I need an appointment?», «What should I bring? (ID?)», «How is my offer calculated?»

### Задача 8. Галерея под золото
- **Где:** блок Gallery `rec4298993903`.
- **Сейчас:** 12 фото, все ювелирные люкс-бренды (Cartier, Van Cleef & Arpels, Chopard, Tiffany, Bulgari); ни одного лома, цепочек, монет или слитков, а страница — под запросы про золото.
- **Сделать:** добавить 4–6 фото золота (цепочки и лом, монеты, слитки) и поставить их первыми. Фото — только реальные от клиента (не стоковые под видом клиентских).

### Задача 9. Отзывы: источник
- **Где:** блок Customer reviews `rec4298994003` (6 отзывов с пятью звёздами).
- **Сейчас:** источник не указан; отзыв Shoshana Zakaria — про ремонт часов («fix my watches for Free»), к золоту не относится.
- **Сделать:** под заголовком «CUSTOMER REVIEWS» добавить «Reviews from Google» или «from Yelp» (как есть на самом деле) со ссылкой на профиль; отзыв про часы перенести в конец. Не добавлять рейтинг и число отзывов без источника.

### Задача 10. Alt у картинок
Сейчас у всех картинок alt пустой. Тексты (по фото на странице):

| Блок | Картинка | Alt |
|---|---|---|
| Первый экран | золотой браслет-цепь слева | Gold chain bracelet |
| Первый экран | серебряный браслет с подвеской справа | Silver charm bracelet |
| Types | Cash for Gold | Gold bracelets and rings we buy for cash |
| Types | Gold Jewelry | Gold jewelry: rings, chains and bracelets we buy |
| Types | Scrap & Broken Gold | Scrap and broken gold chains we buy |
| Types | Gold Coins | Gold coins we buy |
| Types | Gold Bars | Gold bars we buy |
| Types | Silver & Platinum | Silver chain bracelet, we also buy silver and platinum |
| How to sell | шаг 01 | Send photos of your items from your phone |
| How to sell | шаг 02 | Schedule a visit |
| How to sell | шаг 03 | Offer for your items |
| How to sell | шаг 04 | Payment by bank transfer |
| Gallery | 12 фото | по предмету, например «Cartier Love bracelet», «Van Cleef & Arpels necklace» |

### Задача 11. Сжать 7 тяжёлых картинок

| Блок | Файл | Размер | Размеры | Цель |
|---|---|---|---|---|
| Форма `rec4298994203` | `xo0mj11nnclvdpz6yecu.png` | 482 КБ | 926×1328 | WebP/JPG ≤ 120 КБ |
| Форма | `packshot-front_colli.png` | 304 КБ | 718×767 | ≤ 100 КБ |
| How to sell `rec4298993603` | `Frame_24.jpg` | 300 КБ | 1311×705 | ≤ 120 КБ |
| Первый экран `rec4298993003` | `2amFCETnxN39uGLAIpso.png` | 288 КБ | 1000×1000 | ≤ 100 КБ |
| How to sell | `2.png` (шаг 02) | 184 КБ | 866×470 | ≤ 80 КБ |
| How to sell | `4.png` (шаг 04) | 111 КБ | 866×470 | ≤ 60 КБ |
| How to sell | `3.png` (шаг 03) | 92 КБ | 866×470 | ≤ 60 КБ |

Перезалить в блоке сжатыми файлами (WebP или JPG). Итого страница теряет ≈ 1 МБ.

### Задача 12. Бренд на странице
- **Сейчас:** в шапке логотип «LUXEBROKERS — Watches · Jewelry · Diamonds», в блоке Types и в title — «Jewelry Fast Sale».
- **Сделать:** решить с клиентом, какое имя показываем человеку, который пришёл из объявления gold_, и привести к одному. Без ответа клиента не менять.

### Задача 13. Мобильная версия (проверено, править почти нечего)
- Телефон уже в шапке на первом экране и является ссылкой `tel:`; кнопка «Get a free online appraisal» тоже на первом экране. Отдельная закреплённая кнопка звонка — по желанию, не обязательна.
- Пример «23 000$» на иллюстрации шага 03 — уточнить у клиента, что это пример, а не обещание суммы.

### Задача 14 (предложение, ждёт решения пользователя). Переделать блок How to sell
- **Где:** Zero Block `rec4298993603`.
- **Проблемы (проверено по коду и в браузере 13.10):** в блоке нет ни одной кнопки, ссылки или телефона; шаг 02 «Schedule a visit — select a date and time» обещает запись, которой на странице нет; шаг 04 «check or bank transfer» расходится с первым экраном; четыре макета (≈ 690 КБ) не несут смысла для запроса; заголовок не тег и тянет в сторону серебра.
- **Варианты:** A — убрать (и пункт меню «How to sell»); B — оставить; **C — переделать (рекомендовано)**.
- **Вариант C:** заголовок (H2) «How to sell your gold in Beverly Hills»; три шага: 1) «Send photos of your gold for a free online appraisal, or call +1 (213) 794-76-66 to arrange a visit.» 2) «We test and weigh your items and explain how the offer is calculated. Free evaluation, no obligation to sell.» (подтвердить «test and weigh») 3) «Paid in cash or bank transfer. The average transaction takes up to 10 minutes.» Под шагами кнопка «Get a free online appraisal» (на #form) и «Call now» (номер из шапки, чтобы работала подмена Ringostat; после правки тестовый звонок). Без тяжёлых картинок; при принятии варианта C задача 11 для этого блока отпадает.

Второй этап (не сейчас): отдельные страницы или чётко названные разделы под группы «Gold Coins», «Gold Bars», «Scrap & Broken Gold» со своими заголовками. Делать, только если после задач 1–12 «посадочная» останется «ниже среднего» у нескольких ключей.

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

## 7. Вопросы клиенту (ответы нужны для задач 3, 4, 6, 7, 9, 12)

1. ~~Какой адрес верный~~ — закрыто 13.10: 131 N Robertson Blvd.
1а. Какое имя показываем на странице: LuxeBrokers или Jewelry Fast Sale?
2. Нужна ли запись заранее? Что взять с собой (документ с фото)?
3. Как формируется оффер: по пробе и весу, по текущей цене золота? Что из этого можно публиковать?
4. Откуда отзывы (Google / Yelp), какой рейтинг?
5. Чек («check») — возможен или только наличные / перевод?
6. Что подтверждает «пробу и вес при вас» (проверка на месте)?

Источники по практике: [[../../База_знаний/Инструменты/Google-Ads-Quality-Score-компоненты-и-как-поднять]].
