#!/usr/bin/env python
# coding: utf-8
"""Только чтение: где у клиента включены партнёры поиска / КМС и сколько на них уходит,
плюс проба «есть ли в API поля канальных приоритетов».

Зачем: Google с 15.10.2026 раскатывает «Channel prioritization and budget allocation»
(High/Low приоритет канала + доля дневного бюджета для Low). Нужно знать, к каким
нашим кампаниям это вообще применимо и есть ли поля в API. См.
База_знаний/Инструменты/Google-Ads-приоритет-каналов-и-доля-бюджета.md.

Использование:
    python gads_channel_audit.py --customer-id 755-278-1705 --client-folder ProfiMet --days 30
    python gads_channel_audit.py --probe-only            # только проба полей API
    PYTHONPATH=<папка с google-ads 34.0.0> python gads_channel_audit.py --probe-only --api-version v26

Ничего не пишет в кабинет. В Статистика/ клиента кладёт gads_channel_audit.csv.
"""
import argparse
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def _client(api_version=None):
    kw = {"version": api_version} if api_version else {}
    return GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML, **kw)


def _name(client, enum_name, value):
    """Enum из ответа приходит числом — переводим в имя через client.enums."""
    msg = getattr(client.enums, enum_name + "Enum")
    return msg.DESCRIPTOR.enum_types_by_name[enum_name].values_by_number[value].name


def probe_fields(client, terms=("priorit", "allocation", "channel_pri")):
    """Спрашивает у GoogleAdsFieldService, есть ли в этой версии API поля с такими словами."""
    svc = client.get_service("GoogleAdsFieldService")
    found = []
    for t in terms:
        q = (
            "SELECT name, category, data_type, selectable, filterable "
            f"WHERE name LIKE '%{t}%'"
        )
        for row in svc.search_google_ads_fields(query=q):
            found.append(row.name)
    return sorted(set(found))


def fetch_campaigns(client, ga, cid):
    q = """
        SELECT campaign.id, campaign.name, campaign.advertising_channel_type,
               campaign.bidding_strategy_type, campaign.network_settings.target_google_search,
               campaign.network_settings.target_search_network,
               campaign.network_settings.target_content_network,
               campaign_budget.amount_micros, campaign_budget.explicitly_shared,
               campaign_budget.total_amount_micros
        FROM campaign
        WHERE campaign.status = 'ENABLED'
    """
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        c, b = r.campaign, r.campaign_budget
        rows.append({
            "campaign_id": c.id,
            "Campaign": c.name,
            "Type": _name(client, "AdvertisingChannelType", c.advertising_channel_type),
            "Bidding": _name(client, "BiddingStrategyType", c.bidding_strategy_type),
            "Search": c.network_settings.target_google_search,
            "SearchPartners": c.network_settings.target_search_network,
            "Display": c.network_settings.target_content_network,
            "Budget_day": b.amount_micros / 1e6,
            "Shared_budget": b.explicitly_shared,
            "Total_budget": b.total_amount_micros / 1e6 if b.total_amount_micros else 0,
        })
    return pd.DataFrame(rows)


def fetch_network_split(client, ga, cid, d_from, d_to):
    q = f"""
        SELECT campaign.id, segments.ad_network_type, metrics.cost_micros,
               metrics.clicks, metrics.impressions, metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{d_from}' AND '{d_to}' AND campaign.status = 'ENABLED'
    """
    rows = []
    for r in ga.search(customer_id=cid, query=q):
        rows.append({
            "campaign_id": r.campaign.id,
            "network": _name(client, "AdNetworkType", r.segments.ad_network_type),
            "cost": r.metrics.cost_micros / 1e6,
            "clicks": r.metrics.clicks,
            "impr": r.metrics.impressions,
            "conv": r.metrics.conversions,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby(["campaign_id", "network"], as_index=False).sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id")
    ap.add_argument("--client-folder")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--api-version", help="напр. v26 (нужна библиотека, где эта версия есть)")
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args()

    client = _client(args.api_version)
    print(f"API version: {client.version}")
    found = probe_fields(client)
    print("Поля с priorit/allocation в GoogleAdsFieldService:")
    for f in found:
        print("  ", f)
    if not found:
        print("   (нет)")
    if args.probe_only or not args.customer_id:
        return

    client.login_customer_id = client.login_customer_id  # из yaml
    ga = client.get_service("GoogleAdsService")
    cid = args.customer_id.replace("-", "").strip()
    d_to = date.today() - timedelta(days=1)
    d_from = d_to - timedelta(days=args.days - 1)

    camps = fetch_campaigns(client, ga, cid)
    split = fetch_network_split(client, ga, cid, d_from, d_to)
    if camps.empty:
        print("ENABLED-кампаний нет")
        return
    if not split.empty:
        piv = split.pivot_table(index="campaign_id", columns="network", values="cost", aggfunc="sum").fillna(0)
        piv.columns = [f"cost_{c}" for c in piv.columns]
        piv["cost_total"] = piv.sum(axis=1)
        camps = camps.merge(piv.reset_index(), on="campaign_id", how="left")
    camps = camps.round(2)
    print(f"\nПериод {d_from} — {d_to}")
    print(camps.drop(columns=["campaign_id"]).to_string(index=False))
    if args.client_folder:
        out = client_stats_dir(args.client_folder) / "gads_channel_audit.csv"
        camps.to_csv(out, index=False, encoding="utf-8")
        print(f"\nСохранено: {out}")


if __name__ == "__main__":
    main()
