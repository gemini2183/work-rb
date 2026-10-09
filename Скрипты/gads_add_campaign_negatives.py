#!/usr/bin/env python
# coding: utf-8
"""Добавляет кампанийные минус-слова (тексты и тип соответствия задаются явно) в одну кампанию.

ЗАПИСЬ в аккаунт: без --execute — validate_only. Уже существующие (тот же текст и тип) пропускает.
После записи — чтение обратно. Только после согласования таблицы плана (CLAUDE.md).
Парный скрипт для снятия — gads_remove_campaign_negatives.py.

    python gads_add_campaign_negatives.py --customer-id 213-621-6123 --campaign "search / car+truck injuries / s / lp - tilda" \
        --texts "insider accident lawyers;sweetjames law" --match EXACT [--execute]
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient

from gads_remove_campaign_negatives import MATCH, read_negatives
from gads_stats import GOOGLE_ADS_YAML, get_ads_service


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign", required=True, help="точное имя кампании")
    ap.add_argument("--texts", required=True, help="тексты через ';'")
    ap.add_argument("--match", required=True, choices=sorted(MATCH))
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    cid = args.customer_id.replace("-", "")
    texts = [t.strip().lower() for t in args.texts.split(";") if t.strip()]
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    df = read_negatives(ga, cid, args.campaign)
    have = set(zip(df.Text.str.lower(), df.Match)) if len(df) else set()
    new = [t for t in texts if (t, args.match) not in have]
    print("Объект | Действие | Было → Станет")
    for t in texts:
        print(f"{args.campaign} | минус-слово {args.match} «{t}» | {'уже есть, пропуск' if t not in new else 'нет → добавить'}")
    if not new:
        return

    # campaign_id берём из resource_name существующего критерия или по имени кампании
    q = f"SELECT campaign.resource_name FROM campaign WHERE campaign.name = '{args.campaign}' AND campaign.status != REMOVED"
    camp = [r.campaign.resource_name for b in ga.search_stream(customer_id=cid, query=q) for r in b.results]
    if len(camp) != 1:
        raise SystemExit(f"Кампания по имени найдена {len(camp)} раз(а), ожидалась одна")

    req = client.get_type("MutateCampaignCriteriaRequest")
    req.customer_id = cid
    req.validate_only = not args.execute
    for t in new:
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = camp[0]
        c.negative = True
        c.keyword.text = t
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, args.match)
        req.operations.append(op)
    client.get_service("CampaignCriterionService").mutate_campaign_criteria(request=req)
    print("ВЫПОЛНЕНО (добавлено)" if args.execute else "validate_only: ОК, ничего не изменено")

    after = read_negatives(ga, cid, args.campaign)
    have2 = set(zip(after.Text.str.lower(), after.Match)) if len(after) else set()
    print(f"После (чтение обратно): минус-слов всего {len(after)}; из добавляемых на месте: "
          f"{sum((t, args.match) in have2 for t in new)} из {len(new)}")


if __name__ == "__main__":
    main()
