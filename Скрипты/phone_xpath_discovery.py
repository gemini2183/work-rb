#!/usr/bin/env python
# coding: utf-8
"""Разведка сайта клиента: найти ВСЕ вхождения номера телефона (по tel:-ссылкам)
на главной странице и для каждого собрать готовый XPath-кандидат для настройки
подмены номера в коллтрекинге (Ringostat и т.п.).

Зачем нужен: XPath-правило, заданное по одному месту показа номера (например,
хедеру верхнего экрана), не обязательно покрывает другие места — sticky-копию
хедера при скролле, мобильную vs десктопную вёрстку, футер, попапы. На Tilda
(и вероятно других конструкторах) один и тот же визуальный блок нередко
рендерится НЕСКОЛЬКИМИ параллельными DOM-копиями (см.
`База_знаний/Инструменты/Ringostat-механизм-подмены-номера.md`, раздел
"Sticky-хедер на Tilda"), и подмену нужно настраивать в кабинете отдельно на
каждую копию.

Проверяет ДВА viewport'а (desktop/mobile) и ДВА состояния скролла (верх
страницы / после скролла — чтобы поймать sticky-элементы), потому что один и
тот же номер часто показан по-разному в каждой комбинации (текстовая ссылка
на desktop, icon-only кнопка без текста на mobile — см. кейс ProfiMet,
`Клиенты/ProfiMet/Решения.md`, 2026-09-01).

Для каждого найденного tel:-элемента выводит:
  - сырой XPath (по индексам div, для справки — хрупкий, ссылается на текущую
    вёрстку);
  - устойчивый XPath-кандидат по классам (contains/starts-with), если
    удаётся его составить;
  - тип узла: "text" (есть видимый текст номера, обычная маска подойдёт) или
    "icon-only" (номер только в href, видимого текста нет — full-replace
    маской испортит вёрстку, см. `Ringostat-механизм-подмены-номера.md`);
  - в какой копии артборда/блока лежит (по `data-elem-type`/классам Tilda
    `t###`, если есть — для сайтов на других конструкторах будет пусто).

Не проверяет, есть ли уже настроена подмена в кабинете коллтрекинга — это
разведка ДО настройки. Проверку уже настроенной подмены по UTM делает
`phone_swap_check.py`.

Использование:
    python phone_xpath_discovery.py --url "https://mocnaszklarnia.pl/"
    python phone_xpath_discovery.py --url "https://example.com/" --scroll-y 2000
"""
import argparse
import io
import re
import sys

from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

VIEWPORTS = [
    ("desktop", {"width": 1366, "height": 900}, UA_DESKTOP, False),
    ("mobile", {"width": 390, "height": 844}, UA_MOBILE, True),
]

# JS: обходит все tel:-ссылки, для каждой считает bounding rect (viewport
# top < 0 или > 0 говорит, видима ли она СЕЙЧАС — после скролла), собирает
# сырой XPath по индексам и структурную сигнатуру (классы себя и до 4 предков)
# для построения устойчивого XPath-кандидата.
EXTRACT_JS = """
() => {
    function getXPath(el) {
        if (el.id) return `//*[@id="${el.id}"]`;
        const parts = [];
        while (el && el.nodeType === 1) {
            let index = 1;
            let sib = el.previousElementSibling;
            while (sib) {
                if (sib.tagName === el.tagName) index++;
                sib = sib.previousElementSibling;
            }
            parts.unshift(`${el.tagName.toLowerCase()}[${index}]`);
            el = el.parentElement;
        }
        return '/' + parts.join('/');
    }

    function ancestorChain(el, depth) {
        const chain = [];
        let cur = el.parentElement;
        for (let i = 0; i < depth && cur; i++) {
            chain.push({tag: cur.tagName.toLowerCase(), classes: cur.className || ''});
            cur = cur.parentElement;
        }
        return chain;
    }

    const results = [];
    document.querySelectorAll('a[href^="tel:"]').forEach(a => {
        const rect = a.getBoundingClientRect();
        const hasImg = !!a.querySelector('img, svg');
        const text = a.innerText.trim();
        results.push({
            href: a.getAttribute('href'),
            xpath: getXPath(a),
            ownClasses: a.className || '',
            hasImg: hasImg,
            innerText: text,
            nodeType: text ? 'text' : (hasImg ? 'icon-only' : 'empty'),
            visibleNow: rect.top > -5 && rect.top < window.innerHeight && rect.width > 0,
            rectTop: Math.round(rect.top),
            ancestors: ancestorChain(a, 5),
        });
    });
    return results;
}
"""


# служебные классы Tilda/типовых конструкторов — почти всегда встречаются
# сотнями раз на странице САМИ ПО СЕБЕ (общий тип атома/обёртки), бесполезны
# как единственный якорь, но не исключаются полностью — в комбинации с
# другими предками-фильтрами (contains + and-условие на узел) могут всё же
# дать мало совпадений, поэтому только снижаем базовый счёт, не обнуляем
GENERIC_CLASS_MARKERS = ("tn-atom", "t-sociallinks", "t396__elem", "t-img", "t-col", "t-container")
# признаки "содержательности" класса — обычно означают конкретное СОСТОЯНИЕ
# или РОЛЬ блока (sticky-копия, конкретный виджет), а не общий тип атома
MEANINGFUL_MARKERS = ("fixed", "sticky", "header", "footer", "popup", "menu", "phone", "callback", "widget")
# длинные числовые id-подобные суффиксы Tilda (tn-elem__6514636821...) —
# уникальны на странице, но хрупкие: подтверждено на практике ProfiMet, что
# такой id слетает при пересборке блока в редакторе Tilda (старое правило
# "Header scroll bar" перестало матчить что-либо после переверстки сайта, см.
# `Клиенты/ProfiMet/Решения.md`) — поэтому такие классы получают низкий
# приоритет и используются только если ничего стабильнее не нашлось
FRAGILE_ID_RE = re.compile(r"__\d{10,}")


def _class_score(cls: str) -> int:
    """Эвристическая оценка полезности класса как XPath-якоря: чем выше, тем
    больше шанс, что класс уникально и УСТОЙЧИВО описывает СОСТОЯНИЕ/РОЛЬ
    блока, а не просто его общий тип (сотни совпадений) или хрупкий
    автосгенерированный id (слетает при правках вёрстки)."""
    if FRAGILE_ID_RE.search(cls):
        return 1  # хуже любого смыслового класса, но лучше, чем совсем ничего
    score = len(cls)
    if any(marker in cls for marker in GENERIC_CLASS_MARKERS):
        score = max(1, score - 20)
    if any(marker in cls.lower() for marker in MEANINGFUL_MARKERS):
        score += 100
    return score


def build_candidate_xpath(entry, page):
    """Пробуем собрать устойчивый XPath по классам вместо числовых индексов.

    Идём вверх по предкам, на каждом шаге берём класс с максимальной
    эвристической оценкой (см. _class_score) и ПРОВЕРЯЕМ через сам браузер,
    сколько элементов реально матчит `contains(@class, ...)` — годится только
    класс, дающий небольшое число совпадений (в идеале — совпадающее с
    числом реальных мест показа номера в этом состоянии, обычно 1-2, не
    сотни). Без такой проверки эвристика "первый длинный класс" даёт
    юридически валидный, но бесполезный XPath, матчащий тысячу узлов
    (проверено на tn-atom/t396__elem — 1016 совпадений на mocnaszklarnia.pl).
    """
    node_filter = 'starts-with(@href,"tel:")'
    if entry["nodeType"] == "text":
        node_filter += " and not(*)"
    elif entry["nodeType"] == "icon-only":
        # иконка может быть <img> (растровая/svg-файлом) или инлайн <svg>.
        # <svg> живёт в XML-namespace http://www.w3.org/2000/svg — голый шаг
        # "svg" в XPath 1.0 ищет элемент БЕЗ namespace и никогда не совпадёт
        # с настоящим <svg> (проверено: //a[svg] дал 0 совпадений на реальном
        # инлайн-svg внутри t-sociallinks соцссылки-телефона ProfiMet, хотя
        # querySelector('svg') в JS находит его без проблем — JS не требует
        # явного namespace-совпадения). Обход — local-name(), не зависящий
        # от namespace. Это же ограничение будет действовать и в движке
        # XPath самого Ringostat, не только в Playwright — значит любой XPath
        # для inline-svg иконок в кабинете тоже должен использовать
        # local-name(), а не голый тег svg.
        node_filter += ' and (*[local-name()="img"] or *[local-name()="svg"])'

    best = None
    for anc in entry["ancestors"]:
        classes = sorted(anc["classes"].split(), key=_class_score, reverse=True)
        for cls in classes:
            if _class_score(cls) == 0:
                continue
            candidate = f'//*[contains(@class,"{cls}")]//a[{node_filter}]'
            try:
                count = page.locator(f"xpath={candidate}").count()
            except Exception:
                continue
            if 1 <= count <= 3:
                warning = "  [хрупкий id — может слететь при правках вёрстки]" if FRAGILE_ID_RE.search(cls) else ""
                return f"{candidate}{warning}"
            if best is None or count < best[1]:
                best = (candidate, count)

    if best:
        # ничего идеального не нашли — возвращаем наименее "жадный" вариант,
        # но явно предупреждаем, что его нужно проверить руками
        return f"{best[0]}  [ПРОВЕРИТЬ: матчит {best[1]} элементов]"
    return None


def dedupe_key(entry):
    return (entry["xpath"], entry["href"])


def run_discovery(url: str, scroll_y: int, wait_ms: int):
    all_entries = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, viewport, ua, is_mobile in VIEWPORTS:
            page = browser.new_page(
                user_agent=ua, viewport=viewport, is_mobile=is_mobile, has_touch=is_mobile
            )
            for scroll_state, do_scroll in [("top", False), ("scrolled", True)]:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(wait_ms)
                if do_scroll:
                    page.evaluate(f"window.scrollTo(0, {scroll_y + 200})")
                    page.wait_for_timeout(800)
                    page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    page.wait_for_timeout(wait_ms)

                entries = page.evaluate(EXTRACT_JS)
                for e in entries:
                    e["viewport"] = label
                    e["scrollState"] = scroll_state
                    e["candidateXpath"] = build_candidate_xpath(e, page)
                    all_entries.append(e)
            page.close()
        browser.close()

    return all_entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="URL главной страницы клиента")
    ap.add_argument("--scroll-y", type=int, default=1800, help="На сколько px скроллить, чтобы поймать sticky-элементы")
    ap.add_argument("--wait-ms", type=int, default=1200, help="Пауза после networkidle/скролла для JS-анимаций")
    args = ap.parse_args()

    print(f"Сайт: {args.url}")
    print(f"Viewport'ы: {', '.join(v[0] for v in VIEWPORTS)} | скролл до y={args.scroll_y}\n")

    entries = run_discovery(args.url, args.scroll_y, args.wait_ms)

    # группируем по уникальному месту в DOM (xpath+href), показывая в каких
    # viewport/scroll-состояниях элемент видим
    by_key = {}
    for e in entries:
        key = dedupe_key(e)
        by_key.setdefault(key, {"entry": e, "seen": []})
        state = f"{e['viewport']}/{e['scrollState']}" + (" [видим]" if e["visibleNow"] else "")
        by_key[key]["seen"].append(state)

    if not by_key:
        print("Ни одной tel:-ссылки не найдено.")
        sys.exit(1)

    print(f"Найдено уникальных мест с номером: {len(by_key)}\n")
    for i, (key, data) in enumerate(by_key.items(), 1):
        e = data["entry"]
        print(f"--- [{i}] тип: {e['nodeType']} | href: {e['href']} ---")
        print(f"    Встречается в: {', '.join(sorted(set(data['seen'])))}")
        print(f"    Видимый текст: {e['innerText'] or '(нет)'}")
        print(f"    Сырой XPath:   {e['xpath']}")
        if e["candidateXpath"]:
            print(f"    Кандидат XPath (по классу): {e['candidateXpath']}")
        else:
            print("    Кандидат XPath (по классу): не удалось собрать — нет содержательных классов у предков")
        if e["nodeType"] == "icon-only":
            print("    ВНИМАНИЕ: узел без видимого текста (только img/svg) — обычная")
            print("    текстовая маска впишет цифры рядом с иконкой и испортит вид,")
            print("    см. `База_знаний/Инструменты/Ringostat-механизм-подмены-номера.md`.")
        print()


if __name__ == "__main__":
    main()
