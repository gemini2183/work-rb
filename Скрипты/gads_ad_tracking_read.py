#!/usr/bin/env python
# coding: utf-8
"""Google Ads: что стоит в шаблонах отслеживания и суффиксах (аккаунт / кампания / группа / объявление). ТОЛЬКО ЧТЕНИЕ.

Зачем (EkspertAgro, 2026-11-24): перед созданием новой кампании нужно видеть дословно, какие tracking_url_template,
final_url_suffix и final_urls действуют у существующих кампаний, где именно лежит шаблон (объявление / группа / кампания /
аккаунт) и совпадает ли он с тем, что отправляет билдер. Скрипт ничего не пишет в кабинет, режима записи и --execute нет.

Читает (GAQL дословно): ad_group_ad.ad.tracking_url_template, ad_group_ad.ad.final_url_suffix, ad_group_ad.ad.final_urls,
ad_group.tracking_url_template, ad_group.final_url_suffix, campaign.tracking_url_template, campaign.final_url_suffix,
customer.tracking_url_template, customer.final_url_suffix. Кампании выбираются по --campaign-id (повторяемый) и/или
--campaign-name-contains (повторяемый), статус кампании по --status (по умолчанию ENABLED PAUSED). Группы и объявления
показываются все, кроме REMOVED. Значения печатаются как repr (пробелы, слэши, спецсимволы видны); ниже каждого значения
со строкой запроса - разобранные параметры utm_* (и gclid-подобные не трогаем, только utm_*).
Читающих запросов к API: 4 (customer, campaign, ad_group, ad_group_ad), учитываются в gads_quota_ledger.

    python gads_ad_tracking_read.py --customer-id 882-613-4558 --campaign-id 24532288983 --campaign-id 24535726248 \
        --client-folder EkspertAgro
    python gads_ad_tracking_read.py --customer-id 882-613-4558 --campaign-name-contains inmarket --status ENABLED

Пишет (если задан --client-folder) Статистика/gads_ad_tracking_read_<дата>.csv. Дата создания: 2026-11-24.
"""
import argparse
import csv
import re
from datetime import date

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import wrap_ga

SCRIPT = "gads_ad_tracking_read"
STATUSES = {"ENABLED", "PAUSED", "REMOVED"}


def parse_utm(value):
    """Разобрать utm_* из значения (шаблон, суффикс или URL) без декодирования: ключ=значение как написано."""
    if not value:
        return {}
    s = value.split("?", 1)[1] if "?" in value else value
    out = {}
    for part in re.split(r"[&;]", s):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.lower().startswith("utm_"):
                out[k] = v
    return out


def status_where(statuses):
    return "campaign.status IN (" + ", ".join(f"'{s}'" for s in statuses) + ")"


def main():
    ap = argparse.ArgumentParser(description="Чтение шаблонов отслеживания/суффиксов/final_urls (только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-id", action="append", default=[], help="повторяемый")
    ap.add_argument("--campaign-name-contains", action="append", default=[], help="подстрока имени, повторяемый")
    ap.add_argument("--status", nargs="+", default=["ENABLED", "PAUSED"], help="статусы кампаний (по умолчанию ENABLED PAUSED)")
    ap.add_argument("--client-folder", help="папка клиента: CSV в Клиенты/<Имя>/Статистика/")
    a = ap.parse_args()
    statuses = [s.upper() for s in a.status]
    bad = [s for s in statuses if s not in STATUSES]
    if bad:
        ap.error(f"статус: {bad}; допустимо {sorted(STATUSES)}")
    if not a.campaign_id and not a.campaign_name_contains:
        ap.error("нужен --campaign-id и/или --campaign-name-contains (читать весь аккаунт без отбора не даём)")
    cid = a.customer_id.replace("-", "").strip()
    ids = {int(i) for i in a.campaign_id}
    names = [n.lower() for n in a.campaign_name_contains]

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = wrap_ga(client.get_service("GoogleAdsService"), SCRIPT)
    st_name = lambda n: client.enums.CampaignStatusEnum.CampaignStatus.Name(n)  # noqa: E731

    rows = []   # (кампания, группа, объявление, уровень, поле, значение)
    cust = next(iter(ga.search(customer_id=cid, query="SELECT customer.tracking_url_template, customer.final_url_suffix FROM customer"))).customer
    rows.append(("[аккаунт]", "", "", "customer", "tracking_url_template", cust.tracking_url_template))
    rows.append(("[аккаунт]", "", "", "customer", "final_url_suffix", cust.final_url_suffix))

    camps = {}
    for r in ga.search(customer_id=cid, query=f"""SELECT campaign.id, campaign.name, campaign.status, campaign.tracking_url_template,
            campaign.final_url_suffix FROM campaign WHERE {status_where(statuses)}"""):
        c = r.campaign
        # GAQL не умеет скобки и OR между разными полями: отбор по id/имени делаем здесь
        if not (c.id in ids or any(n in c.name.lower() for n in names)):
            continue
        label = f"{c.id} {c.name} [{st_name(c.status)}]"
        camps[c.id] = label
        rows.append((label, "", "", "campaign", "tracking_url_template", c.tracking_url_template))
        rows.append((label, "", "", "campaign", "final_url_suffix", c.final_url_suffix))

    if not camps:
        print("Кампаний по отбору не найдено (статусы:", statuses, ")")
        return
    wh = "campaign.id IN (" + ", ".join(str(i) for i in camps) + ")"
    for r in ga.search(customer_id=cid, query=f"""SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status,
            ad_group.tracking_url_template, ad_group.final_url_suffix FROM ad_group
            WHERE {wh} AND ad_group.status != 'REMOVED'"""):
        g = r.ad_group
        gl = f"{g.id} {g.name} [{client.enums.AdGroupStatusEnum.AdGroupStatus.Name(g.status)}]"
        rows.append((camps[r.campaign.id], gl, "", "ad_group", "tracking_url_template", g.tracking_url_template))
        rows.append((camps[r.campaign.id], gl, "", "ad_group", "final_url_suffix", g.final_url_suffix))

    for r in ga.search(customer_id=cid, query=f"""SELECT campaign.id, ad_group.id, ad_group.name, ad_group_ad.ad.id, ad_group_ad.ad.name,
            ad_group_ad.status, ad_group_ad.ad.tracking_url_template, ad_group_ad.ad.final_url_suffix, ad_group_ad.ad.final_urls
            FROM ad_group_ad WHERE {wh} AND ad_group_ad.status != 'REMOVED'"""):
        ad = r.ad_group_ad.ad
        gl = f"{r.ad_group.id} {r.ad_group.name}"
        al = f"{ad.id} {ad.name!r} [{client.enums.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status)}]"
        rows.append((camps[r.campaign.id], gl, al, "ad", "tracking_url_template", ad.tracking_url_template))
        rows.append((camps[r.campaign.id], gl, al, "ad", "final_url_suffix", ad.final_url_suffix))
        rows.append((camps[r.campaign.id], gl, al, "ad", "final_urls", list(ad.final_urls)))

    print(f"Кампаний найдено: {len(camps)}; запросов к API: 4; статусы: {statuses}\n")
    for camp, grp, ad, lvl, field, val in rows:
        print(f"кампания={camp} | группа={grp or '-'} | объявление={ad or '-'} | уровень={lvl} | {field} = {val!r}")
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            u = parse_utm(v)
            if u:
                print("    разобранные utm_*:", u)
    if a.client_folder:
        out = client_stats_dir(a.client_folder) / f"gads_ad_tracking_read_{date.today().isoformat()}.csv"
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["campaign", "ad_group", "ad", "level", "field", "value_repr", "utm"])
            for camp, grp, ad, lvl, field, val in rows:
                vals = val if isinstance(val, list) else [val]
                utm = {}
                for v in vals:
                    utm.update(parse_utm(v))
                w.writerow([camp, grp, ad, lvl, field, repr(val), repr(utm) if utm else ""])
        print("\n(сохранено:", out, ")")


if __name__ == "__main__":
    main()
