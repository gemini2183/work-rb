---
status: обходится
updated: 2026-11-24
---

# П-051: канала Maps нет в `DemandGenSelectedChannels` (google-ads v23)

**Симптом:** при создании Demand Gen через API канал Google Maps не задать. В `DemandGenSelectedChannels` (google-ads v23, `D:\Programs\Python\Lib\site-packages\google\ads\googleads\v23\resources\types\ad_group.py`) есть только youtube_in_stream, youtube_in_feed, youtube_shorts, discover, gmail, display.

**Что известно:** решение пользователя 24.11 «Discover, Gmail, Maps, Display» по Maps исполнимо только вручную в интерфейсе. Для кампании `dg_montaz_warm_lal` (И-115) Maps не задан.

**Что НЕ установлено:** появится ли поле Maps в более новой версии API (не проверял).

**Обход:** включить Maps вручную в интерфейсе после создания и проверки показов. В API-чтении этот канал не виден (П-031 не закрыт).

**Найдено:** 24.11.2026, `Клиенты\ProfiMet\Работы\2026-11-24_dg_montaz\30_план.md`, Пробел 2.

**Использовано:** —
