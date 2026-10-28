---
status: на согласование и передачу исполнителю; на странице пока ничего не менялось
updated: 2026-10-28
---

# Страница Wrongful Death: что поменять, чтобы она была про любую смерть по чужой вине

Адрес страницы: https://landverpersonalinjury.tilda.ws/wrongful-death-lawyer-california

## Зачем это нужно
Раньше страница говорила «только несчастные случаи на дороге». Начальник клиента 28.10 одобрил взять wrongful death широко: любая смерть по чужой небрежности. Единственное, что не берём, как и раньше: врачебные ошибки (medical malpractice), больницы и дома престарелых. Пока на странице написано узко, реклама не может обещать больше: человек попадёт на страницу, увидит «только дорога» и уйдёт. Поэтому сначала страница, потом реклама.

## Как работать
Весь код страницы лежит в одном блоке Tilda (идентификатор `rec5249094203`). В нём нужно найти нужные строки и заменить, как написано ниже. Больше в строках ничего не трогайте: классы, теги и порядок оставьте. Новых блоков и новых id не создавайте. Делайте по порядку, после каждого пункта можно сохранять.

---

## Пункт 1. Первый экран: фраза про то, какие случаи на странице

Где: под подзаголовком «We are sorry for your loss…», мелким шрифтом.

Найти:

```html
<p class="vb-a2s__hero-fn">This page is about deaths caused by accidents. It is not for medical malpractice, hospital or nursing home cases.</p>
```

Заменить на:

```html
<p class="vb-a2s__hero-fn">This page is about deaths caused by someone else's negligence: accidents, falls, dog attacks, unsafe property, dangerous products and more. It is not for medical malpractice, hospital or nursing home cases.</p>
```

Как проверить: фраза встала под подзаголовком в одну-две строки, на телефоне не обрезана.

---

## Пункт 2. Блок «Deaths Landver Law reviews»: список случаев

Где: блок с заголовком «Deaths Landver Law reviews: caused by someone else's negligence», серые «таблетки» со случаями. Сейчас там только транспорт. Добавить после последней строки списка ещё десять случаев.

Найти:

```html
<li>A fatal Uber or Lyft crash</li>
```

Заменить на (первая строка та же, остальные новые, всё внутри того же списка):

```html
<li>A fatal Uber or Lyft crash</li>
<li>A fatal fall on someone else's property</li>
<li>A fatal dog attack</li>
<li>A death on a construction site or workplace where a third party is at fault</li>
<li>A drowning, for example in a pool or hotel</li>
<li>A fire, explosion or electrocution</li>
<li>A shooting or assault where security was poor</li>
<li>A death caused by a defective product or dangerous drug</li>
<li>A fatal plane, boat, train or transit accident</li>
<li>A scooter, e-bike or golf-cart crash</li>
<li>A fatal accident caused by a dangerous public road or property</li>
```

Закрывающий `</ul>` после списка уже есть в коде, его не трогайте и второй раз не добавляйте.

Как проверить: список теперь из шестнадцати пунктов, на телефоне «таблетки» переносятся на следующие строки, наползаний нет.

---

## Пункт 3. Под этим же списком: оговорка

Найти:

```html
This page is for deaths caused by accidents. It is not for medical malpractice, hospital or nursing home cases. Every case depends on its own facts, evidence, liability and insurance coverage.
```

Заменить на:

```html
This page is for deaths caused by someone else's negligence. It is not for medical malpractice, hospital or nursing home cases. Every case depends on its own facts, evidence, liability and insurance coverage.
```

---

## Пункт 4. Вопросы и ответы: «What if I think a medical error caused the death?»

Найти:

```html
<summary>What if I think a medical error caused the death?</summary> <p>This page is about deaths caused by accidents. It is not for medical malpractice, hospital or nursing home cases.
```

Заменить на:

```html
<summary>What if I think a medical error caused the death?</summary> <p>This page is about deaths caused by someone else's negligence. It is not for medical malpractice, hospital or nursing home cases.
```

Хвост ответа («Those claims follow different rules…») оставить как есть.

---

## Пункт 5. Вопросы и ответы: «Does the death have to happen at the scene?»

Найти:

```html
after an accident such as a crash can still be reviewed
```

Заменить на:

```html
after an accident or injury can still be reviewed
```

---

## Пункт 6. Настройки страницы в Tilda (не код блока)

Где: Настройки страницы → SEO → поле Description. В Facebook и соцсетях поле тоже, если оно заполнено отдельно.

Найти (в SEO Description):

```
Lost a loved one in a fatal accident? Speak with a California wrongful death attorney at Landver Law. Free case review. No fee unless we win. Call 24/7.
```

Заменить на (138 знаков, влезает в поисковую выдачу):

```
Lost a loved one due to someone's negligence? Speak with a California wrongful death attorney at Landver Law. Free case review. Call 24/7.
```

В поле для соцсетей (og:description):

Найти:

```
Lost a loved one in a fatal accident? Speak with a California wrongful death attorney at Landver Law. Free case review.
```

Заменить на:

```
Lost a loved one due to someone's negligence? Speak with a California wrongful death attorney at Landver Law. Free case review.
```

Заголовок страницы (Title) оставить как есть.

---

## Что не менять
- Заголовок первого экрана «California Wrongful Death Lawyer. Free Case Review.» и подзаголовок «We are sorry for your loss…».
- Формы, кнопки, номера телефонов, `id` и классы (по ним работают отслеживание звонков и форм).
- Блоки про адвоката, отзывы, результаты и стоимость.

## Что остаётся за нами после правок страницы
- Я проверю страницу скриптом, что форма, кнопки и подмена номера работают, как раньше.
- Заменю объявление Wrongful Death на широкое (тексты согласованы в чате 28.10).
- Дам знать, если нужно проверить Brain Injury и Rideshare так же.

## Открытый вопрос (не блокирует правки)
Смерть при задержании полицией или в тюрьме, а также дома престарелых не включены ни в список, ни в рекламу. Начальник одобрил «всё, кроме врачебных ошибок»; полицию и тюрьму прямо не называл. Если берём, добавить пункт в список и снять минусы `police`, `jail`, `prison` в группе.
