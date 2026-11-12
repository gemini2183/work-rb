#!/usr/bin/env python
"""agent_read_guard.py - хук PreToolUse для узких агентов: запрет чтения чужого «информационного поля».

Подключается в frontmatter файла агента (`.claude/agents/<имя>.md`, раздел hooks -> PreToolUse).
Харнес передаёт JSON на stdin: {"tool_name": ..., "tool_input": {...}}. Если путь или команда
совпадают с запретным шаблоном (--deny, регулярное выражение, без учёта регистра; пути с `/`),
выходит с кодом 2 и пишет причину в stderr - вызов инструмента блокируется, агент видит причину.
Каждая блокировка дописывается в Скрипты/logs/agent_read_guard.csv (время, агент, инструмент, цель).

ТОЛЬКО ЧТЕНИЕ входа; пишет только свой журнал. Ограничение: проверка по тексту пути/команды -
Bash можно обойти (переменные, склейка путей); это страховка от случайного чтения, а не защита.

Пример: python agent_read_guard.py --agent campaign-scout --deny "Хроника_\\d{4}" --deny "Решения\\.md"
Проверка вручную: echo {"tool_name":"Read","tool_input":{"file_path":"D:/x/Решения.md"}} | python agent_read_guard.py --agent t --deny "Решения\\.md"
"""
import argparse
import csv
import json
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).resolve().parent / "logs" / "agent_read_guard.csv"


def targets(tool: str, ti: dict) -> list[str]:
    """Строки, в которых ищем запретные шаблоны."""
    out = []
    for key in ("file_path", "path", "pattern", "glob", "command", "notebook_path"):
        v = ti.get(key)
        if isinstance(v, str) and v:
            out.append(v)
    return [s.replace("\\", "/") for s in out]


def agent_rules(agent_type: str):
    """(deny, allow) из команды хука во frontmatter .claude/agents/<agent_type>.md; None - файла/хука нет."""
    f = Path(__file__).resolve().parent.parent / ".claude" / "agents" / f"{agent_type}.md"
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r"command:\s*'(.*?agent_read_guard\.py.*?)'\s*$", text, re.M)
    if not m:
        return None
    try:
        toks = shlex.split(m.group(1))
    except ValueError:
        return None
    p = argparse.ArgumentParser()
    p.add_argument("--agent")
    p.add_argument("--deny", action="append", default=[])
    p.add_argument("--allow", action="append", default=[])
    ns, _ = p.parse_known_args([t for t in toks if not t.endswith(".py") and t not in ("python", "PYTHONUTF8=1")])
    return ns.deny, ns.allow


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="?")
    ap.add_argument("--deny", action="append", default=[], help="регулярное выражение запретного пути/команды")
    ap.add_argument("--allow", action="append", default=[], help="исключение: если совпало, не блокировать")
    ap.add_argument("--auto", action="store_true",
                    help="режим settings.json: взять agent_type из входа хука и правила --deny/--allow из frontmatter "
                         "файла .claude/agents/<agent_type>.md; вызов без agent_type (основная сессия) не трогать")
    ap.add_argument("--dump", help="диагностика: дописать сырой вход хука в этот файл (ключи и инструмент, без блокировки)")
    a = ap.parse_args()

    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        data = json.loads(raw)
    except Exception:
        return 0  # нет понятного входа - не мешаем работе
    if a.dump:
        try:
            with open(a.dump, "a", encoding="utf-8") as f:
                f.write(raw[:1500].replace(chr(10), " ") + chr(10))
        except Exception:
            pass
        return 0
    if a.auto:
        at = data.get("agent_type")
        if not at:
            return 0
        rules = agent_rules(at)
        if rules is None:
            return 0
        a.agent, a.deny, a.allow = at, rules[0], rules[1]
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    for s in targets(tool, ti):
        if any(re.search(p, s, re.I) for p in a.allow):
            continue
        for p in a.deny:
            if re.search(p, s, re.I):
                try:
                    LOG.parent.mkdir(exist_ok=True)
                    new = not LOG.exists()
                    with LOG.open("a", encoding="utf-8", newline="") as f:
                        w = csv.writer(f)
                        if new:
                            w.writerow(["время", "агент", "инструмент", "цель", "шаблон"])
                        w.writerow([datetime.now().isoformat(timespec="seconds"), a.agent, tool, s[:300], p])
                except Exception:
                    pass
                msg = (f"ЗАБЛОКИРОВАНО хуком agent_read_guard ({a.agent}): «{s[:200]}» вне твоего поля чтения "
                       f"(шаблон {p}). Не открывай это; если данных не хватает - запиши в «Что нужно от пользователя» "
                       f"и верни ответ.\n")
                # байты в utf-8: консольная кодировка Windows (cp1251/cp866) не должна ронять хук кодом 1
                sys.stderr.buffer.write(msg.encode("utf-8", "replace"))
                sys.stderr.flush()
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
