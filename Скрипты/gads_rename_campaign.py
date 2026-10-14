#!/usr/bin/env python
# coding: utf-8
"""Переименование кампании Google Ads (ЗАПИСЬ, по умолчанию validate_only).

Зачем отдельный скрипт: имя кампании — это ключ для внешних выгрузок (например, облачная функция статистики
ExpertAgro делит кампании на «Мерчант» и «Теплицы» по слову `shop` в названии), поэтому переименование делаем
осознанно: печатаем «было → станет», проверяем, что новое имя свободно, читаем обратно.

Использование:
    python gads_rename_campaign.py --customer-id 8826134558 --campaign-id 24353873699 \
        --new-name "general / search / rozmiary / katalog"            # проверка (validate_only)
    ... --execute                                                       # запись
"""
import argparse

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from gads_stats import GOOGLE_ADS_YAML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--new-name", required=True)
    ap.add_argument("--execute", action="store_true", help="Записать. Без флага — только validate_only")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")

    cur = [(r.campaign.name, r.campaign.status) for r in ga.search(customer_id=cid, query=(
        f"SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.id = {a.campaign_id}"))]
    if not cur:
        raise SystemExit(f"Кампания {a.campaign_id} не найдена")
    old_name = cur[0][0]
    safe = a.new_name.replace("'", "\\'")
    taken = [r.campaign.id for r in ga.search(customer_id=cid, query=(
        f"SELECT campaign.id FROM campaign WHERE campaign.name = '{safe}' AND campaign.status != 'REMOVED'"))]
    if taken and str(a.campaign_id) not in [str(t) for t in taken]:
        raise SystemExit(f"СТОП: имя «{a.new_name}» уже занято кампанией {taken}")
    print(f"Было:   {old_name}\nСтанет: {a.new_name}")
    if old_name == a.new_name:
        print("Имя уже такое, ничего не делаю.")
        return

    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    camp = op.update
    camp.resource_name = f"customers/{cid}/campaigns/{a.campaign_id}"
    camp.name = a.new_name
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["name"]))
    try:
        req = client.get_type("MutateCampaignsRequest")
        req.customer_id = cid
        req.operations.append(op)
        req.validate_only = not a.execute
        svc.mutate_campaigns(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            print("  -", err.message)
        raise SystemExit(1)
    if not a.execute:
        print("Проверка пройдена. НИЧЕГО не изменено (validate_only).")
        return
    for r in ga.search(customer_id=cid, query=(
            f"SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.id = {a.campaign_id}")):
        print(f"Прочитано обратно: {r.campaign.id} | {r.campaign.name} | статус {int(r.campaign.status)} (3 = PAUSED)")


if __name__ == "__main__":
    main()
