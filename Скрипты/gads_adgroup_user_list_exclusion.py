#!/usr/bin/env python
# coding: utf-8
"""Снимает (или возвращает) исключение списка аудитории на уровне ГРУППЫ объявлений Google Ads.

Зачем: опыт 2026-10-12 на `dspl_rtg_engage_mid` (0 показов): временно снять исключение списка корзины
(`GA4 - Добавили товар в корзину (60 дн.)`, id 8365998003) и посмотреть, пойдут ли показы — аудитория после трёх
вычитаний могла упасть ниже порога показа (гипотеза, не проверена).

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись — только с --execute. Снимок «до» сохраняется в Статистика/ клиента,
после записи критерии читаются обратно.

Использование:
    # снять:
    python gads_adgroup_user_list_exclusion.py --customer-id 7552781705 --client-folder ProfiMet \
        --campaign-id 24335049091 --list-id 8365998003 --action remove [--execute]
    # вернуть (откат):
    ... --action add [--execute]
"""
import argparse
import json
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--list-id", required=True)
    ap.add_argument("--action", required=True, choices=["remove", "add"])
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    list_rn = f"customers/{cid}/userLists/{args.list_id}"

    def read():
        q = ("SELECT ad_group.id, ad_group.name, ad_group_criterion.resource_name, ad_group_criterion.negative, "
             "ad_group_criterion.user_list.user_list FROM ad_group_criterion "
             f"WHERE campaign.id = {args.campaign_id} AND ad_group_criterion.type = 'USER_LIST' "
             "AND ad_group_criterion.status != 'REMOVED'")
        out = []
        for r in ga.search(customer_id=cid, query=q):
            c = r.ad_group_criterion
            out.append({"ad_group_id": r.ad_group.id, "ad_group": r.ad_group.name, "resource": c.resource_name,
                        "negative": c.negative, "list": c.user_list.user_list})
        return out

    before = read()
    print("критерии списков в группе(ах) до:")
    for b in before:
        print("  ", b["ad_group"], "|", b["list"].split("/")[-1], "| минус" if b["negative"] else "| включён")
    snap = client_stats_dir(args.client_folder) / f"snapshot_before_adgroup_lists_{args.campaign_id}_{datetime.now():%Y%m%d_%H%M}.json"
    snap.write_text(json.dumps(before, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Снимок «до»:", snap)

    svc = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    if args.action == "remove":
        target = [b for b in before if b["negative"] and b["list"] == list_rn]
        if len(target) != 1:
            raise SystemExit(f"ожидался ровно один минус-критерий списка {args.list_id}, найдено {len(target)}")
        op.remove = target[0]["resource"]
    else:
        groups = {b["ad_group_id"] for b in before}
        if len(groups) != 1:
            raise SystemExit("для add нужна ровно одна группа в кампании")
        if any(b["list"] == list_rn and b["negative"] for b in before):
            raise SystemExit("исключение уже стоит")
        op.create.ad_group = f"customers/{cid}/adGroups/{groups.pop()}"
        op.create.negative = True
        op.create.user_list.user_list = list_rn
    req = client.get_type("MutateAdGroupCriteriaRequest")
    req.customer_id = cid
    req.operations.append(op)
    req.validate_only = not args.execute
    try:
        svc.mutate_ad_group_criteria(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors[:5]:
            print("  -", err.message)
        raise SystemExit(1)
    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не изменено (validate_only).")
        return
    print("прочитано обратно:")
    for b in read():
        print("  ", b["ad_group"], "|", b["list"].split("/")[-1], "| минус" if b["negative"] else "| включён")


if __name__ == "__main__":
    main()
