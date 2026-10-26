#!/usr/bin/env python
# coding: utf-8
"""План правил подмены номера Ringostat для страницы: XPath + маска на каждую ссылку tel:. ТОЛЬКО ЧТЕНИЕ (в кабинет не пишет).

Зачем: при запуске новой посадочной (Landver, 2026-10-24) правила составлялись вручную: сверка с правилами в кабинете, выбор устойчивого
признака ссылки, маска из внутренностей, проверка числа совпадений. Здесь то же автоматически:
  1. Читает с живой страницы (Ringostat заблокирован, видна исходная вёрстка) все ссылки tel: и их внутренности.
  2. Читает действующие XPath-правила проекта из клиентского скрипта Ringostat и проверяет, какие ссылки они уже покрывают.
  3. Для непокрытых ссылок выбирает признак: `data-*` атрибут (если у ссылок он есть и различается), иначе уникальный класс,
     иначе (хрупко!) текст; строит маску: внутренности ссылки, где цифры номера заменены на `#`; если номера в тексте нет —
     добавляет скрытый `<span style="display:none;">+###########</span>` (иначе Ringostat заменит содержимое голым номером).
  4. Объединяет ссылки с одинаковой маской в одно правило (`or`), проверяет Playwright'ом число совпадений каждого XPath и что правила
     вместе покрывают ВСЕ ссылки tel: страницы.
  5. Пишет план в консоль и в Статистика/<клиент>/ringostat_rules_<домен>_<дата>.md, плюс JS-вставку для консоли браузера
     (вход в кабинет Ringostat уже выполнен, форма «Добавить XPath»; см. База_знаний/Агенты/Запуск_трекинга_новой_посадочной.md).
В кабинет правила вносятся браузером после «да» пользователя; после — `phone_swap_check.py` с пул-файлом страницы.

Ограничения: ссылки, которые создаёт скрипт страницы ПОСЛЕ загрузки (кнопка звонка в результате квиза), правилами не охватываются
(нужна правка кода страницы: взять номер из уже подменённой кнопки); номер картинкой и номер без ссылки tel: не видны.

    python ringostat_xpath_plan.py --url https://site/page --client-folder Andverpersonalinjury --name-prefix car-lawyer
"""
import argparse
import io
import json
import re
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from _config import client_stats_dir

BS = chr(92)

LINKS_JS = r"""()=>[...document.querySelectorAll('a[href^="tel:"]')].map((a,i)=>({
  i, href:a.getAttribute('href'), inner:a.innerHTML.replace(/\s+/g,' ').replace(/> </g,'><').trim(),
  text:a.textContent.replace(/\s+/g,' ').trim(), cls:(a.getAttribute('class')||'').split(/\s+/).filter(Boolean),
  data:Object.fromEntries([...a.attributes].filter(x=>x.name.startsWith('data-')).map(x=>[x.name,x.value])),
  visible:!!(a.offsetWidth||a.offsetHeight)}))"""

COUNT_JS = r"""(xp)=>{const s=document.evaluate(xp,document,null,XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,null);const o=[];
  for(let i=0;i<s.snapshotLength;i++){const n=s.snapshotItem(i);o.push(n.tagName==='A'?[...document.querySelectorAll('a[href^="tel:"]')].indexOf(n):-1)}return o}"""


def read_rules(pg):
    """Действующие правила проекта из клиентского скрипта Ringostat."""
    urls = []
    pg2 = pg.context.new_page()
    pg2.on("request", lambda r: urls.append(r.url) if "script.ringostat.com" in r.url else None)
    pg2.goto(pg.url, wait_until="load", timeout=90000)
    pg2.wait_for_timeout(2500)
    pg2.close()
    if not urls:
        return None, []
    js = pg.request.get(urls[0]).text()
    k = js.find('"xpaths":[')
    if k < 0:
        return urls[0], []
    s = js[k + 9:]
    depth = 0
    esc = instr = False
    end = 0
    for n, ch in enumerate(s):
        if instr:
            if esc:
                esc = False
            elif ch == BS:
                esc = True
            elif ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = n + 1
                break
    return urls[0], json.loads(s[:end])


def number_regex(digits):
    """Регэксп номера в любом форматировании: цифры с произвольными разделителями между ними."""
    parts = [re.escape(c) + r"[\s().\- ]*" for c in digits]
    return re.compile(r"\(?" + "".join(parts))


def build_mask(link, main_digits):
    """Маска = внутренности ссылки, где цифры номера заменены на #. Код страны в тексте может отсутствовать (href +1844…, текст (844)…):
    пробуем номер целиком, затем без 1–3 первых цифр (не короче 9 цифр)."""
    inner = link["inner"]
    for k in range(0, 4):
        d = main_digits[k:]
        if len(d) < 9:
            break
        m = number_regex(d).search(inner)
        if m:
            tok = m.group(0).rstrip("  ")
            masked = "".join("#" if c.isdigit() else c for c in tok)
            return inner[:m.start()] + masked + inner[m.start() + len(tok):], True
    # номера нет в тексте (кнопка «Call now»): скрытый span с плейсхолдером
    return inner + '<span style="display:none;">+' + "#" * len(main_digits) + "</span>", False


def pick_selector(link, links):
    # 1) data-атрибут, у которого значение уникально среди ссылок
    for k, v in link["data"].items():
        if sum(1 for l in links if l["data"].get(k) == v) == 1:
            return f'@{k}="{v}"', f"data-атрибут {k}"
    # 2) класс, который есть только у этой ссылки
    for c in link["cls"]:
        if sum(1 for l in links if c in l["cls"]) == 1:
            return f"contains(concat(' ',normalize-space(@class),' '),' {c} ')", f"уникальный класс {c}"
    return None, None


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--client-folder", default=None)
    ap.add_argument("--name-prefix", default="rule")
    ap.add_argument("--ignore-existing", action="store_true", help="не учитывать действующие правила (проверка плана на странице, где правила уже внесены)")
    ap.add_argument("--geo", default="1", help="значение «ГЕО группа» в форме кабинета: 1 = All")
    a = ap.parse_args()
    out = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 1366, "height": 850})
        ctx.route("**/*", lambda r: r.abort() if ("ringostat" in r.request.url and "script.ringostat.com" not in r.request.url) else r.continue_())
        pg = ctx.new_page()
        # исходная вёрстка: блокируем скрипт подмены
        ctx_plain = br.new_context(viewport={"width": 1366, "height": 850})
        ctx_plain.route("**/*", lambda r: r.abort() if "ringostat" in r.request.url else r.continue_())
        pp = ctx_plain.new_page()
        pp.goto(a.url, wait_until="load", timeout=90000)
        pp.wait_for_timeout(4000)
        links = pp.evaluate(LINKS_JS)
        pg.goto(a.url, wait_until="load", timeout=90000)
        pg.wait_for_timeout(1500)
        script_url, rules = read_rules(pg)
        out.append(f"# Правила подмены Ringostat для {a.url}")
        out.append(f"Дата: {datetime.now():%Y-%m-%d %H:%M}. Только чтение.")
        out.append(f"Скрипт Ringostat: {script_url or 'НЕ НАЙДЕН (подмена на странице не подключена?)'}; действующих правил проекта: {len(rules)}")
        if not links:
            print("\n".join(out) + "\nНа странице нет ссылок tel:.")
            return
        main_href = Counter(l["href"] for l in links).most_common(1)[0][0]
        main_digits = re.sub(r"\D", "", main_href)
        out.append(f"Ссылок tel: {len(links)}; основной номер на странице {main_href}")
        # какие ссылки уже покрыты действующими правилами
        covered = set()
        for n, r in enumerate(rules):
            try:
                idx = pp.evaluate(COUNT_JS, r["xPath"])
            except Exception:
                continue
            hit = [i for i in idx if i >= 0]
            if hit:
                covered.update(hit)
                out.append(f"  действующее правило #{n} ({(r.get('xPath') or '')[:90]}) покрывает ссылок: {len(hit)}")
        if a.ignore_existing:
            covered = set()
        out.append(f"Уже покрыто действующими правилами: {len(covered)} из {len(links)}")
        todo = [l for l in links if l["i"] not in covered]
        groups = OrderedDict()
        for l in todo:
            mask, has_num = build_mask(l, main_digits)
            sel, why = pick_selector(l, links)
            if sel is None:
                sel, why = f'contains(.,"{l["text"][:40]}")', "ТЕКСТ ссылки (хрупко: слетит при правке текста)"
            groups.setdefault(mask, []).append((l, sel, why, has_num))
        rules_plan = []
        out.append(f"\n## План: {len(groups)} правил(а) на {len(todo)} непокрытых ссылок")
        for n, (mask, items) in enumerate(groups.items(), 1):
            xp = "//a[" + " or ".join(sorted({s for _, s, _, _ in items})) + "]"
            if len(items) == 1:
                xp = "//a[" + items[0][1] + "]"
            cnt = [i for i in pp.evaluate(COUNT_JS, xp) if i >= 0]
            ok = sorted(cnt) == sorted(l["i"] for l, _, _, _ in items)
            name = f"{a.name_prefix} {n}"
            rules_plan.append({"name": name, "xpath": xp, "mask": mask, "geo": a.geo})
            out.append(f"{n}. {name} | совпадений {len(cnt)} из {len(items)} {'OK' if ok else 'НЕ СОВПАЛО'} | признак: {sorted({w for _, _, w, _ in items})}")
            out.append(f"   XPath: {xp}")
            out.append(f"   Маска: {mask}")
            out.append(f"   Ссылки: {[l['data'] or l['cls'][:2] or l['text'][:20] for l, _, _, _ in items]}"
                       f"{'' if items[0][3] else '  (номера в тексте нет: добавлен скрытый span)'}")
        total = set(covered)
        for r in rules_plan:
            total.update(i for i in pp.evaluate(COUNT_JS, r["xpath"]) if i >= 0)
        out.append(f"\nИтого покрыто: {len(total)} из {len(links)} ссылок tel: {'— ВСЕ' if len(total) == len(links) else '— НЕ ВСЕ: ' + str(sorted(set(range(len(links))) - total))}")
        out.append("Не охвачено по построению: ссылки, создаваемые скриптом страницы после загрузки (кнопки результата квиза и т.п.), номер картинкой, номер без ссылки tel:.")
        # JS для консоли браузера (форма «Добавить XPath» в кабинете Ringostat)
        js_rules = json.dumps([{k: r[k] for k in ("name", "xpath", "mask", "geo")} for r in rules_plan], ensure_ascii=False)
        out.append("\n## JS для консоли страницы «XPaths» проекта в Ringostat (после «да»; затем «Применить настройки»)")
        out.append("```js\n(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));\n"
                   "const set=(n,v)=>{const e=document.querySelector('[name=\"'+n+'\"]');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};\n"
                   f"const rules={js_rules};\n"
                   "for(const r of rules){[...document.querySelectorAll('button')].find(e=>/Добавить XPath/.test(e.textContent)).click();await sleep(1500);\n"
                   "set('data[Xpath][type]','manual');set('data[Xpath][text]',r.xpath);set('data[Xpath][name]',r.name);set('data[Xpath][mask]',r.mask);set('data[Xpath][geo_group]',r.geo);\n"
                   "[...document.querySelectorAll('.modal button[type=submit]')].filter(b=>b.textContent.trim()==='Сохранить').pop().click();await sleep(3500);}\n"
                   "return document.querySelectorAll('table tbody tr').length;})()\n```")
        br.close()
    text = "\n".join(out)
    print(text)
    if a.client_folder:
        host = urlparse(a.url).netloc.replace(".", "_") + "_" + urlparse(a.url).path.strip("/").replace("/", "_")[:40]
        f = client_stats_dir(a.client_folder) / f"ringostat_rules_{host}_{datetime.now():%Y-%m-%d}.md"
        f.write_text(text, encoding="utf-8")
        print("\nСохранено:", f)


if __name__ == "__main__":
    main()
