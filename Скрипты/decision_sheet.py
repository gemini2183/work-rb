"""Таблица для принятия решений (Google Sheets): создать, прочитать статусы, обновить по ответам.

Один универсальный инструмент вместо разовых скриптов. Вводные - JSON-файлы, код не меняется.
Концепция и демо: Клиенты/.. не привязано; демо-таблица в Drive (инфобокс), спецификация -
Скрипты/decision_sheet_example_spec.json.

Команды:
  create   --spec spec.json --into URL|ID [--dry-run]   (--into: пустая таблица, открытая сервисному аккаунту редактором;
           сам он файлы создавать не может - 403 storage quota)
           создаёт таблицу: листы из spec + лист «Доска» (формулы-сводка), форматирование, выпадающий статус
  read     --sheet URL|ID [--tab План] [--all]
           печатает компактно: по каждой строке № / ключевые поля / статус / комментарий / раунд.
           По умолчанию только то, что требует моей реакции: статус «правка» и «нет» с комментарием,
           плюс счётчики и вердикт «можно записывать». --all - все строки.
  update   --sheet URL|ID --file updates.json
           [{"tab":"План","no":2,"set":{"Станет":"..","Ответ Claude":".."},"round_up":true}]
           строка ищется по колонке «№»; поля - по имени заголовка. При round_up раунд +1 и статус
           очищается (ждём нового решения пользователя), если "Ваш статус" не задан в set.
  add-rows --sheet URL|ID --tab План --file rows.json
           дописать строки: [{"Объект":"..","Станет":".."}, ...]; № и формулы ({r} = номер строки) заполняются сами.

Ключ сервисного аккаунта: DECISION_SHEET_KEY, иначе secrets/decision_sheet_service.json, иначе существующий
secrets/rb_cloud_service.json (rb-cloud-admin; _config.py берёт его только на чтение, здесь - со scope на запись).

Формат spec.json - см. decision_sheet_example_spec.json. Запись в таблицу - не запись в рекламный кабинет;
решения из таблицы в кабинет попадают только по протоколу «да» в чате.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

STATUS_OK = "ок"
STATUS_EDIT = "правка"
STATUS_NO = "нет"
NO_COL, STATUS_COL, COMMENT_COL, ANSWER_COL, ROUND_COL = "№", "Ваш статус", "Комментарий", "Ответ Claude", "Раунд"
MAX_ROWS = 1000

KEY_DEFAULT = Path(__file__).parent / "secrets" / "decision_sheet_service.json"
KEY_FALLBACK = Path(__file__).parent / "secrets" / "rb_cloud_service.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

C_HEAD = (0.12, 0.23, 0.37)
C_USER = (1.0, 0.96, 0.80)
C_CLAUDE = (0.89, 0.94, 1.0)
C_OK = (0.78, 0.94, 0.81)
C_EDIT = (1.0, 0.92, 0.61)
C_NO = (0.96, 0.78, 0.76)
WHITE = (1, 1, 1)


def _rgb(t):
    return {"red": t[0], "green": t[1], "blue": t[2]}


def col_letter(i: int) -> str:  # 0-based -> A, B, ...
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def sheet_id_from(arg: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", arg)
    return m.group(1) if m else arg


def client():
    import gspread
    from google.oauth2.service_account import Credentials

    key = Path(os.environ.get("DECISION_SHEET_KEY", KEY_DEFAULT))
    if not key.exists():
        key = KEY_FALLBACK  # существующий сервисный аккаунт агентства (rb-cloud-admin)
    if not key.exists():
        sys.exit(f"Нет ключа сервисного аккаунта: {key}. Положите json туда или задайте DECISION_SHEET_KEY.")
    return gspread.authorize(Credentials.from_service_account_file(str(key), scopes=SCOPES))


# ---------------------------------------------------------------- create
def localize(f, ss):
    """В таблицах с русской локалью разделитель аргументов формулы - «;», иначе #ERROR!. Запятые вне кавычек меняем."""
    if not (isinstance(f, str) and f.startswith("=")) or not str(getattr(ss, "locale", "")).startswith(("ru", "uk", "de", "fr", "es", "pl")):
        return f
    out, q = [], False
    for ch in f:
        if ch == '"':
            q = not q
        out.append(";" if ch == "," and not q else ch)
    return "".join(out)


def state_formula(r: int, s: str, a: str) -> str:
    """Колонка «Состояние»: что с пунктом и чей ход. Статус ставит пользователь; Claude после ответа статус очищает."""
    return (f'=IF({s}{r}="ок","✅ утверждено",IF({s}{r}="нет","✖ снято с плана",IF({s}{r}="правка","⏳ Claude переделывает",'
            f'IF({a}{r}<>"","💬 Claude ответил, ждёт вас","❓ ждёт вашего решения"))))')


# ---------------------------------------------------------------- read / update helpers
def _grid(ws):
    values = ws.get_all_values()
    if not values:
        return [], []
    return values[0], values[1:]


def cmd_read(a):
    gc = client()
    ss = gc.open_by_key(sheet_id_from(a.sheet))
    tabs = [ws for ws in ss.worksheets() if ws.title not in ("Доска", "Как работать")]
    if a.tab:
        tabs = [ws for ws in tabs if ws.title == a.tab]
    total = {STATUS_OK: 0, STATUS_EDIT: 0, STATUS_NO: 0, "": 0}
    out = []
    for ws in tabs:
        headers, rows = _grid(ws)
        if STATUS_COL not in headers:
            continue
        si, ci, ri, ni, ai = (headers.index(x) if x in headers else None for x in (STATUS_COL, COMMENT_COL, ROUND_COL, NO_COL, ANSWER_COL))
        keyi = [i for i, h in enumerate(headers) if h not in (NO_COL, STATUS_COL, COMMENT_COL, ANSWER_COL, ROUND_COL, "Записано")][:3]
        for r in rows:
            r = r + [""] * (len(headers) - len(r))
            if not any(r):
                continue
            st = r[si].strip().lower()
            total[st if st in total else ""] += 1
            answered = ai is not None and r[ai].strip() != ""
            if a.all or st in (STATUS_EDIT, "") or (st == STATUS_NO and not answered):
                key = " | ".join(r[i] for i in keyi if r[i])[:160]
                line = f"[{ws.title} №{r[ni]}] {st or 'нет ответа'} (раунд {r[ri] if ri is not None else '-'}): {key}"
                if ci is not None and r[ci].strip():
                    line += f"\n    ваш комментарий: {r[ci].strip()}"
                out.append(line)
    print("\n".join(out) if out else "(строк, требующих реакции, нет)")
    open_n = total[STATUS_EDIT] + total[""]
    print(f"\nИтого: ок {total[STATUS_OK]}, правка {total[STATUS_EDIT]}, нет {total[STATUS_NO]}, без ответа {total['']}")
    print("ВЕРДИКТ: можно записывать (ждём «да» в чате)" if open_n == 0 else f"ВЕРДИКТ: не готово, открыто {open_n}")


def cmd_update(a):
    gc = client()
    ss = gc.open_by_key(sheet_id_from(a.sheet))
    updates = json.loads(Path(a.file).read_text(encoding="utf-8"))
    cache = {}
    by_ws = {}
    for u in updates:
        ws = cache.get(u["tab"]) or ss.worksheet(u["tab"])
        cache[u["tab"]] = ws
        if ws.title not in by_ws:
            by_ws[ws.title] = (ws, *_grid(ws))
    for title, (ws, headers, rows) in by_ws.items():
        batch = []
        ni = headers.index(NO_COL)
        for u in (x for x in updates if x["tab"] == title):
            rn = next((i for i, r in enumerate(rows) if len(r) > ni and str(r[ni]).strip() == str(u["no"])), None)
            if rn is None:
                sys.exit(f"{title}: строки с № {u['no']} нет")
            row_num = rn + 2
            row = rows[rn] + [""] * (len(headers) - len(rows[rn]))
            sets = dict(u.get("set", {}))
            if u.get("round_up"):
                ri = headers.index(ROUND_COL)
                try:
                    sets[ROUND_COL] = int(row[ri] or 1) + 1
                except ValueError:
                    sets[ROUND_COL] = 2
                sets.setdefault(STATUS_COL, "")
            for h, v in sets.items():
                if h not in headers:
                    sys.exit(f"{title}: нет колонки «{h}»")
                batch.append({"range": f"{col_letter(headers.index(h))}{row_num}", "values": [[v]]})
        ws.batch_update(batch, value_input_option="USER_ENTERED")
        print(f"{title}: обновлено ячеек {len(batch)}")


def cmd_add_rows(a):
    gc = client()
    ws = gc.open_by_key(sheet_id_from(a.sheet)).worksheet(a.tab)
    headers, rows = _grid(ws)
    new = json.loads(Path(a.file).read_text(encoding="utf-8"))
    start = len(rows) + 2
    nums = [r[headers.index(NO_COL)] for r in rows if len(r) > headers.index(NO_COL) and str(r[headers.index(NO_COL)]).isdigit()]
    nxt = max(map(int, nums), default=0) + 1
    out = []
    for k, rec in enumerate(new):
        r = start + k
        row = []
        for h in headers:
            v = rec.get(h, "")
            if h == NO_COL and v == "":
                v, nxt = nxt, nxt + 1
            if h == ROUND_COL and v == "":
                v = 1
            if isinstance(v, str) and v.startswith("="):
                v = v.replace("{r}", str(r))
            row.append(v)
        out.append(row)
    ws.append_rows(out, value_input_option="USER_ENTERED", table_range="A1")
    print(f"{a.tab}: добавлено строк {len(out)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("create")
    c.add_argument("--spec", required=True)
    c.add_argument("--share")
    c.add_argument("--folder-id")
    c.add_argument("--into", help="URL/ID пустой таблицы, открытой для сервисного аккаунта (создание с нуля у него не работает)")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(f=cmd_create)
    r = sp.add_parser("read")
    r.add_argument("--sheet", required=True)
    r.add_argument("--tab")
    r.add_argument("--all", action="store_true")
    r.set_defaults(f=cmd_read)
    u = sp.add_parser("update")
    u.add_argument("--sheet", required=True)
    u.add_argument("--file", required=True)
    u.set_defaults(f=cmd_update)
    ar = sp.add_parser("add-rows")
    ar.add_argument("--sheet", required=True)
    ar.add_argument("--tab", required=True)
    ar.add_argument("--file", required=True)
    ar.set_defaults(f=cmd_add_rows)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
