# Как собрать легковую страницу (Car) в Tilda

Папка: `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Tilda_страница_Car\`

| Файл | Что это |
|---|---|
| `0_maket_prosmotr.html` | Макет всей страницы для просмотра (двойной щелчок, откроется в браузере). Формы в нём нарисованные. |
| `1_blok_top.txt` | Блок 1: шапка, первый экран (H1, доверие, кнопка звонка), нижняя плашка на телефоне. |
| `2_blok_body.txt` | Блок 2: всё под формой A (как проходит звонок, ситуации, страховая, адвокат, отзывы, квиз «Not ready to call?», вопросы, финальный призыв). |
| `3_blok_footer.txt` | Блок 3: подвал с дисклеймерами. |

Блоки сделаны как `.txt`, чтобы открывались в Блокноте двойным щелчком. Содержимое копируется (Ctrl+A, Ctrl+C) и вставляется в блок «HTML» в Tilda. Названия кнопок Tilda ниже написаны по памяти, интерфейс не проверял.

## Шаг 1. Новая страница

1. Дубликат любой готовой страницы сайта `landverpersonalinjury.tilda.ws` (например, страницы Settlement), все блоки удалить.
2. Адрес страницы: `california-car-accident-lawyer`
3. Вкладка SEO:
   - Title: `California Car Accident Lawyer | Free Review | Landver Law`
   - Description: `Hurt in a car accident in California? Get a free case review from Landver Law. No fee unless we win. Call 24/7 or leave your number.`
   - Заголовки для соцсетей: те же.

## Шаг 2. Блоки по порядку

1. Блок HTML: `1_blok_top.txt`
2. Форма Tilda A (компактная, см. ниже)
3. Блок HTML: `2_blok_body.txt`
4. Форма Tilda B (копия A, но обычных размеров)
5. Блок HTML: `3_blok_footer.txt`

## Шаг 3. Формы

Общие настройки: фон кремовый `#f6f2ea`; кнопка `#e8563f`; поля «First name» и «Phone number» (обе обязательные); скрытое поле с именем `quiz_summary`; текст кнопки `Get my free case review`; сообщение после отправки: `Thank you. We've received your request and will contact you to set up your free case review. Prefer to talk now? Call (844) 452-9465 · 24/7.`; под формой: `Submitting this form does not by itself create an attorney-client relationship.`

**Форма A** (сразу под блоком 1) должна быть компактной, иначе на телефоне она уйдёт за границу первого экрана: отступ сверху и снизу в настройках блока 20 px, заголовок `Prefer we call you? Leave your number.`, подзаголовок `Leave your name and phone. We'll contact you to set up your free review with an attorney.`

**Форма B** (после блока 2): заголовок `Get my free case review`, отступы обычные (около 36 px), подзаголовок тот же.

## Шаг 4. Публикация и проверка

1. Опубликовать, открыть на телефоне и на компьютере.
2. Проверить: первый экран показывает заголовок, кнопку звонка и начало формы A; нижняя плашка не закрывает кнопки.
3. Пройти квиз «Not ready to call?», убедиться, что кнопка результата ведёт к форме B.
4. Отправить тестовую заявку из формы A и из формы B; в заявке должно быть поле `quiz_summary`.
5. Прислать мне ссылку: проверю подмену номера (`phone_swap_check.py`) и скажу, какие правила добавить в Ringostat.

## Не делать до проверки

- Не менять адрес страницы в группах Google Ads, пока страница не проверена и нет «да».
- Не ставить `noindex`.
- Не ссылаться на страницу с сайта клиента.

## Откуда брать правки

Исходник текста и сборки: `D:\GitHub\work-rb\Клиенты\Andverpersonalinjury\Кампании\Search\build_car_page.py`. После моих правок файлы в этой папке пересобираются, поэтому вставляйте в Tilda всегда файлы из папки `Tilda_страница_Car`.
