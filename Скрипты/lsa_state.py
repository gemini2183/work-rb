#!/usr/bin/env python
# coding: utf-8
"""Состояние кампании Local Services Ads (LSA) — ТОЛЬКО ЧТЕНИЕ. Ничего не пишет ни в кабинет, ни в вики.

Зачем: LSA живёт в Google Ads как системная кампания `LocalServicesCampaign:SystemGenerated:…`, но интерфейс
«Истории изменений» её не показывает, а окна LSA не дают сводки. 2026-10-15 (Landver) одно и то же чтение
понадобилось трижды за сессию: стратегия, бюджет, гео, услуги, лиды, кто менял.

Что выводит:
  1. статус и primary_status, тип стратегии, бюджет в день и в неделю;
  2. территории (гео) с типом City/County и включённые услуги (local_service_id);
  3. показы, клики, расход по дням за --days и итог (дни без показов и расхода не печатаются);
  4. лиды LSA (тип, статус, списан ли);
  5. история изменений кампании за --history-days (≤29): кто, когда, поля, было → стало.

Ограничения API (проверено 2026-10-15): сумму ставки за заявку API не отдаёт — только тип стратегии
(MANUAL_CPA = ручная «максимум за лид», MAXIMIZE_CONVERSIONS = «максимум заявок»); правки стратегии в
change_event приходят как CAMPAIGN UPDATE с пустым списком полей — видно кто и когда, не видно что.

Использование:
    python lsa_state.py --customer-id 2136216123 [--days 30] [--history-days 29]
"""
import argparse
import sys
from datetime import date, datetime, timedelta

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML

LSA = "campaign.advertising_channel_type = 'LOCAL_SERVICES'"


def en(enum_name, value):
    """Имя значения перечисления (клиент отдаёт int, как в state_digest.py)."""
    holder = getattr(E, enum_name + "Enum")
    inner = getattr(holder, enum_name, None) or getattr(holder, enum_name.replace("LocalServices", ""))
    return inner.Name(value)


def run(svc, cid, q):
    return list(svc.search(customer_id=cid, query=q))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--days", type=int, default=30, help="период статистики, дней")
    ap.add_argument("--history-days", type=int, default=29, help="история изменений, не больше 29 дней")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    global E
    E = client.enums
    svc = client.get_service("GoogleAdsService")

    print("== 1. Кампания")
    camps = run(svc, cid, f"""SELECT campaign.resource_name, campaign.id, campaign.name, campaign.status,
        campaign.primary_status, campaign.bidding_strategy_type, campaign_budget.amount_micros,
        campaign_budget.period FROM campaign WHERE {LSA}""")
    if not camps:
        print("  кампании LSA в аккаунте нет")
        return
    names = set()
    for r in camps:
        c, b = r.campaign, r.campaign_budget
        names.add(c.resource_name)
        day = b.amount_micros / 1e6
        print(f"  {c.name} (id {c.id})")
        print(f"  статус {en('CampaignStatus', c.status)}, primary_status {en('CampaignPrimaryStatus', c.primary_status)}, стратегия {en('BiddingStrategyType', c.bidding_strategy_type)}")
        print(f"  бюджет {day:.2f} $/день ≈ {day * 7:.0f} $/нед ({en('BudgetPeriod', b.period)}); сумму ставки за заявку API не отдаёт")

    print("\n== 2. Территории и услуги")
    geo = [r.campaign_criterion for r in run(svc, cid, f"""SELECT campaign_criterion.location.geo_target_constant,
        campaign_criterion.negative FROM campaign_criterion WHERE {LSA} AND campaign_criterion.type = 'LOCATION'""")]
    if geo:
        consts = ",".join(f"'{g.location.geo_target_constant}'" for g in geo)
        neg = {g.location.geo_target_constant for g in geo if g.negative}
        for r in run(svc, cid, f"""SELECT geo_target_constant.resource_name, geo_target_constant.canonical_name,
                geo_target_constant.target_type FROM geo_target_constant
                WHERE geo_target_constant.resource_name IN ({consts})"""):
            g = r.geo_target_constant
            print(f"  {'ИСКЛ ' if g.resource_name in neg else ''}{g.canonical_name} ({g.target_type})")
    else:
        print("  территорий нет")
    services = [r.campaign_criterion for r in run(svc, cid, f"""SELECT campaign_criterion.local_service_id.service_id,
        campaign_criterion.negative, campaign_criterion.status FROM campaign_criterion
        WHERE {LSA} AND campaign_criterion.type = 'LOCAL_SERVICE_ID'""")]
    on = [s.local_service_id.service_id for s in services if s.local_service_id.service_id and not s.negative]
    print(f"  услуги включены: {', '.join(on) or 'нет'}")

    print(f"\n== 3. Статистика за {a.days} дн. (дни без показов и расхода не печатаются)")
    since = (date.today() - timedelta(days=a.days)).isoformat()
    tot = [0, 0, 0.0, 0.0]
    for r in run(svc, cid, f"""SELECT segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions FROM campaign WHERE {LSA}
            AND segments.date BETWEEN '{since}' AND '{date.today().isoformat()}' ORDER BY segments.date"""):
        m = r.metrics
        cost = m.cost_micros / 1e6
        tot = [tot[0] + m.impressions, tot[1] + m.clicks, tot[2] + cost, tot[3] + m.conversions]
        if m.impressions or cost:
            print(f"  {r.segments.date}  показы {m.impressions}  клики {m.clicks}  расход {cost:.2f} $  конв. {m.conversions:g}")
    print(f"  ИТОГО: показы {tot[0]}, клики {tot[1]}, расход {tot[2]:.2f} $, конверсии {tot[3]:g}")

    print("\n== 4. Лиды LSA за тот же период")
    leads = run(svc, cid, f"""SELECT local_services_lead.creation_date_time, local_services_lead.lead_type,
        local_services_lead.lead_status, local_services_lead.lead_charged, local_services_lead.service_id
        FROM local_services_lead WHERE local_services_lead.creation_date_time >= '{since}'""")
    for r in sorted(leads, key=lambda x: x.local_services_lead.creation_date_time):
        l = r.local_services_lead
        print(f"  {str(l.creation_date_time)[:16]}  {en('LocalServicesLeadType', l.lead_type)}  {en('LocalServicesLeadStatus', l.lead_status)}  "
              f"{'списан' if l.lead_charged else 'не списан'}  {l.service_id or ''}")
    print(f"  всего {len(leads)}, списано {sum(1 for r in leads if r.local_services_lead.lead_charged)}")

    hd = min(a.history_days, 29)
    print(f"\n== 5. История изменений кампании LSA за {hd} дн.")
    start = (datetime.now() - timedelta(days=hd)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    n = 0
    for r in run(svc, cid, f"""SELECT change_event.change_date_time, change_event.user_email, change_event.client_type,
            change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields,
            change_event.campaign, change_event.old_resource, change_event.new_resource FROM change_event
            WHERE change_event.change_date_time >= '{start}' AND change_event.change_date_time <= '{end}'
            ORDER BY change_event.change_date_time LIMIT 10000"""):
        e = r.change_event
        if e.campaign not in names:
            continue
        n += 1
        fields = list(e.changed_fields.paths)
        line = (f"  {str(e.change_date_time)[:19]}  {e.user_email}  {en('ChangeClientType', e.client_type)}  "
                f"{en('ChangeEventResourceType', e.change_resource_type)} {en('ResourceChangeOperation', e.resource_change_operation)}  поля: {fields or '— (API не раскрывает)'}")
        if "status" in fields and en('ChangeEventResourceType', e.change_resource_type) == "CAMPAIGN":
            line += f"  статус {en('CampaignStatus', e.old_resource.campaign.status)} → {en('CampaignStatus', e.new_resource.campaign.status)}"
        if en('ChangeEventResourceType', e.change_resource_type) == "CAMPAIGN_BUDGET":
            line += (f"  бюджет {e.old_resource.campaign_budget.amount_micros / 1e6:.2f} → "
                     f"{e.new_resource.campaign_budget.amount_micros / 1e6:.2f} $/день")
        print(line)
    print(f"  событий: {n}")


if __name__ == "__main__":
    main()
