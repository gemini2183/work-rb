#!/usr/bin/env python
# coding: utf-8
"""Контролёр актуальности: сайт клиента ↔ тексты в рекламе (RSA, ассеты кампаний, группы ассетов PMax). ТОЛЬКО ЧТЕНИЕ.

Что делает:
  1) читает страницы сайта (`site_urls` реестра), достаёт значения по `site_extract` (число подарков, дата акции, заказов в год…);
  2) сверяет с ожидаемыми значениями `expected`: расхождение = «сайт изменился»;
  3) вынимает тексты из Google Ads: заголовки и описания RSA, сайтлинки, уточнения, сниппеты, ценовые ассеты, тексты групп
     ассетов PMax; Demand Gen — если API отдаёт;
  4) по `claims` сверяет числа и даты с фактом сайта, по `banned` ищет запрещённые/недоказанные формулировки;
  5) пишет таблицу находок в `Статистика/ads_facts_audit_<дата>.csv` и печатает сводку. Ничего не меняет ни в рекламе, ни на сайте.

Реестр фактов — `Клиенты/<Имя>/Креативы/facts_registry.yaml` (шаблон — ProfiMet). Плейбук — База_знаний/Агенты/Контролёр_фактов_и_текстов.md.

Использование:
    python ads_facts_audit.py --client-folder ProfiMet                    # все включённые кампании аккаунта
    python ads_facts_audit.py --client-folder ProfiMet --campaign-ids 19158580966 19153311519
    python ads_facts_audit.py --client-folder ProfiMet --site-only        # только сверка сайта с реестром
"""
import argparse
import collections
import csv
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; facts-audit/1.0)"}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip()


def fetch_site_text(urls, shots_dir=None):
    """Текст страниц ПОСЛЕ отрисовки (Playwright/Chromium: видит то, что рисует JS); без Playwright — обычный HTTP.
    shots_dir — куда сохранить скриншоты страниц целиком (для глаз: значки, картинки)."""
    chunks = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            ctx = br.new_context(viewport={"width": 1440, "height": 900}, locale="pl-PL", user_agent=UA["User-Agent"])
            for i, u in enumerate(urls):
                try:
                    pg = ctx.new_page()
                    pg.goto(u, wait_until="networkidle", timeout=60000)
                    pg.wait_for_timeout(1500)
                    chunks.append(norm(pg.inner_text("body")))
                    if shots_dir:
                        Path(shots_dir).mkdir(parents=True, exist_ok=True)
                        pg.screenshot(path=str(Path(shots_dir) / f"{date.today().isoformat()}_{i}.png"), full_page=True)
                    pg.close()
                except Exception as ex:
                    print(f"  сайт: {u} — ошибка отрисовки {type(ex).__name__}: {str(ex)[:100]}")
            br.close()
        if chunks:
            return " ".join(chunks)
    except Exception as ex:
        print(f"  Playwright недоступен ({type(ex).__name__}), читаю обычным запросом (без JS)")
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=40)
            r.raise_for_status()
            html = re.sub(r"(?is)<(script|style)[^>]*>.*?</>", " ", r.text)
            chunks.append(norm(re.sub(r"(?s)<[^>]+>", " ", html).replace("&nbsp;", " ")))
        except Exception as ex:
            print(f"  сайт: {u} — ошибка {type(ex).__name__}: {str(ex)[:100]}")
    return " ".join(chunks)


def extract_site(text, rules):
    out = {}
    for key, rule in rules.items():
        vals = [norm(m.group(1)) for m in re.finditer(rule["regex"], text, re.I)]
        if not vals:
            out[key] = None
        elif rule.get("pick") == "mode":
            out[key] = collections.Counter(vals).most_common(1)[0][0]
        else:
            out[key] = vals[0]
    return out


def same(a, b):
    f = lambda s: re.sub(r"[\s .+]", "", (s or "")).lower()
    return f(a) == f(b)


def collect_texts(ga, cid, campaign_ids):
    """→ список (кампания, вид, id объекта, текст)."""
    where = f"campaign.id IN ({','.join(campaign_ids)})" if campaign_ids else "campaign.status = 'ENABLED'"
    out = []

    def run(label, q, fn):
        try:
            for r in ga.search(customer_id=cid, query=q):
                fn(r)
        except Exception as ex:
            print(f"  [{label}] пропущено: {type(ex).__name__}: {str(ex)[:140]}")

    def rsa(r):
        a = r.ad_group_ad.ad
        for h in a.responsive_search_ad.headlines:
            out.append((r.campaign.name, "RSA заголовок", str(a.id), h.text))
        for d in a.responsive_search_ad.descriptions:
            out.append((r.campaign.name, "RSA описание", str(a.id), d.text))
    run("RSA", "SELECT campaign.name, campaign.status, ad_group.status, ad_group_ad.status, ad_group_ad.ad.id, ad_group_ad.ad.responsive_search_ad.headlines, "
        "ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad "
        f"WHERE {where} AND ad_group_ad.status = 'ENABLED' AND ad_group.status = 'ENABLED' AND campaign.status = 'ENABLED'", rsa)

    def casset(r):
        a = r.asset
        cn, aid = r.campaign.name, str(a.id)
        if a.sitelink_asset.link_text:
            for t in (a.sitelink_asset.link_text, a.sitelink_asset.description1, a.sitelink_asset.description2):
                if t:
                    out.append((cn, "сайтлинк", aid, t))
        if a.callout_asset.callout_text:
            out.append((cn, "уточнение", aid, a.callout_asset.callout_text))
        for v in a.structured_snippet_asset.values:
            out.append((cn, "сниппет", aid, v))
        for po in a.price_asset.price_offerings:
            for t in (po.header, po.description):
                if t:
                    out.append((cn, "цена (ассет)", aid, t))
        if a.promotion_asset.promotion_target:
            out.append((cn, "промо", aid, a.promotion_asset.promotion_target))
    run("ассеты кампаний", "SELECT campaign.name, campaign.status, campaign_asset.status, asset.id, asset.sitelink_asset.link_text, asset.sitelink_asset.description1, "
        "asset.sitelink_asset.description2, asset.callout_asset.callout_text, asset.structured_snippet_asset.values, "
        "asset.price_asset.price_offerings, asset.promotion_asset.promotion_target FROM campaign_asset "
        f"WHERE {where} AND campaign_asset.status = 'ENABLED' AND campaign.status = 'ENABLED'", casset)

    def pmax(r):
        t = r.asset.text_asset.text
        if t:
            out.append((r.campaign.name, "PMax " + r.asset_group.name[:20], str(r.asset.id), t))
    run("PMax", "SELECT campaign.name, campaign.status, asset_group.status, asset_group_asset.status, asset_group_asset.field_type, asset_group.name, asset.id, asset.text_asset.text FROM asset_group_asset "
        f"WHERE {where} AND asset_group_asset.status = 'ENABLED' AND asset_group.status = 'ENABLED' AND campaign.status = 'ENABLED' "
        "AND asset_group_asset.field_type IN ('HEADLINE','LONG_HEADLINE','DESCRIPTION')", pmax)

    def dg(r):
        a = r.ad_group_ad.ad.demand_gen_multi_asset_ad
        for x in list(a.headlines) + list(a.descriptions):
            out.append((r.campaign.name, "Demand Gen", str(r.ad_group_ad.ad.id), x.text))
    run("Demand Gen", "SELECT campaign.name, campaign.status, ad_group_ad.status, ad_group_ad.ad.id, ad_group_ad.ad.demand_gen_multi_asset_ad.headlines, "
        "ad_group_ad.ad.demand_gen_multi_asset_ad.descriptions FROM ad_group_ad "
        f"WHERE {where} AND ad_group_ad.status = 'ENABLED' AND campaign.status = 'ENABLED'", dg)
    def disp(r):
        a = r.ad_group_ad.ad.responsive_display_ad
        cn, aid = r.campaign.name, str(r.ad_group_ad.ad.id)
        for x in list(a.headlines) + list(a.long_headline.text and [a.long_headline] or []) + list(a.descriptions):
            out.append((cn, "Display", aid, x.text))
        if a.business_name:
            out.append((cn, "Display", aid, a.business_name))
    run("Display", "SELECT campaign.name, campaign.status, ad_group_ad.status, ad_group_ad.ad.id, "
        "ad_group_ad.ad.responsive_display_ad.headlines, ad_group_ad.ad.responsive_display_ad.long_headline, "
        "ad_group_ad.ad.responsive_display_ad.descriptions, ad_group_ad.ad.responsive_display_ad.business_name FROM ad_group_ad "
        f"WHERE {where} AND ad_group_ad.status = 'ENABLED' AND campaign.status = 'ENABLED'", disp)
    return out


def audit(texts, reg, site):
    findings = []
    for camp, kind, oid, text in texts:
        for c in reg.get("claims", []):
            for m in re.finditer(c["pattern"], text, re.I):
                val = next((g for g in m.groups() if g), None)
                want = site.get(c["fact"]) or reg.get("expected", {}).get(c["fact"])
                if val and want and not same(val, want):
                    findings.append((camp, kind, oid, text, f"{c['label']}: в тексте «{val}», на сайте «{want}»", "РАСХОДИТСЯ"))
        for b in reg.get("banned", []):
            m = re.search(b["pattern"], text, re.I)
            if m:
                findings.append((camp, kind, oid, text, f"«{m.group(0)}»: {b['reason']}", "ПРОВЕРИТЬ" if b.get("warn") else "НЕ ДОКАЗАНО"))
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-ids", nargs="*", default=[])
    ap.add_argument("--site-only", action="store_true")
    ap.add_argument("--screenshots", action="store_true", help="сохранить полноэкранные скриншоты страниц в Креативы/сайт_скриншоты/")
    ap.add_argument("--registry")
    a = ap.parse_args()
    reg_path = Path(a.registry) if a.registry else ROOT / "Клиенты" / a.client_folder / "Креативы" / "facts_registry.yaml"
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))

    print("== 1. Сайт против реестра фактов")
    shots = (ROOT / "Клиенты" / a.client_folder / "Креативы" / "сайт_скриншоты") if a.screenshots else None
    text = fetch_site_text(reg.get("site_urls", []), shots)
    site = extract_site(text, reg.get("site_extract", {})) if text else {}
    changed = []
    for k, exp in reg.get("expected", {}).items():
        got = site.get(k)
        st = "не найдено на странице" if got is None else ("совпало" if same(got, exp) else "ИЗМЕНИЛОСЬ")
        print(f"   {k:<18} реестр: {exp:<16} сайт: {got or '—':<16} → {st}")
        if st == "ИЗМЕНИЛОСЬ":
            changed.append(k)
    for k in reg.get("site_extract", {}):
        if k not in reg.get("expected", {}):
            print(f"   {k:<18} (справочно) сайт: {site.get(k) or '—'}")
    if a.site_only:
        return

    print("\n== 2. Тексты в Google Ads против сайта и реестра")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    cid = str(reg["customer_id"]).replace("-", "")
    texts = collect_texts(ga, cid, a.campaign_ids)
    uniq = {(c, k, t) for c, k, _, t in texts}
    print(f"   текстов собрано: {len(texts)} (уникальных {len(uniq)}), кампаний {len({c for c, *_ in texts})}")
    f = audit(texts, reg, site)
    by = collections.Counter(x[5] for x in f)
    print(f"   находок: {len(f)} {dict(by)}")
    # группируем одинаковые тексты
    g = collections.defaultdict(set)
    for camp, kind, oid, text, why, st in f:
        g[(st, kind.split()[0], text, why)].add((camp, oid))
    print()
    for (st, kind, text, why), objs in sorted(g.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        camps = collections.Counter(c.split("|")[1].strip() if "|" in c else c for c, _ in objs)
        print(f"   [{st}] {kind} ×{len(objs)} {dict(camps)}\n        «{text[:110]}»\n        ← {why}")
    out = client_stats_dir(a.client_folder) / f"ads_facts_audit_{date.today().isoformat()}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["статус", "кампания", "вид", "id", "текст", "причина"])
        for camp, kind, oid, text, why, st in f:
            w.writerow([st, camp, kind, oid, text, why])
    print("\nТаблица:", out)
    if changed:
        print("\n!!! Сайт изменился относительно реестра по:", ", ".join(changed), "→ обновить facts_registry.yaml и рекламу")


if __name__ == "__main__":
    main()
