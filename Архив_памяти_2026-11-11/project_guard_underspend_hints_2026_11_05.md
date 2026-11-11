---
name: project-guard-underspend-hints-2026-11-05
description: "Подсказки сторожа «недобор расхода» и журнал сигналов построены 05.11, включены 05.11 15:20 (underspend.enabled true), сторожа перезапущены"
metadata:
  node_type: memory
  type: project
  originSessionId: 08ebb5b7-aeb2-4211-bc27-a36d57d37bc4
  modified: 2026-11-05T14:14:50.672Z
---

Построено 2026-11-05: `Скрипты/guard_hints.py`, `guard_signals.py`, `test_guard_hints.py`, секция `underspend:` в `Клиенты/{ProfiMet,EkspertAgro}/guard_config.yaml` (enabled: false). Пороги по решению пользователя: медиана расхода 3 чистых дней < 50% бюджета, потеря по бюджету 0, P(цена ≤ цели) ≥ 80% по двум моделям, k0 = 3, шаг 15%.

**Why:** раздел 7 плейбука сторожа; живые сторожа не перезапускались, конфиг читается при старте. Пробный прогон 05.11 дал 0 предложений «поднять» (расход у большинства кампаний ≥ 57% бюджета), одна справка у EkspertAgro `general / search` (недобор 9%, заявок 0, цена не подтверждена).

**How to apply:** включение = отдельное «да» + `enabled: true` + `Скрипты/stop_guard.ps1 -Client <Имя>`. Ответы на сигналы — `guard_signals.py answer <N> да|нет --client <Имя> [--applied ДАТА]`. Заморозка на эксперимент и `course` отложены пользователем; порог 80% фиксирован (режим риска не считается). Связано: [[feedback_numbers_only_from_scripts]], [[project_guard_universal_state_2026_11_04]], [[project_guard_autostart_2026_11_05]].
