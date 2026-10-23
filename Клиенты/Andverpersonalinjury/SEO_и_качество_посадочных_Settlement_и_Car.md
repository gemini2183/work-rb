---
status: готово к применению, на живых страницах не проверено
updated: 2026-10-23
---

# Настройки страниц под оценку Google «посадочная»: Settlement и легковая (Car)

Зачем: Google оценивает посадочную по тому, насколько она совпадает с объявлением и ключами, даёт полезный оригинальный текст, удобна на телефоне и проста в навигации (Ads Help, «Optimize your ads and landing pages»). Вес факторов Google не раскрывает, высокой оценки гарантировать нельзя. После запуска читаем статус по ключам через 1–2 недели (`D:\GitHub\work-rb\Скрипты\gads_quality_score_keywords.py`).

Эти настройки нужны на обеих страницах. Для Settlement они уже внесены в код и в инструкцию (`D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Tilda_страница_Settlement\ИНСТРУКЦИЯ_сборка_в_Tilda.md`).

## Сводка по полям

| Поле | Settlement (готово) | Легковая страница (для макета) |
|---|---|---|
| Адрес | `california-car-accident-settlement` | `california-car-accident-lawyer` |
| Title (до 60 знаков) | Car Accident Settlement Value in California \| Landver Law (57) | California Car Accident Lawyer \| Free Review \| Landver Law (58) |
| Description (до 155) | Answer 5 quick questions to see what can raise or lower a California car accident settlement and what to avoid before talking to the insurer. Free review. (154) | Hurt in a car accident in California? Get a free case review from Landver Law. No fee unless we win. Call 24/7 or leave your number. (132) |
| H1 (один на странице) | What Is Your California Car Accident Settlement Worth? | California Car Accident Lawyer. Free Case Review. |
| Подзаголовок | See what can raise or lower the value of a car accident claim like yours… | Injured in a car or auto accident? Tell us what happened. An attorney reviews your case for free. No fee unless we win. |
| Главные слова из ключей | car accident, settlement, claim, compensation, calculator, average | car accident, car crash, auto accident, lawyer, attorney, California, Los Angeles, Beverly Hills |
| Open Graph (соцсети) | те же Title и Description | те же Title и Description |
| Alt фото адвоката | Alina Landver, Managing Partner and Trial Attorney at Landver Law | Alina Landver, car accident attorney at Landver Law in Beverly Hills |
| noindex | не ставить | не ставить |

## Заголовки H2 легковой страницы

Один H1, дальше только H2 (без пропусков уровней), в каждом естественное слово из ключей:

1. Что произойдёт, когда вы позвоните car accident lawyer (How it works: What happens when you call)
2. Не готовы звонить? Посмотрите, что относится к вашему случаю (Not ready to call? See what applies to your case)
3. Что страховые делают первыми после аварии (What insurance companies often do first after a car accident)
4. Ваш адвокат по ДТП (Your California car accident attorney)
5. Отзывы клиентов (What people say after working with Landver Law)
6. Вопросы про ДТП и адвоката (Questions about car accidents and hiring a lawyer)
7. Бесплатный разбор (Get your free case review)

## Вопросы FAQ легковой страницы (с ключами, ответы без цифр)

- Do I need a lawyer after a car accident in California? (ответ: если есть травма, бесплатный разбор подскажет; без гарантий и без обещания результата)
- How much does a car accident lawyer cost? (бесплатный разбор, no fee unless we win, дальше текст клиента про contingency)
- My medical treatment is still ongoing. Is it too early to contact a lawyer? (текст клиента)
- What if I may have been partly responsible for the accident? (текст клиента)
- The insurance company is asking for a recorded statement. What should I do? (текст клиента)
- I already received a settlement offer. Can I still have the case reviewed? (текст клиента)
- How long do I have to bring an injury claim in California? (текст клиента)

## Что проверять перед публикацией (обе страницы)

1. Заголовок H1 повторяет слова ключей, а объявление группы не обещает того, чего нет на странице. Сверить с текстом объявлений группы: тексты объявлений легковых групп в кабинете.
2. На странице один H1, у всех изображений есть описание (alt), у кнопок и ссылок понятный текст («Get my free case review», «Call (844) 452-9465»), а не «click here».
3. Телефон, адрес и почта видны; ссылки на Privacy Policy и Terms of Use — после ответа клиента.
4. Нет всплывающих окон и перекрытий на телефоне; плашка внизу не закрывает кнопки.
5. Скорость: Lighthouse мобильный после публикации (цель: LCP до 2,5 с). На старой странице было 3,8 с.
6. Важные слова лежат в обычном тексте, а не только в динамических блоках (вопросы квиза строятся кодом).
7. Title и Description внесены во вкладку SEO в Tilda, адрес страницы задан.
