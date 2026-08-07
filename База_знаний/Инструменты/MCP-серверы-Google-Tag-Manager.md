---
name: mcp-серверы-google-tag-manager
description: Обзор доступных MCP-серверов для управления Google Tag Manager (создание тегов, триггеров, переменных, публикация) через AI-ассистента
status: не протестировано
updated: 2026-08-07
---

# MCP-серверы для Google Tag Manager

## Зачем

Регулярно всплывает задача завести/поправить тег, триггер или переменную в GTM
клиента вручную (например, ручная настройка Enhanced Conversions — см.
[[Расширенные-конверсии-Google-Ads-ручная-настройка]]). MCP-сервер к Google Tag
Manager API позволяет делать это через диалог с ассистентом вместо ручного клика
по интерфейсу GTM.

## Официальный / готовый вариант

**Stape MCP Server for GTM** — размещённый (remote) сервер, аутентификация через
Google OAuth, без необходимости своего хостинга.
- Подключение: `npx -y mcp-remote https://gtm-mcp.stape.ai/mcp` в конфиге MCP-клиента.
- После первого запуска открывается браузер для OAuth-авторизации Google-аккаунта,
  у которого есть доступ к нужному GTM-контейнеру.
- Архитектура безопасности: чтение (аудит тегов/триггеров/переменных) выполняется
  сразу, а любая мутация — создание, правка, удаление, публикация версии, merge,
  environment/destination — требует явного подтверждения человеком. Это разумный
  барьер для работы с продовыми контейнерами клиентов.
- Источник: [stape.io/blog/mcp-server-for-google-tag-manager](https://stape.io/blog/mcp-server-for-google-tag-manager),
  опенсорсный код — [github.com/stape-io/google-tag-manager-mcp-server](https://github.com/stape-io/google-tag-manager-mcp-server).

## Community-варианты (self-hosted, требуют своей настройки OAuth/service account)

- [`pouyanafisi/gtm-mcp`](https://github.com/pouyanafisi/gtm-mcp) — чтение
  тегов/триггеров/переменных, публикация контейнеров, аудит изменений через
  Claude/Gemini.
- [`neep305/mcp-for-gtm`](https://mcpservers.org/servers/neep305/mcp-for-gtm) —
  полный CRUD по тегам/триггерам/переменным + готовые шаблоны (GA4, Facebook
  Pixel, отслеживание конверсий).
- [`VasthavM/google-tag-manager-mcp`](https://github.com/VasthavM/google-tag-manager-mcp) —
  локальный stdio-сервер на Go, работает с Claude Desktop/Claude Code без облака.
- [`shakibmolla/gtm-mcp`](https://github.com/shakibmolla/gtm-mcp) — локальный,
  управление тегами/триггерами/переменными, создание и публикация версий контейнера.
- [`Synter-Media-AI/google-tag-manager-agent`](https://github.com/Synter-Media-AI/google-tag-manager-agent) —
  заточен под Amp/Cursor/Claude Desktop/VS Code.

## Оценка применимости

Для наших задач (создание dataLayer-переменных под Enhanced Conversions, привязка
их к тегам конверсии, публикация) любой из вариантов теоретически закрывает
потребность — это прямые обёртки над Google Tag Manager API v2. Разница в основном
в: (а) remote vs self-hosted, (б) наличии барьера подтверждения на мутациях
(у Stape есть явно, у community-вариантов нужно проверять поведение по умолчанию).

**Риск:** это прямой доступ на запись в GTM-контейнер клиента — ошибка в теге
ломает отслеживание конверсий незаметно, пока кто-то не заметит просадку данных.
Не давать автопилот без подтверждения на mutation-операции, независимо от того,
какой сервер выбран.

## Статус

Не протестировано — ни один из серверов не подключался и не проверялся на
практике. Кандидат №1 для первой пробы — Stape (официальный, remote, есть
встроенный барьер подтверждения). При тестировании — обновить статус страницы и
зафиксировать результат отдельной записью (успех/проблемы, на каком клиенте).
