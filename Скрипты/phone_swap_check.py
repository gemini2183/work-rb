#!/usr/bin/env python
# coding: utf-8
"""Проверка подмены номера телефона (коллтрекинг) на сайте по UTM-меткам.

Открывает сайт клиента через headless-браузер (Playwright) с тестовой
комбинацией UTM-параметров в URL, снимает номера телефонов со страницы после
полной подгрузки JS (подмена делается на клиенте скриптом коллтрекинга —
Ringostat/Calltouch/CoMagic/Callibri и т.п., в исходном HTML её не видно, см.
`Клиенты/Юристы США/Решения.md`, запись 2026-08-18), и сверяет с пулом
допустимых номеров канала.

Номера ищутся в двух источниках: (1) tel:-ссылки по всему HTML, (2) видимый
посетителю текст страницы (page.inner_text — рендеренный текст видимых
элементов, БЕЗ содержимого <script>/<style>/скрытых блоков). Второй источник
нужен, чтобы поймать номер, показанный просто текстом без ссылки. Важно
использовать именно видимый текст, а не искать по всему HTML — иначе ловятся
ложные срабатывания на statичные номера в schema.org JSON-LD разметке и
номера, зашитые как строковые константы внутри кода самого скрипта
коллтрекинга (оба случая найдены на landverpersonalinjury.com, 2026-08-18 —
не место реального показа номера, попадать в сверку не должны).

Сервисы коллтрекинга (проверено на Ringostat, 2026-08-18) отдают номер ИЗ
ПУЛА по сессии/ротации, не жёстко 1 UTM = 1 номер — поэтому сверка идёт не с
одним ожидаемым номером, а со списком номеров пула канала: совпадение с
ЛЮБЫМ из них считается корректным.

Пул номеров — ручной YAML в `Клиенты/<client_folder>/Коллтрекинг/Пул_номеров.yaml`
(заполняется по скриншотам из кабинета сервиса коллтрекинга — публичного API
для выгрузки правил подмены и пулов у Ringostat нет), формат:

    url: "https://example.com/"
    default: "+18444529465"          # номер без UTM / вне зоны действия каналов
    channels:
      - name: "Google Ads"
        utm_test: {utm_source: google, utm_medium: cpc}   # конкретная комбинация для прогона
        pool: ["+18883783267", "+18883448725", "+18883025461"]
      - name: "SEO"
        utm_test: {utm_source: google, utm_medium: organic}
        pool: ["+18001234567"]

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
# видимый текст: разрешаем пробелы/скобки/дефисы между цифрами (написание
# "+1 844 452 9465" или "(888) 352-9465"), не только слитную запись
VISIBLE_PHONE_RE = re.compile(r"\+?1?[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def normalize_phone(raw: str) -> str:
    """Пробелы/скобки/дефисы/%20 убираем, оставляем только цифры и ведущий +."""
    decoded = raw.replace("%20", "").replace("%2B", "+")
    digits = re.sub(r"[^\d+]", "", decoded)
    return digits


def grab_numbers(page, url: str, wait_ms: int) -> set[str]:
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(wait_ms)

    html = page.content()
    tel_matches = TEL_RE.findall(html)

    # только видимый посетителю текст — НЕ весь HTML, иначе ловятся
    # статичные номера в schema.org JSON-LD и внутри кода <script> самого
    # скрипта коллтрекинга (не место реального показа номера)
    visible_text = page.inner_text("body")
    visible_matches = VISIBLE_PHONE_RE.findall(visible_text)

    numbers = {normalize_phone(m) for m in tel_matches + visible_matches}
    # артефакты незавершённого JS-рендера (напр. "tel:+1+1") отбрасываем
    return {n for n in numbers if len(re.sub(r"\D", "", n)) >= 10}


def check_one(page, base_url: str, utm: dict, pool: list[str], wait_ms: int) -> dict:
    url = base_url if not utm else f"{base_url}?{urlencode(utm)}"
    numbers = grab_numbers(page, url, wait_ms)
    pool_norm = {normalize_phone(p) for p in pool}
    matched = numbers & pool_norm
    ok = bool(matched) if pool_norm else False
    return {
        "utm": utm,
        "url": url,
        "pool": pool,
        "found": sorted(numbers),
        "matched": sorted(matched),
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
    channels = config.get("channels", [])

    cases = []
    if default_expected:
        cases.append({"name": "default", "utm": {}, "pool": [default_expected]})
    for ch in channels:
        pool = ch.get("pool") or []
        if not pool:
            print(f"[SKIP] канал '{ch.get('name')}' — пул пуст, пропускаю")
            continue
        cases.append({"name": ch.get("name", "?"), "utm": ch["utm_test"], "pool": pool})

    if not cases:
        print("Нет ни 'default', ни каналов с непустым пулом — нечего проверять.")
        sys.exit(1)

    print(f"Клиент: {args.client_folder} | сайт: {base_url} | случаев: {len(cases)}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA)
        for case in cases:
            res = check_one(page, base_url, case["utm"], case["pool"], args.wait_ms)
            res["name"] = case["name"]
            results.append(res)
            status = "OK" if res["ok"] else "MISMATCH"
            label = f"{case['name']} {res['utm'] or '(без UTM)'}"
            print(f"[{status}] {label} -> пул {res['pool']}, нашли {res['found']}")
        browser.close()

    mismatches = [r for r in results if not r["ok"]]

    out_dir = VAULT_ROOT / "Клиенты" / args.client_folder / "Статистика"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = out_dir / f"phone_swap_check_{timestamp}.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("channel,utm,pool,found,matched,ok\n")
        for r in results:
            utm_str = ";".join(f"{k}={v}" for k, v in r["utm"].items()) or "default"
            pool_str = "|".join(r["pool"])
            found_str = "|".join(r["found"])
            matched_str = "|".join(r["matched"])
            f.write(f'"{r["name"]}","{utm_str}","{pool_str}","{found_str}","{matched_str}",{r["ok"]}\n')

    print(f"\nСохранено: {out_path}")
    if mismatches:
        print(f"\n{len(mismatches)} из {len(results)} случаев НЕ прошли проверку.")
        sys.exit(1)
    else:
        print("\nВсе случаи прошли проверку.")


if __name__ == "__main__":
    main()
