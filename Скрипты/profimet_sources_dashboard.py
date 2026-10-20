#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: НАШ дашборд «По источникам» из выгрузки продаж CRM, Google Ads и BigQuery — ТОЛЬКО ЧТЕНИЕ.

Те же строки и колонки, что в клиентском дашборде (Источник, Цена, Клики, Показы, Цена клика, CTR, Конверсии, % конверсии,
Цена заявки, Звонки, Продажи, % продажи, Цена продажи), но все определения собственные и выписаны под таблицей. Нужен, чтобы
человек сравнил его с клиентским глазами; сами расхождения скрипт не разбирает (решение пользователя 2026-10-20).

Откуда данные и как считаем (лист `mocnaszklarnia.pl` выгрузки CRM):
  • Цена / Клики / Показы — Google Ads: из API по аккаунту (все кампании) за даты периода; Facebook: BigQuery
    `redbird-196813.adwhite.fb_stats_profimet` (в таблице хранится в долларах, пересчёт в евро — параметр `--usd-eur`).
    У «Нет метки», «Телефон», «Прочее» рекламных показателей нет.
  • Конверсии — обращения (звонки + формы) выгрузки, НОВЫЕ по правилу 60 дней: обращение новое, если у этого номера на
    этом сайте не было засчитанного нового обращения за последние 60 дней (окно считается от последнего засчитанного, повторы
    окно не продлевают — как в боевом скрипте ringostat_profimet2; в памяти все источники и формы). Источник обращения — как в выгрузке.
  • Звонки — из конверсий те, что звонки.
  • Продажи — проданные заказы (в выгрузке есть «Дата продажи» в периоде; количество товара в выгрузке нет, поэтому это заказы,
    не единицы). Источник продажи — источник ПЕРВОГО обращения этого номера за 60 дней до первой строки заказа (правило клиента).
  • % конверсии = Конверсии ÷ Клики; Цена заявки = Цена ÷ Конверсии; % продажи = Продажи ÷ Конверсии; Цена продажи = Цена ÷ Продажи;
    CTR = Клики ÷ Показы; Цена клика = Цена ÷ Клики. «Итого»: цена и показатели Google + Facebook, конверсии и продажи по всем строкам.
  • Справочно под таблицей: звонки Google/Facebook по боевому правилу Ringostat (только входящие, в памяти 4 канала) — те же, что в
    таблице агентства `ringostat_calls_profimet2`.

Использование:
    PYTHONIOENCODING=utf-8 python profimet_sources_dashboard.py [--from 2026-08-01] [--to 2026-10-19] [--by month|week]
        [--usd-eur 0.85] [--cache путь.pkl]
Пишет `Клиенты/ProfiMet/Статистика/dashboard_sources_<с>_<по>.csv`. Запускать без -I.
"""
import argparse
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE, client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_season_audit import W, fetch_ringostat_full, prod_unique

SITE = "mocnaszklarnia.pl"
ADS_CUSTOMER = "7552781705"
SOURCES = ["Google Ads", "Facebook", "Нет метки", "Телефон", "Прочее"]
WINDOW = 60


def ads_daily(frm, to):
    c = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    q = (f"SELECT segments.date, metrics.cost_micros, metrics.clicks, metrics.impressions FROM customer "
         f"WHERE segments.date BETWEEN '{frm}' AND '{to}'")
    rows = [(r.segments.date, r.metrics.cost_micros / 1e6, r.metrics.clicks, r.metrics.impressions)
            for r in c.get_service("GoogleAdsService").search(customer_id=ADS_CUSTOMER, query=q)]
    d = pd.DataFrame(rows, columns=["date", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def fb_daily(frm, to):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/bigquery"])
    c = bigquery.Client(project="redbird-196813", credentials=creds)
    q = (f"SELECT date, SUM(spend) cost, SUM(clicks) clicks, SUM(impressions) impr FROM `redbird-196813.adwhite.fb_stats_profimet` "
         f"WHERE date BETWEEN '{frm}' AND '{to}' GROUP BY date")
    d = pd.DataFrame([dict(r.items()) for r in c.query(q).result()], columns=["date", "cost", "clicks", "impr"])
    d["date"] = pd.to_datetime(d["date"]).dt.date
    return d


def contacts_with_new_flag(sheet):
    """Обращения (звонок/форма) листа с флагом «новое по правилу 60 дн» (лестница: окно от последнего засчитанного)."""
    s = sheet[(sheet["site"] == SITE) & sheet["type"].isin(["звонок", "форма"]) & (sheet["p9"] != "")].copy()
    s["src2"] = s["src"].replace("", "Нет метки")
    s.loc[~s["src2"].isin(SOURCES), "src2"] = "Прочее"
    s["day"] = s["ts"].dt.tz_convert(W).dt.date
    s = s.sort_values("ts", kind="mergesort")
    last, flags = {}, []
    for p9, day in zip(s["p9"], s["day"]):
        prev = last.get(p9)
        new = prev is None or (day - prev).days > WINDOW
        if new:
            last[p9] = day
        flags.append(new)
    s["new"] = flags
    return s


def sales_with_source(sheet):
    """Проданные заказы: дата продажи, источник первого обращения номера за 60 дн до первой строки заказа."""
    s = sheet[sheet["site"] == SITE]
    by_phone = {p: g for p, g in s.groupby("p9") if p}
    rows = []
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd:
            continue
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        parts = [by_phone[p] for p in set(grp["p9"]) if p in by_phone]
        t = pd.concat(parts) if parts else grp
        t = t[(t["ts"] >= t0 - pd.Timedelta(days=WINDOW)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        src = (t.iloc[0]["src"] if not t.empty else grp.iloc[0]["src"]) or "Нет метки"
        rows.append({"order": order, "sale_date": pd.Timestamp(min(sd)).date(), "src2": src if src in SOURCES else "Прочее"})
    return pd.DataFrame(rows)


def build(frm, to, ads, fb, contacts, sales, usd_eur):
    f, t = pd.Timestamp(frm).date(), pd.Timestamp(to).date()
    a = ads[(ads["date"] >= f) & (ads["date"] <= t)]
    b = fb[(fb["date"] >= f) & (fb["date"] <= t)]
    paid = {"Google Ads": (a["cost"].sum(), a["clicks"].sum(), a["impr"].sum()),
            "Facebook": (b["cost"].sum() * usd_eur, b["clicks"].sum(), b["impr"].sum())}
    c = contacts[contacts["new"] & (contacts["day"] >= f) & (contacts["day"] <= t)]
    sl = sales[(sales["sale_date"] >= f) & (sales["sale_date"] <= t)]
    out, notes = [], []
    for src in SOURCES:
        cost, clk, imp = paid.get(src, (None, None, None))
        cc = c[c["src2"] == src]
        conv, calls = len(cc), int((cc["type"] == "звонок").sum())
        # Структура колонок как у клиентского дашборда: конверсиями считаются Google Ads, Facebook, «Нет метки» (звонки — только
        # у Google и Facebook); перезвоны «Телефон» и «Прочее» в конверсии не входят. Убранное из колонок печатается под таблицей.
        if src in ("Телефон", "Прочее"):
            notes.append(f"{src}: новых обращений {conv} (из них звонков {calls}) — в «Конверсии» и «Звонки» не включены")
            conv = calls = None
        elif src == "Нет метки":
            notes.append(f"Нет метки: из {conv} конверсий звонков {calls} — в колонке «Звонки» не показаны")
            calls = None
        out.append({"Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": conv, "Звонки": calls,
                    "Продажи": int((sl["src2"] == src).sum())})
    df = pd.DataFrame(out)
    tot_cost = sum(v[0] for v in paid.values())
    tot = {"Источник": "Итого", "Цена": tot_cost, "Клики": sum(v[1] for v in paid.values()), "Показы": sum(v[2] for v in paid.values()),
           "Конверсии": int(df["Конверсии"].sum()), "Звонки": int(df["Звонки"].sum()), "Продажи": int(df["Продажи"].sum())}
    df = pd.concat([df, pd.DataFrame([tot])], ignore_index=True)
    df["Цена клика"] = df["Цена"] / df["Клики"]
    df["CTR %"] = df["Клики"] / df["Показы"] * 100
    df["% конверсии"] = df["Конверсии"] / df["Клики"] * 100
    df["Цена заявки"] = df["Цена"] / df["Конверсии"].where(df["Конверсии"] > 0)
    df["% продажи"] = df["Продажи"] / df["Конверсии"].where(df["Конверсии"] > 0) * 100
    df["Цена продажи"] = df["Цена"] / df["Продажи"].where(df["Продажи"] > 0)
    # «Итого»: клики/показы только Google+Facebook, поэтому % конверсии у строк без рекламы не считаем
    df.loc[df["Клики"].isna(), ["Цена клика", "CTR %", "% конверсии"]] = None
    cols = ["Источник", "Цена", "Клики", "Показы", "Цена клика", "CTR %", "Конверсии", "% конверсии", "Цена заявки", "Звонки",
            "Продажи", "% продажи", "Цена продажи"]
    df = df[cols]
    df.attrs["notes"] = notes
    return df


def show(df, title):
    print(f"\n=== {title} ===")
    fmt = df.copy()
    for c in ("Цена", "Цена клика", "Цена заявки", "Цена продажи"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:,.2f} €".replace(",", " "))
    for c in ("Клики", "Показы", "Конверсии", "Звонки"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", " "))
    for c in ("CTR %", "% конверсии", "% продажи"):
        fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}%")
    print(fmt.to_string(index=False))
    for n in df.attrs.get("notes", []):
        print("  *", n)


DEFINITIONS = [
    "Цена, клики, показы: Google Ads — из Google Ads API по аккаунту целиком; Facebook — из BigQuery adwhite.fb_stats_profimet "
    "(там доллары, в евро пересчитано по курсу из параметра --usd-eur).",
    "Конверсии: новые обращения (звонки и формы) из выгрузки CRM по правилу 60 дней — обращение новое, если у этого номера не было "
    "засчитанного нового обращения за последние 60 дней (окно от последнего засчитанного, повторы окно не продлевают).",
    "Звонки: из конверсий те, что звонки (показаны только у Google Ads и Facebook).",
    "Продажи: проданные заказы (в выгрузке есть «Дата продажи» в периоде); источник продажи — источник первого обращения этого номера "
    "за 60 дней до первой строки заказа. Количества товара в выгрузке нет, поэтому это заказы, а не единицы.",
    "% конверсии = Конверсии ÷ Клики; Цена заявки = Цена ÷ Конверсии; % продажи = Продажи ÷ Конверсии; Цена продажи = Цена ÷ Продажи; "
    "CTR = Клики ÷ Показы; Цена клика = Цена ÷ Клики. «Итого»: цена, клики, показы — Google + Facebook; конверсии и продажи — по всем строкам.",
]


def _fmt_df(df):
    f = df.copy()
    for c in ("Цена", "Цена клика", "Цена заявки", "Цена продажи"):
        f[c] = f[c].map(lambda v: "—" if pd.isna(v) else f"{v:,.2f} €".replace(",", " "))
    for c in ("Клики", "Показы", "Конверсии", "Звонки", "Продажи"):
        f[c] = f[c].map(lambda v: "—" if pd.isna(v) else f"{int(v):,}".replace(",", " "))
    for c in ("CTR %", "% конверсии", "% продажи"):
        f[c] = f[c].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}%")
    return f


def write_html(path, frames, meta):
    """Самодостаточная страница: таблицы по источникам (весь период и по месяцам), определения, дата данных. Открывается двойным щелчком."""
    import html as H
    blocks = []
    for title, df in frames:
        f = _fmt_df(df)
        head = "".join(f"<th{' class=\"l\"' if i == 0 else ''}>{H.escape(c)}</th>" for i, c in enumerate(f.columns))
        rows = []
        for _, r in f.iterrows():
            cls = ' class="tot"' if r["Источник"] == "Итого" else ""
            rows.append(f"<tr{cls}>" + "".join(f"<td{' class=\"l\"' if i == 0 else ''}>{H.escape(str(v))}</td>" for i, v in enumerate(r)) + "</tr>")
        notes = "".join(f"<li>{H.escape(n)}</li>" for n in df.attrs.get("notes", []))
        blocks.append(f"<section><h2>{H.escape(title)}</h2><div class='w'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
                      f"<ul class='n'>{notes}</ul></section>")
    defs = "".join(f"<li>{H.escape(d)}</li>" for d in DEFINITIONS)
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProfiMet по источникам</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--tot:#f3f6f4;--acc:#1b7f4a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--line:#333;--tot:#1f2a24;--acc:#4cc28a}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif;max-width:1400px;margin:auto}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 8px;color:var(--acc)}} .m{{color:var(--mut);font-size:13px}}
.w{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:1100px}}
th,td{{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}} th{{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}}
.l{{text-align:left}} tr.tot td{{font-weight:600;background:var(--tot)}} ul.n{{margin:6px 0 0;padding-left:18px;color:var(--mut);font-size:13px}}
ol.d{{margin:12px 0;padding-left:20px;font-size:13px;color:var(--mut)}}
</style></head><body>
<h1>ProfiMet: по источникам</h1><div class="m">{H.escape(meta)}</div>
{''.join(blocks)}
<h2>Как считается</h2><ol class="d">{defs}</ol>
</body></html>"""
    Path(path).write_text(page, encoding="utf-8")


MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def daily_table(frm, to, ads, fb, contacts, sales):
    """Длинная таблица «дата × источник»: расход/клики/показы (Google — евро, Facebook — доллары как в BigQuery), конверсии,
    звонки (из конверсий), продажи. Из неё формулы листа «Дашборд» собирают любой период."""
    cm = contacts[contacts["new"]].groupby(["day", "src2"]).agg(conv=("type", "size"), calls=("type", lambda s: int((s == "звонок").sum())))
    sm = sales.groupby(["sale_date", "src2"]).size()
    a, b = ads.set_index("date"), fb.set_index("date")
    rows = []
    for d in pd.date_range(frm, to).date:
        for src in SOURCES:
            cost = clk = imp = None
            src_df = a if src == "Google Ads" else b if src == "Facebook" else None
            if src_df is not None:
                if d in src_df.index:
                    cost, clk, imp = float(src_df.loc[d, "cost"]), int(src_df.loc[d, "clicks"]), int(src_df.loc[d, "impr"])
                else:
                    cost, clk, imp = 0.0, 0, 0
            conv = int(cm["conv"].get((d, src), 0)) if (d, src) in cm.index else 0
            calls = int(cm["calls"].get((d, src), 0)) if (d, src) in cm.index else 0
            rows.append({"Дата": d, "Источник": src, "Цена": cost, "Клики": clk, "Показы": imp, "Конверсии": conv,
                         "Звонки": calls, "Продажи": int(sm.get((d, src), 0))})
    return pd.DataFrame(rows)


def write_xlsx_dynamic(path, daily, usd_eur, frm, to):
    """Книга для Google Таблиц: «Дашборд» (выпадающий выбор периода + формулы), «Данные» (по дням), «Списки» (периоды), «Как считается»."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "Дашборд"
    wd = wb.create_sheet("Данные")
    wl = wb.create_sheet("Списки")
    wh = wb.create_sheet("Как считается")
    bold, head, inp = Font(bold=True), PatternFill("solid", fgColor="DDEBF7"), PatternFill("solid", fgColor="FFF2CC")

    # --- Данные
    wd.append(["Дата", "Источник", "Цена (Google — €, Facebook — $ как в BigQuery)", "Клики", "Показы", "Конверсии (новые обращения)", "из них звонки", "Продажи"])
    for c in wd[1]:
        c.font, c.fill = bold, head
    for _, r in daily.iterrows():
        wd.append([r["Дата"], r["Источник"], r["Цена"], r["Клики"], r["Показы"], r["Конверсии"], r["Звонки"], r["Продажи"]])
        wd.cell(wd.max_row, 1).number_format = "DD.MM.YYYY"
    wd.freeze_panes = "A2"
    for col, w in zip("ABCDEFGH", (12, 12, 22, 10, 12, 18, 14, 10)):
        wd.column_dimensions[col].width = w

    # --- Списки: готовые периоды (динамические от сегодняшней даты и статические месяцы/недели)
    wl.append(["Период", "Начало", "Конец"])
    for c in wl[1]:
        c.font, c.fill = bold, head
    dyn = [("Текущий месяц", "=DATE(YEAR(TODAY()),MONTH(TODAY()),1)", "=EOMONTH(TODAY(),0)"),
           ("Прошлый месяц", "=EOMONTH(TODAY(),-2)+1", "=EOMONTH(TODAY(),-1)"),
           ("Текущая неделя", "=TODAY()-WEEKDAY(TODAY(),2)+1", None),
           ("Прошлая неделя", "=TODAY()-WEEKDAY(TODAY(),2)-6", None),
           ("Последние 7 дней", "=TODAY()-7", "=TODAY()-1"),
           ("Последние 30 дней", "=TODAY()-30", "=TODAY()-1")]
    for label, b, e in dyn:
        wl.append([label, b, e if e else f"=B{wl.max_row + 1}+6"])
    f0, t0 = pd.Timestamp(frm), pd.Timestamp(to)
    wl.append([f"Весь период ({f0:%d.%m.%Y}–{t0:%d.%m.%Y})", f0.date(), t0.date()])
    for s, e, _ in periods(frm, to, "month"):
        wl.append([f"{MONTHS_RU[s.month - 1]} {s.year}", s, e])
    for s, e, _ in periods(frm, to, "week"):
        wl.append([f"Неделя {s:%d.%m}–{e:%d.%m.%Y}", s, e])
    wl.append(["Свой период", None, None])
    last_list = wl.max_row
    for row in wl.iter_rows(min_row=2, min_col=2, max_col=3):
        for c in row:
            c.number_format = "DD.MM.YYYY"
    wl.column_dimensions["A"].width = 34
    wl.column_dimensions["B"].width = wl.column_dimensions["C"].width = 14

    # --- Дашборд
    ws["A1"] = "ProfiMet: по источникам"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"], ws["B2"] = "Период (выберите из списка)", "Текущий месяц"
    ws["A3"], ws["B3"] = "Начало", '=IF($B$2="Свой период",$E$3,VLOOKUP($B$2,\'Списки\'!$A$2:$C$%d,2,FALSE))' % last_list
    ws["A4"], ws["B4"] = "Конец", ('=IF($B$2="Свой период",$E$4,MIN(VLOOKUP($B$2,\'Списки\'!$A$2:$C$%d,3,FALSE),MAX(\'Данные\'!$A:$A)))' % last_list)
    ws["D3"], ws["E3"] = "Свой период: начало", f0.date()
    ws["D4"], ws["E4"] = "Свой период: конец", t0.date()
    ws["A5"], ws["B5"] = "Курс USD→EUR для Facebook (допущение, можно менять)", usd_eur
    ws["A6"], ws["B6"] = "Данные есть по", "=MAX('Данные'!$A:$A)"
    for ref in ("B3", "B4", "B6", "E3", "E4"):
        ws[ref].number_format = "DD.MM.YYYY"
    for ref in ("B2", "E3", "E4", "B5"):
        ws[ref].fill = inp
    for ref in ("A2", "A3", "A4", "A5", "A6", "D3", "D4"):
        ws[ref].font = bold
    dv = DataValidation(type="list", formula1=f"='Списки'!$A$2:$A${last_list}", allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv)
    dv.add("B2")

    cols = ["Источник", "Цена", "Клики", "Показы", "Цена клика", "CTR %", "Конверсии", "% конверсии", "Цена заявки", "Звонки", "Продажи", "% продажи", "Цена продажи"]
    for j, c in enumerate(cols, 1):
        cell = ws.cell(8, j, c)
        cell.font, cell.fill, cell.alignment = bold, head, Alignment(horizontal="center", wrap_text=True)

    def S(col, r):
        return f"SUMIFS('Данные'!${col}:${col},'Данные'!$A:$A,\">=\"&$B$3,'Данные'!$A:$A,\"<=\"&$B$4,'Данные'!$B:$B,$A{r})"

    D = "—"
    for r, src in zip(range(9, 14), SOURCES):
        paid, has_conv, has_calls = src in ("Google Ads", "Facebook"), src in ("Google Ads", "Facebook", "Нет метки"), src in ("Google Ads", "Facebook")
        ws.cell(r, 1, src)
        ws.cell(r, 2, f"={S('C', r)}" + ("*$B$5" if src == "Facebook" else "") if paid else D)
        ws.cell(r, 3, f"={S('D', r)}" if paid else D)
        ws.cell(r, 4, f"={S('E', r)}" if paid else D)
        ws.cell(r, 5, f'=IFERROR(B{r}/C{r},"")' if paid else D)
        ws.cell(r, 6, f'=IFERROR(C{r}/D{r}*100,"")' if paid else D)
        ws.cell(r, 7, f"={S('F', r)}" if has_conv else D)
        ws.cell(r, 8, f'=IFERROR(G{r}/C{r}*100,"")' if paid else D)
        ws.cell(r, 9, f'=IFERROR(B{r}/G{r},"")' if paid else D)
        ws.cell(r, 10, f"={S('G', r)}" if has_calls else D)
        ws.cell(r, 11, f"={S('H', r)}")
        ws.cell(r, 12, f'=IFERROR(K{r}/G{r}*100,"")' if has_conv else D)
        ws.cell(r, 13, f'=IFERROR(B{r}/K{r},"")' if paid else D)
    ws.cell(14, 1, "Итого")
    ws.cell(14, 2, "=SUM(B9:B10)")
    ws.cell(14, 3, "=SUM(C9:C10)")
    ws.cell(14, 4, "=SUM(D9:D10)")
    ws.cell(14, 5, '=IFERROR(B14/C14,"")')
    ws.cell(14, 6, '=IFERROR(C14/D14*100,"")')
    ws.cell(14, 7, "=SUM(G9:G11)")
    ws.cell(14, 8, '=IFERROR(G14/C14*100,"")')
    ws.cell(14, 9, '=IFERROR(B14/G14,"")')
    ws.cell(14, 10, "=SUM(J9:J10)")
    ws.cell(14, 11, "=SUM(K9:K13)")
    ws.cell(14, 12, '=IFERROR(K14/G14*100,"")')
    ws.cell(14, 13, '=IFERROR(B14/K14,"")')
    for c in ws[14]:
        c.font = bold
    money, intf, pct = '#,##0.00 "€"', "#,##0", '0.00"%"'
    fm = {2: money, 5: money, 9: money, 13: money, 3: intf, 4: intf, 7: intf, 10: intf, 11: intf, 6: pct, 8: pct, 12: pct}
    for r in range(9, 15):
        for j, f in fm.items():
            ws.cell(r, j).number_format = f
            ws.cell(r, j).alignment = Alignment(horizontal="right")
    ws["A16"] = f'="Телефон: новых обращений "&{S("F", 12)}&" (из них звонков "&{S("G", 12)}&") — в «Конверсии» и «Звонки» не включены"'
    ws["A17"] = f'="Нет метки: из "&G11&" конверсий звонков "&{S("G", 11)}&" — в колонке «Звонки» не показаны"'
    ws["A18"] = f'="Прочее: новых обращений "&{S("F", 13)}&" — в «Конверсии» и «Звонки» не включены"'
    ws.column_dimensions["A"].width = 46
    for col in "BCDEFGHIJKLM":
        ws.column_dimensions[col].width = 14
    ws.column_dimensions["D"].width = 22
    ws.row_dimensions[8].height = 32
    ws.freeze_panes = "A9"

    # --- Как считается
    wh.column_dimensions["A"].width = 150
    for t in DEFINITIONS + ["Курс USD→EUR для Facebook — ячейка B5 листа «Дашборд» (допущение; в BigQuery расход хранится в долларах).",
                            "Период выбирается в ячейке B2 листа «Дашборд»; для «Свой период» даты вводятся в E3 и E4. «Текущий месяц» и «Текущая неделя» считаются "
                            "от сегодняшней даты, но данных нет позже даты, указанной в B6 (данные обновляются повторным запуском скрипта profimet_sources_dashboard.py)."]:
        wh.append([t])
        wh.cell(wh.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


DASHBOARD_SHEET_ID = "1yQ4YnDv0M_XjXFt2XQLf0wZfLqCJYJ7mC_kCtA-8xAk"  # «ProfiMet — по источникам (дашборд)» в Google Диске пользователя; сервисному аккаунту выдан «Редактор»


def refresh_google_sheet(file_id, daily, frm, to):
    """Обновляет в Google Таблице только листы «Данные» и «Списки» (периоды) и диапазон выпадающего списка; лист «Дашборд»
    (выбранный период, свои даты, курс) не трогает. Нужен доступ «Редактор» сервисному аккаунту."""
    import datetime
    from google.auth.transport.requests import AuthorizedSession
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    s = AuthorizedSession(creds)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
    ser = lambda d: (d - datetime.date(1899, 12, 30)).days
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in s.get(base + "?fields=sheets(properties(sheetId,title))", timeout=60).json()["sheets"]}

    import json

    def clean(v):  # NaN/None → пусто (JSON null), numpy → python
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return v.item() if hasattr(v, "item") else v

    # Сначала готовим и проверяем ВСЕ данные (json.dumps упадёт на NaN), и только потом очищаем листы: сбой не оставит таблицу пустой.
    rows = [[clean(x) for x in (ser(r["Дата"]), r["Источник"], r["Цена"], r["Клики"], r["Показы"], r["Конверсии"], r["Звонки"], r["Продажи"])]
            for _, r in daily.iterrows()]
    f0, t0 = pd.Timestamp(frm), pd.Timestamp(to)
    st = [[f"Весь период ({f0:%d.%m.%Y}–{t0:%d.%m.%Y})", ser(f0.date()), ser(t0.date())]]
    st += [[f"{MONTHS_RU[sd.month - 1]} {sd.year}", ser(sd), ser(ed)] for sd, ed, _ in periods(frm, to, "month")]
    st += [[f"Неделя {sd:%d.%m}–{ed:%d.%m.%Y}", ser(sd), ser(ed)] for sd, ed, _ in periods(frm, to, "week")]
    st += [["Свой период", None, None]]
    json.dumps(rows), json.dumps(st)

    # Данные: очистить и записать заново (даты — числами: так таблица не зависит от локали)
    s.post(base + "/values/Данные!A2:H5000:clear", json={}, timeout=60).raise_for_status()
    s.put(base + "/values/Данные!A2?valueInputOption=USER_ENTERED", json={"values": rows}, timeout=120).raise_for_status()

    # Списки: статическая часть (весь период, месяцы, недели, «Свой период») начиная с 8-й строки; динамические 2–7 не трогаем
    s.post(base + "/values/Списки!A8:C200:clear", json={}, timeout=60).raise_for_status()
    s.put(base + "/values/Списки!A8?valueInputOption=USER_ENTERED", json={"values": st}, timeout=60).raise_for_status()
    last = 7 + len(st)
    fmt = {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}}}
    req = [{"setDataValidation": {"range": {"sheetId": ids["Дашборд"], "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": f"='Списки'!$A$2:$A${last}"}]}, "strict": True, "showCustomUi": True,
                     "inputMessage": "Выберите период из списка. Для произвольных дат выберите «Свой период» и впишите даты в E3 и E4."}}},
           {"repeatCell": {"range": {"sheetId": ids["Данные"], "startRowIndex": 1, "endRowIndex": len(rows) + 1, "startColumnIndex": 0, "endColumnIndex": 1},
                           "cell": fmt, "fields": "userEnteredFormat.numberFormat"}},
           {"repeatCell": {"range": {"sheetId": ids["Списки"], "startRowIndex": 1, "endRowIndex": last, "startColumnIndex": 1, "endColumnIndex": 3},
                           "cell": fmt, "fields": "userEnteredFormat.numberFormat"}}]
    s.post(base + ":batchUpdate", json={"requests": req}, timeout=60).raise_for_status()
    return len(rows), last


def periods(frm, to, by):
    f, t = pd.Timestamp(frm), pd.Timestamp(to)
    if by == "month":
        cur = f
        while cur <= t:
            end = min((cur + pd.offsets.MonthEnd(0)), t)
            yield cur.date(), end.date(), cur.strftime("%Y-%m")
            cur = end + pd.Timedelta(days=1)
    elif by == "week":
        cur = f - pd.Timedelta(days=f.weekday())
        while cur <= t:
            s, e = max(cur, f), min(cur + pd.Timedelta(days=6), t)
            yield s.date(), e.date(), f"неделя {cur.strftime('%d.%m')}"
            cur += pd.Timedelta(days=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--to", dest="to", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--by", choices=["month", "week"], default=None)
    ap.add_argument("--usd-eur", type=float, default=0.85, help="курс для расхода Facebook (в BigQuery — доллары); ПАРАМЕТР, не факт")
    ap.add_argument("--cache", default=None, help="pickle (sheet, ringo_full), как у profimet_season_audit.py")
    ap.add_argument("--no-open", action="store_true", help="не открывать страницу в браузере после запуска")
    ap.add_argument("--update-sheet", nargs="?", const=DASHBOARD_SHEET_ID, default=None, metavar="ID",
                    help="обновить данные в Google Таблице дашборда (по умолчанию — «ProfiMet — по источникам (дашборд)»): листы «Данные» и «Списки»")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if a.cache and Path(a.cache).exists():
        sheet, ringo = pickle.load(open(a.cache, "rb"))
    else:
        sheet, ringo = load_sheet(SHEET_ID), fetch_ringostat_full()
        if a.cache:
            pickle.dump((sheet, ringo), open(a.cache, "wb"))
    ads, fb = ads_daily(a.frm, a.to), fb_daily(a.frm, a.to)
    contacts, sales = contacts_with_new_flag(sheet), sales_with_source(sheet)

    total = build(a.frm, a.to, ads, fb, contacts, sales, a.usd_eur)
    show(total, f"ProfiMet, по источникам, {a.frm} — {a.to}")
    out_dir = client_stats_dir("ProfiMet")
    total.to_csv(out_dir / f"dashboard_sources_{a.frm}_{a.to}.csv", index=False, encoding="utf-8-sig")
    if a.by:
        for s, e, label in periods(a.frm, a.to, a.by):
            show(build(s, e, ads, fb, contacts, sales, a.usd_eur), f"{label}: {s} — {e}")

    # страница: весь период + каждый месяц (всегда), открывается в браузере
    frames = [(f"Весь период: {a.frm} — {a.to}", total)]
    for s, e, label in periods(a.frm, a.to, "month"):
        frames.append((f"{label}: {s} — {e}", build(s, e, ads, fb, contacts, sales, a.usd_eur)))
    meta = (f"Данные выгрузки CRM до {sheet['ts'].max().tz_convert(W):%d.%m.%Y %H:%M}; расход Facebook — BigQuery (доллары) × {a.usd_eur} "
            f"(курс — параметр); сформировано {pd.Timestamp.now(tz=W):%d.%m.%Y %H:%M}.")
    html_path = out_dir / f"dashboard_sources_{a.frm}_{a.to}.html"
    write_html(html_path, frames, meta)
    xlsx_path = out_dir / f"dashboard_sources_{a.frm}_{a.to}.xlsx"
    daily = daily_table(a.frm, a.to, ads, fb, contacts, sales)
    write_xlsx_dynamic(xlsx_path, daily, a.usd_eur, a.frm, a.to)
    if a.update_sheet:
        n, last = refresh_google_sheet(a.update_sheet, daily, a.frm, a.to)
        print(f"Google Таблица обновлена: https://docs.google.com/spreadsheets/d/{a.update_sheet}/edit — строк данных {n}, периодов в списке {last - 1}")
    print(f"\nСтраница: {html_path}\nТаблица Excel (можно загрузить в Google Таблицы): {xlsx_path}")
    if not a.no_open:
        import os
        try:
            os.startfile(str(html_path))
        except Exception as ex:
            print("(не удалось открыть автоматически:", ex, ")")

    pu = prod_unique(ringo, count_other=False, date_to=a.to)
    pu = pu[(pu["date"] >= pd.Timestamp(a.frm).date()) & (pu["date"] <= pd.Timestamp(a.to).date())]
    print("\nСправочно: звонки по боевому правилу Ringostat (ringostat_profimet2) за период:",
          {k: int((pu["category"] == k).sum()) for k in ("Google Ads", "Facebook", "Google SEO")})
    print(f"Расход Facebook в BigQuery хранится в долларах; пересчёт в евро по курсу {a.usd_eur} (параметр --usd-eur). "
          f"Последняя дата в выгрузке CRM: {sheet['ts'].max().tz_convert(W):%Y-%m-%d %H:%M}.")


if __name__ == "__main__":
    main()
