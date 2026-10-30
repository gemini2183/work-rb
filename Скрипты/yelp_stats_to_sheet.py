"""Yelp (LuxeBrokers): суточные показы/клики из снимка страницы Ad performance -> Google-таблица «Yelp - Stats».

Снимок делает `yelp_chart_capture.js` (в Chrome, на странице Ad performance); результат кладётся в
`Клиенты/LuxeBrokers/Статистика/yelp_daily_<дата>.json`. Скрипт:
  1. сверяет сумму показов и кликов по дням месяца с итогом месяца из таблицы кабинета Yelp (не сошлось - стоп);
  2. берёт среднюю цену клика месяца из той же таблицы кабинета и ставит её во все дни этого месяца;
  3. по датам находит строки в таблице, показывает план (было -> станет), по --execute пишет и читает обратно.

Колонки листа: A Date, B Impressions, C Clicks, D Leads (НЕ трогаем), E Avg CPC, F Cost (=C*E).
Другие месяцы не меняются. По умолчанию - только план (режим проверки).

Запуск (из Скрипты/):
    PYTHONUTF8=1 python yelp_stats_to_sheet.py --data ../Клиенты/LuxeBrokers/Статистика/yelp_daily_2026-10-30.json
    ... --execute        # записать
"""
import argparse
import json
import re
import sys
from datetime import date, datetime

import gspread
from google.oauth2.service_account import Credentials

from _config import SERVICE_ACCOUNT_FILE

DEFAULT_SHEET_ID = "1atdJiyIN4vpSdY-o5De3ontsSOtRg0JQ-Fii-FihFNA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
EPOCH = date(1899, 12, 30)  # нулевая дата серийных номеров Google Sheets
MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def serial(d: date) -> int:
    return (d - EPOCH).days


def load_capture(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    days = {}
    for item in raw["days"].split(";"):
        d, imp, clk = item.split(",")
        days[datetime.strptime(d, "%Y-%m-%d").date()] = (int(imp), int(clk))
    return {"days": days, "periods": raw["periods"]}


def month_period(periods: list, year: int, month: int) -> dict:
    """Строка таблицы кабинета для месяца: период вида «Oct 1 - Oct 29, 2026»."""
    for p in periods:
        m = re.match(r"([A-Z][a-z]{2}) (\d+) - ([A-Z][a-z]{2}) (\d+), (\d{4})$", p["period"])
        if m and MON[m.group(1)] == month and int(m.group(2)) == 1 and int(m.group(5)) == year:
            return p
    raise SystemExit(f"В снимке нет итога месяца {year}-{month:02d} (строка «... 1 - ..., {year}»)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="JSON со снимка yelp_chart_capture.js")
    ap.add_argument("--month", help="ГГГГ-ММ; по умолчанию месяц последнего дня в снимке")
    ap.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    ap.add_argument("--execute", action="store_true", help="записать в таблицу (без флага - только план)")
    a = ap.parse_args()

    cap = load_capture(a.data)
    last = max(cap["days"])
    year, month = (int(x) for x in a.month.split("-")) if a.month else (last.year, last.month)
    days = {d: v for d, v in sorted(cap["days"].items()) if d.year == year and d.month == month}
    if not days:
        raise SystemExit("В снимке нет дней выбранного месяца")

    # 1. Сверка с итогом кабинета
    per = month_period(cap["periods"], year, month)
    sum_imp = sum(v[0] for v in days.values())
    sum_clk = sum(v[1] for v in days.values())
    print(f"Сверка с кабинетом Yelp ({per['period']}): показы {sum_imp} против {per['impressions']}, "
          f"клики {sum_clk} против {per['clicks']}")
    if sum_imp != per["impressions"] or sum_clk != per["clicks"]:
        raise SystemExit("СТОП: сумма по дням не равна итогу кабинета - снимок неполный или график сдвинулся. В таблицу не пишу.")
    avg_cpc = per["avg_cpc"]
    print(f"Средняя цена клика месяца (кабинет): {avg_cpc} $; расход по кабинету {per['spend']} $ "
          f"(в таблице будет {sum_clk * avg_cpc:.2f} $ - разница от округления цены клика)")

    # 2. Текущее состояние таблицы
    gc = gspread.authorize(Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES))
    sh = gc.open_by_key(a.sheet_id)
    ws = sh.sheet1
    cur = ws.get("A1:F", value_render_option="UNFORMATTED_VALUE")
    cur_f = ws.get("A1:F", value_render_option="FORMULA")
    if [str(c).strip() for c in cur[0][:6]] != ["Date", "Impressions", "Clicks", "Leads", "Avg CPC", "Cost"]:
        raise SystemExit(f"СТОП: заголовок листа изменился: {cur[0]}")
    rows = {}  # serial -> номер строки
    for i, r in enumerate(cur[1:], start=2):
        if r and isinstance(r[0], (int, float)):
            rows[int(r[0])] = i
    n_rows = len(cur)

    def cell(r, c, src=cur):
        row = src[r - 1] if r - 1 < len(src) else []
        return row[c] if c < len(row) else ""

    # 3. План
    plan = []      # (строка, дата, поле, было, станет)
    writes = []    # (A1-адрес, значение)
    new_rows = []
    next_row = n_rows + 1
    for d, (imp, clk) in days.items():
        r = rows.get(serial(d))
        if r is None:
            r = next_row
            next_row += 1
            new_rows.append(r)
            plan.append((r, d, "A (дата)", "", d.strftime("%d.%m.%Y")))
            writes.append((f"A{r}", serial(d)))
        for col, name, new in (("B", "Impressions", imp), ("C", "Clicks", clk), ("E", "Avg CPC", avg_cpc)):
            old = cell(r, "ABCDEF".index(col))
            if old != new:
                plan.append((r, d, f"{col} ({name})", old, new))
                writes.append((f"{col}{r}", new))
        want_f = f"=C{r}*E{r}"
        old_f = cell(r, 5, cur_f)
        if old_f != want_f:
            plan.append((r, d, "F (Cost)", old_f, want_f))
            writes.append((f"F{r}", want_f))

    print(f"\nПлан по таблице «{sh.title}», месяц {year}-{month:02d} (D/Leads не трогаю):")
    if not plan:
        print("  изменений нет - таблица уже совпадает со снимком")
    for r, d, field, old, new in plan:
        print(f"  строка {r:>3}  {d:%d.%m.%Y}  {field:<16} {old!s:>12} -> {new}")
    print(f"Ячеек к записи: {len(writes)}; новых строк: {len(new_rows)}")

    if not a.execute:
        print("\nРежим плана: ничего не записано. Для записи добавить --execute.")
        return
    if not writes:
        return

    # 4. Запись: у новых строк сначала копируем формат с последней существующей строки
    if new_rows:
        src = max(rows.values())
        sh.batch_update({"requests": [{"copyPaste": {
            "source": {"sheetId": ws.id, "startRowIndex": src - 1, "endRowIndex": src,
                       "startColumnIndex": 0, "endColumnIndex": 6},
            "destination": {"sheetId": ws.id, "startRowIndex": new_rows[0] - 1, "endRowIndex": new_rows[-1],
                            "startColumnIndex": 0, "endColumnIndex": 6},
            "pasteType": "PASTE_FORMAT"}}]})
    ws.batch_update([{"range": addr, "values": [[v]]} for addr, v in writes], value_input_option="USER_ENTERED")

    # 5. Чтение обратно
    back = ws.get("A1:F", value_render_option="UNFORMATTED_VALUE")
    got_imp = got_clk = 0
    got_cost = 0.0
    for d in days:
        r = next(i for i, row in enumerate(back[1:], start=2) if row and row[0] == serial(d))
        row = back[r - 1]
        got_imp += row[1]
        got_clk += row[2]
        got_cost += row[5]
    print(f"\nПрочитано обратно: показы {got_imp}, клики {got_clk}, расход {got_cost:.2f} $ "
          f"(кабинет: {per['impressions']}, {per['clicks']}, {per['spend']} $)")
    if got_imp != per["impressions"] or got_clk != per["clicks"]:
        sys.exit("ВНИМАНИЕ: после записи суммы не совпали с кабинетом - проверить таблицу вручную")
    print("OK: суммы совпали с кабинетом")


if __name__ == "__main__":
    main()
