#!/usr/bin/env python
# coding: utf-8
"""ProfiMet: таблица заказов «как у клиента» + расхождения с выгрузкой CRM по номерам заказов — ТОЛЬКО ЧТЕНИЕ.

Что делает. Соединяет список продаж дашборда клиента (TSV: Дата, Заказ, Телефон, Товар, Кол-во, Источник, UTM, Площадка, Автор) и проданные
заказы выгрузки CRM (листы ProfiMet; лист Ekspertagro.pl не используется) и пишет одну строку на заказ:
  • колонки клиента как в его списке (дата UTC, номер заказа из 8 знаков, телефон, товар, количество, источник заказа, UTM, площадка, автор);
  • «Где есть»: оба / только у клиента / только в выгрузке CRM;
  • из выгрузки CRM: полный номер заказа, дата первой строки (≈ создание заказа), чем начат заказ, статус, дата продажи, отмена;
  • «А'. Воспроизведение по правилу клиента»: если у заказа есть строка-форма, источник = источник формы по UTM (Google Ads, Facebook, иначе
    «Нет метки»); если формы нет (заказ менеджера), источник «Телефон». На 01–20.10 совпало с источником клиента у 70 из 74 найденных заказов;
  • варианты источника заказа (шаг 3.1 отчёта): А = источник у клиента; Б = первое обращение за всю историю; В = первое обращение за
    `--window` дней до заказа; Г = первое обращение, привязанное к номеру заказа в выгрузке CRM;
  • «Рекламное касание» (строка Google Ads / Facebook или gclid у номера до заказа, по выгрузке CRM), «Повторная покупка» (у номера есть
    другая проданная неотменённая покупка не позднее чем за `--repeat-days` дней до заказа);
  • «Причина расхождения» для строк «только у клиента» / «только в выгрузке» и для строк, где источник у клиента не совпал с Г.
Сверка идёт по номерам заказов (первые 8 знаков), не по суммам. Дополнение Г «по времени и телефону» (перезвон менеджера) здесь пока НЕ реализовано:
нужен Ringostat, это следующая версия. Ограничения: данные одного периода, правила проверены только на 01–20.10.2026.

Использование (из папки Скрипты):
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python profimet_client_replica.py --client-list ПУТЬ.tsv [--from 2026-10-01] [--to 2026-10-20]
        [--window 60] [--repeat-days 7]
Пишет `Клиенты/ProfiMet/Статистика/orders_replica_<с>_<по>.csv` и печатает сводку.
"""
import argparse
import re

import pandas as pd

from _config import client_stats_dir
from profimet_sales_vs_ringostat import SHEET_ID, load_sheet

PM_SITES_EXCLUDE = {"Ekspertagro.pl"}
ADS = {"Google Ads", "Facebook"}


def last9(x):
    d = re.sub(r"\D", "", str(x or ""))
    return d[-9:] if len(d) >= 9 else ""


def read_client(path):
    c = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    c["p9"] = c["Телефон"].map(last9)
    c["ts"] = pd.to_datetime(c["Дата"], utc=True)
    c["qty"] = c["Кол-во"].replace("", "1").astype(int)
    g = c.groupby("Заказ", sort=False).agg(
        client_date=("ts", "min"), client_phone=("Телефон", "first"), p9=("p9", "first"), product=("Товар", lambda s: "; ".join(s)),
        qty=("qty", "sum"), client_source=("Источник", "first"), client_utm=("UTM", "first"), platform=("Площадка", "first"),
        author=("Автор", "first")).reset_index().rename(columns={"Заказ": "key"})
    return g


def our_orders(pm):
    o = pm[pm["order"] != ""]
    rows = []
    for order, g in o.groupby("order"):
        g = g.sort_values("ts", kind="mergesort")
        sd = [d for d in g["sale_date"] if d]
        rows.append({"order": order, "key": order[:8], "p9": g.iloc[0]["p9"], "phone": g.iloc[0]["phone"], "created": g.iloc[0]["ts"],
                     "first_type": g.iloc[0]["type"], "first_src": g.iloc[0]["src"] or "Нет метки", "status_first": g.iloc[0]["status"],
                     "rows": len(g), "sale": min(sd) if sd else "", "cancel": max([d for d in g["cancel_date"] if d] or [""]),
                     "sites": ",".join(sorted(set(g["site"])))})
    r = pd.DataFrame(rows)
    r["sale_d"] = pd.to_datetime(r["sale"].replace("", pd.NA))
    # Отмена учитывается, если дата отмены не раньше даты продажи (даты ISO, одна на заказ). Отмена до продажи и новая продажа:
    # заказ действует (так считает и клиент). Статус строки — снимок на момент обращения, по нему отмену определять нельзя.
    r["cancelled"] = [bool(c) and (not s or c >= s) for c, s in zip(r["cancel"], r["sale"])]
    return r


REASON_TEXT = {
    "первое обращение Google SEO (органика), рекламных касаний нет":
        "Заказ начался с бесплатного поиска Google (SEO), рекламы в истории нет. У клиента такие заказы на вкладке «SEO», не в «Ads + FB»",
    "первое обращение «Телефон» (60 дн), не рекламный":
        "Человек впервые позвонил на номер без рекламы («Телефон» в выгрузке CRM), реклама ни при чём",
    "продан раньше даты первой строки (звонок добавлен к заказу позже)":
        "Заказ продан раньше, чем появилась его первая строка в выгрузке CRM (на 2–42 дня). Эта строка это звонок человека уже после продажи, он записан к тому же заказу. "
        "Мы берём датой заказа дату первой строки, поэтому ставим заказ позже, чем он создан. Клиент берёт дату создания заказа, и у него такой заказ попадает в другое время, "
        "часто в прошлый месяц (пример: 076e3f0e продан 08.09, звонок записан 20.10). Даты создания заказа в выгрузке CRM нет",
    "повторная покупка": "Повторная покупка: человек уже покупал раньше",
    "причина неизвестна": "Причина неизвестна",
    "в выгрузке CRM нет ни заказа, ни обращений этого телефона": "В выгрузке CRM нет ни заказа, ни обращений с этим телефоном",
    "заказа с таким номером нет, обращения этого телефона есть": "Заказа с таким номером в выгрузке CRM нет, есть только обращения с этим телефоном",
}


REASON_SHORT = {
    "первое обращение Google SEO (органика), рекламных касаний нет": "SEO, не реклама",
    "первое обращение «Телефон» (60 дн), не рекламный": "первое обращение «Телефон», не реклама",
    "продан раньше даты первой строки (звонок добавлен к заказу позже)": "продан раньше первой строки",
}


def plain_reason(s):
    if s.startswith("правило клиента даёт"):
        return s.replace("правило клиента даёт", "Правило клиента даёт", 1).replace("(вероятно, ручной выбор менеджера)", "(вероятно, менеджер выбрал источник вручную)")
    return REASON_TEXT.get(s, s)


COLNAMES = {
    "Источник заказа (клиент) = вариант А": "Дашборд клиента: источник заказа",
    "А'. Воспроизведение по правилу клиента": "Наш расчёт: источник заказа по схеме клиента",
    "Г. Обращение, привязанное к заказу": "Источник обращения, привязанного к заказу",
    "Б. Первое обращение за всю историю": "Первое обращение за всю историю",
    "Заказ начат": "Чем начат заказ",
    "Дата первой строки (≈ создание) UTC": "Дата первой строки заказа в выгрузке CRM, UTC",
}
REP_COL = "А'. Воспроизведение по правилу клиента"
SRC_ORDER = ["Google Ads", "Facebook", "Нет метки", "Телефон"]
UNCLEAR = [
    "Откуда клиент берёт заказы, которых нет в нашей выгрузке CRM (раздел «Заказы есть в дашборде клиента, а в выгрузке CRM их нет»)? В выгрузке CRM нет ни заказа с таким номером, "
    "а у части нет даже обращений с этим телефоном.",
    "Почему клиент не показывает часть проданных заказов из нашей выгрузки CRM (раздел «причина неизвестна или повторные покупки»)? Отмена и другой период их не объясняют. "
    "Нужен ответ клиента по статусу каждого заказа.",
    "Как менеджер выбирает источник заказа, если он не «Телефон» (4 заказа: у клиента «Нет метки» или «Google Ads», правило даёт «Телефон»)? Мы предполагаем, что менеджер выбрал источник вручную.",
    "По какому правилу клиент считает обращение «новым» во вкладке «Вне обращений»? Список под таблицей клиента показывает меньше заказов, чем сама таблица.",
    "Почему заказы без рекламного следа (форма без метки с direct, organic или без данных Google Analytics; заказ менеджера со звонком через пул «САЙТ») входят в «Итого» рекламного дашборда клиента? "
    "В нашу схему такие заказы тоже входят, потому что клиент их показывает; «нет в данных» не значит «не из рекламы».",
]
LIMITS = [
    "В выгрузке CRM нет даты создания заказа. Дату заказа мы оцениваем: дата продажи, если первая строка заказа позже продажи или раньше продажи больше чем на 7 дней, иначе дата первой строки. "
    "Эта оценка совпала с датой клиента у 74 из 75 общих заказов.",
    "В выгрузке CRM нет товара, количества, площадки и автора заказа. Эти колонки взяты из списка продаж дашборда клиента; у заказов, которых у клиента нет, количество считается равным 1.",
]


def write_html(df, C, a, n_nonad=0):
    """HTML «как у клиента»: таблица по источникам (продажи), список заказов, три списка расхождений, блок «что непонятно»."""
    included = df[(df["Где есть"] == "оба") | ((df["Где есть"] == "только в выгрузке CRM") &
                                               df["Причина расхождения"].isin(["причина неизвестна", "повторная покупка"]))].copy()
    included["qty"] = pd.to_numeric(included["Кол-во"], errors="coerce").fillna(1).astype(int)
    included["rep"] = included[REP_COL].replace("", "Телефон")
    rows = []
    for s in SRC_ORDER:
        cl = C[C["client_source"] == s]
        mine = included[included["rep"] == s]
        rows.append((s, int(cl["qty"].sum()), len(cl), int(mine["qty"].sum()), len(mine)))
    tot = [sum(r[i] for r in rows) for i in (1, 2, 3, 4)]
    def tr(cells, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
    src_tbl = "<table>" + tr(["Источник", "У клиента: продажи (количество товара)", "У клиента: заказов", "У нас по правилу клиента: продажи",
                               "У нас по правилу клиента: заказов"], "th") + "".join(tr(r) for r in rows) + tr(["Итого"] + tot) + "</table>"
    w = f"В. Первое обращение за {a.window} дн"
    cols_client = ["Дата клиента UTC", "Заказ", "Телефон клиента", "Товар", "Кол-во", "Источник заказа (клиент) = вариант А", "Площадка", "Автор", "Причина расхождения"]
    cols_crm = ["Заказ", "Номер заказа в выгрузке CRM", "Дата первой строки (≈ создание) UTC", "Заказ начат", "Статус первой строки", "Дата продажи",
                "Г. Обращение, привязанное к заказу", "Рекламное касание до заказа", "Повторная покупка", "Причина расхождения"]
    cols_crm_short = ["Заказ", "Дата первой строки (≈ создание) UTC", "Заказ начат", "Дата продажи", "Г. Обращение, привязанное к заказу", "Причина расхождения"]
    cols_both = ["Дата клиента UTC", "Заказ", "Источник заказа (клиент) = вариант А", REP_COL, "Заказ начат", "Причина расхождения"]
    cols_all = ["Где есть", "Заказ", "Дата клиента UTC", "Дата первой строки (≈ создание) UTC", "Источник заказа (клиент) = вариант А", REP_COL,
                "Г. Обращение, привязанное к заказу", "Заказ начат", "Статус первой строки", "Дата продажи", "Рекламное касание до заказа", "Повторная покупка",
                "Причина расхождения"]
    def table(d, cs):
        d = d.fillna("").copy()
        cs_show = [COLNAMES.get(c, c) for c in cs]
        d["Причина расхождения"] = d["Причина расхождения"].map(lambda s: s if s in REASON_SHORT.values() else plain_reason(s))
        return "<table>" + tr(cs_show, "th") + "".join(tr([str(x) for x in r]) for r in d.reindex(columns=cs).fillna("").values.tolist()) + "</table>"
    only_c = df[df["Где есть"] == "только у клиента"]
    only_o = df[(df["Где есть"] == "только в выгрузке CRM") & df["Причина расхождения"].isin(["причина неизвестна", "повторная покупка"])]
    expl = df[(df["Где есть"] == "только в выгрузке CRM") & ~df["Причина расхождения"].isin(["причина неизвестна", "повторная покупка"])]
    orders_tbl = df[df["Где есть"].isin(["оба", "только в выгрузке CRM"])].copy()
    orders_tbl["Есть у клиента"] = orders_tbl["Где есть"].map({"оба": "да", "только в выгрузке CRM": "нет"})
    orders_tbl = orders_tbl.sort_values("Дата первой строки (≈ создание) UTC", ascending=False)
    n_ord = len(orders_tbl)
    q_ord = int(pd.to_numeric(orders_tbl["Кол-во"], errors="coerce").fillna(1).astype(int).sum())
    cols_orders = ["Дата первой строки (≈ создание) UTC", "Заказ", "Номер заказа в выгрузке CRM", "Заказ начат", REP_COL, "Источник заказа (клиент) = вариант А",
                   "Есть у клиента", "Товар", "Кол-во", "Площадка", "Автор", "Причина расхождения"]
    mism = df[(df["Где есть"] == "оба") & (df["Причина расхождения"] != "")]
    exp_sum = expl["Причина расхождения"].value_counts().to_dict()
    css = ("body{font-family:system-ui,Segoe UI,Arial;max-width:1200px;margin:24px auto;padding:0 16px;background:#fff;color:#111}"
           "table{border-collapse:collapse;margin:8px 0 24px;font-size:13px}th,td{border:1px solid #ccc;padding:4px 8px;text-align:left}th{background:#f2f2f2}"
           "td{vertical-align:top;max-width:340px;word-break:break-word}h2{margin-top:32px}@media(prefers-color-scheme:dark){body{background:#161616;color:#eee}th{background:#2a2a2a}th,td{border-color:#555}}")
    parts = [f"<html><head><meta charset='utf-8'><title>ProfiMet по схеме клиента</title><style>{css}</style></head><body>",
             f"<h1>ProfiMet: дашборд по схеме клиента, {a.d0} … {a.d1}</h1>",
             "<p>Источник заказа здесь воспроизведён по правилу клиента: если у заказа есть форма, источник берётся из UTM формы, иначе «Телефон». "
             "Сверка идёт по номерам заказов (первые 8 знаков), не по суммам. Данные одного периода, правило проверено только на нём. "
             "Количество товара, площадка и автор взяты из списка продаж дашборда клиента. Проданные заказы выгрузки CRM, которые по правилу клиента к рекламному дашборду не относятся (вкладка «SEO», первое обращение «Телефон», продажа в другом месяце), в реплику не включены: " + str(n_nonad) + ".</p>",
             "<h2>Почему заказы не совпадут с дашбордом клиента</h2><p>Расхождения по номерам заказов будут всегда, пока клиент даёт нам только выгрузку CRM: "
             "1) часть заказов дашборда клиента в выгрузке CRM отсутствует (нет ни заказа, ни обращений) или есть только обращения без заказа с таким номером; "
             "2) часть проданных заказов из выгрузки CRM дашборд клиента не показывает, и причина неизвестна; "
             "3) в выгрузке CRM нет даты создания заказа, товара, количества, площадки и автора, поэтому дату и количество мы угадываем. "
             "Итоги по сумме могут совпасть случайно, поэтому сверка идёт по номерам. Что именно непонятно, описано в разделе «Что непонятно» ниже.</p>",
             "<h2>По источникам (продажи)</h2>", src_tbl,
             f"<h2>Заказы есть в дашборде клиента, а в выгрузке CRM их нет ({len(only_c)})</h2>", table(only_c, cols_client),
             f"<h2>Заказы есть в выгрузке CRM, а клиент их не показывает: причина неизвестна или это повторные покупки ({len(only_o)}). Они входят в нашу таблицу</h2>", table(only_o, cols_crm),
             f"<h2>Заказы, у которых источник в дашборде клиента отличается от того, что даёт правило клиента ({len(mism)})</h2>",
             "<p>Правило клиента: если у заказа есть форма, источник берётся из формы, иначе заказ создал менеджер и источник «Телефон». У этих заказов менеджера клиент поставил другой источник.</p>", table(mism, cols_both),
             "<h2>Что непонятно</h2><ol>" + "".join(f"<li>{u}</li>" for u in UNCLEAR) + "</ol>",
             f"<h2>Заказы по схеме клиента, посчитанные по данным нашей выгрузки CRM: {n_ord} шт. / {q_ord} ед.</h2>",
             "<p>Это не копия списка клиента. Мы применили правила, которые использует клиент (как мы их поняли), к данным нашей выгрузки CRM. "
             "Поэтому в этой таблице есть заказы, которых нет в дашборде клиента (колонка «Есть у клиента»: нет), и нет заказов клиента, которых нет в выгрузке CRM "
             "(они в списке выше). Товар, количество, площадка и автор есть только у заказов, которые есть у клиента; у остальных количество считается равным 1.</p>",
             table(orders_tbl, cols_orders), "</body></html>"]
    path = client_stats_dir("ProfiMet") / f"dashboard_client_replica_{a.d0}_{a.d1}.html"
    path.write_text(chr(10).join(parts), encoding="utf-8")
    print("HTML:", path)
    return path


def write_html_scheme(scheme, diff, cl, a):
    """HTML на единой схеме (та же, что в profimet_sources_dashboard.client_scheme_orders): заказы по схеме клиента из нашей выгрузки CRM + расхождения."""
    css = ("body{font-family:system-ui,Segoe UI,Arial;max-width:1200px;margin:24px auto;padding:0 16px;background:#fff;color:#111}"
           "table{border-collapse:collapse;margin:8px 0 24px;font-size:13px}th,td{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top;max-width:340px;word-break:break-word}"
           "th{background:#f2f2f2}h2{margin-top:32px}@media(prefers-color-scheme:dark){body{background:#161616;color:#eee}th{background:#2a2a2a}th,td{border-color:#555}}")
    def tr(cells, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
    def tbl(d, cols):
        d = d.fillna("")
        return "<table>" + tr(cols, "th") + "".join(tr([str(x) for x in r]) for r in d[cols].values.tolist()) + "</table>"
    m = scheme.merge(cl, on="key", how="left")
    m["Есть у клиента"] = ["да" if isinstance(x, str) and x else "нет" for x in m["client_source"]]
    m["qty_show"] = m["qty_x"] if "qty_x" in m else m["qty"]
    m["Дата заказа (оценка) UTC"] = m["est"].dt.strftime("%Y-%m-%d %H:%M")
    m = m.sort_values("est", ascending=False)
    rows = []
    for s in SRC_ORDER:
        c = cl[cl["client_source"] == s]
        o = m[m["rule"] == s]
        rows.append((s, int(c["qty"].sum()), len(c), int(o["qty_show"].sum()), len(o)))
    tot = [sum(r[i] for r in rows) for i in (1, 2, 3, 4)]
    src_tbl = "<table>" + tr(["Источник", "У клиента: продажи (количество товара)", "У клиента: заказов", "По схеме клиента на нашей выгрузке: продажи",
                               "По схеме клиента на нашей выгрузке: заказов"], "th") + "".join(tr(r) for r in rows) + tr(["Итого"] + tot) + "</table>"
    groups = {k: diff[diff["Раздел"] == k] for k in diff["Раздел"].unique()}
    parts = [f"<html><head><meta charset='utf-8'><title>ProfiMet по схеме клиента</title><style>{css}</style></head><body>",
             f"<h1>ProfiMet: рекламный дашборд по схеме клиента, {a.d0} … {a.d1}</h1>",
             "<p>Мы применили к данным нашей выгрузки CRM правила, которые использует клиент (как мы их поняли): если у заказа есть форма, источник берётся из формы, иначе "
             "заказ создал менеджер и источник «Телефон». Поэтому у нас есть заказы, которых нет в дашборде клиента, и наоборот. Сверка идёт по номерам заказов, не по суммам. "
             "Данные одного периода. Заказы вкладки «SEO», заказы с первым обращением «Телефон» без формы и заказы, проданные раньше первой строки в выгрузке CRM, в схему не входят.</p>",
             "<h2>По источникам (продажи)</h2>", src_tbl,
             "<p>Как считается источник заказа в нашем расчёте: если у заказа есть форма, источник берётся из формы (Google Ads, Facebook, иначе «Нет метки»); если формы нет, заказ создал менеджер, и источник «Телефон». Это правило выведено из данных клиента: оно совпало с его источником у 70 из 74 заказов, у остальных четырёх менеджер, вероятно, выбрал источник вручную. Первое обращение человека (за 60 дней или за всю историю) для источника заказа клиент не использует: такие правила совпали бы только примерно у половины заказов.</p>"]
    m = m.reset_index(drop=True)
    m["№"] = range(1, len(m) + 1)
    parts += [f"<h2>Заказы по схеме клиента: {len(m)} шт. / {int(m['qty_show'].sum())} ед.</h2>",
              tbl(m.assign(**{"Заказ": m["key"], "Кол-во": m["qty_show"], "Телефон": m["phone"], "Товар": m["product"],
                              "Наш расчёт: источник заказа по схеме клиента": m["rule"], "Дашборд клиента: источник заказа": m["client_source"],
                              "Площадка": m["platform"], "Автор": m["author"]}),
                  ["№", "Дата заказа (оценка) UTC", "Заказ", "Телефон", "Товар", "Кол-во", "Наш расчёт: источник заказа по схеме клиента",
                   "Дашборд клиента: источник заказа", "Есть у клиента", "Площадка", "Автор"])]
    dcols = ["Дата", "Заказ", "Дашборд клиента: источник заказа", "Наш расчёт: источник заказа по схеме клиента", "Первое обращение за 60 дней",
             "Было рекламное касание", "Причина"]
    for k, title in (("Есть у клиента, нет у нас", "Заказы есть в дашборде клиента, а в выгрузке CRM их нет ({n}). В нашу таблицу они не входят"),
                     ("Есть у нас, нет у клиента", "Заказы есть в выгрузке CRM, а клиент их не показывает: причина неизвестна или это повторные покупки ({n}). Они входят в нашу таблицу"),
                     ("Источник у клиента другой", "Заказы, у которых источник в дашборде клиента отличается от того, что даёт правило клиента ({n})")):
        g = groups.get(k)
        if g is not None and len(g):
            parts += [f"<h2>{title.format(n=len(g))}</h2>", tbl(g.rename(columns={"Источник у клиента": "Дашборд клиента: источник заказа"}), dcols)]
    parts += ["<h2>Что нужно выяснить у клиента</h2><ol>" + "".join(f"<li>{u}</li>" for u in UNCLEAR) + "</ol>",
              "<h2>Ограничения данных</h2><ul>" + "".join(f"<li>{u}</li>" for u in LIMITS) + "</ul>", "</body></html>"]
    path = client_stats_dir("ProfiMet") / f"dashboard_client_replica_{a.d0}_{a.d1}.html"
    path.write_text(chr(10).join(parts), encoding="utf-8")
    print("HTML:", path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-list", required=True)
    ap.add_argument("--from", dest="d0", default="2026-10-01")
    ap.add_argument("--to", dest="d1", default="2026-10-20")
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--repeat-days", type=int, default=7)
    a = ap.parse_args()
    t0 = pd.Timestamp(a.d0, tz="UTC")
    t1 = pd.Timestamp(a.d1, tz="UTC") + pd.Timedelta(days=1)

    sheet = load_sheet(SHEET_ID).sort_values("ts", kind="mergesort")
    pm = sheet[~sheet["site"].isin(PM_SITES_EXCLUDE)].copy()
    O = our_orders(pm)
    sold = O[O["sale_d"].notna() & ~O["cancelled"]]
    C = read_client(a.client_list)
    by_key = O.drop_duplicates("key").set_index("key")

    def our_for_client(r):
        if r["key"] in by_key.index:
            return by_key.loc[r["key"]], "по номеру"
        cand = O[(O["p9"] == r["p9"]) & ((O["created"] - r["client_date"]).abs() <= pd.Timedelta(days=1.2))]
        if len(cand):
            return cand.iloc[0], "по телефону и дате"
        return None, "не найден"

    rows = []
    nonad = []
    used = set()
    for _, r in C.iterrows():
        o, how = our_for_client(r)
        row = {"Где есть": "оба" if o is not None else "только у клиента", "Как найден в выгрузке CRM": how,
               "Дата клиента UTC": r["client_date"].strftime("%Y-%m-%d %H:%M"), "Заказ": r["key"], "Телефон клиента": r["client_phone"],
               "Товар": r["product"], "Кол-во": r["qty"], "Источник заказа (клиент) = вариант А": r["client_source"], "UTM": r["client_utm"],
               "Площадка": r["platform"], "Автор": r["author"]}
        if o is not None:
            used.add(o["order"])
        rows.append((row, o, r["p9"], r["client_date"], r["client_source"]))
    for _, o in sold[(sold["created"] >= t0) & (sold["created"] < t1)].iterrows():
        if o["order"] in used or o["key"] in set(C["key"]):
            continue
        h0 = pm[(pm["p9"] == o["p9"]) & (pm["ts"] <= o["created"] + pd.Timedelta(minutes=3))]
        if o["sites"] == "szklarniaprofimet.pl" or (o["first_src"] == "Google SEO" and not len(h0[h0["src"].isin(ADS) | h0["gclid"].ne("")])):
            nonad.append(o["key"])  # заказ вкладки «SEO» (второй сайт или первое обращение Google SEO без рекламы): в «Ads + FB» не входит
            continue
        row = {"Где есть": "только в выгрузке CRM", "Как найден в выгрузке CRM": "", "Дата клиента UTC": "", "Заказ": o["key"],
               "Телефон клиента": "", "Товар": "", "Кол-во": "", "Источник заказа (клиент) = вариант А": "", "UTM": "", "Площадка": "", "Автор": ""}
        rows.append((row, o, o["p9"], o["created"], ""))

    out = []
    for row, o, p9, cdate, csrc in rows:
        if o is None:
            ph = pm[pm["p9"] == p9]
            row["Причина расхождения"] = ("в выгрузке CRM нет ни заказа, ни обращений этого телефона" if ph.empty
                                          else "заказа с таким номером нет, обращения этого телефона есть")
            out.append(row)
            continue
        p9o = o["p9"]
        og = pm[pm["order"] == o["order"]].sort_values("ts", kind="mergesort")
        fo = og[og["type"] == "форма"]
        rep_src = ((fo.iloc[0]["src"] if fo.iloc[0]["src"] in ADS else "Нет метки") if len(fo) else "Телефон")
        hist = pm[(pm["p9"] == p9o) & (pm["ts"] <= o["created"] + pd.Timedelta(minutes=3))]
        w = hist[hist["ts"] >= o["created"] - pd.Timedelta(days=a.window)]
        b = (hist.iloc[0]["src"] or "Нет метки") if len(hist) else "нет в выгрузке CRM"
        v = (w.iloc[0]["src"] or "Нет метки") if len(w) else "нет в выгрузке CRM"
        ad = hist[hist["src"].isin(ADS) | hist["gclid"].ne("")]
        prev = sold[(sold["p9"] == p9o) & (sold["order"] != o["order"]) &
                    (sold["sale_d"].dt.tz_localize("UTC") <= o["created"] - pd.Timedelta(days=a.repeat_days))]
        row.update({"Номер заказа в выгрузке CRM": o["order"], "Телефон в выгрузке CRM": o["phone"],
                    "Дата первой строки (≈ создание) UTC": o["created"].strftime("%Y-%m-%d %H:%M"), "Заказ начат": o["first_type"],
                    "Статус первой строки": o["status_first"], "Дата продажи": o["sale"], "Дата отмены": o["cancel"],
                    f"Б. Первое обращение за всю историю": b, f"В. Первое обращение за {a.window} дн": v,
                    "А'. Воспроизведение по правилу клиента": rep_src, "Г. Обращение, привязанное к заказу": o["first_src"], "Рекламное касание до заказа": "да" if len(ad) else "нет",
                    "Повторная покупка": "да" if len(prev) else "нет"})
        reason = ""
        if row["Где есть"] == "только в выгрузке CRM":
            if o["sale"] and pd.Timestamp(o["sale"]) < o["created"].tz_convert(None).normalize() - pd.Timedelta(days=1):
                reason = "продан раньше даты первой строки (звонок добавлен к заказу позже)"
            elif "Google SEO" in (v, o["first_src"]) and not len(ad):
                reason = "первое обращение Google SEO (органика), рекламных касаний нет"
            elif len(prev):
                reason = "повторная покупка"
            elif v == "Телефон":
                reason = f"первое обращение «Телефон» ({a.window} дн), не рекламный"
            else:
                reason = "причина неизвестна"
        else:
            if csrc != rep_src:
                reason = f"правило клиента даёт «{rep_src}», у клиента «{csrc}» (вероятно, ручной выбор менеджера)"
        row["Причина расхождения"] = reason
        out.append(row)

    df = pd.DataFrame(out)
    # Реплика только рекламного дашборда: заказы выгрузки CRM, которые по правилу клиента к нему не относятся (первое обращение «Телефон»,
    # продажа в другом месяце), в реплику не входят.
    keep = ["причина неизвестна", "повторная покупка"]
    drop = (df["Где есть"] == "только в выгрузке CRM") & ~df["Причина расхождения"].isin(keep)
    n_out = int(drop.sum()) + len(nonad)
    df = df[~drop].reset_index(drop=True)
    from profimet_sources_dashboard import client_scheme_orders, read_client_list
    cl = read_client_list(a.client_list)
    scheme, diff = client_scheme_orders(sheet.reset_index(drop=True), cl, a.d0, a.d1)
    html_path = write_html_scheme(scheme, diff, cl, a)
    print(f"По единой схеме: заказов {len(scheme)}, количество товара {int(scheme['qty'].sum())}; расхождений {len(diff)}")
    path = client_stats_dir("ProfiMet") / f"orders_replica_{a.d0}_{a.d1}.csv"
    df["Причина расхождения"] = df["Причина расхождения"].map(plain_reason)
    df.rename(columns=COLNAMES).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Период {a.d0} … {a.d1}; заказов у клиента {len(C)}, всего строк {len(df)}; не относится к рекламному дашборду (не включены): {len(nonad)}")
    print(df["Где есть"].value_counts().to_string())
    for who in ("только у клиента", "только в выгрузке CRM"):
        x = df[df["Где есть"] == who]["Причина расхождения"].value_counts()
        print(f"\nПричины, {who}:\n{x.to_string()}")
    both = df[df["Где есть"] == "оба"]
    print(f"\nУ обеих сторон: {len(both)}; правило клиента не воспроизвело источник: {int((both['Причина расхождения'] != '').sum())}")
    print("\nCSV:", path)


if __name__ == "__main__":
    main()
