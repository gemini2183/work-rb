"""
Собирает каталог товаров ekspertagro.pl (Tilda-магазин) напрямую с сайта и
строит из него Google Merchant Center XML-фид.

Зачем: у клиента источник Merchant Center "Файл (вручную)" не имеет
автоматической генерации (см. База_знаний/Инструменты/Merchant-Center-ручной-
XML-фид-добавление-товаров.md) — предыдущая версия файла (131 товар,
19.12.2025) устарела: 100 из 121 общих товаров разошлись по цене, 10 товаров
пропали с сайта, 32 появились новых (см. Клиенты/EkspertAgro/Мерчант/Решения.md,
запись 2026-09-22). Этот скрипт — способ пересобрать фид с нуля из
актуального состояния сайта, не полагаясь на ручной ввод.

Как работает: Tilda рендерит карточки товаров через JS после загрузки (нет
публичного JSON API/фида) и подгружает лишние товары по клику "Pokaż więcej"
("Показать больше") — поэтому обычный HTTP-запрос (curl/WebFetch) отдаёт
пустой каталог, нужен headless-браузер, который дожимает кнопку до конца.
ID товара, название, цена и характеристики лежат в data-атрибутах карточки
(field="st_title__<ID>", data-product-price-def="<цена>") — надёжнее, чем
парсить текст.

Категория Google Product Category (693, Greenhouses) намеренно одна на все
4 раздела сайта (теплицы/фундаменты/аксессуары/поликарбонат) — в официальной
таксономии Google нет точных категорий под специализированные аксессуары
теплиц, и все они продаются только как аксессуары к теплицам этого магазина
(решение пользователя, см. Решения.md).

Результат НЕ загружается в Merchant Center автоматически — только собирает
XML-файл, дальше он проверяется вручную и заливается через UI (кнопка
"Обновить" на странице источника, см. инструкцию в базе знаний выше).
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from playwright.sync_api import sync_playwright

CATEGORY_URLS = [
    "https://ekspertagro.pl/szklarni",
    "https://ekspertagro.pl/fundament-do-szklarni",
    "https://ekspertagro.pl/akcesoria-do-szklarni",
    "https://ekspertagro.pl/poliweglan",
]

# (product_type для g:product_type, google_product_category)
CATEGORY_MAP = {
    "https://ekspertagro.pl/szklarni": ("Szklarnie", "693"),
    "https://ekspertagro.pl/fundament-do-szklarni": ("Fundamenty", "693"),
    "https://ekspertagro.pl/akcesoria-do-szklarni": ("Akcesoria", "693"),
    "https://ekspertagro.pl/poliweglan": ("Poliweglan", "693"),
}

SHOP_TITLE = "Ekspert Agro - Szklarnie Ogrodowe"
SHOP_LINK = "https://ekspertagro.pl"
SHOP_DESCRIPTION = "Szklarnie ogrodowe z poliwęglanu od polskiego producenta"
BRAND = "Ekspert Agro"


def scrape_category(page, url, max_load_more=40):
    try:
        page.goto(url, wait_until="networkidle", timeout=20000)
    except Exception:
        try:
            page.goto(url, wait_until="load", timeout=30000)
        except Exception:
            pass
    page.wait_for_timeout(3000)

    clicks = 0
    while clicks < max_load_more:
        btn = page.locator("text=Pokaż więcej")
        if btn.count() == 0 or not btn.first.is_visible():
            break
        try:
            btn.first.click(timeout=3000)
            clicks += 1
            page.wait_for_timeout(1200)
        except Exception:
            break

    cards = page.locator(".t-store__card")
    count = cards.count()
    print(f"{url}: {count} cards, {clicks} load-more clicks", file=sys.stderr)

    items = []
    for i in range(count):
        card = cards.nth(i)
        try:
            link_el = card.locator("a[href*='tproduct']").first
            href = link_el.get_attribute("href") if link_el.count() else None

            name_el = card.locator(".js-product-name").first
            title = name_el.inner_text().strip() if name_el.count() else None

            descr_el = card.locator(".js-store-prod-descr").first
            descr_html = descr_el.inner_html() if descr_el.count() else ""
            descr_text = re.sub(r"<[^>]+>", " ", descr_html)
            descr_text = re.sub(r"\s+", " ", descr_text).strip()

            price_el = card.locator("[data-product-price-def]").first
            price = price_el.get_attribute("data-product-price-def") if price_el.count() else None

            img_el = card.locator("img.js-product-img").first
            img = img_el.get_attribute("data-original") if img_el.count() else None

            field_attr = name_el.get_attribute("field") if name_el.count() else None
            product_id = None
            if field_attr and "__" in field_attr:
                product_id = field_attr.split("__")[-1]
            if not product_id and href:
                m = re.search(r"-(\d{9,})-", href)
                if m:
                    product_id = m.group(1)

            if not (product_id and title and href and price):
                print(f"  skip incomplete card #{i} on {url}", file=sys.stderr)
                continue

            items.append({
                "id": product_id,
                "title": title,
                "description": descr_text,
                "link": href,
                "image_link": img,
                "price": price,
                "category_url": url,
            })
        except Exception as e:
            print(f"  row {i} error: {e}", file=sys.stderr)

    return items


def scrape_all():
    all_items = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        for url in CATEGORY_URLS:
            all_items.extend(scrape_category(page, url))
        browser.close()

    seen = set()
    deduped = []
    for it in all_items:
        pid = it["id"]
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(it)

    print(f"TOTAL scraped: {len(all_items)}, after dedupe: {len(deduped)}", file=sys.stderr)
    return deduped


def build_xml(items):
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">',
        "  <channel>",
        f"    <title>{escape(SHOP_TITLE)}</title>",
        f"    <link>{escape(SHOP_LINK)}</link>",
        f"    <description>{escape(SHOP_DESCRIPTION)}</description>",
    ]

    for it in items:
        product_type, gcat = CATEGORY_MAP.get(it["category_url"], ("Inne", "693"))
        price = it["price"]
        price_fmt = f"{float(price):.2f} PLN"

        lines.append("    <item>")
        lines.append(f"      <g:id>{escape(it['id'])}</g:id>")
        lines.append(f"      <g:title>{escape(it['title'])}</g:title>")
        lines.append(f"      <g:description>{escape(it['description'])}</g:description>")
        lines.append(f"      <g:link>{escape(it['link'])}</g:link>")
        lines.append(f"      <g:image_link>{escape(it['image_link'])}</g:image_link>")
        lines.append("      <g:availability>in stock</g:availability>")
        lines.append(f"      <g:price>{price_fmt}</g:price>")
        lines.append(f"      <g:brand>{escape(BRAND)}</g:brand>")
        lines.append("      <g:condition>new</g:condition>")
        lines.append(f"      <g:google_product_category>{gcat}</g:google_product_category>")
        lines.append(f"      <g:product_type>{escape(product_type)}</g:product_type>")
        lines.append(f"      <g:mpn>EXP-{it['id']}</g:mpn>")
        lines.append("      <g:shipping>")
        lines.append("        <g:country>PL</g:country>")
        lines.append("        <g:service>Standardowa</g:service>")
        lines.append("        <g:price>0 PLN</g:price>")
        lines.append("      </g:shipping>")
        lines.append("    </item>")

    lines.append("  </channel>")
    lines.append("</rss>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = (
        f"../Клиенты/EkspertAgro/Мерчант/Статистика/"
        f"google_merchant_feed_{date.today().isoformat()}.xml"
    )
    parser.add_argument(
        "--out",
        default=default_out,
        help="Путь для сохранения XML (по умолчанию — в Статистика/ клиента, с датой в имени)",
    )
    parser.add_argument(
        "--dump-json",
        help="Дополнительно сохранить сырые собранные товары в JSON (для отладки/диффа)",
    )
    args = parser.parse_args()

    items = scrape_all()

    if args.dump_json:
        Path(args.dump_json).write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Saved raw items to {args.dump_json}", file=sys.stderr)

    xml = build_xml(items)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(xml, encoding="utf-8")
    print(f"Written {len(items)} items to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
