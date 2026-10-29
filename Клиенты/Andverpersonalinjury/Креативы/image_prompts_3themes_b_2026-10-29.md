---
status: план 29.10, генерация и загрузка — после «да» пользователя
updated: 2026-10-29
---

# Групповые картинки для Motorcycle, Pedestrian, Bicycle (Google Search, ассеты изображений) — по образцу И-110

Образец: `image_prompts_3themes_2026-10-28.md`, `images_3groups_plan_2026-10-28.json`. Группы включены 29.10 (И-118) и сейчас показывают 11 кампанийных картинок (бинты, авария, деньги), пока групповых нет — групповые перекрывают кампанийные.

Правила плейбука `База_знаний/Агенты/Создатель_картинок.md` и чек-листа `База_знаний/Паттерны/Юристы-Калифорния-картинки-в-рекламе-что-нельзя-и-как-проверять.md`: людей в кадре нет (в том числе нет велосипедиста, мотоциклиста и пешехода), денег и бинтов нет, текста, номеров, логотипов и марок нет, нет следов аварии (вмятин, обломков, обуви на дороге — «драматизация» по §6157.2(a)(3)(B)), нет полиции и скорой. Файл — ИИ: `.meta.json`, метка «created or edited with AI» ставится в интерфейсе (в API поля нет).

Форматы: 1536×1024 → кадрирование `image_tool.py fit` до 1200×628 (1,91:1) и отдельная генерация 1024×1024 (1:1), как 28.10. По 3 кадра на тему, 18 файлов.

## Motorcycle
1. `mc_1_helmet` — Black motorcycle helmet and a pair of leather riding gloves resting on a polished wooden desk, soft natural daylight from a window, blurred modern law office in the background, warm calm neutral tones, photorealistic, no people, no text, no logos, no brand markings, no money, no signage.
2. `mc_2_parked` — A parked motorcycle seen from the side on a quiet Los Angeles street at golden hour, palm trees blurred in the background, no rider, no people, no license plate, no logos or brand badges, no text, undamaged, calm mood, photorealistic.
3. `mc_3_handlebar` — Close-up of a motorcycle handlebar and side mirror with a blurred city street at dusk behind it, no rider, no people, no logos, no text, calm mood, photorealistic.

## Pedestrian
1. `pd_1_crosswalk` — An empty marked crosswalk on a quiet Los Angeles street in daylight, palm trees, no cars, no people, no readable text or street signs, calm neutral tones, photorealistic.
2. `pd_2_signal` — A pedestrian crossing signal showing the white walking figure symbol on a street corner, blurred city background, daylight, no people, no vehicles, no letters or words anywhere, photorealistic.
3. `pd_3_corner` — A quiet street corner with a curb ramp and sidewalk at dusk, soft warm light from blurred shop windows, empty, no people, no vehicles, no signage, no text, photorealistic.

## Bicycle
1. `bc_1_lane` — A green painted bike lane with a white bicycle symbol on the asphalt of a quiet Los Angeles street in daylight, no cyclists, no cars, no people, no text, photorealistic.
2. `bc_2_parked` — A bicycle parked against a plain wall on a sunny sidewalk, palm tree shadow, no rider, no people, undamaged, no brand logos, no text, calm neutral tones, photorealistic.
3. `bc_3_handlebar` — Close-up of a bicycle handlebar, bell and front wheel with a blurred city street behind, no rider, no people, no brand logos, no text, photorealistic.

## Что проверяю глазами на каждом файле перед загрузкой (скрипт этого не видит)
Люди и мелкие фигуры на фоне; читаемые надписи и номера (в том числе искажённые «буквы» на знаках и корпусах); логотипы на шлеме и мотоцикле; следы аварии; в кадре с сигналом пешехода — нет слов «WALK»; миниатюра 150–200 px читается (плейбук, «Уроки по клиентской обратной связи»). Кадр с дефектом пересоздаю до двух раз, иначе исключаю из загрузки.
