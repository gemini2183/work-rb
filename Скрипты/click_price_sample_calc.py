#!/usr/bin/env python
# coding: utf-8
"""Допустимая цена клика и объём теста по конверсии клик/визит -> заявка. ТОЛЬКО РАСЧЁТ (API не вызывает, пишет только в --out).

Зачем: площадка с оплатой за клик/переход (статьи, объявления, любые тесты). Нужно знать, сколько можно платить за клик
при целевой цене заявки, сколько кликов и денег нужно, чтобы тест дал вывод, и когда остановить расход без заявок.

Что считает:
  1) конверсия визит -> заявка = leads / visits, интервал Уилсона 80 и 95 % (формула как в sales_pace.wilson);
     заявок < 10 -> предупреждение «данных мало» и чем это грозит;
  2) допустимая цена клика = цена заявки без НДС x конверсия визит->заявка x визитов на клик (центр и границы интервала);
  3) на один тест: клики, чтобы ожидаемых заявок >= --min-leads-per-test (центр и нижняя граница), бюджет теста,
     сколько тестов покрывает --budget;
  4) стоп-правило (Алгоритм_анализа_кампании, 2.6): P(0 заявок) = exp(-S/A), S - расход, A - допустимая цена заявки;
  5) допущения.

Режимы: один, только расчёт. Файл пишется только если задан --out (CSV, UTF-8 с BOM).

Пример (контрольные числа, не боевые):
  PYTHONUTF8=1 python click_price_sample_calc.py --target-cpa 2500 --cpa-includes-vat true --vat-rate 0.22 \\
      --leads 7 --visits 600 --clicks 650 --budget 50000 --tests 5 --out check.csv

Дата: 2026-11-18.
"""
import argparse
import csv
import math
import sys

Z = {80: 1.2816, 95: 1.96}      # 95 % - как Z в sales_pace.py
FRACS = [0.5, 1, 1.5, 2, 3]


def wilson(k, n, z):
    """Интервал Уилсона - тот же расчёт, что sales_pace.wilson."""
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(c - h, 0.0), min(c + h, 1.0)


def tbool(s):
    s = str(s).strip().lower()
    if s in ("true", "1", "yes", "да"):
        return True
    if s in ("false", "0", "no", "нет"):
        return False
    raise argparse.ArgumentTypeError("нужно true или false")


def f(v, nd=2):
    if v is None:
        return "-"
    if v == float("inf"):
        return "не определено (конверсия 0)"
    return f"{v:,.{nd}f}".replace(",", " ")


def pct(v):
    return "-" if v is None else f"{v * 100:.2f} %"


def main():
    ap = argparse.ArgumentParser(description="Допустимая цена клика и объём теста (только расчёт).")
    ap.add_argument("--target-cpa", type=float, required=True, help="целевая цена заявки")
    ap.add_argument("--cpa-includes-vat", type=tbool, required=True, help="true|false: сумма в --target-cpa с НДС")
    ap.add_argument("--vat-rate", type=float, required=True, help="ставка НДС, например 0.22 (значения по умолчанию нет)")
    ap.add_argument("--leads", type=int, required=True, help="заявки за период")
    ap.add_argument("--visits", type=int, required=True, help="визиты за тот же период")
    ap.add_argument("--clicks", type=int, default=None, help="платные клики/переходы за период (нет - визитов на клик = 1)")
    ap.add_argument("--budget", type=float, default=None, help="бюджет тестов (в тех же деньгах, что цена клика, без НДС)")
    ap.add_argument("--tests", type=int, default=None, help="число одновременных тестов")
    ap.add_argument("--min-leads-per-test", type=float, default=3, help="минимум ожидаемых заявок на тест (по умолчанию 3)")
    ap.add_argument("--conf", type=int, nargs="*", default=[80, 95], choices=[80, 95], help="уровни (по умолчанию оба)")
    ap.add_argument("--out", default=None, help="CSV с результатами")
    a = ap.parse_args()

    if a.visits <= 0 or a.leads < 0 or a.leads > a.visits or a.target_cpa <= 0 or a.vat_rate < 0:
        sys.exit("Проверьте входы: visits>0, 0<=leads<=visits, target-cpa>0, vat-rate>=0.")
    rows = []   # (раздел, показатель, значение)
    notes = []

    cpa = a.target_cpa / (1 + a.vat_rate) if a.cpa_includes_vat else a.target_cpa
    print("=== Входы ===")
    print(f"Цена заявки: {f(a.target_cpa)} ({'с НДС' if a.cpa_includes_vat else 'без НДС'}); НДС {a.vat_rate * 100:.1f} %"
          f" -> цена заявки без НДС = {f(cpa)}")
    print(f"Заявки {a.leads}, визиты {a.visits}, клики {a.clicks if a.clicks else 'не заданы'}")
    rows += [("вход", "цена заявки без НДС", cpa), ("вход", "заявки", a.leads), ("вход", "визиты", a.visits)]

    # 1. конверсия
    p = a.leads / a.visits
    iv = {c: wilson(a.leads, a.visits, Z[c]) for c in a.conf}
    print("\n=== 1. Конверсия визит -> заявка ===")
    print(f"Центр: {a.leads} / {a.visits} = {pct(p)}")
    for c in a.conf:
        print(f"Интервал Уилсона {c} %: {pct(iv[c][0])} ... {pct(iv[c][1])}")
        rows += [(f"конверсия {c}%", "нижняя", iv[c][0]), (f"конверсия {c}%", "верхняя", iv[c][1])]
    rows.append(("конверсия", "центр", p))
    if a.leads < 10:
        print(f"ВНИМАНИЕ: заявок {a.leads} < 10 - данных мало. Интервал очень широкий; цена клика и объём теста ниже "
              f"могут отличаться от реальных в разы: рискуем либо переплатить за клик, либо недобрать трафик.")
        notes.append("заявок < 10")

    # визитов на клик
    if a.clicks and a.clicks > 0:
        vpc = a.visits / a.clicks
        print(f"Визитов на клик = {a.visits} / {a.clicks} = {vpc:.3f}")
    else:
        vpc = 1.0
        print("Оговорка: --clicks не задан, визитов на клик принято 1.0 (каждый платный клик = один визит). "
              "Если клики и визиты различаются (боты, отказы до загрузки), цена клика будет завышена.")
        notes.append("визитов на клик = 1 (допущение)")
    rows.append(("вход", "визитов на клик", vpc))

    # 2. цена клика
    price_c = cpa * p * vpc
    print("\n=== 2. Допустимая цена клика ===")
    print("Формула: цена клика = цена заявки без НДС x конверсия визит->заявка x визитов на клик")
    print(f"Центр: {f(cpa)} x {pct(p)} x {vpc:.3f} = {f(price_c, 4)}")
    rows.append(("цена клика", "центр", price_c))
    price_lo = {}
    for c in a.conf:
        lo, hi = iv[c]
        price_lo[c] = cpa * lo * vpc
        print(f"{c} %: нижняя {f(cpa)} x {pct(lo)} x {vpc:.3f} = {f(price_lo[c], 4)};  "
              f"верхняя {f(cpa)} x {pct(hi)} x {vpc:.3f} = {f(cpa * hi * vpc, 4)}")
        rows += [(f"цена клика {c}%", "нижняя", price_lo[c]), (f"цена клика {c}%", "верхняя", cpa * hi * vpc)]
    print("Платить по центру безопасно, только если конверсия действительно у центра; по нижней границе - гарантия, "
          "что не переплатим при худшей конверсии из интервала.")

    # 3. тесты
    m = a.min_leads_per_test
    print(f"\n=== 3. Один тест: ожидаемых заявок >= {m:g} ===")
    clicks_c = m / (p * vpc) if p > 0 else float("inf")
    budget_c = clicks_c * price_c if p > 0 else float("inf")
    print(f"Центр: клики = {m:g} / ({pct(p)} x {vpc:.3f}) = {f(clicks_c, 0)}; бюджет = клики x цена клика = {f(budget_c)}"
          f" (= {m:g} x цена заявки)")
    rows += [("тест", "клики, центр", clicks_c), ("тест", "бюджет, центр", budget_c)]
    budgets = {"центр": budget_c}
    for c in a.conf:
        lo = iv[c][0]
        cl = m / (lo * vpc) if lo > 0 else float("inf")
        bud = cl * price_c if lo > 0 else float("inf")
        budgets[f"нижняя {c}%"] = bud
        print(f"Нижняя граница {c} %: клики = {m:g} / ({pct(lo)} x {vpc:.3f}) = {f(cl, 0)}; "
              f"бюджет при цене клика центра = {f(bud)}")
        rows += [(f"тест нижняя {c}%", "клики", cl), (f"тест нижняя {c}%", "бюджет", bud)]
    if a.budget is not None:
        print(f"\nБюджет {f(a.budget)}" + (f", тестов одновременно {a.tests}" if a.tests else ""))
        for k, b in budgets.items():
            n = a.budget // b if b not in (0, float("inf")) else 0
            line = f"  по сценарию «{k}»: бюджет теста {f(b)} -> покрывает {int(n)} тест(ов)"
            if a.tests:
                line += f"; на {a.tests} тест(ов) нужно {f(b * a.tests)}" + (" - ХВАТАЕТ" if n >= a.tests else " - НЕ ХВАТАЕТ")
            print(line)
            rows.append(("бюджет", f"тестов покрыто, {k}", n))
    elif a.tests:
        for k, b in budgets.items():
            print(f"  на {a.tests} тест(ов) по сценарию «{k}» нужно {f(b * a.tests)}")

    # 4. стоп-правило
    print("\n=== 4. Стоп-правило: P(0 заявок) = exp(-S / A) ===")
    print("S - расход на тест, A - допустимая цена заявки (без НДС). При нижней границе конверсии при цене клика центра "
          "реальная цена заявки A_eff = A x конверсия_центр / конверсия_нижняя.")
    hdr = f"{'S / A':>6} | {'S':>12} | {'P(0), центр':>12}"
    for c in a.conf:
        hdr += f" | {'P(0), ниж. ' + str(c) + '%':>16}"
    print(hdr)
    for fr in FRACS:
        S = fr * cpa
        p0 = math.exp(-S / cpa)
        line = f"{fr:>6g} | {f(S):>12} | {p0 * 100:>11.1f}%"
        rows.append(("стоп", f"S={fr}A, центр", p0))
        for c in a.conf:
            lo = iv[c][0]
            if lo > 0:
                aeff = cpa * p / lo
                pl = math.exp(-S / aeff)
            else:
                pl = 1.0
            line += f" | {pl * 100:>15.1f}%"
            rows.append(("стоп", f"S={fr}A, нижняя {c}%", pl))
        print(line)
    print("Читать: если после расхода S заявок 0, а P(0) уже мала (например < 5-10 %), конверсия, вероятно, ниже допустимой "
          "- останавливать. Пока P(0) велика, отсутствие заявок ничего не доказывает.")

    # 5. допущения
    print("\n=== 5. Допущения ===")
    for t in [
        f"НДС {a.vat_rate * 100:.1f} %: цена заявки приводится к цене без НДС"
        + (" (делением на 1+ставка)" if a.cpa_includes_vat else " (задана без НДС)")
        + "; цена клика и бюджет считаются в тех же деньгах без НДС - если площадка берёт НДС сверху, пересчитайте.",
        "Конверсия визит->заявка одинакова для всех статей/объявлений теста (на деле различается - скрипт этого не проверяет).",
        "Визиты и заявки независимы; заявка пуассоновская, визиты биномиальны - без учёта повторных визитов и дней недели.",
        "Конверсия и визитов на клик взяты из исходного периода и считаются постоянными; сезонность, смена аудитории и "
        "позиции, цена клика по факту аукциона скрипту неизвестны.",
        "Скрипт не знает, сколько кликов площадка реально продаст по этой цене клика и какой у неё минимальный порог ставки.",
        "Заявка = тот же стандарт, что в исходных заявках (не проверяется; дубли и качество заявок не учтены).",
    ]:
        print(" - " + t)
    if notes:
        print("Оговорки этого прогона: " + "; ".join(notes))

    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["раздел", "показатель", "значение"])
            for r in rows:
                w.writerow(r)
        print(f"\nCSV: {a.out}")


if __name__ == "__main__":
    main()
