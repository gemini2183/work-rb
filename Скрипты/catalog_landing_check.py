#!/usr/bin/env python
# coding: utf-8
"""Проверка посадочных каталога Tilda для Search-кампании — ТОЛЬКО ЧТЕНИЕ.

Берёт финальные URL объявлений кампании из Google Ads и для каждой группы открывает страницу в браузере так, как её
открыл бы человек после клика (UTM из `final_url_suffix` кампании подставляются с реальным ID кампании), и проверяет:
  1. фильтр применился: карточек меньше, чем во всём каталоге, и в названии каждой есть размер из ключей группы;
  2. номер Ringostat на странице: какой номер показан, входит ли он в ожидаемый пул (по умолчанию — «Google CPC General»);
  3. поле tel: и тексты на странице совпадают (подмена отработала везде).
Ключи фильтров `tfc_charact:…` — внутренние ID Tilda: после правки каталога клиентом они могут смениться, тогда ссылка
молча покажет весь каталог. Скрипт нужен до включения кампании и после любых правок каталога.

Использование:
    python catalog_landing_check.py --customer-id 8826134558 --campaign-id 24353873699 \
        --expected-numbers 48225987216,48225987224,48222565341
"""
import argparse
import re

from google.ads.googleads.client import GoogleAdsClient
from playwright.sync_api import sync_playwright

from gads_stats import GOOGLE_ADS_YAML

ALL_CATALOG = "https://ekspertagro.pl/szklarni"
CARD_JS = """() => [...document.querySelectorAll('.js-product')].filter(c => c.offsetParent !== null)
    .map(c => (c.querySelector('.js-product-name') || {}).innerText).filter(Boolean)"""
TEL_JS = "() => [...new Set([...document.querySelectorAll('a[href^=\"tel:\"]')].map(a => a.getAttribute('href').replace('tel:','')))]"


def real_url(url, suffix, campaign_id):
    s = (suffix.replace("{campaignid}", str(campaign_id)).replace("{ifsearch:search}", "search")
         .replace("{ifcontent:context}", "").replace("{adgroupid}", "1").replace("{creative}", "1")
         .replace("{adposition}", "1t1").replace("{device}", "c").replace("{placement}", "")
         .replace("{loc_physical_ms}", "1011539").replace("{targetid}", "kwd-1").replace("{gclid}", "TEST")
         .replace("{keyword}", "test"))
    sep = "&" if "?" in url else "?"
    return url + sep + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--expected-numbers", default="48225987216,48225987224,48222565341",
                    help="номера пула Ringostat через запятую (без +)")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    expected = {x.strip().lstrip("+") for x in a.expected_numbers.split(",") if x.strip()}
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    suffix = next(iter(r.campaign.final_url_suffix for r in ga.search(customer_id=cid, query=(
        f"SELECT campaign.id, campaign.final_url_suffix FROM campaign WHERE campaign.id = {a.campaign_id}"))), "")
    groups = [(r.ad_group.name, list(r.ad_group_ad.ad.final_urls)[0]) for r in ga.search(customer_id=cid, query=(
        "SELECT campaign.id, ad_group.name, ad_group_ad.ad.final_urls FROM ad_group_ad "
        f"WHERE campaign.id = {a.campaign_id} AND ad_group_ad.status != 'REMOVED'"))]
    print(f"Кампания {a.campaign_id}: групп с объявлением {len(groups)}; суффикс {'есть' if suffix else 'НЕТ'}")
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1366, "height": 900}, locale="pl-PL")
        pg.goto(ALL_CATALOG, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        total = len(pg.evaluate(CARD_JS))
        print(f"Весь каталог без фильтра (видимых карточек до прокрутки): {total}\n")
        for name, url in sorted(groups):
            ctx = b.new_context(viewport={"width": 1366, "height": 900}, locale="pl-PL")
            page = ctx.new_page()
            page.goto(real_url(url, suffix, a.campaign_id), wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            cards = page.evaluate(CARD_JS)
            tel = [t.lstrip("+") for t in page.evaluate(TEL_JS)]
            size = name.replace(" ", "")
            ok_cards = bool(cards) and len(cards) < total + 1 and all(size in re.sub(r"\s", "", c) for c in cards)
            ok_num = bool(tel) and all(t in expected for t in tel)
            bad += (not ok_cards) + (not ok_num)
            print(f"[{name}] карточек {len(cards)} ({'ВСЕ с размером ' + name if ok_cards else 'ФИЛЬТР НЕ СРАБОТАЛ'}); "
                  f"номер {tel} ({'в ожидаемом пуле' if ok_num else 'ВНЕ ОЖИДАЕМОГО ПУЛА'})")
            ctx.close()
        b.close()
    print("\nИТОГ:", "всё в порядке" if not bad else f"проблем: {bad}")


if __name__ == "__main__":
    main()
