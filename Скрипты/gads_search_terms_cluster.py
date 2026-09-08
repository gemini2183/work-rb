#!/usr/bin/env python
# coding: utf-8
"""Кластеризация search terms по товарным темам, понедельная динамика.

Группирует реальные поисковые запросы (search_term_view) по темам через
поиск ключевых кусков слова (regex, без ML) — темы и паттерны заданы в
CLUSTERS ниже, под конкретного клиента их нужно менять руками. Сделано для
Корогвы (Merchant_Shopping) по запросу пользователя: понять, какая товарная
тема перестала конвертить, а не смотреть на 6000+ разрозненных строк.

ВНИМАНИЕ: search_term_view для Shopping/PMax кампаний покрывает НЕ весь
трафик кампании (см. База_знаний/Инструменты/Search-Term-View-ограничения-
Shopping-Performance-Max.md, факт №3) — суммы здесь дают верную ПРОПОРЦИЮ
между темами и неделями, но не точный абсолютный объём кампании. Для
абсолютных цифр расхода/конверсий использовать gads_campaigns_breakdown.py
без --search-terms.

Логика классификации: для каждого запроса, в порядке списка CLUSTERS,
проверяется первый совпавший regex-паттерн — тема присваивается по первому
совпадению (порядок важен для неоднозначных случаев, напр. "корогва
прапори" должен попасть в "Бренд", а не в "Прапори", если Бренд идёт
первым в списке). Запросы без совпадений попадают в "Інше".

Использование:
    python gads_search_terms_cluster.py --customer-id 845-234-6433 \
        --client-folder "Корогва" --campaigns "Merchant_Shopping" \
        --date-from 2026-07-01 --date-to 2026-09-07
"""
import argparse
import re

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

# Темы под Корогву (флаги/одежда, укр+рус+транслит варианты) — под другого
# клиента переписать этот список под его ассортимент.
CLUSTERS = [
    ("Бренд (корогва/corogva)", [r"корогв", r"corogva", r"corohva"]),
    ("Прапори", [r"прапор", r"флаг", r"флажок"]),
    ("Худі/Зіп-худі", [r"худ[іи]", r"з[іи]п.?худ"]),
    ("Футболки", [r"футбол", r"т[іи]шот", r"t.?shirt"]),
    ("Штани/Шорти", [r"штан", r"джогер", r"шорт"]),
    ("Світшот/Лонгслів", [r"св[іи]тшот", r"лонгслів", r"лонгслив"]),
    ("Череп/Skull", [r"черен", r"skull", r"скелет"]),
    ("Донбас/Донецьк", [r"донецьк", r"донбас"]),
    ("Мерч/коллаб (артисты)", [r"стерненко", r"русор[іи]з", r"норд див[іи]жн", r"\bмур\b", r"band merch", r"мерч"]),
]


def classify(term: str) -> str:
    t = str(term).lower()
    for label, patterns in CLUSTERS:
        for p in patterns:
            if re.search(p, t):
                return label
    return "Інше (без чіткої теми)"


def fetch_search_terms_by_date(ga_service, customer_id, date_from, date_to, campaign_names):
    query = f"""
        SELECT
            segments.date,
            campaign.name,
            search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND campaign.status != 'REMOVED'
    """
    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            if campaign_names and row.campaign.name not in campaign_names:
                continue
            rows.append({
                "date": row.segments.date,
                "campaign": row.campaign.name,
                "term": row.search_term_view.search_term,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost": row.metrics.cost_micros / 1_000_000,
                "conversions": row.metrics.conversions,
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/')
    ap.add_argument("--campaigns", required=True, help="Список названий кампаний через запятую (Shopping/Search — не PMax, search_term_view для PMax пуст)")
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    if args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
    elif args.customer_id:
        customer_id = args.customer_id.replace("-", "")
    else:
        print("Нужен либо --client, либо --customer-id")
        return

    campaign_names = {c.strip() for c in args.campaigns.split(",")}
    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    df = fetch_search_terms_by_date(ga_service, customer_id, args.date_from, args.date_to, campaign_names)
    if df.empty:
        print("Нет данных search_term_view за период/кампании")
        return

    df["cluster"] = df["term"].apply(classify)
    df["date"] = pd.to_datetime(df["date"])
    df["week_start"] = (df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")).dt.date

    out_dir = client_stats_dir(args.client_folder)
    raw_path = out_dir / f"search_terms_clustered_{args.date_from}_to_{args.date_to}.csv"
    df.drop(columns=["date"]).to_csv(raw_path, index=False, encoding="utf-8")
    print(f"Сохранено (сырые строки с темой): {raw_path} ({len(df)} строк)")

    weekly = df.groupby(["cluster", "week_start"]).agg(
        clicks=("clicks", "sum"), cost=("cost", "sum"), conversions=("conversions", "sum")
    ).reset_index()
    weekly["CPA"] = (weekly["cost"] / weekly["conversions"]).round(1)
    weekly_path = out_dir / f"search_terms_clustered_weekly_{args.date_from}_to_{args.date_to}.csv"
    weekly.to_csv(weekly_path, index=False, encoding="utf-8")
    print(f"Сохранено (понедельная сводка по темам): {weekly_path}")

    pd.set_option("display.width", 200)
    print("\nПонедельная динамика конверсий по темам (0.0 — были клики, конверсий нет):")
    piv_conv = weekly.pivot(index="cluster", columns="week_start", values="conversions").fillna(0).round(1)
    print(piv_conv.to_string())

    print("\nПонедельный CPA по темам (inf — были клики, ни одной конверсии за неделю):")
    piv_cpa = weekly.pivot(index="cluster", columns="week_start", values="CPA")
    print(piv_cpa.to_string())

    print("\nТоп-15 'Інше' по расходу (не попало ни в одну тему — либо расширить CLUSTERS, либо мусорный трафик):")
    other = df[df["cluster"] == "Інше (без чіткої теми)"].groupby("term").agg(
        cost=("cost", "sum"), clicks=("clicks", "sum"), conversions=("conversions", "sum")
    ).sort_values("cost", ascending=False).head(15)
    print(other.to_string())


if __name__ == "__main__":
    main()
