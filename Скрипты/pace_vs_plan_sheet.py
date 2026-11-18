#!/usr/bin/env python
# coding: utf-8
"""Темп к плану -> листы Google Таблицы дашборда ProfiMet. По умолчанию НИЧЕГО не пишет (печатает план листов и диапазонов).

Зачем: результат pace_vs_plan.py (план месяца, факт, план на дату с весом выходных, прогноз, допустимая цена заявки)
видеть в той же таблице, что дашборд, с графиками. Расчёт не дублируется: берётся pace_vs_plan.run().

Листы (только свои; «Дашборд», «Заявки», «Данные» и прочие не трогаются):
  «Темп к плану»  — A1:C2.. шапка, таблица A6:C36 (фиксированная раскладка строк: показатель | значение | источник и срез),
                    B2 = дата данных (последний завершённый день), B3 = время обновления, A38:A.. предупреждения;
                    три графика справа (колонка E): накопленный расход, накопленные заявки, цена заявки по дням.
  «Темп_по_дням»  — плоская таблица A1:J<дней месяца+1>: по строке на каждый день месяца.
Графики пересоздаются при каждой записи (удаляются только свои, по названию); другие графики не трогаются.

Режимы:
  без флагов        — считает (чтение Google Ads / Supabase / Ringostat / Цели2) и печатает, что напишет; в таблицу не пишет;
  --update-sheet [ID] — пишет листы и графики, читает обратно диапазон значений и печатает «было -> стало» по ключевым ячейкам.
Использование (из папки Скрипты, PYTHONUTF8=1):
    python pace_vs_plan_sheet.py --customer-id 7552781705 --client-folder ProfiMet [--month ГГГГ-ММ] [--today ГГГГ-ММ-ДД]
                                 [--weeks 6] [--weekend-weight X] [--update-sheet [ID]]
Таблица по умолчанию — дашборд ProfiMet (DASHBOARD_SHEET_ID из profimet_sources_dashboard.py), сервисный аккаунт из _config.py.
Создан 2026-11-16.
"""
import sys
from datetime import date, datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")

import pace_vs_plan as P  # noqa: E402

DASHBOARD_SHEET_ID = "1yQ4YnDv0M_XjXFt2XQLf0wZfLqCJYJ7mC_kCtA-8xAk"  # как в profimet_sources_dashboard.py
S_MAIN, S_DAY = "Темп к плану", "Темп_по_дням"
DAY_HEAD = ["Дата", "День недели", "Расход", "Заявки", "Цена заявки", "Расход накопленный, факт", "Расход накопленный, план",
            "Заявки накопленные, факт", "Заявки накопленные, план", "Допустимая цена заявки"]
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
CHARTS = {  # название -> (столбец факта, столбец плана/линии, подпись оси Y)
    "Расход накопленный: факт и план": (5, 6, "Расход, $"),
    "Заявки накопленные: факт и план": (7, 8, "Заявки, шт."),
    "Цена заявки по дням и допустимая цена": (4, 9, "Цена заявки, $"),
}
FIRST_ROW = 7   # первая строка таблицы показателей (фиксировано)


def num(v):
    return None if v is None else round(float(v), 4)


def pct(a, b):
    return round(a / b - 1, 4) if b else None


def build(r):
    """-> (строки таблицы показателей [(показатель, значение, источник)], строки по дням)."""
    first, last, done_end, today = r["first"], r["last"], r["done_end"], r["today"]
    sp, ld, ws, wl = r["spend"], r["leads"], r["ws"], r["wl"]
    per, plan_src, wl_note = r["per"], r["plan_src"], r["wl_note"]
    spent, got = r["spent"], r["got"]
    s_src = f"{r['src_cost']}; завершённые дни {per}, сегодня не входит"
    l_src = f"{r['src_leads']}; {per}"
    wts = f"план × вес выходных (будни 1.0); {wl_note}"
    rows = [
        ("План месяца: бюджет", num(r["plan_b"]), plan_src),
        ("План месяца: заявки", num(r["plan_l"]), plan_src),
        ("План месяца: цена заявки", num(r["plan_cpa"]), plan_src),
        ("Факт на дату: расход", num(spent), s_src),
        ("Факт на дату: заявки", got, l_src),
        ("Факт на дату: цена заявки", num(r["cpa_fact"]) if got else None, f"расход / заявки, {per}"),
        ("План на дату: расход (с весом выходных)", num(r["exp_s"]), f"{wts}; взвешенных дней всего {r['Ws_tot']:.2f}"),
        ("Расход: отставание(-)/опережение(+), $ (с весом)", num(spent - r["exp_s"]), f"факт - план на дату с весом"),
        ("Расход: отставание/опережение, % (с весом)", pct(spent, r["exp_s"]), "факт / план на дату с весом - 1"),
        ("План на дату: заявки (с весом выходных)", num(r["exp_l"]), f"{wts}; взвешенных дней всего {r['Wl_tot']:.2f}"),
        ("Заявки: отставание(-)/опережение(+), шт. (с весом)", num(got - r["exp_l"]), "факт - план на дату с весом"),
        ("Заявки: отставание/опережение, % (с весом)", pct(got, r["exp_l"]), "факт / план на дату с весом - 1"),
        ("Для сравнения, по календарным дням: план расхода на дату", num(r["cal_s"]), f"план бюджета × {r['elapsed']}/{r['dim']}, как state_digest"),
        ("Для сравнения: расход, отставание(-)/опережение(+), $", num(spent - r["cal_s"]), "факт - календарный план"),
        ("Для сравнения: расход, %", pct(spent, r["cal_s"]), "факт / календарный план - 1"),
        ("Для сравнения, по календарным дням: план заявок на дату", num(r["cal_l"]), f"план заявок × {r['elapsed']}/{r['dim']}"),
        ("Для сравнения: заявки, отставание(-)/опережение(+), шт.", num(got - r["cal_l"]), "факт - календарный план"),
        ("Для сравнения: заявки, %", pct(got, r["cal_l"]), "факт / календарный план - 1"),
        ("Прогноз закрытия месяца: расход", num(r["fc_s"]), "факт / взвешенные будни прошло × всего; текущий темп"),
        ("Прогноз закрытия месяца: заявки", num(r["fc_l"]), "факт / взвешенные будни прошло × всего; текущий темп"),
        ("Прогноз закрытия месяца: цена заявки", num(r["fc_cpa"]) if r["fc_l"] else None, "прогноз расхода / прогноз заявок"),
        ("Нужный расход в будний день до конца месяца", num(r["need_day_b"]), f"(план бюджета - факт) / взвешенные будни {today}..{last}"),
        ("Нужно заявок в будний день до конца месяца", num(r["need_day_l"]), "(план заявок - факт) / взвешенные будни по заявкам"),
        ("Допустимая цена заявки в будний день на остаток", num(r["allowed"]), "нужный расход в будний день / нужные заявки в будний день; пусто, если план заявок выполнен или бюджет исчерпан"),
        ("Вес выходных: расход", num(ws), f"среднее выходного дня / будничного; окно {r['w_start']}..{r['w_end']} ({r['weeks']} нед.)"),
        ("Вес выходных: заявки", num(wl), "то же окно"),
        ("Справочно: расход, суббота", num(r["sa_s"]), "в расчёте не участвует"),
        ("Справочно: расход, воскресенье", num(r["su_s"]), "в расчёте не участвует"),
        ("Справочно: заявки, суббота", num(r["sa_l"]), "в расчёте не участвует"),
        ("Справочно: заявки, воскресенье", num(r["su_l"]), "в расчёте не участвует"),
    ]
    # по дням
    days, cs, cl = [], 0.0, 0
    Ws_tot, Wl_tot = r["Ws_tot"], r["Wl_tot"]
    allowed = r["allowed"] if r["allowed"] is not None else r["plan_cpa"]
    d, cps, cpl = first, 0.0, 0.0
    while d <= last:
        cps += P.day_w(ws, d)
        cpl += P.day_w(wl, d)
        fact = d <= done_end
        if fact:
            cs += sp.get(d, 0.0)
            cl += ld.get(d, 0)
        s_d, l_d = sp.get(d, 0.0), ld.get(d, 0)
        days.append([d.isoformat(), WD[d.weekday()],
                     num(s_d) if fact else None, l_d if fact else None,
                     num(s_d / l_d) if fact and l_d else None,
                     num(cs) if fact else None, num(r["plan_b"] * cps / Ws_tot),
                     cl if fact else None, num(r["plan_l"] * cpl / Wl_tot), num(allowed)])
        d += timedelta(days=1)
    return rows, days


def plan_text(r, rows, days, sheet_id):
    n = len(days)
    last_row = FIRST_ROW + len(rows) - 1
    warns = r["warns"]
    out = [f"Таблица: https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
           f"Листы (создать, если нет; существующие свои перезаписать; остальные не трогать): «{S_MAIN}», «{S_DAY}»",
           f"«{S_MAIN}»: A1 заголовок; A2:B2 дата данных = {r['done_end']}; A3:B3 время обновления; "
           f"A6:C6 шапка; A{FIRST_ROW}:C{last_row} ({len(rows)} показателей: показатель | значение | источник и срез); "
           f"A{last_row + 2}:A{last_row + 1 + len(warns)} предупреждения ({len(warns)})",
           f"«{S_DAY}»: A1:J1 шапка; A2:J{n + 1} ({n} дней {r['first']}..{r['last']}; факт до {r['done_end']}, дальше только план)",
           f"Графики на «{S_MAIN}» (удалить свои с теми же названиями и создать заново): " + "; ".join(f"«{t}»" for t in CHARTS),
           "", "Показатели (значение):"]
    for i, (k, v, s) in enumerate(rows):
        out.append(f"  B{FIRST_ROW + i:<3} {k}: {v}")
    out.append("")
    out.append("По дням (первые 3 и день данных):")
    for dd in days[:3] + [x for x in days if x[0] == r["done_end"].isoformat()]:
        out.append("  " + " | ".join("" if v is None else str(v) for v in dd))
    return "\n".join(out)


def write_sheet(sheet_id, r, rows, days):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials
    from _config import SERVICE_ACCOUNT_FILE
    from zoneinfo import ZoneInfo
    s = AuthorizedSession(Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"

    def meta():
        return s.get(base + "?fields=sheets(properties(sheetId,title),charts(chartId,spec(title)))", timeout=60).json()["sheets"]

    sheets = meta()
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in sheets}
    need = [n for n in (S_MAIN, S_DAY) if n not in ids]
    if need:
        s.post(base + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": n}}} for n in need]}, timeout=60).raise_for_status()
        sheets = meta()
        ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in sheets}
    sid_m, sid_d = ids[S_MAIN], ids[S_DAY]

    # было (ключевые ячейки)
    def read(rng):
        return s.get(base + f"/values/{rng}?valueRenderOption=UNFORMATTED_VALUE", timeout=60).json().get("values", [])
    before = {x[0]: x[1] for x in read(f"{S_MAIN}!A{FIRST_ROW}:B{FIRST_ROW + len(rows) - 1}") if len(x) > 1}

    n, last_row = len(days), FIRST_ROW + len(rows) - 1
    now = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%d.%m.%Y %H:%M")
    for sh, rng in ((S_MAIN, "A1:C39"), (S_DAY, "A1:J400")):  # ниже строки 40 — блок «Продажи» от sales_pace.py, его не стираем
        s.post(base + f"/values/{sh}!{rng}:clear", json={}, timeout=60).raise_for_status()
    data = [
        {"range": f"{S_MAIN}!A1", "values": [[f"ProfiMet: темп к плану месяца {r['first']:%Y-%m} (скрипт pace_vs_plan_sheet.py)"]]},
        {"range": f"{S_MAIN}!A2:B3", "values": [["Дата данных (последний завершённый день)", r["done_end"].isoformat()], ["Обновлено (Варшава)", now]]},
        {"range": f"{S_MAIN}!A4", "values": [["Раскладка строк фиксирована. Будни = 1.0, выходные = вес выходных. Цена заявки, расход - $."]]},
        {"range": f"{S_MAIN}!A6:C6", "values": [["Показатель", "Значение", "Источник и срез"]]},
        {"range": f"{S_MAIN}!A{FIRST_ROW}", "values": [[k, v, src] for k, v, src in rows]},
        {"range": f"{S_MAIN}!A{last_row + 2}", "values": [["Предупреждение: " + w] for w in r["warns"]] or [["Предупреждений нет"]]},
        {"range": f"{S_DAY}!A1", "values": [DAY_HEAD] + days},
    ]
    s.post(base + "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data}, timeout=120).raise_for_status()

    rg = lambda sid, r0, r1, c0, c1: {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}
    bold = {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.867, "green": 0.922, "blue": 0.969}}}
    req = []
    # удалить свои графики
    for x in sheets:
        if x["properties"]["sheetId"] == sid_m:
            for c in x.get("charts", []):
                if c.get("spec", {}).get("title") in CHARTS:
                    req.append({"deleteEmbeddedObject": {"objectId": c["chartId"]}})
    pc = lambda a, b, c, d, f: {"repeatCell": {"range": rg(a, b, c, d, d + 1), "cell": {"userEnteredFormat": {"numberFormat": f}}, "fields": "userEnteredFormat.numberFormat"}}
    req += [
        {"repeatCell": {"range": rg(sid_m, 5, 6, 0, 3), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"repeatCell": {"range": rg(sid_d, 0, 1, 0, 10), "cell": bold, "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"repeatCell": {"range": rg(sid_m, 0, 1, 0, 1), "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}}, "fields": "userEnteredFormat.textFormat"}},
        pc(sid_m, 1, 2, 1, {"type": "DATE", "pattern": "dd.mm.yyyy"}),
        pc(sid_d, 1, n + 1, 0, {"type": "DATE", "pattern": "dd.mm.yyyy"}),
        {"updateSheetProperties": {"properties": {"sheetId": sid_d, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid_m, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 380}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid_m, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2}, "properties": {"pixelSize": 110}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid_m, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3}, "properties": {"pixelSize": 420}, "fields": "pixelSize"}},
    ]
    # проценты (строки с «%» в названии) и числа
    for i, (k, v, _s) in enumerate(rows):
        row0 = FIRST_ROW - 1 + i
        if "%" in k:
            fmt = {"type": "PERCENT", "pattern": "0%"}
        elif "Вес выходных" in k or k.startswith("Справочно"):
            fmt = {"type": "NUMBER", "pattern": "0.00"}
        elif "заявок в будний" in k or "Заявки:" in k or "план заявок" in k or "заявки (с весом" in k or "Прогноз закрытия месяца: заявки" in k:
            fmt = {"type": "NUMBER", "pattern": "0.0"}
        else:
            fmt = {"type": "NUMBER", "pattern": "0"}
        req.append(pc(sid_m, row0, row0 + 1, 1, fmt))
    # графики
    for k, (t, (cf, cp, ytitle)) in enumerate(CHARTS.items()):
        src = lambda col: {"sourceRange": {"sources": [rg(sid_d, 0, n + 1, col, col + 1)]}}
        req.append({"addChart": {"chart": {"spec": {
            "title": t,
            "basicChart": {
                "chartType": "LINE", "legendPosition": "BOTTOM_LEGEND", "headerCount": 1,
                "axis": [{"position": "BOTTOM_AXIS", "title": "День месяца"}, {"position": "LEFT_AXIS", "title": ytitle}],
                "domains": [{"domain": {"sourceRange": {"sources": [rg(sid_d, 0, n + 1, 0, 1)]}}}],
                "series": [{"series": src(cf), "targetAxis": "LEFT_AXIS"}, {"series": src(cp), "targetAxis": "LEFT_AXIS"}],
            }},
            "position": {"overlayPosition": {"anchorCell": {"sheetId": sid_m, "rowIndex": 1 + 20 * k, "columnIndex": 4},
                                              "widthPixels": 640, "heightPixels": 360}}}}})
    s.post(base + ":batchUpdate", json={"requests": req}, timeout=60).raise_for_status()

    after = {x[0]: x[1] for x in read(f"{S_MAIN}!A{FIRST_ROW}:B{last_row}") if len(x) > 1}
    print("Прочитано обратно (было -> стало), ключевые ячейки:")
    for k in ("Факт на дату: расход", "Факт на дату: заявки", "Прогноз закрытия месяца: расход", "Прогноз закрытия месяца: заявки",
              "Допустимая цена заявки в будний день на остаток"):
        print(f"  {k}: {before.get(k, '(пусто)')} -> {after.get(k, '(пусто)')}")
    print(f"Строк показателей записано: {len(after)} из {len(rows)}; строк по дням: {n}; графиков создано: {len(CHARTS)}")


def main():
    ap = P.build_parser()
    ap.description = "Темп к плану -> листы Google Таблицы дашборда (по умолчанию ничего не пишет)"
    ap.add_argument("--update-sheet", nargs="?", const=DASHBOARD_SHEET_ID, default=None, metavar="ID",
                    help="записать листы «Темп к плану» и «Темп_по_дням» с графиками (по умолчанию — таблица дашборда ProfiMet)")
    a = ap.parse_args()
    r = P.run(a)
    rows, days = build(r)
    sheet_id = a.update_sheet or DASHBOARD_SHEET_ID
    print("\n=== Выгрузка в Google Таблицу: " + ("ЗАПИСЬ" if a.update_sheet else "план (в таблицу НЕ пишу, нужен --update-sheet)") + " ===")
    print(plan_text(r, rows, days, sheet_id))
    if a.update_sheet:
        write_sheet(sheet_id, r, rows, days)


if __name__ == "__main__":
    main()
