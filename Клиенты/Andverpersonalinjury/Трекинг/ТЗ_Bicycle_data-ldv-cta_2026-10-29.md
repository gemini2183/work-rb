---
status: готово к отправке исполнителю, не отправлено
updated: 2026-10-29
---

# ТЗ исполнителю страницы Bicycle (один пункт): добавить второй атрибут к кнопкам

Страница: https://landverpersonalinjury.tilda.ws/bicycle-accident-lawyer-california

**Зачем.** На остальных наших страницах (Car, Motorcycle, Pedestrian) у кнопок стоит атрибут `data-ldv-cta`. По нему подставляется номер из рекламы (коллтрекинг) и записывается, какую кнопку нажали. На Bicycle стоит только `data-vb-cta`, поэтому реклама видит общий номер (844) 452-9465 и звонки с неё не засчитываются. Проверено 29.10: если добавить `data-ldv-cta`, подмена работает на всех 8 ссылках.

**Что сделать.** В каждой из 18 ссылок на странице, где есть `data-vb-cta="…"`, дописать рядом второй атрибут с тем же значением. Ничего не удалять и не менять.

Было:
```
<a class="vb-q7x__tel" href="tel:+18444529465" data-vb-cta="header_call">
```
Стало:
```
<a class="vb-q7x__tel" href="tel:+18444529465" data-vb-cta="header_call" data-ldv-cta="header_call">
```

Так же для всех значений: `header_call`, `header_form`, `hero_fee`, `hero_call`, `sticky_call`, `sticky_form`, `how_form`, `how_call`, `fee_form`, `fee_call`, `cases_form`, `attorney_form`, `attorney_call`, `reviews_form`, `final_form`, `final_call`, `footer_call`, `footer_email`.

Если в Tilda проще заменой в коде блоков: найти `data-vb-cta="X"`, заменить на `data-vb-cta="X" data-ldv-cta="X"` (X — каждое из значений выше).

**Как проверить.** Открыть страницу с адресом `…/bicycle-accident-lawyer-california?utm_source=google&utm_medium=cpc` — в кнопках звонка должен быть не (844) 452-9465, а другой номер (888). Без меток номер остаётся (844) 452-9465. Остальное проверим мы.
