# 12. Закрепления, ассеты группы, промо и быстрые ссылки (EkspertAgro, только чтение)

Источник: GAQL по customer 8826134558 через GoogleAdsClient (`gads_stats.GOOGLE_ADS_YAML`), `python -c`, без файла-скрипта. Дата 2026-11-23.
Проверено до запроса: `Скрипты/README.md`, `gads_pmax_asset_groups.py` (только метрики по дням), `gads_assets_full_dump.py` (промо: только target+occasion; текстов группы нет). Готового среза «тексты группы + промо полностью» нет.

## 1. Группа ассетов 6774334868 (кампания 24479597485)
- Имя: «Заинтересованные покупатели», статус ENABLED.
- final_urls: `https://ekspertagro.pl/`; final_mobile_urls: пусто.
- Закрепления (pinned): API не отдаёт. У asset_group_asset нет поля pin; в PMax закрепления нет как функции. Есть только performance_label, в этой версии API (v23) запрос по нему вернул «Unrecognized field».
- Статусы: все 36 ассетов группы ENABLED, REMOVED/PAUSED нет (в выдаче).

Тексты (field_type, status, asset.id):

| field_type | id | текст | знаков |
|---|---|---|---|
| HEADLINE | 315699496979 | Szklarnie TIG z poliwęglanu | 27 |
| HEADLINE | 315699496982 | Szklarnie od producenta | 23 |
| HEADLINE | 315699496985 | Szklarnie TIG — od 2008 roku | 28 |
| HEADLINE | 315699496988 | Wytrzymałe szklarnie TIG | 24 |
| HEADLINE | 315699496991 | Szklarnie dla Twojej działki | 28 |
| HEADLINE | 315699496994 | Rabat od 100 zł za 2 szt | 24 |
| HEADLINE | 315699496997 | Dostawa 5-10 dni gratis | 23 |
| HEADLINE | 315699497000 | Płatność przy odbiorze | 22 |
| HEADLINE | 315699497003 | Eksport do 7 krajów Europy | 26 |
| HEADLINE | 315699497006 | Plony w każdą pogodę | 20 |
| HEADLINE | 315965185549 | Szklarnie ogrodowe poliwęglan | 29 |
| LONG_HEADLINE | 315965185552 | Szklarnie TIG. Własna produkcja. Sprawdzona jakość. Ceny od producenta. Darmowa dostawa! | 88 |
| LONG_HEADLINE | 315965185555 | Szklarnie z poliwęglanu. Dostawa gratis. Rabat 20% na profesjonalny montaż. Konsultacja! | 88 |
| DESCRIPTION | 315699497009 | Wysokiej jakości szklarnie z poliwęglanu od producenta. Rabat od 100 zł za 2 szt. Dzwoń! | 88 |
| DESCRIPTION | 315699497012 | Szklarnie TIG od 2008 roku — 15+ lat doświadczenia. Eksport do 7 krajów UE. Dzwoń! | 83 |
| DESCRIPTION | 315699497015 | Dostawa za 5-10 dni w całym kraju. Rabat 20% na profesjonalny montaż. Konsultacja! | 83 |
| DESCRIPTION | 334869311645 | Własna produkcja. Sprawdzona jakość. Ceny od producenta bez marży. Darmowa dostawa. | 84 |

(Знаки посчитаны на глаз по тексту, не из API; для записи пересчитать скриптом.)
Всего 11 заголовков, 2 длинных, 4 описания. Прочие ассеты группы (все ENABLED): MARKETING_IMAGE 4 (id 315887481866, 315964099153, 334935734749, 334976062794), PORTRAIT_MARKETING_IMAGE 4 (315887465024, 316010297373, 334846522025, 334846731131), SQUARE_MARKETING_IMAGE 4 (315887481092, 315887481836, 334846731137, 334975800582), YOUTUBE_VIDEO 5 (440107471762, 440182042302, 440182042866, 440182043469, 440182047006). Логотипа и business name в выдаче группы нет (могут быть на уровне кампании/аккаунта, не проверял).

## 2. Промо-ассет 315547243524
- type PROMOTION; promotion_target «montaż szklarni»; percent_off 200000 (микро-единицы = 20%); discount_modifier UNKNOWN (не задан); occasion UNKNOWN (не задан); language_code pl.
- Не заданы (в ответе пусто): promotion_code, orders_over_amount, money_amount_off, даты start/end и redemption.
- final_urls: `https://ekspertagro.pl/#promo`.
- Привязка: campaign_asset кампании 24479597485, field_type PROMOTION, ENABLED. customer_asset: нет. В asset_group_asset группы: нет.

## 3. Быстрые ссылки кампании 24479597485 (campaign_asset, все ENABLED)

| id | якорь (final_url) | текст | описание 1 | описание 2 |
|---|---|---|---|---|
| 315545297514 | https://ekspertagro.pl/#bs1 | Wszystkie rozmiary | Od kompaktowych do profesjonalnych | Szybka wysyłka z magazynu |
| 315545297517 | #bs2 | Oszczędność przy zakupie | Rabat od 100 zł na 2+ sztuki | Montaż z rabatem 20% |
| 315545297520 | #bs3 | Pomoc w wyborze szklarni | Ekspert-ogrodnik odpowie na pytania | Pomożemy wybrać idealny rozmiar |
| 315545297523 | #bs4 | Szybka dostawa | Darmowa dostawa za 5-10 dni | Wysyłka w całej Polsce |
| 315545297526 | #bs5 | Sprawdzony producent | Własna produkcja od 2008 roku | Eksport do 7 krajów Europy |
| 315545297529 | #bs6 | Wygodna płatność | Płatność za pobraniem towaru | Bez wymaganej przedpłaty |

(Все адреса на `https://ekspertagro.pl/`; якоря существуют ли на странице, не проверялось. customer_asset по 315545297514 и 315547243524: пусто. В группу ссылки не привязаны.)

## Вердикт
1. Группа 6774334868: final URL `https://ekspertagro.pl/`, все 36 ассетов ENABLED, REMOVED/PAUSED нет.
2. Текстов 17: 11 заголовков, 2 длинных, 4 описания; полный список с id выше.
3. Закрепления: API не отдаёт (в PMax pin не существует как поле asset_group_asset).
4. Промо 315547243524: «montaż szklarni», 20% (percent_off=200000), pl, без кода, без порога заказа, без дат, occasion не задан.
5. Промо привязано на уровне кампании 24479597485, ENABLED; на уровне аккаунта и группы нет.
6. Быстрых ссылок 6, все ENABLED, на кампании; якоря #bs1-#bs6 на главной ekspertagro.pl.
7. Совпадение смысла: 20% относится к монтажу (промо и тексты ссылок/длинных заголовков), «Rabat od 100 zł za 2 szt» отдельно; соответствие странице не сверялось (вне задачи).
8. Пробела нет, запись в кабинет не делалась, --execute не запускался.
