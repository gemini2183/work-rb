#!/usr/bin/env python
# coding: utf-8
"""Проверка подмены номера телефона (коллтрекинг) на сайте по UTM-меткам.

Открывает сайт клиента через headless-браузер (Playwright) с тестовой
комбинацией UTM-параметров в URL, снимает номера телефонов со страницы после
полной подгрузки JS (подмена делается на клиенте скриптом коллтрекинга —
Ringostat/Calltouch/CoMagic/Callibri и т.п., в исходном HTML её не видно, см.
`Клиенты/Andverpersonalinjury/Решения.md`, запись 2026-08-18), и сверяет с пулом
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

ПРОВЕРКА СТРОГАЯ (с 2026-10-06): каждый элемент страницы с номером (tel:-ссылка —
и href, и текст внутри, и текстовые узлы вне ссылок) проверяется отдельно и обязан
показывать номер из пула. Один не подменённый элемент (hero/footer/финальный
блок) = MISMATCH с указанием секции и CSS-класса, куда заводить правило. Каждый
случай прогоняется на десктопе и мобиле (--desktop-only отключает мобилу).
Сравнение по последним 10 цифрам, написание (+1…/(888)…) не важно. Опциональный
ключ `ignore_numbers: [...]` в YAML — номера, которые законно не подменяются.

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


def canon(raw: str) -> str | None:
    """Канонический вид номера для сравнения: последние 10 цифр.

    "+18883025461", "(888) 302-5461", "8883025461" -> "8883025461". Раньше
    сравнивали строки как есть, из-за чего один номер в разных написаниях
    считался разными. Артефакты незавершённого JS-рендера ("tel:+1+1") — None.
    """
    digits = re.sub(r"\D", "", normalize_phone(raw))
    return digits[-10:] if len(digits) >= 10 else None


# Собирает КАЖДЫЙ элемент страницы с номером отдельно (а не общее множество
# номеров): tel:-ссылки (и href, и текст внутри) + текстовые узлы с номером вне
# tel:-ссылок. <script>/<style>/<noscript>/<template> пропускаются — там
# статичные номера из JSON-LD и кода самого коллтрекинга, не место показа.
# Скрытые элементы (напр. mobile-bar на десктопе) НЕ пропускаются: на другом
# экране они видны, и их номер так же обязан быть подменён.
COLLECT_JS = r"""() => {
  const out = [];
  const rx = /\+?1?[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}/g;
  const sec = el => { const s = el.closest('[id]'); return s ? s.id : ''; };
  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  document.querySelectorAll('a[href^="tel:"]').forEach(a => {
    out.push({kind: 'tel', href: a.getAttribute('href') || '',
              text: (a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
              cls: String(a.className || '').slice(0, 80), section: sec(a), visible: vis(a)});
  });
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) continue;
    if (el.closest('a[href^="tel:"]')) continue;
    const hits = n.textContent.match(rx);
    if (hits) out.push({kind: 'text', href: '', text: hits.join(' | ').slice(0, 80),
                        cls: String(el.className || '').slice(0, 80), section: sec(el), visible: vis(el)});
  }
  return out;
}"""


def grab_elements(page, url: str, wait_ms: int) -> list[dict]:
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(wait_ms)
    return page.evaluate(COLLECT_JS)


def element_numbers(el: dict) -> set[str]:
    """Номера одного элемента: из href и из видимого текста (канонический вид)."""
    nums = set()
    if el["href"]:
        c = canon(el["href"])
        if c:
            nums.add(c)
    for m in VISIBLE_PHONE_RE.findall(el["text"]):
        c = canon(m)
        if c:
            nums.add(c)
    return nums


def check_one(page, base_url: str, utm: dict, pool: list[str], wait_ms: int, ignore: set[str]) -> dict:
    """Строгая проверка: КАЖДЫЙ элемент с номером должен показывать номер из пула.

    Раньше успехом считалось, если на странице нашёлся хоть один номер пула —
    поэтому страница, где подмена сработала только в header/mobile-bar, а hero/
    footer остались с дефолтным номером, проходила как OK (найдено 2026-10-06 на
    california-car-truck-accident). Теперь любой элемент с номером вне пула
    (в href или в тексте) — это ошибка, элемент выводится с секцией и классом,
    чтобы сразу было видно, куда заводить правило коллтрекинга.
    ok = нет ни одного "плохого" элемента И хотя бы один элемент совпал с пулом.
    """
    url = base_url if not utm else f"{base_url}?{urlencode(utm)}"
    pool_norm = {canon(p) for p in pool} - {None}
    elements = grab_elements(page, url, wait_ms)

    found, matched, bad = set(), set(), []
    for el in elements:
        nums = element_numbers(el) - ignore
        if not nums:
            continue
        found |= nums
        matched |= nums & pool_norm
        outside = nums - pool_norm
        if outside:
            bad.append({**el, "outside": sorted(outside)})

    ok = bool(matched) and not bad if pool_norm else False
    return {
        "utm": utm,
        "url": url,
        "pool": pool,
        "found": sorted(found),
        "matched": sorted(matched),
        "bad": bad,
        "ok": ok,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "Юристы США"')
    ap.add_argument("--pool-file", default="Коллтрекинг/Пул_номеров.yaml", help="Путь относительно папки клиента")
    ap.add_argument("--wait-ms", type=int, default=5000, help="Пауза после networkidle для JS-подмены номера")
    ap.add_argument("--desktop-only", action="store_true",
                    help="Не проверять мобильный экран (по умолчанию каждый случай прогоняется на десктопе и мобиле — "
                         "на мобиле показываются элементы, скрытые на десктопе, напр. mobile call bar)")
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
    # номера, которые законно не подменяются (напр. отдельный факс/офис) — игнорируются в строгой проверке
    ignore = {canon(n) for n in config.get("ignore_numbers", [])} - {None}

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
        viewports = [("desktop", 1280, 900)] + ([] if args.desktop_only else [("mobile", 390, 844)])
        for case in cases:
            for vp_name, w, h in viewports:
                page.set_viewport_size({"width": w, "height": h})
                res = check_one(page, base_url, case["utm"], case["pool"], args.wait_ms, ignore)
                res["name"] = f"{case['name']} [{vp_name}]"
                results.append(res)
                status = "OK" if res["ok"] else "MISMATCH"
                label = f"{res['name']} {res['utm'] or '(без UTM)'}"
                print(f"[{status}] {label} -> пул {res['pool']}, нашли {res['found']}")
                for b in res["bad"]:
                    print(f"    !! не из пула {b['outside']}: {b['kind']} section={b['section'] or '-'} "
                          f"class={b['cls'] or '-'} href={b['href'] or '-'} text={b['text']!r} "
                          f"{'видим' if b['visible'] else 'скрыт'}")
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
