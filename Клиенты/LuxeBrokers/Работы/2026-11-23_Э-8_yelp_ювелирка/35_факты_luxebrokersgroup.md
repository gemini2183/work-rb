Есть 9 замечаний: на luxebrokersgroup.com нет «no fees / commissions», «free evaluation», «up to 10 min», «complete confidentiality», «meet privately with an expert»; телефон на сайте (213) 266-5112, а не 794-7666.

---
agent: Контроль фактов (fact-checker)
date: 2026-11-23
статус: сверка, пакет 20_пакет_Э-8.md не правился
---

# Сверка текстов Э-8 v2 со страницами luxebrokersgroup.com

## Шапка
- Проверено: `D:\GitHub\work-rb\Клиенты\LuxeBrokers\Работы\2026-11-23_Э-8_yelp_ювелирка\20_пакет_Э-8.md`, п. 3, 4, 5, баннер.
- Источник: боевой сайт luxebrokersgroup.com, прямой запрос (python urllib / curl, User-Agent браузера), 23.11.2026. Формы не отправлялись, ничего не записывалось.
- Страницы прочитаны ПОЛНОСТЬЮ (текст, без скриптов/стилей): `/` (главная), `/sell/jewelry/`, `/sell/tiffany/`, `/location/beverly-hills/`, `/sell/estate-jewelry/`, `/sell/gold-jewelry/`, `/sell/diamond-rings/`. Контент отдаётся сервером, скрипт не нужен.
- НЕ открыты: `/sell/cartier/`, `/sell/van-cleef/`, `/sell/graff/`, `/sell/bulgari/`, `/sell/designer-jewelry/`, `/faq/`, `/why-us`, `/how-it-works/`, `/about`, `/contact`, `/appointment/`, `/online-appraisal/`, `/reviews/`, `/terms`. Сначала ответ 403, затем 410 «Gone» с кнопкой unblock: защита сайта заблокировала мои запросы по частоте. Обход не делал. Эти страницы остаются непроверенными (в п. «Не проверено»).
- Раньше (пакет, [C]) утверждения сверялись по jewelryfastsale.com. Подвал нового сайта: «© 2026 Jewelry Fast Sale» (тот же владелец/шаблон), но тексты страниц другие: формулировок «no fees or commissions», «free evaluation, no obligation to sell», «up to 10 minutes», «complete confidentiality», «meet privately with a expert» на прочитанных страницах нет.

## Резюме
1. Подтверждено по смыслу: бренды Cartier, Van Cleef & Arpels, Bulgari, Graff покупаются (`/sell/jewelry/`: «Cartier, Tiffany & Co., Van Cleef & Arpels, Bulgari, Harry Winston, Graff and other makers»); Tiffany тоже назван, значит замечание «Tiffany не подтверждён» устарело для этого сайта.
2. Подтверждено: «no obligation» (бейдж «No obligation» на `/sell/jewelry/`, `/location/beverly-hills/`), приватность/дискретность («Private & discreet», «Discretion is a priority»), адрес и часы.
3. Не подтверждено, нет ни одной фразы по смыслу: «no fees» / «no fees or commissions», «free evaluation» (есть только «Free online appraisal» — это онлайн-оценка, не визит), «deals up to 10 min» (на сайте «Get Offer in 10 minutes» только как кнопка меню), «complete confidentiality» (есть «discretion and confidentiality are core to our service» на главной в FAQ — смысл близкий, см. таблицу).
4. Противоречия: телефон на сайте (213) 266-5112, в Yelp (213) 794-7666. Номер 794-7666 на сайте есть только в WhatsApp-ссылке главной (`api.whatsapp.com/send/?phone=12137947666`).
5. Same-Day: «Same-day offer», «Same-day payment» на сайте есть, значит CTA «Same-Day Luxury Evaluations» подтверждается по смыслу («Same-day offer & immediate payment»; «Most evaluations can be completed the same day»).
6. Способ оплаты (cash / check / bank transfer) на прочитанных страницах НЕ назван; везде только «payment can be made the same day». Cash упомянут лишь в «sell jewelry for cash», «Cash for Gold».
7. Что убрать или заменить из текстов A–D, баннера, Portfolio: «no fees», «free evaluation» (в смысле бесплатного визита), «up to 10 min», «complete confidentiality», «private meeting with an expert» дословно, пока клиент не подтвердит или не будут прочитаны недоступные страницы (`/faq/`, `/why-us`, `/how-it-works/`).
8. Превосходные степени и сроки отдельным списком — ниже.

## Таблица сверки

| Поле | Утверждение | Чем подтверждается на странице (путь и цитата) | Статус | Замена |
|---|---|---|---|---|
| Текст A, B, C, D, баннер, Portfolio | Free evaluation (бесплатная оценка) | Прямо: `/sell/jewelry/`: «Free online appraisal» (ссылка «Prefer to start online? Send photos and details for a preliminary estimate»); подвал: «Free Online Appraisal». Бесплатность визита и оценки в магазине нигде не названа; «Get an Offer Online» / «transparent evaluation in a private setting». | Частично: подтверждена только онлайн-оценка по фото; бесплатность очной оценки не найдена | см. таблицу ниже |
| A, B, C, D, баннер («FREE EVALUATION • NO FEES»), Portfolio | No fees / no fees or commissions | На прочитанных страницах нет ни «fee», ни «commission», ни «free of charge». Ближайшее: «No obligation», «no pressure to sell». | Не найдено | убрать или спросить клиента |
| A, B, C, D, баннер, подпись, Portfolio | Deals / transaction up to 10 min | Только пункт меню «Get Offer in 10 minutes» (`/` и все страницы, навигация). Страницы говорят: «Most evaluations can be completed the same day, depending on item complexity», «Many evaluations can be completed the same day. Large collections may take longer». Срок сделки «до 10 минут» как обещание не найден; «Offer in 10 minutes» — об онлайн-оффере. | Расходится по смыслу (сайт обещает «в тот же день», 10 минут только в меню) | «Same-day offer», «Get an offer in 10 minutes» только если именно онлайн-оценка |
| B, C, D, Portfolio | No obligation | `/sell/jewelry/`: бейдж «No obligation»; `/location/beverly-hills/`: «No obligation»; «with no pressure to sell». | Подтверждено | — |
| A, C, Portfolio | Cartier, Van Cleef, Bulgari, Graff | `/sell/jewelry/`: «Cartier, Tiffany & Co., Van Cleef & Arpels, Bulgari, Harry Winston, Graff and other makers.»; главная и подвал: «Top Brands We Buy: Cartier, Tiffany & Co., Van Cleef & Arpels, Bulgari». | Подтверждено | — |
| Тексты, фото 02 (Tiffany) | Tiffany | `/sell/tiffany/`: «Sell Tiffany & Co. Jewelry in Beverly Hills», «We buy authentic Tiffany rings, bracelets…». | Подтверждено: пометку «Tiffany не подтверждён» можно снять для этого сайта | — |
| A, B | We buy luxury jewelry / expert | Главная: «Sell Jewelry, Diamonds, Watches & Gold in Beverly Hills», «Bring your fine jewelry, luxury watches…»; «Expertise Across Jewelry Categories». «Luxury», «expert» — оценочные | Подтверждено | — |
| B, C, D, Portfolio | Privately / private meeting with an expert | `/sell/jewelry/`: «Get a transparent evaluation in a private setting»; «Private evaluation + clear explanation»; главная: «Private appointments», «Walk-ins are welcome when available — appointments ensure dedicated time with an expert». Дословного «private meeting» нет, смысл («частная встреча с экспертом по записи») передан. | Подтверждено по смыслу | — |
| C, D, Portfolio | Confidential / complete confidentiality | Главная, FAQ: «Is the evaluation private? Yes — discretion and confidentiality are core to our service.»; `/location/beverly-hills/`: «calm, confidential environment» (главная: «Our Beverly Hills location offers a calm, confidential environment»). Слов «complete confidentiality of our clients» нет, но смысл (конфиденциальность) передан; «complete» — усиление | Подтверждено по смыслу («confidential»); «complete confidentiality» дословно убрать | «confidential» / «discreet» |
| D, баннер, подписи | Beverly Hills | Главная: «Beverly Hills Jewelry, Watch & Gold Buyer»; адрес в подвале | Подтверждено | — |
| Portfolio, подпись входа | Адрес 131 N Robertson Blvd, Beverly Hills, CA 90211 | Главная и все страницы: «Address: 131 N Robertson Blvd,Beverly hills,CA,90211» | Подтверждено (написано с ошибкой регистра «Beverly hills», это сайт) | — |
| Portfolio | Open daily 10 AM-7 PM | Все страницы: «Hours: Daily 10 am to 7 pm» | Подтверждено | — |
| Профиль Yelp / подпись «Call» | Телефон (213) 794-7666 | Все страницы, шапка и подвал: «+1 (213) 266-5112»; `tel:+12132665112`. 794-7666 есть только в WhatsApp-ссылке главной: `https://api.whatsapp.com/send/?phone=12137947666` | Расходится: на сайте основной номер другой | Выбрать, какой номер правильный; в тексты Yelp телефон не вписан |
| CTA | «Same-Day Luxury Evaluations» | Главная: «Same-Day Offer & Immediate Payment»; `/sell/jewelry/`: «Same-day in-store offers available»; «Many evaluations can be completed the same day» | Подтверждено по смыслу (оговорку «дословно нет» в п. 5 пакета можно снять); «Same-Day Offer» точнее «Evaluations» | при желании «Same-Day Luxury Offers» |
| Баннер | WE BUY JEWELRY | Главная: «Sell Jewelry, Diamonds, Watches & Gold»; `/sell/jewelry/`: «We buy fine jewelry, estate pieces, diamond rings, designer jewelry and complete collections» | Подтверждено | — |
| Способ оплаты (в тексты не включён) | cash / check / bank transfer | Не найден: «payment can be made the same day», «Same-day payment available», «Get cash for gold». Check и bank transfer на прочитанных страницах нет | Не найдено | в рекламе не использовать, как в пакете |
| Ограничение (для справки) | ID required | Подвал: «ID required for transactions (CA compliance)» | Есть на сайте | — |

## Прямые противоречия: «было → станет» (только где страница говорит иное)

| Было (пакет) | Что на странице | Станет (только из источника) |
|---|---|---|
| «Deals up to 10 min» (A, B, баннер, C «up to 10 min») | сайт: «Same-day offer», «Most evaluations can be completed the same day»; «Get Offer in 10 minutes» — пункт меню | «Same-day offer» (A: «We buy luxury jewelry: Cartier, Van Cleef, Bulgari and more. Same-day offer, no obligation.»; баннер: «Same-day offer • No obligation • Beverly Hills») |
| «Free evaluation» / «FREE EVALUATION • NO FEES» | бесплатной очной оценки нет; «Free online appraisal» по фото есть | если нужен «free», то «Free online appraisal»; иначе «No obligation» |
| «No fees / no fees or commissions» | нет | убрать; допущение (не из источника): если клиент подтвердит «no fees», тогда оставить; пока не использовать |
| «Complete confidentiality» | «confidential environment», «discretion and confidentiality» | «Confidential» / «Private & discreet» |

## Превосходные степени и сроки (отдельным списком)
- Сроки: «up to 10 min» (не подтверждён, см. выше); «Same-Day» (подтверждён: «Same-day offer», «payment can be made the same day»); «Open daily 10 AM-7 PM» (подтверждён).
- Превосходные степени и оценочные слова: «luxury», «expert», «fully confidential»/«complete confidentiality» (усиление), «highest» — в тексты не вставлено (по пакету). Проверять число не нужно.

## Длины и лимиты
Пересчёт знаков не делался (пакет правится другим агентом); при замене на «Same-day offer, no obligation» длину текстов A–D перепроверить: лимит превью ≈ 117 знаков.

## Не проверено
- Страницы без доступа (защита сайта): `/faq/`, `/why-us`, `/how-it-works/`, `/about`, `/contact`, `/appointment/`, `/online-appraisal/`, `/reviews/`, `/terms`, `/sell/cartier/`, `/sell/van-cleef/`, `/sell/graff/`, `/sell/bulgari/`, `/sell/designer-jewelry/`. На них могут быть «no fees», «free evaluation», способ оплаты. Как проверить: открыть в браузере пользователя (Chrome) или снять блокировку; повторить через 10–15 мин с паузой между запросами.
- Телефон и часы на карточке Yelp: сам профиль Yelp не читал, сравнение — с цифрами из задания (адрес и часы совпали, телефон нет).
- Подтверждение клиента про «no fees / commissions» и «free evaluation» (вопрос для пользователя).

## Что нужно от пользователя
1. Решить, какой телефон верный (на сайте 266-5112, в Yelp 794-7666; 794-7666 есть в WhatsApp-ссылке сайта).
2. Спросить клиента: есть ли комиссия/сборы, бесплатна ли оценка в магазине, реально ли «до 10 минут». Или открыть в Chrome страницы `/faq/`, `/why-us`, `/how-it-works/` и прислать текст.

Файл: `D:\GitHub\work-rb\Клиенты\LuxeBrokers\Работы\2026-11-23_Э-8_yelp_ювелирка\35_факты_luxebrokersgroup.md`

## Решение пользователя 23.11 (поверх вердикта выше)
Формулировки «no fees or commissions», «free evaluation», «deals up to 10 min» подтверждает клиент; «complete confidentiality» допустимо по смыслу («confidential»). Тексты A–D, баннер hero_J и Portfolio НЕ переписываются. Замены из таблицы выше не применять. Остаётся открытым только телефон: (213) 266-5112 (сайт) против (213) 794-7666 (профиль Yelp).
