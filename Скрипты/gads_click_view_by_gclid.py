#!/usr/bin/env python
# coding: utf-8
"""Заявка → клик в Google Ads по gclid (click_view) — ТОЛЬКО ЧТЕНИЕ.

Зачем: понять, из какой сети/канала пришли конкретные заявки (например, спам-формы из PMax):
по gclid из URL заявки находим клик и читаем сеть (ad_network_type), устройство, кампанию.
(Поля click_type/slot/location несовместимы в одном запросе с click_view — проверено 2026-10-14, INVALID_ARGUMENT.) Плюс сводка по `gad_campaignid` из URL: какому каналу он соответствует.

Вход: CSV (utf-8) с колонками `date` (дата заявки, ГГГГ-ММ-ДД), `gclid`, `label` (любой текст,
например телефон/метка «фейк»), `gad_campaignid` (необязательно). click_view требует фильтр по ОДНОЙ дате,
поэтому для каждого gclid пробуем дату заявки и `--back` предыдущих дней (клик мог быть раньше заявки).
Ограничение API: click_view хранит ~90 дней.

Использование:
    python gads_click_view_by_gclid.py --customer-id 8826134558 --csv leads_gclid.csv [--back 2] \
        [--out ..\\Клиенты\\EkspertAgro\\Статистика\\click_view_gclid.csv]
"""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML

_CLIENT = None


def enum_name(enum_type, field, value):
    if hasattr(value, "name"):
        return value.name
    return getattr(_CLIENT.enums, enum_type).DESCRIPTOR.enum_types_by_name[field].values_by_number[int(value)].name


def find_click(ga, cid, gclid, day):
    q = f"""
        SELECT click_view.gclid, segments.date, segments.ad_network_type, segments.device,
               campaign.id, campaign.name
        FROM click_view
        WHERE click_view.gclid = '{gclid}' AND segments.date = '{day}'
    """
    for batch in ga.search_stream(customer_id=cid, query=q):
        for r in batch.results:
            return r
    return None


def main():
    global _CLIENT
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--back", type=int, default=2, help="сколько предыдущих дней пробовать после даты заявки")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    _CLIENT = client
    ga = client.get_service("GoogleAdsService")

    leads = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    out_rows, not_found = [], []
    for ld in leads:
        gclid = (ld.get("gclid") or "").strip()
        d0 = date.fromisoformat(ld["date"])
        hit = None
        if gclid:
            for k in range(0, a.back + 1):
                day = d0 - timedelta(days=k)
                try:
                    hit = find_click(ga, cid, gclid, day.isoformat())
                except Exception as e:  # noqa: BLE001 — показываем причину и идём дальше
                    print(f"  ! {ld.get('label')} {day}: {str(e)[:160]}")
                    break
                if hit:
                    break
        if not hit:
            not_found.append(ld)
            out_rows.append([ld["date"], ld.get("label", ""), ld.get("gad_campaignid", ""), gclid[:20],
                             "НЕ НАЙДЕН", "", "", ""])
            continue
        out_rows.append([
            ld["date"], ld.get("label", ""), ld.get("gad_campaignid", ""), gclid[:20],
            hit.segments.date,
            enum_name("AdNetworkTypeEnum", "AdNetworkType", hit.segments.ad_network_type),
            enum_name("DeviceEnum", "Device", hit.segments.device),
            f"{hit.campaign.id} {hit.campaign.name}",
        ])

    hdr = ["дата заявки", "метка", "gad_campaignid", "gclid", "дата клика", "сеть", "устройство", "кампания"]
    print("\t".join(hdr))
    for r in out_rows:
        print("\t".join(str(x) for x in r))

    print("\n=== сводка по gad_campaignid → сеть / устройство ===")
    agg = defaultdict(Counter)
    for r in out_rows:
        agg[r[2]][(r[5], r[6])] += 1
    for k, c in agg.items():
        print(f"gad_campaignid={k or '—'}: " + "; ".join(f"{n}/{s} × {v}" for (n, s), v in c.items()))
    print(f"найдено кликов: {len(out_rows) - len(not_found)} из {len(out_rows)}")

    if a.out:
        with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(hdr)
            w.writerows(out_rows)
        print(f"(сохранено: {a.out})")


if __name__ == "__main__":
    main()
