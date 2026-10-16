---
status: протестировано (чтение API на Landver)
updated: 2026-10-15
---

# Microsoft Clarity: что можно достать через API (Data Export API)

**Проверено на практике 2026-10-15 (Landver, см. раздел ниже):** токен работает, формат ответа подтверждён. Лимиты и список разрезов — из официальной документации Microsoft (обновлена 2025-12-05) и заметок разработчиков интеграций.

## Что отдаёт
- Endpoint: `GET https://www.clarity.ms/export-data/api/v1/project-live-insights`, заголовок `Authorization: Bearer <токен>`.
- Токен создаёт только админ проекта: Settings → Data Export → Generate new API token. Один токен — один проект (сайт).
- Только **сводные** цифры дашборда за последние **1, 2 или 3 дня** (`numOfDays`), до 3 разрезов за запрос.
- Разрезы: Browser, Device, Country/Region, OS, **Source, Medium, Campaign** (UTM), Channel, **URL**.
- Метрики: Traffic (сессии, боты, пользователи, страниц за сессию), Scroll Depth, Engagement Time, Popular Pages, Referrer URL, Dead Clicks, Rage Clicks, Excessive Scroll, Quickback Click, Script Errors, Error Clicks.

## Чего НЕ отдаёт
- Ни сессий поштучно, ни записей, ни тепловых карт, ни gclid/ключа/utm_term → **связать с конкретным кликом Google Ads и заявкой нельзя**.
- Истории старше 3 дней нет: чтобы копить ряд, надо забирать каждый день и складывать у себя (так делает коннектор PostHog).
- Лимиты: 10 запросов в день на проект, ответ до 1 000 строк без пагинации, ошибка 429 при превышении.

## Как применять
- Годится для ежедневной сводки «URL × Campaign»: rage/dead clicks, quickback, скролл, время — сигналы поломок страницы и «ушёл сразу» по кампаниям.
- Для корреляции «ключ → поведение → заявка» — свои события в GA4 с gclid, см. [[../Паттерны/Поведение-на-сайте-диагностика-реклама-или-сайт]].
- Опыт пользователя (2026-10-15, по другим сайтам): Clarity как источник данных для анализа работает плохо.

## Пример
Landver: на главном сайте landverpersonalinjury.com Clarity стоит (проект `xi4m628zww`, через GTM-KD54VXTM); на tilda-странице car+truck до 2026-10-15 его не было, с версии 6 контейнера GTM-KVLHDKJJ стоит отдельный проект `yy4382dsrf`.

## Источники
- [Microsoft Learn — Clarity Data Export API](https://learn.microsoft.com/en-us/clarity/clarity-data-export-api)
- [PostHog — Microsoft Clarity as a source](https://posthog.com/docs/data-warehouse/sources/microsoft-clarity)
- [Microsoft Clarity MCP Server (README)](https://mcpservers.org/ru/servers/github-com-urdigitalau-mcp-integrations-tree-main-packages-clarity)

## Проверка на практике (Landver, 2026-10-15)
Токен проекта `yy4382dsrf` работает: запрос с `numOfDays=3&dimension1=URL` — HTTP 200, 9 метрик (Traffic, ScrollDepth, EngagementTime, DeadClickCount, RageClickCount, ExcessiveScroll, QuickbackClick, ScriptErrorCount, ErrorClickCount). Поля Traffic: `totalSessionCount`, `totalBotSessionCount`, `distinctUserCount`, `pagesPerSessionPercentage`, `Url`. Проект отделён от главного сайта; тестовые заходы Playwright Clarity помечает как боты (`totalBotSessionCount`). Скрипт копит историю — `Скрипты/clarity_daily.py`.
