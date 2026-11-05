---
name: demand-gen-оптимизация-ассетов-короткие-и-ресайз-видео
description: Что делают переключатели Asset optimization в видеообъявлении Demand Gen (Shorter videos, Resized videos, Overlay on videos, Landing page previews, Generated text) и как их выключить
status: не протестировано
updated: 2026-11-04
---

# Demand Gen: оптимизация ассетов у видео (Shorter / Resized / Overlay)

Источник: справка Google «About video enhancements» (support.google.com/google-ads/answer/13652431), Search Engine Land про Overlay (статья не открылась, 403, использован пересказ из поиска), API-перечисление `AssetAutomationType`. Не сверено с поведением нашего кабинета.

## Что делает каждый переключатель
| Переключатель | Что делает | По умолчанию |
|---|---|---|
| Shorter videos | Gemini выбирает ключевые моменты и режет из вашего видео более короткие версии; показываются, если прошли проверку качества. Пример Google: версия, лучше удерживающая внимание в первые 5 с. В API: `GENERATE_SHORTER_YOUTUBE_VIDEOS` | вкл |
| Resized videos | ИИ «переворачивает или расширяет» видео под другие пропорции (вертикаль, квадрат); «модель 2» достраивает кадр генеративно | вкл |
| Overlay on videos (новое, октябрь 2026) | Накладывает на видео текст с ключевыми сообщениями из ваших текстовых ассетов | по пересказам вкл по умолчанию; в нашем кабинете 04.11 стоит «Off» |
| Landing page previews | Картинки с посадочной (превью страницы) как дополнительные изображения | вкл |
| Generated text | ИИ-тексты | в нашем кабинете «Off» |

В справке не сказано: минимальная длина, площадки, способ кадрирования, ставится ли ИИ-метка, можно ли увидеть сгенерированные версии до показа. Что известно про ИИ-метки: на показах в ЕС Google помечает ассеты, изменённые ИИ (текст в самом кабинете, см. [[Google-Ads-изображения-ассеты-требования-и-ИИ-метки]]).

## Как выключить (по справке Google, для Demand Gen)
Шестерёнка кампании → объявление → Video ad → Review campaign → Creative optimizations → выключить Shorter videos и Resized videos → Publish campaign. Правка по каждому объявлению отдельно.

## Применение к ProfiMet YouTube
Кампания `yt_warm`: у нас два ролика под два номера Ringostat (16:9 и 9:16), каждый с отдельным `utm_content`. Нарезка и ресайз Google создают производные от ролика, но ссылка и номер те же, поэтому атрибуция не ломается. Риски: подписи в 9:16 подняты на уровень около 60% высоты ([[../../Клиенты/ProfiMet_YouTube/Решения]]), автокадрирование 16:9 → вертикаль может их срезать или закрыть; автообрезка может отрезать заставку «Płacisz przy odbiorze» и призыв. Это гипотеза, на практике не проверено.

## Источники
- https://support.google.com/google-ads/answer/13652431
- https://searchengineland.com/google-ads-adds-automatic-text-overlays-to-demand-gen-video-ads-494885
- https://developers.google.com/google-ads/api/reference/rpc/v22/AssetAutomationTypeEnum.AssetAutomationType
