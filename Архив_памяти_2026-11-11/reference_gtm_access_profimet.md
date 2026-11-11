---
name: reference-gtm-access-profimet
description: "Как зайти в GTM ProfiMet (GTM-TKGN4NT): какой Google-аккаунт, ссылка, что менялось 01.09 и 06.10.2026"
metadata:
  type: reference
---

GTM-контейнер ProfiMet (mocnaszklarnia.pl) — `GTM-TKGN4NT`, account 6003760261, container 44158621. Лежит в Google-аккаунте **AdWhite Digital**, не в `infobox.anton@gmail.com` (там его нет). В Chrome пользователя это второй аккаунт: открывается ссылкой `https://tagmanager.google.com/?authuser=1#/home` (проверено 2026-10-07; индекс может смениться). **Tag Manager API включён пользователем 2026-10-07 и работает:** ключ `Скрипты/secrets/rb_cloud_service.json` (`rb-cloud-admin@redbird-196813.iam.gserviceaccount.com`, scope `tagmanager.readonly`), в GTM выдан доступ «Читать» на контейнер; видит аккаунт `accounts/6003760261`, контейнер `containers/44158621`. Читать так: `GET https://tagmanager.googleapis.com/tagmanager/v2/accounts/6003760261/containers/44158621/versions:live`. Для записи и публикации прав пока нет (повышать по мере задач; для создания контейнеров, скорее всего, нужен админ аккаунта, не проверено). Цель пользователя: собирать шаблонные GTM-контейнеры для новых проектов через API. Chrome-расширение тоже подключено.

История: 01.09.2026 опубликовано 11 версий (44–54, откат Restored_46), 06.10 версии 60–61 — триггер корзины `addToCart` → `add_to_cart`. Подробности — `Клиенты/ProfiMet/Аудитории/Диагностика_2026-10-07.md`.

**How to apply:** для вопросов про теги/триггеры ProfiMet открывать этот контейнер через `authuser=1`, только чтение; публикацию и правки не делать без явного «да» пользователя. Связано с [[reference-ga4-access-profimet]].
