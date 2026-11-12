"""_runlog.py - общий помощник скриптов записи: --log-file дублирует вывод скрипта в файл (utf-8).

Зачем: результат записи (что создано, какая версия, чтение обратно, откат) попадает в `файлы/` папки задачи
сам, и `40_запись.md` собирается из лога, а не пересказом. Скрипт по-прежнему печатает в консоль.

Использование в скрипте:
    import _runlog
    ap = argparse.ArgumentParser(); ...; _runlog.add_arg(ap)
    a = ap.parse_args(); _runlog.start(a)      # после parse_args (и после замены sys.stdout, если она есть)

В файл первой строкой пишется шапка: время, команда (argv), режим (ПЛАН/EXECUTE). Секретов не пишет: argv скриптов GTM их не содержит.
"""
import sys
from datetime import datetime
from pathlib import Path


class _Tee:
    def __init__(self, stream, f):
        self._s, self._f = stream, f

    def write(self, data):
        self._s.write(data)
        try:
            self._f.write(data)
            self._f.flush()
        except Exception:
            pass
        return len(data)

    def flush(self):
        self._s.flush()

    def __getattr__(self, name):
        return getattr(self._s, name)


def add_arg(ap):
    ap.add_argument("--log-file", help="дублировать весь вывод в этот файл (utf-8, дозапись); папка создаётся")


def start(args):
    path = getattr(args, "log_file", None)
    if not path:
        return None
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    f = p.open("a", encoding="utf-8", newline="\n")
    mode = "EXECUTE" if getattr(args, "execute", False) else "ПЛАН (без записи)"
    f.write(f"# {datetime.now().isoformat(timespec='seconds')} | {mode} | {' '.join(sys.argv)}\n")
    f.flush()
    sys.stdout = _Tee(sys.stdout, f)
    sys.stderr = _Tee(sys.stderr, f)
    return f
