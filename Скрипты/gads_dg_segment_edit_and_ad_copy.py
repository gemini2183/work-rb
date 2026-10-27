#!/usr/bin/env python
# coding: utf-8
"""Demand Gen Landver (`dg_search_segment`, Э-10): убрать ключи со словом injury из сегмента «искали на Google» и
завести дубли объявлений, чтобы Google заново проверил их по политике «HEALTH_IN_PERSONALIZED_ADS».

Зачем: оба объявления получили APPROVED_LIMITED по теме HEALTH_IN_PERSONALIZED_ADS (27.10), даже B без injury/hurt/victim —
гипотеза: ограничение вызывает сегмент (в нём 5 из 12 ключей про injury), а не текст. Правка сегмента сама повторной проверки
объявлений, скорее всего, не запустит (решение пользователя 27.10: завести дубли объявлений).

Что делает:
  1) читает текущие ключи сегмента и пишет снимок «до» в Статистика/ (JSON);
  2) обновляет ключи сегмента: оставляет только KEEP_KEYWORDS (члены перезаписываются целиком, так работает update в API);
  3) читает объявления группы и создаёт копии (те же тексты и те же ассеты картинок), имя + « copy ДДММ»;
  4) читает всё обратно: ключи сегмента, объявления, статус одобрения и тему политики.

БЕЗОПАСНОСТЬ: по умолчанию validate_only (ничего не пишет). Запись — только с --execute после «да» пользователя.
Откат сегмента: вернуть 12 ключей из снимка (`--restore-from <файл снимка> --execute`); копии объявлений — поставить на паузу или удалить.

Использование:
    python gads_dg_segment_edit_and_ad_copy.py --customer-id 213-621-6123              # проверка
    python gads_dg_segment_edit_and_ad_copy.py --customer-id 213-621-6123 --execute    # запись
    python gads_dg_segment_edit_and_ad_copy.py --customer-id 213-621-6123 --read-back-only
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

CAMPAIGN_NAME = "dg_search_segment"
CUSTOM_AUDIENCE_ID = 1028533814
KEEP_KEYWORDS = ["car accident lawyer", "car accident attorney", "car accident law firm", "car crash attorney",
                 "car crash lawyer", "traffic accident lawyer", "attorney for car accident"]
CLIENT_FOLDER = "Andverpersonalinjury"


def read_members(client, cid):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    out = []
    for r in ga.search(customer_id=cid, query=(
            "SELECT custom_audience.id, custom_audience.name, custom_audience.type, custom_audience.members "
            f"FROM custom_audience WHERE custom_audience.id = {CUSTOM_AUDIENCE_ID}")):
        for m in r.custom_audience.members:
            out.append((E.CustomAudienceMemberTypeEnum.CustomAudienceMemberType.Name(m.member_type), m.keyword))
        name = r.custom_audience.name
    return name, out


def read_ads(client, cid):
    ga = client.get_service("GoogleAdsService")
    ads = []
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group.resource_name, ad_group_ad.status, ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.ad.final_urls, "
            "ad_group_ad.ad.demand_gen_multi_asset_ad.headlines, ad_group_ad.ad.demand_gen_multi_asset_ad.descriptions, "
            "ad_group_ad.ad.demand_gen_multi_asset_ad.business_name, ad_group_ad.ad.demand_gen_multi_asset_ad.call_to_action_text, "
            "ad_group_ad.ad.demand_gen_multi_asset_ad.marketing_images, ad_group_ad.ad.demand_gen_multi_asset_ad.square_marketing_images, "
            "ad_group_ad.ad.demand_gen_multi_asset_ad.logo_images "
            f"FROM ad_group_ad WHERE campaign.name = '{CAMPAIGN_NAME}' AND ad_group_ad.status != 'REMOVED'")):
        a = r.ad_group_ad.ad
        m = a.demand_gen_multi_asset_ad
        ads.append(dict(ad_group=r.ad_group.resource_name, id=a.id, name=a.name, urls=list(a.final_urls),
                        headlines=[h.text for h in m.headlines], descriptions=[d.text for d in m.descriptions],
                        business=m.business_name, cta=m.call_to_action_text,
                        landscape=[x.asset for x in m.marketing_images], square=[x.asset for x in m.square_marketing_images],
                        logo=[x.asset for x in m.logo_images]))
    return ads


def read_back(client, cid):
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    name, members = read_members(client, cid)
    print(f"\n=== Чтение обратно ===\nсегмент {name}: {len(members)} ключей:")
    for t, k in members:
        print("  ", t, k)
    for r in ga.search(customer_id=cid, query=(
            "SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.status, ad_group_ad.policy_summary.approval_status, "
            "ad_group_ad.policy_summary.review_status, ad_group_ad.policy_summary.policy_topic_entries "
            f"FROM ad_group_ad WHERE campaign.name = '{CAMPAIGN_NAME}' AND ad_group_ad.status != 'REMOVED'")):
        ps = r.ad_group_ad.policy_summary
        print(f"  объявление {r.ad_group_ad.ad.id} | {r.ad_group_ad.ad.name} | "
              f"{E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status)} | "
              f"{E.PolicyApprovalStatusEnum.PolicyApprovalStatus.Name(ps.approval_status)} | "
              f"{E.PolicyReviewStatusEnum.PolicyReviewStatus.Name(ps.review_status)} | "
              f"темы {[t.topic for t in ps.policy_topic_entries]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    ap.add_argument("--read-back-only", action="store_true")
    ap.add_argument("--restore-from", help="JSON снимка «до»: вернуть ключи сегмента из него")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums
    if a.read_back_only:
        read_back(client, cid)
        return

    name, before = read_members(client, cid)
    print(f"Сегмент {name}: сейчас {len(before)} ключей")
    for t, k in before:
        print("  ", t, k)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = Path(client_stats_dir(CLIENT_FOLDER)) / f"snapshot_before_dg_segment_{stamp}.json"
    if a.restore_from:
        keep = [k for t, k in json.loads(Path(a.restore_from).read_text(encoding="utf-8"))["members"]]
    else:
        keep = KEEP_KEYWORDS
    ads = read_ads(client, cid)
    print(f"\nПлан: ключей в сегменте {len(before)} -> {len(keep)}; убираются: {[k for t, k in before if k not in keep]}")
    if not a.restore_from:
        print("Копии объявлений:", [ (x['id'], x['name']) for x in ads ])
    if a.execute:
        snap.write_text(json.dumps({"customer": cid, "audience_id": CUSTOM_AUDIENCE_ID, "name": name, "members": before,
                                    "ads": [{k: v for k, v in x.items()} for x in ads]}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print("Снимок «до»:", snap)

    try:
        op = client.get_type("CustomAudienceOperation")
        op.update.resource_name = f"customers/{cid}/customAudiences/{CUSTOM_AUDIENCE_ID}"
        for kw in keep:
            m = op.update.members.add()
            m.member_type = E.CustomAudienceMemberTypeEnum.KEYWORD
            m.keyword = kw
        op.update_mask.paths.append("members")
        req = client.get_type("MutateCustomAudiencesRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not a.execute
        client.get_service("CustomAudienceService").mutate_custom_audiences(request=req)
        print("Сегмент:", "обновлён" if a.execute else "проверка пройдена (validate_only)")

        if not a.restore_from:
            suffix = " copy " + datetime.now().strftime("%d%m")
            ops = []
            for x in ads:
                mo = client.get_type("MutateOperation")
                aga = mo.ad_group_ad_operation.create
                aga.ad_group = x["ad_group"]
                aga.status = E.AdGroupAdStatusEnum.ENABLED
                aga.ad.name = x["name"] + suffix
                aga.ad.final_urls.extend(x["urls"])
                m = aga.ad.demand_gen_multi_asset_ad
                m.business_name = x["business"]
                m.call_to_action_text = x["cta"]
                for t in x["headlines"]:
                    m.headlines.add().text = t
                for t in x["descriptions"]:
                    m.descriptions.add().text = t
                for rn in x["landscape"]:
                    m.marketing_images.add().asset = rn
                for rn in x["square"]:
                    m.square_marketing_images.add().asset = rn
                for rn in x["logo"]:
                    m.logo_images.add().asset = rn
                ops.append(mo)
            mreq = client.get_type("MutateGoogleAdsRequest")
            mreq.customer_id = cid
            mreq.mutate_operations.extend(ops)
            mreq.validate_only = not a.execute
            ga.mutate(request=mreq)
            print("Копии объявлений:", f"созданы ({len(ops)})" if a.execute else f"проверка пройдена ({len(ops)}, validate_only)")
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)

    if a.execute:
        read_back(client, cid)
    else:
        print("\nНИЧЕГО не записано (validate_only).")


if __name__ == "__main__":
    main()
