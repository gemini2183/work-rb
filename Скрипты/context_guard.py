#!/usr/bin/env python3
"""context_guard.py - хук UserPromptSubmit: сигнал, что контекст сессии прошёл порог разреза. ТОЛЬКО ЧТЕНИЕ.

Читает вход хука (JSON на stdin: transcript_path / session_id), берёт размер контекста по последнему
вызову модели из журнала сессии и, если он >= порога, печатает JSON с additionalContext - строка попадает
в контекст модели перед ответом. Сам ничего не режет и не перезапускает. Повторный сигнал - только после
роста контекста на STEP с прошлого сигнала (состояние в Скрипты/logs/context_guard_state.json).
Диагностика: --dump <файл> дописывает ключи входа хука (без блокировки) - проверить, что хук получает путь журнала.
Тест вручную:  echo {"transcript_path":"<путь к jsonl>","session_id":"x"} | python Скрипты/context_guard.py --threshold 1
"""
import argparse
import json
import sys
from pathlib import Path

LOGDIR = Path(__file__).resolve().parent / "logs"
STATE = LOGDIR / "context_guard_state.json"
TAIL_BYTES = 600_000


def last_ctx(path: Path):
    """Размер контекста последнего вызова модели (ввод + кэш) читаем с хвоста файла."""
    size = path.stat().st_size
    with path.open("rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", errors="replace")
    for line in reversed(data.splitlines()):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") != "assistant":
            continue
        u = (r.get("message") or {}).get("usage")
        if not u or (r.get("message") or {}).get("model") == "<synthetic>":
            continue
        return ((u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                + (u.get("cache_read_input_tokens") or 0))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=150_000)
    ap.add_argument("--step", type=int, default=40_000)
    ap.add_argument("--dump", help="дописать ключи входа хука в файл")
    a = ap.parse_args()
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    LOGDIR.mkdir(exist_ok=True)
    if a.dump:
        with open(a.dump, "a", encoding="utf-8") as f:
            f.write(json.dumps({k: (str(v)[:80]) for k, v in data.items()}, ensure_ascii=False) + "\n")
    tp = data.get("transcript_path")
    if not tp or not Path(tp).exists():
        return 0
    try:
        ctx = last_ctx(Path(tp))
    except Exception:
        return 0
    if ctx is None or ctx < a.threshold:
        return 0
    sid = data.get("session_id") or Path(tp).stem
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    last = st.get(sid, 0)
    if last and ctx - last < a.step:
        return 0
    st[sid] = ctx
    try:
        STATE.write_text(json.dumps(st), encoding="utf-8")
    except Exception:
        pass
    msg = (f"[context_guard] Контекст сессии ~{ctx // 1000} тыс. токенов, порог разреза {a.threshold // 1000} тыс. "
           "На ближайшей границе этапа (не посреди записи в кабинет) скажи пользователю число и предложи чекпоинт по "
           "База_знаний/Агенты/Чекпоинт_сессии.md: записать чекпоинт, дать промпт старта новой сессии. "
           "Не прерывай идущий ответ и запись; чекпоинт не заменяет чтение обратно из кабинета.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
