#!/usr/bin/env python
# coding: utf-8
"""Только чтение: у всех ли включённых кампаний Google Ads клик приносит UTM (иначе коллтрекинг не определяет канал).

Зачем: если у клика нет `utm_source/utm_medium`, Ringostat не относит посетителя к каналу и показывает номер сайта по
умолчанию; звонок попадает в «Нет метки» / «Телефон», хотя пришёл из рекламы (ProfiMet, 2026-10-20). Скрипт читает шаблон
отслеживания аккаунта, кампании и объявления (`tracking_url_template`, `final_url_suffix`, `final_urls`) и показывает, где
UTM есть, а где нет, с расходом за последние дни по кампании. Ничего не пишет в кабинет.

Использование:
    python gads_utm_template_audit.py --customer-id 755-278-1705 --client-folder ProfiMet --days 30
Пишет `Статистика/gads_utm_template_audit_<дата>.csv` (по кампаниям).
"""
import argparse
from datetime import date

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def has_utm(*texts):
    s = " ".join(t or "" for t in texts).lower()
    return {"source": "utm_source" in s, "medium": "utm_medium" in s, "campaign": "utm_campaign" in s}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    cust = next(iter(ga.search(customer_id=cid, query="SELECT customer.tracking_url_template, customer.final_url_suffix FROM customer"))).customer
    print("Аккаунт: шаблон отслеживания:", cust.tracking_url_template or "—", "| суффикс:", cust.final_url_suffix or "—")

    q = f"""SELECT campaign.id, campaign.name, campaign.advertising_channel_type, campaign.tracking_url_template, campaign.final_url_suffix,
                   metrics.cost_micros, metrics.clicks
            FROM campaign WHERE campaign.status = 'ENABLED' AND segments.date DURING LAST_{a.days}_DAYS"""
    camps = {}
    for r in ga.search(customer_id=cid, query=q):
        c = camps.setdefault(r.campaign.id, {"id": r.campaign.id, "campaign": r.campaign.name,
                                              "type": client.enums.AdvertisingChannelTypeEnum.DESCRIPTOR.enum_types_by_name[
                                                  "AdvertisingChannelType"].values_by_number[r.campaign.advertising_channel_type].name,
                                              "template": r.campaign.tracking_url_template, "suffix": r.campaign.final_url_suffix,
                                              "cost": 0.0, "clicks": 0})
        c["cost"] += r.metrics.cost_micros / 1e6
        c["clicks"] += r.metrics.clicks

    ads = {}
    qa = """SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.ad.tracking_url_template, ad_group_ad.ad.final_url_suffix, ad_group_ad.ad.final_urls
            FROM ad_group_ad WHERE campaign.status = 'ENABLED' AND ad_group_ad.status = 'ENABLED'"""
    for r in ga.search(customer_id=cid, query=qa):
        d = ads.setdefault(r.campaign.id, {"n": 0, "own": 0, "utm_in_url": 0, "override_no_utm": 0})
        ad = r.ad_group_ad.ad
        d["n"] += 1
        d["own"] += int(bool(ad.tracking_url_template or ad.final_url_suffix))
        d["utm_in_url"] += int(any("utm_" in u for u in ad.final_urls))
        # собственный шаблон объявления ПЕРЕКРЫВАЕТ шаблон кампании: без UTM в нём клик приходит без меток
        if ad.tracking_url_template and not all(has_utm(ad.tracking_url_template, ad.final_url_suffix)[k] for k in ("source", "medium")):
            d["override_no_utm"] += 1
    # то же на уровне групп объявлений и ключевых слов (шаблон ключа перекрывает шаблон объявления и кампании)
    over = {"группа": [], "ключ": []}
    for r in ga.search(customer_id=cid, query="""SELECT campaign.id, campaign.name, ad_group.name, ad_group.tracking_url_template
            FROM ad_group WHERE campaign.status = 'ENABLED' AND ad_group.status = 'ENABLED'"""):
        if r.ad_group.tracking_url_template:
            over["группа"].append((r.campaign.name, r.ad_group.name, r.ad_group.tracking_url_template))
    for r in ga.search(customer_id=cid, query="""SELECT campaign.id, campaign.name, ad_group.name, ad_group_criterion.tracking_url_template
            FROM ad_group_criterion WHERE campaign.status = 'ENABLED' AND ad_group.status = 'ENABLED' AND ad_group_criterion.status = 'ENABLED'
            AND ad_group_criterion.type = KEYWORD"""):
        if r.ad_group_criterion.tracking_url_template:
            over["ключ"].append((r.campaign.name, r.ad_group.name, r.ad_group_criterion.tracking_url_template))
    for k, v in over.items():
        no_utm = [x for x in v if not (has_utm(x[2])["source"] and has_utm(x[2])["medium"])]
        print(f"Собственный шаблон на уровне «{k}»: {len(v)}; из них без utm_source+utm_medium (перекрывают UTM кампании): {len(no_utm)}",
              no_utm[:3] if no_utm else "")

    rows = []
    for c in camps.values():
        eff = has_utm(cust.tracking_url_template, cust.final_url_suffix, c["template"], c["suffix"])
        d = ads.get(c["id"], {"n": 0, "own": 0, "utm_in_url": 0, "override_no_utm": 0})
        ad_utm = d["own"] > 0 or d["utm_in_url"] > 0
        rows.append({"id": c["id"], "campaign": c["campaign"], "type": c["type"], "cost": round(c["cost"], 2), "clicks": c["clicks"],
                     "template": c["template"], "suffix": c["suffix"], "utm_source": eff["source"], "utm_medium": eff["medium"],
                     "utm_campaign": eff["campaign"], "ads": d["n"], "ads_с_своим_шаблоном_или_UTM_в_url": d["own"] + d["utm_in_url"],
                     "объявлений_с_шаблоном_без_UTM": d["override_no_utm"], "UTM_есть_где-то": (eff["source"] and eff["medium"]) or ad_utm})
    df = pd.DataFrame(rows).sort_values("cost", ascending=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
    print(f"\nВключённые кампании с расходом за {a.days} дн: {len(df)}; расход {df['cost'].sum():.2f}")
    print(df[["campaign", "type", "cost", "clicks", "utm_source", "utm_medium", "utm_campaign", "ads", "ads_с_своим_шаблоном_или_UTM_в_url", "объявлений_с_шаблоном_без_UTM"]].to_string(index=False))
    bad = df[~df["UTM_есть_где-то"]]
    print(f"\nКампании без UTM source+medium ни в аккаунте, ни в кампании, ни в объявлениях: {len(bad)}; расход {bad['cost'].sum():.2f} из {df['cost'].sum():.2f}")
    for _, r in bad.iterrows():
        print("  ", r["campaign"], r["type"], "расход", r["cost"], "| шаблон:", r["template"] or "—", "| суффикс:", r["suffix"] or "—")
    out = client_stats_dir(a.client_folder) / f"gads_utm_template_audit_{date.today().isoformat()}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print("\n(сохранено:", out, ")")


if __name__ == "__main__":
    main()
