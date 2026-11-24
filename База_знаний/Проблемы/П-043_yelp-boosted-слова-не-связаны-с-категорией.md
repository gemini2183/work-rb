---
name: п-043-yelp-boosted-слова-не-связаны-с-категорией
description: Yelp Ads: после смены категории Gold Buyers → Jewelry пять из шести Boosted-слов стали серыми «no longer related to your business categories»
status: открыта
system: Yelp Ads (LuxeBrokers)
first_seen: 2026-11-23
updated: 2026-11-23
---

# П-043. Yelp: Boosted-слова серые после смены категории

**Статус:** открыта (обход предложен — вернуть Gold Buyers; решение пользователя не принято)  |  **Система:** Yelp Ads, кабинет LuxeBrokers

## Симптом (дословно, скриншот пользователя 23.11)
В модалке Keywords у Boosted: «Jewelry Buyers», «Jewelry Buyers Near Me», «Sell Cartier», «Sell Jewelry», «Sell Jewelry Near Me» серые; «Sell Luxury Jewelry» активно. Подсказка при наведении: «This keyword is no longer related to your business categories.»

## Что известно
- Слова внесены 23.11 до смены категории и сохранены активными; категория сменена на Shopping > Jewelry позже в тот же день (Журнал И-033).
- Страница Ad settings показывает статус «Your ad is up and running», Estimated audience «typical».
- Причина по факту (23.11): при попытке добавить в Boosted «Jewelry Buyers» и «Sell Jewelry» Yelp показывает ошибку «Boosted keywords must be related to your business.» и слово не добавляет. Yelp отклоняет в Boosted слова, которые не считает связанными с категорией. Остальные три слова пакета (Jewelry Buyers Near Me, Sell Jewelry Near Me, Sell Cartier) не пробовали.
- Чтение кабинета 23.11 вечером: в Boosted остаётся одно слово «sell luxury jewelry»; пять серых слов исчезли из Boosted сами (кто убрал — в данных нет).

## Что НЕ установлено
- Кто и когда убрал пять серых слов из Boosted (в данных нет).
- Влияет ли Boosted из одного слова на показы (не измерено; база ≈ 74 показа в день в Э-8).
- Какие фразы Yelp считает связанными с Shopping > Jewelry (правила Yelp не найдены; три слова пакета не пробовали).

## Обход / проверка
- Открыть Keywords позже (через несколько часов, завтра) и сверить вид слов.
- Сравнить показы за 24 ч после смены категории с базой ≈ 74 в день (Э-8 в `Эксперименты.md`).
- Если слова остаются серыми — решить пользователю: откат категории на Gold Buyers (одна правка, см. снимок `Клиенты/LuxeBrokers/Работы/2026-11-23_Э-8_yelp_ювелирка/05_снимок_до_кабинета_Yelp.md`) или иная категория.

## Использовано
—
