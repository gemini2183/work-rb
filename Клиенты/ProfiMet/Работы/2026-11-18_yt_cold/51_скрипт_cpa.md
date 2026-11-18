# 51. Скрипт: --target-cpa (2026-11-18)

Скрипт: `D:\GitHub\work-rb\Скрипты\gads_set_campaign_bidding.py`. Новый параметр `--target-cpa N` (только с `MAXIMIZE_CONVERSIONS`).

## Снимок «до» (чтение, 18.11 10:22)
yt_cold 24468615055: PAUSED, MAXIMIZE_CONVERSIONS, target_cpa 0, cpc_ceiling 0. Файл: `D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\Статистика\snapshot_before_bidding_24468615055_20261118_1022.json`.

## Проверки
- `python -m py_compile` - ок; `--help` показывает `--target-cpa`.
- validate_only, `maximize_conversions.target_cpa_micros=33000000`: ОШИБКА дословно `The operation is not allowed for the given context. | context_error: OPERATION_NOT_PERMITTED_FOR_CONTEXT` (П-038).
- Альтернативы (разовый validate_only): `target_cpa.target_cpa_micros=33` - ок; `maximize_conversions.target_cpa_micros=0` - ок; маска `maximize_conversions` целиком - `FIELD_HAS_SUBFIELDS`.
- Скрипт после правки на `--target-cpa 33`: «Проверка пройдена... MAXIMIZE_CONVERSIONS (target_cpa 0.0) → TARGET_CPA (target_cpa 33.0)».

## Не проверено
- `--execute` (запись); как кампания поведёт себя на TARGET_CPA без истории конверсий.
- Портфельная стратегия (`bidding_strategy`) - не пробовали, обход не понадобился.
- Документация типа объекта Demand Gen: доступа к ней в сессии не было; сверено только поведением Google (validate_only). Метка «по документации проверено» НЕ ставится.

## Обновлено
`Скрипты\README.md` (новый раздел), `База_знаний\Агенты\Каталог_операций.md` (строка «Смена стратегии»), `Инфраструктура.md`, `База_знаний\Проблемы\П-038_...md` + `index.md`.

## Команда для записи (только по «да»)
`python D:\GitHub\work-rb\Скрипты\gads_set_campaign_bidding.py --customer-id 7552781705 --client-folder ProfiMet_YouTube --campaign-id 24468615055 --strategy MAXIMIZE_CONVERSIONS --target-cpa 33 --execute`
