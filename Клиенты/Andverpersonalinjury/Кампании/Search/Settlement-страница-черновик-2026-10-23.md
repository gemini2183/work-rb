---
status: черновик, не опубликован
updated: 2026-10-23
---

# Страница для группы «Car Accident - Settlement»: структура и тексты (вариант 2)

Черновик по сессии 2026-10-23. Основание — аудит страницы california-car-truck-accident ([[../../Хроника_2026-10]], «аудит посадочной»), метод — [[../../../../База_знаний/Паттерны/Юристы-PI-посадочная-ДТП-аудит-соответствие-запросу-и-доверие]]. Эксперимент Э-08 заводится в момент запуска. Факты о фирме (Бар, 2004, 4.8/45, отзывы, FAQ, дисклеймеры) взяты с текущей страницы клиента дословно или близко к тексту; в `[скобках]` то, что нужно подтвердить до публикации.

URL (предложение): `landverpersonalinjury.tilda.ws/california-car-accident-settlement`. Только группа Settlement. Страницу не линкуем нигде на сайте. `noindex` НЕ ставим: у Google нет документа о влиянии обычного noindex на оценку рекламы, а для Dynamic-групп он назван причиной «страница не сканируется» — не рисковать без проверки.

## Структура (телефон, ~7–8 экранов)

0. Шапка без меню: логотип, телефон, кнопка «Get my free case review». Закреплённая плашка на телефоне: CALL NOW · 24/7 | GET MY FREE CASE REVIEW.
1. Первый экран + квиз (вопрос 1 уже на первом экране).
2. Квиз, вопросы 2–5 (тот же блок).
3. Экран результата (вариант 2) + форма контакта.
4. Под квизом (видно сразу, для тех, кто квиз не трогает): почему сумма так отличается; что делает страховая; что будет на звонке; адвокат; отзывы; FAQ; финальный призыв; подвал.

## 1. Первый экран

**H1:** What Is Your California Car Accident Claim Worth?
**Подзаголовок:** Answer 5 quick questions. See what can raise or lower the value of a case like yours, and what to avoid before you talk to the insurance company.
**Полоса доверия:** ★ 4.8 · 45 Google reviews  |  Practicing since 2004  |  Free case review  |  No fee unless we win
**Квиз:** «Question 1 of 5», крупные кнопки-ответы.

## 2. Вопросы квиза (значения идут в скрытые поля формы)

| № | Вопрос | Ответы | Поле |
|---|---|---|---|
| 1 | What was the most serious injury? | Head or brain injury · Neck or back (spine) · Broken bone · Soft tissue (sprain, whiplash, bruising) · Other / not sure yet | injury_type |
| 2 | Where is your treatment right now? | Hospital or ER so far · Ongoing treatment (doctor, therapy) · Surgery recommended or completed · No treatment yet · Still being diagnosed | treatment_status |
| 3 | Have you missed work? | No · A few days · Several weeks · I can't return to my job | work_missed |
| 4 | Who was at fault? | The other driver · Shared or disputed · I'm not sure | fault |
| 5 | Has an insurance company contacted you? | No, not yet · Yes, they asked for a statement · Yes, they made an offer (not signed) · I already signed | insurer_status |

Уровень результата (поле result_tier): **serious** — травма голова/мозг, позвоночник, перелом или лечение «surgery»/«hospital»; **developing** — «no treatment yet», «still being diagnosed», «soft tissue» без лечения или «not sure»; **moderate** — всё остальное.

## 3. Экран результата

**Первая строка по уровню:**
- serious: Your answers point to a serious injury case.
- moderate: Your answers point to a moderate injury case.
- developing: Your injury picture is still developing.

**Общий абзац:** The same type of crash can end in a few thousand dollars or in seven figures. The difference is rarely the crash itself. It is what happens in the next few weeks. [Для developing добавить: That is often when the costliest mistakes are made.]

**3 mistakes that can cost you money right now**
1. Giving the insurer a recorded statement before you know what applies to you.
2. Gaps in treatment, which insurers may use to argue the injury isn't from the crash.
3. Signing a quick offer. A signed release can close the claim for good.

**But these 3 are the general ones. Your case has its own.**

**Персональная строка** (по ответу 5; если «No, not yet» и лечение «No treatment yet» — строка про лечение):
- Offer, not signed: An offer is on the table. Before you answer it, find out what it may leave out.
- Asked for a statement: They asked for a statement. Before you give one, find out what it may be used for.
- Already signed: You already signed. Tell us today, because the next steps are different.
- No contact yet: The insurer may call soon. Know what to say, and what not to, before they do.
- No treatment yet: Treatment hasn't started. Waiting can hurt the claim. Tell us what happened so far.

**Call or leave your number. We'll set up a free review of your case with an attorney, who can tell you:** (осторожный вариант: инструкцию колл-центру пока не отправляем, решение пользователя 2026-10-23; жёсткий вариант «In one free call you'll get: what NOT to do right now…» — только после отправки инструкции клиенту)
✓ what applies to YOUR case, not general advice
✓ what NOT to do so you don't lose compensation
✓ your next steps, in plain language
✓ where your case stands, based on what you tell us
No fee unless we win.

**Кнопки:** [Get my free case review] (прокрутка к форме Tilda)  [Call (844) 452-9465 · 24/7]
**Форма Tilda под квизом:** заголовок «Get my free case review»; подзаголовок «Leave your name and phone. We'll contact you to set up your free review with an attorney.»; поля First name, Phone number; кнопка «Get my free case review».
**После отправки:** Thank you. We've received your request and will contact you to set up your free case review. Prefer to talk now? Call (844) 452-9465 · 24/7.
**Мелкий шрифт:** Free. No obligation. A review, not a promise of results. Submitting this form does not by itself create an attorney-client relationship.

## 4. Блоки под квизом

**Why the same crash can be worth very different amounts** (4 карточки)
- Your medical record: What treatment you've had, what's still ahead, and whether the record shows the injury came from the crash.
- Your lost income: Missed work, reduced hours, or a job you can no longer do the same way.
- Who was at fault: California reduces compensation by your share of fault, so how fault is shown matters.
- The insurance involved: Which policies apply, and what the insurer says early on.
Подпись: No formula can set a case value from the crash type alone. [Кнопка: Get the number for my case]

**What insurance companies often do first**
- Ask for a recorded statement. Know who is asking and why before you agree.
- Make a quick offer. If you sign a release, the claim may be closed before the full medical picture is known.
- Point to your share of the blame. California reduces compensation by your percentage of fault, and the first number is not always the final one.

**What happens when you call**
1. Tell us what happened: the crash, your injuries, your treatment so far.
2. We set up a free review of your case with an attorney.
3. The attorney explains what applies to you and what to avoid. You decide whether to move forward. No obligation.

**Meet your attorney:** Alina Landver, Esq., MBA, Managing Partner · Trial Attorney. Admitted to the California Bar in June 2004 (Bar No. 231077). Began her career representing corporate clients on the defense side, which helps show how insurers challenge claims. Beverly Hills office, 8730 Wilshire Blvd, Suite 416.

**Reviews:** 4.8 out of 5 · 45 Google reviews. Цитаты (как на текущей странице): «Best attorney ever!» (Google Review, January 2026); «Great experience working with Landver Law Alina Landver esq.» (January 2026); «The attorney treated my case with great seriousness from the start.» (Elsy Castellanos, October 2025). Подпись: A review is someone else's experience, not a promise about yours.

**FAQ (6)** — тексты берём из уже опубликованного FAQ клиента: №1 стоимость, №2 лечение ещё идёт, №3 частично моя вина, №7 записанное заявление, №8 уже получил предложение, №10 сроки (2 года; 6 месяцев для претензии к госорганам).

**Финальный призыв:** Don't guess what your case is worth. Get the number for your case. Те же 4 пункта «in one free call» + кнопки.

**Подвал:** дисклеймеры, адрес, телефон, email — как на текущей странице (Attorney Advertising, Legal Disclaimer).

## Техническое до запуска

1. Tilda: дубликат страницы, квиз — блок HTML (5 шагов), скрытые поля формы: injury_type, treatment_status (есть), work_missed, fault, insurer_status, result_tier, cta_source (есть).
2. Ringostat: добавить правила подмены номера для нового URL и проверить `phone_swap_check.py` (строгая версия) до включения трафика.
3. GTM: события quiz_start, quiz_step, quiz_complete, result_tier; block_view по новым блокам (`gtm_apply_plan.py`, план отдельным файлом).
4. Группа Settlement: final URL → новая страница (`gads_adgroup_plan.py`, только по «да»); объявление должно говорить о цене дела, не обещая сумму.
5. Через 1–2 недели — перечитать оценку Google «посадочная» по ключам группы, снять поведение по шагам квиза.

## Подтвердить до публикации
- «No fee unless we win» — подтверждено пользователем 2026-10-23, можно ставить;
- что в разговоре люди реально получают «next steps» и оценку, как обещает текст;
- (844) 452-9465 отвечает круглосуточно — подтверждено пользователем 2026-10-23: ставим «24/7» у телефона в шапке, на плашке CALL NOW и рядом с кнопкой звонка на экране результата; приём — аутсорс-колл-центр, первый звонок = сбор данных, разговор по существу с адвокатом позже ([[../../../../Хроника_2026-10]]; осторожные формулировки 3.9, 3.12, 3.14 — в сессии 2026-10-23);
- скорость от обращения в колл-центр до разговора с адвокатом (если «в тот же день» — ставим на страницу) и обратного звонка, если обещаем «мы перезвоним»;
- инструкция колл-центру (3 правила «что не делать» в первом звонке) — отправить клиенту вместе с запуском, иначе 3.9 остаётся осторожным вариантом;
- названия уровней «serious / moderate / developing»;
- вопрос про грузовик в этой версии не задаём (страница под легковые); если нужны грузовые, добавить в вопрос 1.

## Код квиза (готов, проверен локально 2026-10-23)

Файл: `Клиенты/Andverpersonalinjury/Кампании/Search/settlement_quiz_t123.html` — один блок T123 (стили, разметка, скрипт; H1, подзаголовок, полоса доверия, квиз из 5 вопросов, экран результата, кнопки). Проверка в Playwright на локальной копии: 12 сценариев (все три уровня и все пять персональных строк), кнопка «Back», «Change my answers», события dataLayer, скрытые поля, ссылка tel, якорь `#ldv-form`, нет горизонтальной прокрутки на 390 px, нет ошибок в консоли. На живой Tilda не проверено.

Как поставить:
1. В копии страницы Tilda убрать верхние блоки, вставить блок T123 с содержимым файла.
2. Сразу под ним — обычная форма Tilda (имя, телефон). Скрытые поля код создаёт сам; надёжнее в конструкторе формы завести одно скрытое поле с именем `quiz_summary` (там все ответы строкой и уровень) — тогда оно точно уйдёт в письмо/интеграцию.
3. Закреплённая плашка: CALL NOW · 24/7 | GET MY FREE CASE REVIEW (ссылка `#ldv-form`).
4. Ringostat: добавить правило подмены номера для ссылки с классом `ldvq-phone` (и для номера в шапке/плашке) на новом URL; прогнать `phone_swap_check.py` до включения трафика.
5. GTM: события `quiz_start`, `quiz_step`, `quiz_complete`, `quiz_cta`, `quiz_restart` приходят в dataLayer; триггеры и теги GA4 — отдельным планом `gtm_apply_plan.py`.
6. noindex не ставить (см. выше); ссылку не публиковать, кроме группы Settlement.

## Страница целиком — сборка в Tilda (2026-10-23, проверено локально, на живой Tilda не проверено)

Файлы (все в `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search\`):
- `settlement_quiz_t123.html` — блок 1: шапка, первый экран, квиз, закреплённая плашка на телефоне;
- `settlement_body_t123.html` — блок 2: почему сумма разная, что делает страховая, что будет на звонке, адвокат, отзывы, FAQ (6), финальный призыв, якорь `#ldv-form-2`;
- `settlement_footer_t123.html` — блок 3: подвал с дисклеймерами;
- `settlement_page_preview.html` — локальный макет всей страницы для просмотра (формы Tilda в нём имитированы), открыть двойным щелчком.

Порядок блоков в Tilda (новая страница = дубликат, старые блоки удалить): 1 → Форма A → 2 → Форма B (копия A) → 3.

Форма Tilda (A и B одинаковые): фон кремовый `#f6f2ea`, заголовок «Get my free case review», подзаголовок «Leave your name and phone. We'll contact you to set up your free review with an attorney.», поля First name и Phone number (обязательные), скрытое поле `quiz_summary` (остальные поля код создаёт сам), кнопка «Get my free case review» цвета `#e8563f`, мелкий текст «Free. No obligation. Submitting this form does not by itself create an attorney-client relationship.», сообщение после отправки «Thank you. We've received your request and will contact you to set up your free case review. Prefer to talk now? Call (844) 452-9465 · 24/7.»

Что отличается от текущей страницы клиента: фото адвоката подтянуто по ссылке с домена клиента (то же фото, что на текущей странице); FAQ №1 дополнен «there is no fee unless we win»; у «Terms of Use» и «Privacy Policy» в подвале нет ссылок (как на текущей странице) — для формы со сбором телефона лучше привязать реальные страницы.
Высота: ≈8 440 px на телефоне 390 px (~10 экранов), 6 300 px на десктопе; горизонтальной прокрутки нет, ошибок консоли нет.
События dataLayer: к квизовым добавлено `ldv_cta` с `cta_place` (header_call/form, sticky_call/form, why_form, how_form/call, final_form/call, footer_call).

## Настройки Tilda для оценки Google «посадочная» (2026-10-23)

Что Google пишет сам (Ads Help, «Optimize your ads and landing pages»): страница должна «closely match your ad and keywords», давать «useful, original information», быть простой в навигации, быстрой на телефоне и «easy to contact». Вес факторов Google не раскрывает, оценка качества «not an input in the ad auction», но качество посадочной входит в Ad Rank. Гарантии высокой оценки нет; после запуска читаем статус по ключам через 1–2 недели.

В Tilda (Настройки страницы → SEO) — то, чего нет в блоках кода:
- Title (57 знаков): Car Accident Settlement Value in California | Landver Law
- Description (153 знака): Answer 5 quick questions to see what can raise or lower a California car accident settlement and what to avoid before talking to the insurer. Free review.
- Заголовки для соцсетей (OG): те же Title и Description.
- Адрес страницы: california-car-accident-settlement.

Что уже сделано в коде под оценку: H1 повторяет слова ключей («California Car Accident Settlement Worth»), подзаголовок «car accident claim», строка «Not a settlement calculator…» для запросов «calculator» (согласована с объявлением «Calculators Can't See Injuries»), H2 «car accident settlements», два вопроса FAQ под «settlement worth» и «average car accident settlement» без цифр, один H1, осмысленные H2, alt у фото, фото 107 КБ с ленивой загрузкой и размерами (не тормозит), нет всплывающих окон, навигация только якоря, контакты и адрес на виду, текст оригинальный и по теме.

Что остаётся открытым: у клиента нет страниц Privacy Policy и Terms of Use (на landverpersonalinjury.com адреса `/privacy-policy/` и `/terms-of-use/` дают 404; в подвале клиента это простой текст) — для формы со сбором телефона лучше завести страницу и поставить ссылку (вопрос клиенту); вопросы квиза строятся кодом, поэтому Google (AdsBot) может их не увидеть — важные слова вынесены в статический текст.
