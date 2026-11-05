#!/usr/bin/env python
# coding: utf-8
"""Журнал сигналов сторожа: `Клиенты/<Имя>/Статистика/guard_signals.csv` — одна строка на подсказку сторожа.
Решение пользователя 2026-11-05 (см. База_знаний/Агенты/Сторож_жизненный_цикл_кампаний_и_план_изменений.md, раздел 7).

Пишут двое: сторож (`guard_hints.py`: новые сигналы, напоминания, эффект) и оператор (этот скрипт: ответ «да»/«нет» и дата применения).
Чтобы не потерять строки при одновременной записи, файл всегда пишется целиком во временный файл и подменяется атомарно
(`os.replace`), а сторож перечитывает файл прямо перед записью.

Команды (из папки Скрипты):
    python guard_signals.py list --client ProfiMet [--open]
    python guard_signals.py answer 3 да  --client ProfiMet [--applied 2026-11-06]
    python guard_signals.py answer 3 нет --client ProfiMet
    python guard_signals.py answer 3 да  --client ProfiMet --applied 2026-11-06     # дату применения можно дописать позже
Номер — «С-003» или просто 3. Ответ «да» только фиксирует решение: запись в кабинет идёт отдельно по протоколу
«таблица плана → «да» → запись → чтение обратно». Эффект сторож посчитает сам через N чистых дней после даты применения.
"""
import argparse
import csv
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "Клиенты"
COLUMNS = ["id", "date", "campaign_id", "campaign", "type", "lever", "lever_from", "lever_to", "clean_days", "median_share",
           "budget", "lost_budget_is", "leads_hist", "cost_hist", "cpl_hist", "target", "p_campaign", "p_pooled", "gate",
           "cost_3d", "leads_3d", "status", "answer_date", "applied_date", "last_reminder", "effect"]
TYPE_RAISE = "недобор_поднять"
TYPE_UNCONFIRMED = "недобор_цена_не_подтверждена"
# статусы: предложено → да | нет → закрыт (эффект измерен или сигнал снят); справка — только запись без предложения
ST_OFFERED, ST_YES, ST_NO, ST_CLOSED, ST_INFO = "предложено", "да", "нет", "закрыт", "справка"


def path_for(client, plan=False):
    return CLIENTS_DIR / client / "Статистика" / ("guard_signals_plan.csv" if plan else "guard_signals.csv")


def load(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def save(path, rows):
    """Атомарная запись: временный файл рядом + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".guard_signals_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in COLUMNS})
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def next_id(rows):
    n = 0
    for r in rows:
        try:
            n = max(n, int(str(r.get("id", "")).split("-")[-1]))
        except ValueError:
            pass
    return f"С-{n + 1:03d}"


def norm_id(x):
    s = str(x).strip()
    return f"С-{int(s.split('-')[-1]):03d}"


def is_open_raise(r):
    """Предложение поднять рычаг, по которому ещё нет итога: без ответа или «да» без измеренного эффекта."""
    return r.get("type") == TYPE_RAISE and r.get("status") in (ST_OFFERED, ST_YES)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list")
    pl.add_argument("--client", required=True)
    pl.add_argument("--open", action="store_true", help="только предложения без итога")
    pl.add_argument("--plan", action="store_true", help="файл пробного прогона (guard_signals_plan.csv)")
    pa = sub.add_parser("answer")
    pa.add_argument("id")
    pa.add_argument("answer", choices=["да", "нет"])
    pa.add_argument("--client", required=True)
    pa.add_argument("--applied", help="дата применения в кабинете ГГГГ-ММ-ДД (для «да»)")
    a = ap.parse_args()
    path = path_for(a.client, getattr(a, "plan", False))
    rows = load(path)
    if a.cmd == "list":
        for r in rows:
            if a.open and not is_open_raise(r):
                continue
            print(f"{r['id']} {r['date']} {r['campaign']} | {r['type']} | {r['lever']} {r['lever_from']}→{r['lever_to']} | "
                  f"статус {r['status']} ответ {r['answer_date'] or '—'} применено {r['applied_date'] or '—'} | {r['effect'][:120]}")
        if not rows:
            print("(пусто)")
        return
    sid = norm_id(a.id)
    row = next((r for r in rows if r["id"] == sid), None)
    if not row:
        sys.exit(f"сигнал {sid} не найден в {path}")
    if row["type"] != TYPE_RAISE:
        sys.exit(f"{sid}: это запись «{row['type']}», на неё отвечать нечем (предложения не было)")
    if row["status"] == ST_CLOSED:
        sys.exit(f"{sid}: сигнал уже закрыт ({row['effect'][:80]}), ответ не меняю")
    if a.answer == "нет":
        row["status"], row["answer_date"] = ST_NO, row["answer_date"] or date.today().isoformat()
    else:
        row["status"], row["answer_date"] = ST_YES, row["answer_date"] or date.today().isoformat()
        if a.applied:
            date.fromisoformat(a.applied)   # проверка формата
            row["applied_date"] = a.applied
    save(path, rows)
    print(f"{sid} {row['campaign']}: статус «{row['status']}», ответ {row['answer_date']}, применено {row['applied_date'] or '—'}")
    if row["status"] == ST_YES and not row["applied_date"]:
        print("дата применения не указана: эффект сторож не считает, пока она не записана (--applied ГГГГ-ММ-ДД)")


if __name__ == "__main__":
    main()
