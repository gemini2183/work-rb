---
status: черновик на согласование, ничего не собрано и не опубликовано
updated: 2026-10-28
---

# Pedestrian: черновик текста страницы `california-pedestrian-accident-lawyer`

Образец структуры и тона: раздел «1. Motorcycle» в `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Тексты_6_страниц_черновик_2026-10-28.md` (согласован 28.10). Поля соответствуют словарю `PAGES["motorcycle"]` в `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search\build_topic_pages.py`. Спрос по теме: «pedestrian accident lawyer» 1300 в месяц, всего по теме 3200 (Keyword Planner, Калифорния, 28.10.2026; `Темы_вне_ДТП_таблица_для_начальника_2026-10-28.md`).

## Что узнал (источник каждого пункта)

**Идея страницы.** Пешеход ранен, часто не за рулём и не знает, чья страховка вообще платит. Ему сразу говорят «вы выскочили из ниоткуда» или «вы были не на переходе». Поэтому первый экран и первый блок отвечают на вопрос «меня обвинят?», а не повторяют «мы лучшие». Второй страх, которого нет на мотоцикле: водитель уехал. Третий: «я не за рулём, чья страховка платит». Всё это есть в тексте отдельными блоками.

**Читатель.** Человек после наезда или близкий: боль, счета, работа стоит; плюс спор, кто виноват. Источник: конкуренты ниже; на наших кампаниях по этой теме данных ещё нет.

**Чего боится и что ему говорят (первый экран и первый блок).**
1. «Он выскочил из ниоткуда» / «вы шли не там».
2. «Меня обвинят, раз я был не на переходе».
3. «Давайте быстро запишем ваше заявление» и «вот быстрое предложение».
4. Водитель уехал.
5. «Я не за рулём. Чья страховка платит за лечение?»
6. Цена юриста.

**Законы и сроки (чтение, не проверено юристом клиента).** Сайт Законодательного собрания Калифорнии (`leginfo.legislature.ca.gov`) закрыт Cloudflare (403), в том числе через Playwright. Тексты читал на FindLaw (воспроизводит кодексы, на странице стоит «актуально на 1 января 2026», с оговоркой «сверяйте с официальным источником»). WebFetch отдавал пересказ подразделов, не дословный текст.
- Vehicle Code 21950: водитель обязан уступить пешеходу в размеченном переходе и в неразмеченном на перекрёстке; пешеход не должен внезапно выходить с тротуара под близко идущую машину; обязанность водителя проявлять должную осторожность остаётся. https://codes.findlaw.com/ca/vehicle-code/veh-sect-21950/
- Vehicle Code 21954: вне перехода пешеход должен уступить машинам, которые создают непосредственную опасность; водитель всё равно обязан проявлять должную осторожность к человеку на проезжей части. https://codes.findlaw.com/ca/vehicle-code/veh-sect-21954/
- Vehicle Code 20001: водитель, причинивший травму, обязан остановиться на месте; нарушение уголовно наказуемо. https://codes.findlaw.com/ca/vehicle-code/veh-sect-20001/
- Code of Civil Procedure 335.1: два года на иск о телесных повреждениях и о гибели. https://codes.findlaw.com/ca/code-of-civil-procedure/ccp-sect-335-1/
- Government Code 911.2: претензия к госоргану по травме или гибели подаётся не позднее 6 месяцев со дня возникновения права на иск. https://codes.findlaw.com/ca/government-code/gov-sect-911-2/
- Insurance Code 11580.2 (hit-and-run, собственная страховка пострадавшего, uninsured motorist): водитель неизвестен; нужен физический контакт; о происшествии сообщают в полицию в течение 24 часов; письменное заявление страховщику в течение 30 дней; иск или арбитраж в течение двух лет. https://codes.findlaw.com/ca/insurance-code/ins-sect-11580-2/ В текст страницы цифры 24 часа и 30 дней не ставлю: только «сроки могут быть короткими». Цифры нужны адвокату для проверки.
- Сравнительная вина (pure comparative negligence, Li v. Yellow Cab, 1975): вторичные источники (блоги юристов, конспекты дел), первичный текст решения не открывал. На страницах Car и Motorcycle эта формулировка уже стоит. Источники: https://www.casebriefs.com/blog/law/torts/torts-keyed-to-epstein/plaintiffs-conduct/li-v-yellow-cab-co-of-california/ и https://deldarlegal.com/auto-accidents/comparative-fault-california-injury-claim/
- Статистику (число пострадавших и погибших пешеходов) в текст не ставил. Конкуренты цитируют OTS, но я нашёл только пересказы на сайтах юристов и сайт OTS не открыл (404 на угаданном адресе). Без первичного источника цифры не нужны.

**Конкуренты (WebFetch, по пересказу, не по скриншотам).**

| Сайт | Первый экран | На что отвечает | Порядок блоков | Что взять | Что слабо |
|---|---|---|---|---|---|
| Carpenter & Zuckerman, cz.law/practice-areas/pedestrian-accident | H1 «Pedestrian Accident Attorneys in California», подзаголовок «Trial-Ready Representation for Injured Pedestrians» | Спорная вина, сравнительная халатность («небрежность пешехода не снимает обязанность водителя»); цену называет коротко | Лид, список вердиктов, причины аварий, кто отвечает, какие убытки, офисы, СМИ, форма | Мысль «вина пешехода не отменяет обязанность водителя»; перечень «кто может отвечать» | FAQ нет; «$2 млрд» без периода; вердикты не про пешеходов; отзыв про другой тип дела; ошибочно разная формулировка «win» / «successfully resolve» |
| The Advocates, theadvocates.com/california/pedestrian-accident-lawyer | H1 «California Pedestrian Accident Lawyer», подзаголовок «A Pedestrian Accident Attorney Can Help Your Case» | Цена, занижение страховой, jaywalking, водитель уехал, сроки 2 года и 6 месяцев, парковка и частная территория, язык | Лид, причины, FAQ (6), почему мы, отзывы (5), статистика, травмы, кто отвечает, убытки, форма | Набор из 6 реальных вопросов аудитории: «если водитель уехал», «если я переходил не там», «парковка и частный проезд» | «$500M», «maximum compensation possible», «fight for every dollar»; цифры без ссылок; отзывы про мотоцикл и «disability lawyer» |
| Shouse Law, shouselaw.com/ca/personal-injury/pedestrian-accident-lawyer-los-angeles | H1 «Pedestrian Accident Lawyer Los Angeles», подзаголовок про халатность другой стороны | Своя вина (jaywalking), уменьшение выплаты, страховщик | Типы аварий, кто ответчик, роль юриста, польза, ссылки на законы, формы | Ссылка на конкретный закон и на источник статистики (OTS) | FAQ нет; «biggest settlement possible», «maximum compensation»; «respond in 5 minutes» не подтверждено; два отзыва про DUI и DMV |
| GJEL, gjel.com/pedestrian-accident-lawyers | H1 «California Pedestrian Accident Lawyers», «400+ Google reviews, 4.9 average», пункты: бесплатный разбор, no win no fee, 24/7 | Самый сильный по страхам: «вы вышли перед машиной», вне перехода, счета без дохода (liens), мало страховки (UM/UIM), записанное заявление, слишком ранняя сделка, 6 месяцев к госоргану, тревога после наезда | Результаты, последствия, 3 шага, «не уверены, есть ли дело? Начните с разговора», убытки, гид по шагам и вине, FAQ (5), форма | Формат «3 шага», блок «не уверены, есть ли дело?», таблица «вне перехода: что это значит для иска», упоминание тревоги и страха переходить дорогу | «99% успеха», «$980M» без определения; результаты в крупном шрифте, оговорка внизу; плотный абзац про 6 месяцев |
| Arash Law, arashlaw.com/?p=1601 | H1 «California Pedestrian Accident Lawyers», бейджи про «$1 billion» и ноль до выигрыша | Вина («darted out», видимость), водитель уехал (в FAQ), иск к городу за опасный переход, сроки, статус иммиграции | Кто может подать иск, вердикты, ответчики, отзывы, убытки, какие доказательства, как идёт иск, сроки, FAQ (10) | FAQ с вопросом «can I sue the city for a dangerous crosswalk»; список доказательств (911, видео с дверных звонков, телефонные записи) | «$1B» без источника; «case costs may apply» мелким шрифтом при крупном «zero fees»; вердикты не про пешеходов; «25 times what the insurance company offered» |
| Del Dar Legal, deldarlegal.com/personal-injury/pedestrian-accident | H1 «California Pedestrian Accident Attorneys» | Вина, «всегда ли у пешехода приоритет?», сроки | Причины, FAQ (7), призыв, отзывы, форма | Вопрос «Are pedestrians always given the right of way?» | Мало содержания; «Do not be a victim»; «two years» без оговорки про госорганы |
| West Coast Trial Lawyers | не открылась (403) | | | | |
| aa.law | в этой сессии не открывал (по итогам Motorcycle была 403) | | | | |

**Страница самого клиента.** Отдельной страницы по пешеходам на landverpersonalinjury.com нет. В сетке практик (`/practice-areas/`) карточка «Pedestrian Accidents» есть, но без ссылки и без описания; на главной в тексте слова про пешеходов нет (alt картинки с опечаткой «pedistrain accident»). Угаданный адрес `/practice-areas/california-pedestrian-accident-lawyer/` даёт 404. Взять нечего; зато нет и старого рискованного текста, которого нужно избегать. Результата дела про пешехода на сайте клиента нет, придумывать нельзя.

**Что взял из этого:** вопросы реальной аудитории (водитель уехал, не на переходе, парковка, иск к городу, чья страховка), блок «не уверены, есть ли дело» (GJEL), три шага; от себя: сразу ответ на «меня обвинят?» на первом экране. Чего избегаем: «maximum compensation», «biggest settlement», «99%», суммы без периода, результаты не про пешеходов крупным шрифтом, «no fee» без оговорки про договор, статистика без ссылки, отзывы не по теме.

**Подтверждённые факты о фирме:** как в задании (Alina Landver, Esq., MBA, Bar 231077, допущена June 2004, 20+ лет в State and Federal Court, Beverly Hills, 8730 Wilshire Blvd, Suite 416, оплата только из полученной суммы, 24/7, Google 4.8 и 45 отзывов, результаты с главной страницы клиента). Тексты карточек результатов — с главной клиента (WebFetch, 28.10): сайт читал заново для $17.1M.

## Результаты и chip на первом экране (предложение)

Своего результата про пешехода у фирмы на сайте нет. Предлагаю:
- **Chip на первом экране: убрать сумму.** Любая сумма рядом с «Pedestrian» читается как «выиграли такое дело», а это не так (и правила B&P 6157.2 и 6158.3 требуют осторожности). В слот ставлю факт о сервисе: `("24/7", "free case review")`. Рейтинг Google 4.8, 45 отзывов и «Practicing since 2004» уже стоят в строке доверия. Сборщику нужно уметь принять chip без суммы (сноска «*Past results…» под строкой тогда не нужна; остаётся у блока результатов).
- **Блок результатов: три карточки из существующих.** $38.5M motor vehicle (ближайший по механике: водитель, тяжёлая травма, подробная доказательная база; текст уже в `RESULTS_ALL["mva"]`), $35.2M truck (крупный транспорт; в городах пешеходов сбивают и грузовики; текст уже в `RESULTS_ALL["truck"]`), $17.1M bus (претензия к госоргану, то есть к тому же типу, что опасный переход или неисправный светофор; текст с главной: «A public transit passenger hurt through no fault of their own. We went after the agency and got a result that actually reflected the severity of the injury.», в `RESULTS_ALL` его надо добавить). Не берём $18.5M (мотоцикл у него своя страница), $14M wrongful death (на этой странице читатель живой, а такая карточка сдвигает смысл к гибели; для неё будет своя страница), $28.7M школьный округ и $25M class action (не про людей на улице).
- **H2 блока результатов не «Recent settlements and verdicts», а «Results in other serious vehicle-collision cases»** и строка: «These are results in other matters, not pedestrian cases.» Так читатель не решит, что это дела пешеходов. Это единственное место, где формулировка отличается от общего блока.

## Title, Description, адрес

| Поле | Значение | Знаков |
|---|---|---|
| Адрес | `california-pedestrian-accident-lawyer` | |
| Title | California Pedestrian Accident Lawyer \| Landver Law | 51 из 60 |
| Description | Hit by a car while walking in California? Get a free case review from Landver Law. No fee unless we win. Call 24/7 or leave your number. | 136 из 155 |
| Alt фото адвоката | Alina Landver, pedestrian accident attorney at Landver Law in Beverly Hills | 75 |

Длины проверены в Python 28.10.

## Текст страницы

Порядок блоков (как на Motorcycle): первый экран → форма A → что говорят пешеходу → что делать и чего пока не делать → как проходит звонок → оплата → ситуации → результат → адвокат → отзывы → вопросы → финальный призыв → форма B → подвал.

### 1. Первый экран
**H1:** California Pedestrian Accident Lawyer. Free Case Review.

**Подзаголовок:** Hit by a car while walking? Drivers and insurers often say the pedestrian stepped out or was not in the crosswalk. Tell us what happened. An attorney reviews your case for free.

**Три строки под подзаголовком (общие, как на Motorcycle):**
- Alina Landver began her career on the defense side. She knows how insurers undervalue claims.
- Over 20 years in State and Federal Court throughout California.
- If you decide to hire the firm, you pay no fee unless you win. *See how it works*

**Строка доверия:** ★ 4.8 · 45 Google reviews · Practicing since 2004 · **24/7 free case review** (chip без суммы, см. выше)

**Кнопка:** Call (844) 452-9465 · 24/7 · под ней: No pressure: you decide after the review.

**Форма A:** Prefer we call you? Leave your number.

### 2. Что говорят пешеходу и чего он боится
**H2:** What pedestrians are often told after being hit, and what to know

1. **«He came out of nowhere.»** That is the driver's version, not a legal conclusion. Drivers are expected to watch for people on foot. Who was at fault depends on what happened: where you were, signals, speed, lighting, witnesses and video.
2. **«You weren't in the crosswalk.»** Being outside a crosswalk does not automatically end a claim. A pedestrian outside a crosswalk generally has to yield to close vehicles, and a driver still has to use due care. How much that matters depends on the facts.
3. **«We just need a quick recorded statement,»** or **«Here is a quick offer.»** If you sign a release, the claim may be closed before the full medical picture is known. You can find out where you stand before you agree to anything.
4. **«The driver drove away.»** That does not necessarily end a claim. Video, witnesses and the police report can sometimes help identify the driver, and other coverage may apply, including your own auto policy. Report the crash to the police as soon as you can: policies and the law can set short deadlines.

Подпись под блоком: California reduces compensation by your percentage of fault. It does not automatically cancel it, and the insurer's first number is not always the final one.

### 3. Что делать и чего не делать
**H2:** After being hit by a car: what to do now, and what to hold off on

**Do now**
- Get medical care. Tell the doctor everything that hurts, even if it seems small. Some pain shows up hours or days later.
- Make sure the police are called and a report is made. Save the report number.
- Take photos if you can: the crosswalk or street, signals and signs, lighting, your injuries, and the vehicle and its plate.
- Write down names and phone numbers of witnesses. Notice nearby cameras (stores, doorbells): footage may be deleted after some time.
- Keep the clothes, shoes, phone, bag and glasses you had on as they are. Do not wash, repair or throw them away.

**Hold off until you have talked to an attorney**
- Giving a recorded statement to the driver's insurer.
- Signing a release or accepting a quick offer.
- Saying «it was my fault» or «I'm fine» at the scene or to an insurer. Say what hurts and what you remember.
- Posting about the crash on social media.

Подпись: This is general information, not legal advice.

### 4. Как проходит звонок
**H2:** What happens when you call a pedestrian accident lawyer
1. **Tell us what happened.** Where it was, whether the driver stayed, your injuries and treatment so far. You don't need documents yet.
2. **We set up a free review of your case with an attorney.** Free, with no obligation.
3. **The attorney explains what applies to you and what to avoid.** Then you decide: hire the firm now, later, or not at all. No pressure.

Кнопки: Get my free case review · Call (844) 452-9465 · 24/7

### 5. Оплата (общий блок, как на Car и Motorcycle, без изменений)
**H2:** Why is the first review free, and how does Landver Law get paid?

### 6. Ситуации
**H2:** Common pedestrian accident situations Landver Law reviews
- A driver did not yield in a crosswalk
- Hit while crossing outside a crosswalk
- A driver turning left or right did not see you
- The driver left the scene (hit-and-run)
- Hit in a parking lot or driveway
- Hit by a distracted, speeding or drunk driver
- A broken signal, poor lighting or a dangerous crossing
- A loved one died after being hit by a vehicle

Подпись (как на Motorcycle): Not sure which one fits? That is okay. Tell us what happened and an attorney will review it. Every case depends on its own facts, injuries, evidence, liability and insurance coverage.

### 7. Результаты
**H2:** Results in other serious vehicle-collision cases
- **$38.5M · Motor vehicle accident:** A highway rear-end collision caused severe spinal injuries and a prolonged recovery. The firm built a comprehensive evidentiary record and secured a top verdict.
- **$35.2M · Truck accident:** One of the firm's most contested cases. The result was a top verdict for the client.
- **$17.1M · Bus accident:** A public transit passenger was hurt through no fault of their own. The firm pursued the agency and obtained a result that reflected the severity of the injury.

Строка: These are results in other matters, not pedestrian cases.
Оговорка (общая): Past results do not guarantee, predict or imply a similar outcome in any other matter. Every case depends on its own facts, injuries, evidence, liability, insurance coverage and applicable law.

### 8. Адвокат (общий блок, как на Car и Motorcycle)
**H2:** Your California pedestrian accident attorney: Alina Landver, Esq., MBA. Текст, Bar number и дата допуска без изменений.

### 9. Отзывы (общий статичный блок, как на Car и Motorcycle)
Те же три отзыва. Отзывов про пешеходов на сайте клиента нет, «под тему» не подбираю.

### 10. Вопросы
**H2:** Questions about pedestrian accidents and hiring a lawyer

**The driver says I stepped out in front of them. Does that end my claim?**
No. That is the driver's version, and it is not a legal conclusion. California Vehicle Code section 21950 generally requires drivers to yield to pedestrians in a marked crosswalk or in an unmarked crosswalk at an intersection, and says drivers must still use due care. It also says a pedestrian may not suddenly leave a curb and walk into the path of a vehicle that is too close to yield. What really happened depends on where you were, signals, speed, lighting, witnesses and video. If a pedestrian is found partly responsible, California uses comparative fault: damages can be reduced by that percentage, not automatically denied. A free case review looks at what happened in your crash.

**Can I have a claim if I was not in a crosswalk, or was jaywalking?**
Possibly. Outside a crosswalk, a pedestrian generally has to yield to vehicles that are close enough to be an immediate hazard (California Vehicle Code section 21954), but the same section says drivers must still use due care toward people on the road. An insurer may argue that you were partly at fault. That can reduce compensation by your percentage of fault; it does not automatically cancel the claim. Tell the attorney exactly where you crossed and what you saw.

**The driver left the scene. What can I do?**
Leaving the scene after hitting a person is a crime in California, because the driver must stop (Vehicle Code section 20001). It does not necessarily end your claim. Police reports, witnesses and nearby camera footage can sometimes help identify the driver, and other coverage may apply, such as the uninsured motorist coverage in your own auto policy. Policies and the Insurance Code can set short deadlines, for example for reporting the crash to the police, so report it as soon as you can and keep the report number. An attorney can review what may apply to you.

**I wasn't driving. Whose insurance pays for my care?**
It depends on the facts. Depending on the case, coverage may come from the driver's auto liability policy, from your own auto policy, or from other sources. Do not assume that something is or is not available. The review looks at who may be responsible and what coverage may exist.

**The other driver's insurance company called me. What should I do?**
First identify who is calling and which insurer they represent. Avoid guessing about facts you do not know, minimizing injuries that are still being evaluated, or signing releases you do not understand. If you are unsure about a recorded statement or an offer, consider getting legal advice before agreeing to it.

**Can the city or county be responsible for a dangerous crossing?**
Sometimes. If a road or crossing condition, such as a broken signal or poor lighting, contributed to the crash, a claim against a government agency may be possible. Those claims can require a notice much earlier than a regular lawsuit, generally within six months of the injury. Whether this applies to your case depends on the facts.

**How much does a pedestrian accident lawyer cost?**
(общий ответ `cost` из FAQ_COMMON; `{topic}` = pedestrian accident.)

**How much is my pedestrian accident case worth?**
No honest number can be named without the facts. It depends on your injuries, medical costs, time off work, future care, who was at fault and the insurance coverage available. The review shows what applies to your case. Landver Law does not promise a result.

**My treatment is still ongoing. Is it too early to contact a lawyer?**
(общий ответ `treatment` из FAQ_COMMON.)

**How long do I have to bring a pedestrian injury claim in California?**
For many California personal-injury lawsuits, the general deadline is two years from the date of injury. But that is not a universal rule. Different facts can create different deadlines. If a government agency or a road condition is involved, a claim against a California government agency can require an administrative claim much earlier, generally within six months of the injury. Claims under your own insurance policy, for example for a hit-and-run, can have their own deadlines. Do not use the general two-year period to assume your own deadline.

Под блоком: как на Car (general information, not legal advice; attorney-client relationship not created).

### 11. Финальный призыв и форма B
**H2:** Get your free pedestrian accident case review
Call or leave your number. We'll set up a free review of your case with an attorney, who can tell you: what applies to YOUR case, not general advice · what NOT to do so you don't lose compensation · your next steps, in plain language · where your case stands, based on what you tell us. No fee unless we win. Кнопки как на Car.

### 12. Подвал (общий, как согласовано на Motorcycle)

## Что нужно от вас

1. «Да» или правки по тексту Pedestrian.
2. Результаты: согласны ли с тремя карточками ($38.5M, $35.2M, $17.1M) под H2 «Results in other serious vehicle-collision cases» и строкой «These are results in other matters, not pedestrian cases», и с chip без суммы (`24/7 · free case review`)? Альтернатива: вообще без блока результатов на этой странице.
3. Юристу клиента (Alina) нужно посмотреть юридические формулировки (законы, сроки, uninsured motorist): список в разделе «Не проверено». Без этого на публикацию не ставлю.
4. Берёт ли фирма дела с уехавшим водителем (hit-and-run) и с аварией на парковке и частной территории? Если нет, уберу из ситуаций и из FAQ.
5. Строка «A loved one died after being hit by a vehicle» без отдельного текста: ок оставить до готовности страницы Wrongful death?

## Источники

- https://codes.findlaw.com/ca/vehicle-code/veh-sect-21950/ (VC 21950)
- https://codes.findlaw.com/ca/vehicle-code/veh-sect-21954/ (VC 21954)
- https://codes.findlaw.com/ca/vehicle-code/veh-sect-20001/ (VC 20001)
- https://codes.findlaw.com/ca/code-of-civil-procedure/ccp-sect-335-1/ (CCP 335.1)
- https://codes.findlaw.com/ca/government-code/gov-sect-911-2/ (Gov Code 911.2)
- https://codes.findlaw.com/ca/insurance-code/ins-sect-11580-2/ (Ins Code 11580.2)
- https://www.casebriefs.com/blog/law/torts/torts-keyed-to-epstein/plaintiffs-conduct/li-v-yellow-cab-co-of-california/ и https://deldarlegal.com/auto-accidents/comparative-fault-california-injury-claim/ (сравнительная вина, вторичные)
- Конкуренты: https://www.cz.law/practice-areas/pedestrian-accident/ · https://www.theadvocates.com/california/pedestrian-accident-lawyer/ · https://www.shouselaw.com/ca/personal-injury/pedestrian-accident-lawyer-los-angeles/ · https://www.gjel.com/pedestrian-accident-lawyers · https://arashlaw.com/?p=1601 · https://deldarlegal.com/personal-injury/pedestrian-accident
- Клиент: https://landverpersonalinjury.com/ и https://landverpersonalinjury.com/practice-areas/ (результаты, список практик)
- Внутренние: `D:\GitHub\work-rb\База_знаний\Агенты\Запуск_трекинга_новой_посадочной.md`, `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\SEO_и_качество_посадочных_Settlement_и_Car.md`, `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search\Темы_вне_ДТП_таблица_для_начальника_2026-10-28.md`

## Не проверено

- Все пункты законов (VC 21950, 21954, 20001; CCP 335.1; Gov Code 911.2; Ins Code 11580.2): первичный сайт `leginfo.legislature.ca.gov` недоступен (Cloudflare, 403, также через Playwright), читал FindLaw; WebFetch отдал пересказ подразделов, не дословный текст. Перед публикацией юрист клиента сверяет.
- Сравнительная вина (pure comparative negligence): только вторичные источники, первичное решение Li v. Yellow Cab не открывал. Формулировка совпадает со страницами Car и Motorcycle, которые клиент принимал.
- Утверждение «собственная страховка пострадавшего может применяться при уехавшем водителе (uninsured motorist)» опирается на пересказ Ins Code 11580.2 с FindLaw. Условия там строгие (контакт с машиной, сообщение в полицию в течение 24 часов, сроки иска); на странице они не названы, только «short deadlines».
- «Some pain shows up hours or days later» и «footage may be deleted after some time»: общие утверждения без источника, формулировка осторожная (`some`, `may`); если юрист не согласен, заменить.
- «Видео, свидетели и полицейский отчёт иногда помогают найти водителя»: общая практика, источника нет, формулировка `can sometimes`.
- Тексты карточек результатов взяты с главной страницы клиента (WebFetch, 28.10, пересказ); $17.1M описан по «Bus Accident» на главной.
- Данные про конкурентов: пересказ WebFetch, не скриншоты. Не открылись: westcoasttriallawyers.com (403), страница клиента по пешеходам не существует (404). aa.law не открывался.
