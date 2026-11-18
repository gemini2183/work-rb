---
status: обходится
updated: 2026-11-18
система: Google Ads API v23 / Demand Gen
---

# П-038: Demand Gen: maximize_conversions.target_cpa_micros=N отклоняется

**Симптом (18.11, validate_only, `yt_cold` 24468615055, аккаунт 7552781705):** `gads_set_campaign_bidding.py --strategy MAXIMIZE_CONVERSIONS` с записью `campaign.maximize_conversions.target_cpa_micros = 33000000` вернул дословно: `The operation is not allowed for the given context. | context_error: OPERATION_NOT_PERMITTED_FOR_CONTEXT`. С значением 0 (без изменения) проходит; маска `maximize_conversions` целиком - `FIELD_HAS_SUBFIELDS`.

**Что работает (validate_only, 18.11):** `campaign.target_cpa.target_cpa_micros = 33000000` с маской `target_cpa.target_cpa_micros` - Google принял. В API это стратегия TARGET_CPA (в интерфейсе - «Максимум конверсий» с целевой ценой конверсии). Скрипт `--target-cpa` теперь пишет именно так.

**Не установлено:** принимает ли запись (`--execute`) то же; через портфельную стратегию (`bidding_strategy`) не проверяли; по документации типа объекта не сверено (нет доступа в сессии) - сверено только поведением validate_only.

**Как проверить:** `python Скрипты\gads_set_campaign_bidding.py --customer-id 7552781705 --client-folder ProfiMet_YouTube --campaign-id 24468615055 --strategy MAXIMIZE_CONVERSIONS --target-cpa 33` - «Проверка пройдена». После `--execute` читать обратно: ожидаем strategy TARGET_CPA, target_cpa 33.
