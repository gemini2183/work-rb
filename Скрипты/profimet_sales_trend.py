#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: НАШ дашборд «Заявки → продажи, тренд» — ТОЛЬКО ЧТЕНИЕ (запрос пользователя 2026-10-21).

Отвечает на вопросы: сколько стоит рекламная продажа сейчас, как заявки превращаются в продажи по источникам и падают ли продажи за последние 7 дней.

Определения (те же, что в `profimet_sources_dashboard.py`, плюс выводы 2026-10-21):
  • Расход — Google Ads (API) + Facebook (BigQuery, доллары × `--usd-eur`).
  • Заявки (конверсии) — новые обращения (звонки и формы) по правилу 60 дней, источники Google Ads, Facebook, «Нет метки».
  • Рекламная продажа — проданный заказ (есть «Дата продажи», нет «Даты отмены»), у которого источник первого обращения номера за 60 дней до заказа
    Google Ads, Facebook или «Нет метки». Заказы с первым обращением «Телефон» (звонок без метки и без рекламного следа) в рекламу НЕ входят,
    так считает клиент. Цена продажи = (Google + Facebook) ÷ рекламные продажи.
  • Продажа относится к дате продажи, а не к дате заявки: заявка превращается в продажу с задержкой (медиана печатается), поэтому «последние 7 дней»
    сравнивать только с предыдущими 7 днями и со средним за 4 недели, а не с 30 днями.
Окно «последние 7 дней» заканчивается последним ПОЛНЫМ днём выгрузки CRM (сегодняшний неполный день не берётся).

Использование: PYTHONIOENCODING=utf-8 python profimet_sales_trend.py [--from 2026-08-01] [--usd-eur 0.8244] [--no-open]
Пишет `Клиенты/ProfiMet/Статистика/dashboard_sales_trend.html` и `sales_trend_daily.csv`. Запускать без -I.
"""
import argparse
import html as H
import os
from datetime import date, timedelta

import pandas as pd

from _config import client_stats_dir
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet
from profimet_sources_dashboard import (SITE, SOURCES, WINDOW, ads_daily, contacts_with_new_flag, fb_daily)

AD_SRC = ["Google Ads", "Facebook", "Нет метки"]


def sales_table(sheet):
    """Проданные заказы без отмены: дата продажи и источник первого обращения номера за 60 дн до заказа."""
    s = sheet[sheet["site"] == SITE]
    by_phone = {p: g for p, g in s.groupby("p9") if p}
    rows, cancelled = [], 0
    for order, grp in s[s["order"] != ""].groupby("order"):
        sd = [d for d in grp["sale_date"] if d]
        if not sd:
            continue
        if any(grp["cancel_date"] != ""):
            cancelled += 1
            continue
        grp = grp.sort_values("ts", kind="mergesort")
        t0 = grp.iloc[0]["ts"]
        parts = [by_phone[p] for p in set(grp["p9"]) if p in by_phone]
        t = pd.concat(parts) if parts else grp
        t = t[(t["ts"] >= t0 - pd.Timedelta(days=WINDOW)) & (t["ts"] <= t0)].sort_values("ts", kind="mergesort")
        first = t.iloc[0] if not t.empty else grp.iloc[0]
        src = first["src"] or "Нет метки"
        sale = pd.Timestamp(min(sd)).date()
        rows.append({"order": order, "sale_date": sale, "src2": src if src in SOURCES else "Прочее",
                     # дата первого обращения (за 60 дн до заказа), но не позже даты самой продажи: звонок, привязанный к старой продаже
                     # (заказ создан раньше строки звонка), не переносит продажу в новый период (случай 076e3f0e, 2026-10-21)
                     "touch_date": min(first["ts"].tz_convert("Europe/Warsaw").date(), sale)})
    return pd.DataFrame(rows), cancelled


def daily_frame(frm, to, ads, fb, usd_eur, contacts, sales):
    idx = pd.date_range(frm, to).date
    d = pd.DataFrame({"day": idx}).set_index("day")
    d["cost_g"] = ads.set_index("date")["cost"].reindex(idx).fillna(0).values
    d["cost_f"] = fb.set_index("date")["cost"].reindex(idx).fillna(0).values * usd_eur
    d["cost"] = d["cost_g"] + d["cost_f"]
    c = contacts[contacts["new"] & contacts["src2"].isin(AD_SRC)]
    d["leads"] = c.groupby("day").size().reindex(idx).fillna(0).astype(int).values
    for s in AD_SRC:
        d[f"sales_{s}"] = sales[sales["src2"] == s].groupby("sale_date").size().reindex(idx).fillna(0).astype(int).values
        d[f"leads_{s}"] = c[c["src2"] == s].groupby("day").size().reindex(idx).fillna(0).astype(int).values
    d["sales"] = d[[f"sales_{s}" for s in AD_SRC]].sum(axis=1)
    d["phone_sales"] = sales[sales["src2"] == "Телефон"].groupby("sale_date").size().reindex(idx).fillna(0).astype(int).values
    return d


def window(d, a, b):
    x = d.loc[a:b]
    cost, sales, leads = x["cost"].sum(), int(x["sales"].sum()), int(x["leads"].sum())
    return {"Расход": cost, "Заявки": leads, "Продажи": sales, "Цена заявки": cost / leads if leads else None,
            "Цена продажи": cost / sales if sales else None, "Продажи на 100 заявок": sales / leads * 100 if leads else None,
            "Google": int(x["sales_Google Ads"].sum()), "Facebook": int(x["sales_Facebook"].sum()),
            "Нет метки": int(x["sales_Нет метки"].sum()), "«Телефон» (вне рекламы)": int(x["phone_sales"].sum())}


def money(v):
    return "—" if v is None or pd.isna(v) else f"{v:,.0f} €".replace(",", " ")


def num(v, nd=0, suf=""):
    return "—" if v is None or pd.isna(v) else f"{v:,.{nd}f}{suf}".replace(",", " ")


def svg_line(xs, ys, w=900, h=220, target=None, label=""):
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None and not pd.isna(y)]
    if len(pts) < 2:
        return ""
    ymax = max(max(y for _, y in pts), target or 0) * 1.1
    ymin = 0
    X = lambda i: 40 + i * (w - 60) / (len(xs) - 1)
    Y = lambda y: h - 28 - (y - ymin) / (ymax - ymin) * (h - 48)
    path = " ".join(f"{'M' if k == 0 else 'L'}{X(xs.index(x)):.1f},{Y(y):.1f}" for k, (x, y) in enumerate(pts))
    ticks = "".join(f"<text x='{X(i):.0f}' y='{h - 8}' font-size='11' fill='var(--mut)' text-anchor='middle'>{xs[i]:%d.%m}</text>"
                    for i in range(0, len(xs), max(1, len(xs) // 10)))
    grid = "".join(f"<line x1='40' x2='{w - 20}' y1='{Y(v):.0f}' y2='{Y(v):.0f}' stroke='var(--line)'/><text x='34' y='{Y(v) + 4:.0f}' font-size='11' fill='var(--mut)' text-anchor='end'>{v:.0f}</text>"
                   for v in [ymax * k / 4 for k in range(0, 4)])
    tl = (f"<line x1='40' x2='{w - 20}' y1='{Y(target):.0f}' y2='{Y(target):.0f}' stroke='#c0392b' stroke-dasharray='5 4'/>"
          f"<text x='{w - 22}' y='{Y(target) - 5:.0f}' font-size='11' fill='#c0392b' text-anchor='end'>цель {target:.0f} €</text>") if target else ""
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='{H.escape(label)}'>{grid}{tl}"
            f"<path d='{path}' fill='none' stroke='var(--acc)' stroke-width='2.2'/>{ticks}</svg>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-08-01")
    ap.add_argument("--usd-eur", type=float, default=0.8244)
    ap.add_argument("--target", type=float, default=30.0, help="цель по цене продажи, €")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    sheet = load_sheet(SHEET_ID)
    last_ts = sheet[sheet["site"] == SITE]["ts"].max().tz_convert("Europe/Warsaw")
    end = last_ts.date() - timedelta(days=1)  # последний полный день
    frm = pd.Timestamp(a.frm).date()
    ads, fb = ads_daily(frm, end), fb_daily(frm, end)
    contacts = contacts_with_new_flag(sheet)
    sales, cancelled = sales_table(sheet)
    d = daily_frame(frm, end, ads, fb, a.usd_eur, contacts, sales)
    d.to_csv(client_stats_dir("ProfiMet") / "sales_trend_daily.csv", encoding="utf-8-sig")

    w0 = window(d, end - timedelta(days=6), end)
    w1 = window(d, end - timedelta(days=13), end - timedelta(days=7))
    w4 = window(d, end - timedelta(days=27), end)
    w4_avg = {k: (v / 4 if k in ("Расход", "Заявки", "Продажи", "Google", "Facebook", "Нет метки", "«Телефон» (вне рекламы)") else v) for k, v in w4.items()}

    # скользящие 7 дней
    roll_x, roll_price, roll_sales = [], [], []
    for i in range(6, len(d)):
        x = d.iloc[i - 6:i + 1]
        s = x["sales"].sum()
        roll_x.append(d.index[i])
        roll_price.append(x["cost"].sum() / s if s >= 3 else None)
        roll_sales.append(float(s))

    # недели пн–вс
    d2 = d.copy()
    d2.index = pd.to_datetime(d2.index)
    wk = d2.resample("W-SUN").sum(numeric_only=True)
    wk["Цена продажи"] = wk["cost"] / wk["sales"].where(wk["sales"] > 0)
    wk["Цена заявки"] = wk["cost"] / wk["leads"].where(wk["leads"] > 0)
    wk["Продаж на 100 заявок"] = wk["sales"] / wk["leads"].where(wk["leads"] > 0) * 100

    def delta(a_, b_):
        if a_ is None or b_ is None or pd.isna(a_) or pd.isna(b_) or b_ == 0:
            return "—"
        p = (a_ - b_) / b_ * 100
        return f"{p:+.0f}%"

    rows = ["Расход", "Заявки", "Продажи", "Цена заявки", "Цена продажи", "Продажи на 100 заявок", "Google", "Facebook", "Нет метки"]
    fmt = {"Расход": money, "Цена заявки": money, "Цена продажи": money, "Продажи на 100 заявок": lambda v: num(v, 1, "")}
    trs = ""
    for k in rows:
        f = fmt.get(k, lambda v: num(v, 0))
        f4 = fmt.get(k, lambda v: num(v, 1))
        trs += (f"<tr><td class='l'>{H.escape(k)}</td><td>{f(w0[k])}</td><td>{f(w1[k])}</td><td>{delta(w0[k], w1[k])}</td>"
                f"<td>{f4(w4_avg[k])}</td><td>{delta(w0[k], w4_avg[k])}</td></tr>")
    wk_rows = ""
    for dt, r in wk.tail(10).iterrows():
        part = " (неполная)" if dt.date() > end else ""
        wk_rows += (f"<tr><td class='l'>{(dt - pd.Timedelta(days=6)):%d.%m}–{dt:%d.%m}{part}</td><td>{money(r['cost'])}</td><td>{int(r['leads'])}</td>"
                    f"<td>{int(r['sales'])}</td><td>{money(r['Цена заявки'])}</td><td>{money(r['Цена продажи'])}</td><td>{num(r['Продаж на 100 заявок'], 1)}</td>"
                    f"<td>{int(r['sales_Google Ads'])}</td><td>{int(r['sales_Facebook'])}</td><td>{int(r['sales_Нет метки'])}</td></tr>")
    css = """:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--acc:#1b7f4a}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--line:#333;--acc:#4cc28a}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif;max-width:1200px;margin:auto}
h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:28px 0 8px;color:var(--acc)} .m{color:var(--mut);font-size:13px}
.w{overflow-x:auto} table{border-collapse:collapse;width:100%} th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;color:var(--mut)} .l{text-align:left} ul{color:var(--mut);font-size:13px;padding-left:18px}"""
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProfiMet заявки и продажи</title><style>{css}</style></head><body>
<h1>ProfiMet: заявки → продажи, тренд</h1>
<div class="m">Данные CRM до {last_ts:%d.%m.%Y %H:%M}; окно «последние 7 дней» = {end - timedelta(days=6):%d.%m}–{end:%d.%m} (последний полный день). Цель по цене продажи — {a.target:.0f} €.</div>
<h2>Последние 7 дней против предыдущих 7 и среднего за 4 недели</h2>
<div class="w"><table><thead><tr><th class="l"></th><th>Последние 7 дн.</th><th>Предыдущие 7 дн.</th><th>Изменение</th><th>Среднее за неделю (4 нед.)</th><th>Изменение</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="m">Не реклама, в таблицу не входит (справочно): заказы, начатые звонком «Телефон» без рекламного следа, — {w0["«Телефон» (вне рекламы)"]} за последние 7 дней, {w1["«Телефон» (вне рекламы)"]} за предыдущие 7.</p>
<h2>Цена рекламной продажи, скользящие 7 дней (без заказов «Телефон»)</h2>{svg_line(roll_x, roll_price, target=a.target, label="Цена продажи, скользящие 7 дней")}
<h2>Рекламные продажи, сумма за скользящие 7 дней (Google + Facebook + Нет метки, без «Телефон»)</h2>{svg_line(roll_x, roll_sales, label="Продажи, сумма за 7 дней")}
<h2>По неделям (пн–вс)</h2>
<div class="w"><table><thead><tr><th class="l">Неделя</th><th>Расход</th><th>Заявки</th><th>Продажи</th><th>Цена заявки</th><th>Цена продажи</th><th>Продаж на 100 заявок</th><th>Google</th><th>Facebook</th><th>Нет метки</th></tr></thead><tbody>{wk_rows}</tbody></table></div>
<h2>Как читать</h2><ul>
<li>Продажи — рекламные: проданные заказы без отмены, у которых первое обращение номера за 60 дн. — Google Ads, Facebook или «Нет метки». «Телефон» (звонок без метки и без рекламного следа) в рекламу не входит, как у клиента.</li>
<li>Цена продажи = расход Google + Facebook ÷ рекламные продажи за те же даты. Продажа учитывается по дате продажи, не по дате заявки.</li>
<li>Продажи неровные: менеджеры проставляют даты пачками, в выходные продаж почти нет. Окна сравниваются с одинаковой раскладкой дней недели; по одной неделе вывод не делать.</li>
<li>Заявки — новые обращения по правилу 60 дн. из CRM (звонки и формы Google, Facebook, «Нет метки»). Метки у форм с 31.08 теряются, часть «Нет метки» — реклама.</li>
<li>Отменённых заказов за период исключено: {cancelled}. Если в неделе меньше 3 продаж, точка цены на графике не рисуется.</li></ul>
</body></html>"""
    out = client_stats_dir("ProfiMet") / "dashboard_sales_trend.html"
    out.write_text(page, encoding="utf-8")
    print(f"Данные CRM до {last_ts:%d.%m %H:%M}; окно {end - timedelta(days=6):%d.%m}–{end:%d.%m}")
    print(f"{'':28}{'7 дн':>10}{'пред. 7':>10}{'ср. 4 нед':>11}")
    for k in rows:
        f = fmt.get(k, lambda v: num(v, 0))
        print(f"{k:28}{f(w0[k]):>10}{f(w1[k]):>10}{fmt.get(k, lambda v: num(v, 1))(w4_avg[k]):>11}")
    for lab, a_, b_ in (("сентябрь", date(2026, 9, 1), date(2026, 9, 30)), ("октябрь до " + f"{end:%d.%m}", date(2026, 10, 1), end)):
        w = window(d, a_, b_)
        print(f"{lab}: расход {money(w['Расход'])}, рекламных продаж {w['Продажи']}, цена продажи {money(w['Цена продажи'])}, цена заявки {money(w['Цена заявки'])}")
    print("отменённых заказов исключено:", cancelled)
    print("Файл:", out)
    if not a.no_open:
        os.startfile(str(out))


if __name__ == "__main__":
    main()
