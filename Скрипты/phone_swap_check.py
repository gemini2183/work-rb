#!/usr/bin/env python
# coding: utf-8
"""Проверка подмены номера телефона (коллтрекинг) на сайте по UTM-меткам.

Открывает сайт клиента через headless-браузер (Playwright) с заданной
комбинацией UTM-параметров в URL, снимает все tel:-ссылки со страницы после
полной подгрузки JS (подмена делается на клиенте скриптом коллтрекинга —
Ringostat/Calltouch/CoMagic/Callibri и т.п., в исходном HTML её не видно, см.
`Клиенты/Юристы США/Решения.md`, запись 2026-08-18), и сверяет с ожидаемым
номером из ручного файла пула клиента.

Пул номеров — ручной YAML в `Клиенты/<client_folder>/Коллтрекинг/Пул_номеров.yaml`,
формат:

    url: "https://example.com/"
    default: "+18444529465"          # номер без UTM / для нераспознанного источника
    pool:
      - utm: {utm_source: google, utm_medium: cpc}
        expected: "+18883783267"
      - utm: {utm_source: yandex, utm_medium: cpc}
        expected: "+18001234567"

Использование:
    python phone_swap_check.py --client-folder "Юристы США"
    python phone_swap_check.py --client-folder "Юристы США" --pool-file "Коллтрекинг/Пул_номеров_desert.yaml"
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import yaml
from playwright.sync_api import sync_playwright

from _config import VAULT_ROOT

TEL_RE = re.compile(r"tel:([0-9+%]+)")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def normalize_phone(raw: str) -> str:
    """%20 и прочий мусор из tel: убираем, оставляем только цифры и ведущий +."""
    decoded = raw.replace("%20", "").replace("%2B", "+")
    digits = re.sub(r"[^\d+]", "", decoded)
    return digits


def grab_tel_numbers(page, url: str, wait_ms: int) -> set[str]:
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(wait_ms)
    html = page.content()
    raw_matches = TEL_RE.findall(html)
    numbers = {normalize_phone(m) for m in raw_matches}
    # артефакты незавершённого JS-рендера (напр. "tel:+1+1") отбрасываем
    return {n for n in numbers if len(re.sub(r"\D", "", n)) >= 10}


def check_one(page, base_url: str, utm: dict, expected: str, wait_ms: int) -> dict:
    url = base_url if not utm else f"{base_url}?{urlencode(utm)}"
    numbers = grab_tel_numbers(page, url, wait_ms)
    expected_norm = normalize_phone(expected)
    ok = expected_norm in numbers
    return {
        "utm": utm,
        "url": url,
        "expected": expected,
        "found": sorted(numbers),
        "ok": ok,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--pool-file", default="Коллтрекинг/Пул_номеров.yaml", help="Путь относительно папки клиента")
    ap.add_argument("--wait-ms", type=int, default=5000, help="Пауза после networkidle для JS-подмены номера")
    args = ap.parse_args()

    pool_path = VAULT_ROOT / "Клиенты" / args.client_folder / args.pool_file
    if not pool_path.exists():
        print(f"Файл пула не найден: {pool_path}")
        print("Создай его вручную по формату из docstring этого скрипта.")
        sys.exit(1)

    with open(pool_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    base_url = config["url"]
    default_expected = config.get("default")
    pool = config.get("pool", [])

    cases = []
    if default_expected:
        cases.append({"utm": {}, "expected": default_expected})
    for entry in pool:
        cases.append({"utm": entry["utm"], "expected": entry["expected"]})

    if not cases:
        print("В пуле нет ни 'default', ни записей 'pool' — нечего проверять.")
        sys.exit(1)

    print(f"Клиент: {args.client_folder} | сайт: {base_url} | случаев: {len(cases)}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA)
        for case in cases:
            res = check_one(page, base_url, case["utm"], case["expected"], args.wait_ms)
            results.append(res)
            status = "OK" if res["ok"] else "MISMATCH"
            label = res["utm"] or "(без UTM / default)"
            print(f"[{status}] {label} -> ожидали {res['expected']}, нашли {res['found']}")
        browser.close()

    mismatches = [r for r in results if not r["ok"]]

    out_dir = VAULT_ROOT / "Клиенты" / args.client_folder / "Статистика"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = out_dir / f"phone_swap_check_{timestamp}.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("utm,expected,found,ok\n")
        for r in results:
            utm_str = ";".join(f"{k}={v}" for k, v in r["utm"].items()) or "default"
            found_str = "|".join(r["found"])
            f.write(f'"{utm_str}","{r["expected"]}","{found_str}",{r["ok"]}\n')

    print(f"\nСохранено: {out_path}")
    if mismatches:
        print(f"\n{len(mismatches)} из {len(results)} случаев НЕ прошли проверку.")
        sys.exit(1)
    else:
        print("\nВсе случаи прошли проверку.")


if __name__ == "__main__":
    main()
