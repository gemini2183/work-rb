#!/usr/bin/env python
# coding: utf-8
"""Итоги одной кампании Google Ads (Search) за период: ТОЛЬКО ЧТЕНИЕ, в аккаунт не пишет.

Собирает в одну команду то, что раньше делали разовыми запросами (Landver, dog bite и car+truck, 2026-10-15):
  1. настройки кампании сейчас: статус, стратегия, потолок цены клика, бюджет, партнёры, AI Max;
  2. итог за период и разбивка по сетям (чистый поиск / партнёры);
  3. по неделям: показы, клики, расход, конверсии, цена клика, доля показов, потеряно по рангу и бюджету;
  4. конверсии по датам и конверсионным действиям;
  5. группы объявлений: ставка, показы, клики, CTR, доля показов, доля верхних показов;
  6. ключи: тип соответствия, статус, показы, клики, расход, конверсии;
  7. поисковые запросы: какая доля показов/расхода/конверсий видна в отчёте запросов, топ запросов
     с типом соответствия (EXACT / PHRASE / NEAR_EXACT / NEAR_PHRASE / BROAD — имена из enum, не руками);
  8. история изменений (последние 29 дней — лимит API) со старыми и новыми значениями:
     статус, бюджет, потолок цены клика, ставки групп, статусы ключей, минус-слова.

Выводов скрипт не делает: «кампания слабая» — только после сверки конверсий
(База_знаний/Паттерны/Сверка-конверсий-Директ-Метрика-Коллтрекинг.md).

    python gads_campaign_summary.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury \
        --campaign "search / dog bite" --date-from 2026-09-01 --date-to 2026-10-14

CSV ключей и запросов кладётся в Статистика/ клиента: campaign_summary_<кампания>_<от>_to_<до>_{keywords,terms}.csv
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, sanitize_filename
from gads_stats import GOOGLE_ADS_YAML

MAX_HISTORY_DAYS = 29  # change_event: API отказывает уже на ровно 30 днях (см. gads_change_history.py)


def enum_name(client, enum_msg: str, value) -> str:
    """Имя значения enum (клиент отдаёт int): KeywordMatchTypeEnum + 2 → EXACT."""
    try:
        msg = getattr(client.enums, enum_msg)
        return msg.DESCRIPTOR.enum_types_by_name[enum_msg[:-4]].values_by_number[int(value)].name
    except Exception:
        try:
            return value.name
        except AttributeError:
            return str(value)


def money(micros) -> float:
    return round(micros / 1e6, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign", required=True, help="Точное имя кампании или её id")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", default=str(date.today() - timedelta(1)))
    ap.add_argument("--top-terms", type=int, default=40)
    a = ap.parse_args()

    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = lambda m, v: enum_name(client, m, v)  # noqa: E731

    def q(query):
        return [r for b in ga.search_stream(customer_id=cid, query=query) for r in b.results]

    where_c = (f"campaign.id = {a.campaign}" if a.campaign.isdigit()
               else "campaign.name = '" + a.campaign.replace("'", "\\'") + "'")
    period = f"segments.date BETWEEN '{a.date_from}' AND '{a.date_to}'"

    # 1. Настройки
    rows = q(f"""SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type,
        campaign.target_spend.cpc_bid_ceiling_micros, campaign.network_settings.target_search_network,
        campaign.ai_max_setting.enable_ai_max, campaign_budget.amount_micros
        FROM campaign WHERE {where_c}""")
    if not rows:
        raise SystemExit(f"Кампания не найдена: {a.campaign}")
    c = rows[0].campaign
    camp_id = c.id
    print(f"=== {c.name} (id {camp_id}) | период {a.date_from} → {a.date_to} | только чтение ===\n")
    print("[1] Настройки сейчас:")
    print(f"  статус {E('CampaignStatusEnum', c.status)}, стратегия {E('BiddingStrategyTypeEnum', c.bidding_strategy_type)}, "
          f"потолок цены клика {('$' + str(money(c.target_spend.cpc_bid_ceiling_micros))) if c.target_spend.cpc_bid_ceiling_micros else 'нет'}, бюджет ${money(rows[0].campaign_budget.amount_micros)}/день, "
          f"партнёры {'да' if c.network_settings.target_search_network else 'нет'}, AI Max {'да' if c.ai_max_setting.enable_ai_max else 'нет'}")

    # 2. Сети
    print("\n[2] Итог и сети:")
    tot = [0, 0, 0, 0.0]
    for r in q(f"""SELECT segments.ad_network_type, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM campaign WHERE campaign.id = {camp_id} AND {period}"""):
        m = r.metrics
        tot = [tot[0] + m.impressions, tot[1] + m.clicks, tot[2] + m.cost_micros, tot[3] + m.conversions]
        print(f"  {E('AdNetworkTypeEnum', r.segments.ad_network_type):16} показы {m.impressions:6} клики {m.clicks:5} "
              f"${money(m.cost_micros):9} конв {m.conversions:.1f}")
    cpa = f"${money(tot[2] / tot[3])}" if tot[3] else "—"
    print(f"  ВСЕГО            показы {tot[0]:6} клики {tot[1]:5} ${money(tot[2]):9} конв {tot[3]:.1f} | цена конверсии {cpa}")

    # 3. Недели
    print("\n[3] По неделям (неделя с понедельника):")
    for r in q(f"""SELECT segments.week, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions,
        metrics.search_impression_share, metrics.search_rank_lost_impression_share, metrics.search_budget_lost_impression_share,
        metrics.search_top_impression_share
        FROM campaign WHERE campaign.id = {camp_id} AND {period} ORDER BY segments.week"""):
        m = r.metrics
        if not m.impressions:
            continue
        cpc = money(m.cost_micros / m.clicks) if m.clicks else 0
        print(f"  {r.segments.week} показы {m.impressions:5} клики {m.clicks:4} ${money(m.cost_micros):8} конв {m.conversions:4.1f} "
              f"CPC ${cpc:6} | доля показов {m.search_impression_share:.0%} потеряно: рейтинг {m.search_rank_lost_impression_share:.0%}, "
              f"бюджет {m.search_budget_lost_impression_share:.0%} | вверху {m.search_top_impression_share:.0%}")

    # 4. Конверсии по датам
    print("\n[4] Конверсии по датам и действиям:")
    conv_rows = q(f"""SELECT segments.date, segments.conversion_action_name, metrics.conversions, metrics.all_conversions
        FROM campaign WHERE campaign.id = {camp_id} AND {period} AND metrics.all_conversions > 0 ORDER BY segments.date""")
    for r in conv_rows:
        print(f"  {r.segments.date} {r.segments.conversion_action_name}: в «Конверсиях» {r.metrics.conversions:.1f}, "
              f"всего {r.metrics.all_conversions:.1f}")
    if not conv_rows:
        print("  нет (это данные Ads; звонки Ringostat/формы вне Ads сверять отдельно)")

    # 5. Группы
    print("\n[5] Группы объявлений:")
    for r in q(f"""SELECT ad_group.name, ad_group.status, ad_group.cpc_bid_micros, metrics.impressions, metrics.clicks,
        metrics.cost_micros, metrics.conversions, metrics.search_impression_share, metrics.search_top_impression_share
        FROM ad_group WHERE campaign.id = {camp_id} AND {period} AND metrics.impressions > 0"""):
        m = r.metrics
        print(f"  {r.ad_group.name} [{E('AdGroupStatusEnum', r.ad_group.status)}] ставка ${money(r.ad_group.cpc_bid_micros)} | "
              f"показы {m.impressions} клики {m.clicks} CTR {m.clicks / m.impressions:.1%} ${money(m.cost_micros)} "
              f"конв {m.conversions:.1f} | доля показов {m.search_impression_share:.0%}, вверху {m.search_top_impression_share:.0%}")

    stats = client_stats_dir(a.client_folder)
    base = sanitize_filename(f"campaign_summary_{c.name}_{a.date_from}_to_{a.date_to}")

    # 6. Ключи
    kw = []
    for r in q(f"""SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
        ad_group_criterion.status, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM keyword_view WHERE campaign.id = {camp_id} AND {period} AND metrics.impressions > 0"""):
        k, m = r.ad_group_criterion, r.metrics
        kw.append({"group": r.ad_group.name, "keyword": k.keyword.text,
                   "match": E("KeywordMatchTypeEnum", k.keyword.match_type), "status": E("AdGroupCriterionStatusEnum", k.status),
                   "impr": m.impressions, "clicks": m.clicks, "cost": money(m.cost_micros), "conv": round(m.conversions, 2)})
    kw_df = pd.DataFrame(kw)
    print("\n[6] Ключи (с показами; сначала с конверсиями, потом по расходу):")
    if not kw_df.empty:
        kw_df = kw_df.sort_values(["conv", "cost"], ascending=False)
        kw_df.to_csv(stats / f"{base}_keywords.csv", index=False, encoding="utf-8-sig")
        for _, x in kw_df.head(30).iterrows():
            print(f"  [{x.match}] {x.keyword} ({x.group}, {x.status}) | показы {x.impr} клики {x.clicks} ${x.cost} конв {x.conv}")
        if len(kw_df) > 30:
            print(f"  … ещё {len(kw_df) - 30}, полный список в CSV")

    # 7. Запросы
    agg = defaultdict(lambda: {"impr": 0, "clicks": 0, "cost": 0.0, "conv": 0.0, "match": set(), "kw": set()})
    for r in q(f"""SELECT search_term_view.search_term, segments.search_term_match_type, segments.keyword.info.text,
        metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM search_term_view WHERE campaign.id = {camp_id} AND {period}"""):
        x, m = agg[r.search_term_view.search_term], r.metrics
        x["impr"] += m.impressions; x["clicks"] += m.clicks; x["cost"] += m.cost_micros / 1e6; x["conv"] += m.conversions
        x["match"].add(E("SearchTermMatchTypeEnum", r.segments.search_term_match_type)); x["kw"].add(r.segments.keyword.info.text)
    terms = pd.DataFrame([{"term": t, "impr": v["impr"], "clicks": v["clicks"], "cost": round(v["cost"], 2),
                           "conv": round(v["conv"], 2), "match": ",".join(sorted(v["match"])), "keywords": "; ".join(sorted(v["kw"]))}
                          for t, v in agg.items()])
    print("\n[7] Поисковые запросы:")
    if terms.empty:
        print("  отчёт запросов пуст")
    else:
        vi, vc, vv = terms.impr.sum(), terms.cost.sum(), terms.conv.sum()
        share = lambda p, w: f"{p / w:.0%}" if w else "—"  # noqa: E731
        print(f"  видно в отчёте: {len(terms)} запросов, показы {vi} из {tot[0]} ({share(vi, tot[0])}), "
              f"расход ${vc:.0f} из ${money(tot[2])} ({share(vc, tot[2] / 1e6)}), конверсии {vv:.1f} из {tot[3]:.1f}")
        by_match = terms.assign(match=terms.match.str.split(",")).explode("match").groupby("match")[["impr", "clicks", "cost"]].sum()
        print("  по типу соответствия (запрос с несколькими типами считается в каждом):")
        for mt, x in by_match.sort_values("impr", ascending=False).iterrows():
            print(f"    {mt:12} показы {x.impr:5} клики {x.clicks:4} ${x.cost:.0f}")
        terms = terms.sort_values(["conv", "cost", "impr"], ascending=False)
        terms.to_csv(stats / f"{base}_terms.csv", index=False, encoding="utf-8-sig")
        for _, x in terms.head(a.top_terms).iterrows():
            print(f"  {x.term} | показы {x.impr} клики {x.clicks} ${x.cost:.0f} конв {x.conv} | {x.match} | ключ: {x.keywords[:70]}")

    # 8. История изменений
    print("\n[8] История изменений (лимит API — последние 29 дней):")
    h_from = max(datetime.strptime(a.date_from, "%Y-%m-%d").date(), date.today() - timedelta(MAX_HISTORY_DAYS))
    if datetime.strptime(a.date_from, "%Y-%m-%d").date() < h_from:
        print(f"  ВНИМАНИЕ: история до {h_from} через API недоступна")
    ev = q(f"""SELECT change_event.change_date_time, change_event.change_resource_type, change_event.resource_change_operation,
        change_event.user_email, change_event.client_type, change_event.changed_fields, change_event.old_resource, change_event.new_resource,
        change_event.change_resource_name
        FROM change_event WHERE change_event.campaign = 'customers/{cid}/campaigns/{camp_id}'
        AND change_event.change_date_time >= '{h_from}' AND change_event.change_date_time <= '{date.today() + timedelta(1)}'
        ORDER BY change_event.change_date_time LIMIT 10000""")
    # change_event отдаёт только изменённые поля: у паузы ключа нет текста, у созданного — типа соответствия.
    # Текст, тип и признак минуса берём из текущего состояния по resource_name (удалённые критерии там не найдутся).
    crit = {}
    for r in q(f"""SELECT ad_group_criterion.resource_name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
        ad_group_criterion.negative FROM ad_group_criterion WHERE campaign.id = {camp_id} AND ad_group_criterion.type = KEYWORD"""):
        k = r.ad_group_criterion
        crit[k.resource_name] = (k.keyword.text, E("KeywordMatchTypeEnum", k.keyword.match_type), k.negative)
    for r in q(f"""SELECT campaign_criterion.resource_name, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type,
        campaign_criterion.negative FROM campaign_criterion WHERE campaign.id = {camp_id} AND campaign_criterion.type = KEYWORD"""):
        k = r.campaign_criterion
        crit[k.resource_name] = (k.keyword.text, E("KeywordMatchTypeEnum", k.keyword.match_type), k.negative)
    groups = {r.ad_group.resource_name: r.ad_group.name
              for r in q(f"SELECT ad_group.resource_name, ad_group.name FROM ad_group WHERE campaign.id = {camp_id}")}
    neg = defaultdict(list)
    for r in ev:
        e = r.change_event
        ts, who = str(e.change_date_time)[:16], e.user_email
        rtype = E("ChangeEventResourceTypeEnum", e.change_resource_type)
        op = E("ResourceChangeOperationEnum", e.resource_change_operation)
        o, n = e.old_resource, e.new_resource
        fields = list(e.changed_fields.paths)
        if rtype == "CAMPAIGN":
            parts = []
            if "status" in fields:
                parts.append(f"статус {E('CampaignStatusEnum', o.campaign.status)} → {E('CampaignStatusEnum', n.campaign.status)}")
            if any("cpc_bid_ceiling" in f for f in fields):
                ceil = lambda v: f"${money(v)}" if v else "нет"  # noqa: E731
                parts.append(f"потолок клика {ceil(o.campaign.target_spend.cpc_bid_ceiling_micros)} → {ceil(n.campaign.target_spend.cpc_bid_ceiling_micros)}")
            if any("bidding" in f or "manual_cpc" in f or "target_spend" in f for f in fields) and not parts:
                parts.append("стратегия ставок: " + ", ".join(fields))
            print(f"  {ts} КАМПАНИЯ {'; '.join(parts) or ', '.join(fields) or '(поля не переданы)'}  [{who}]")
        elif rtype == "CAMPAIGN_BUDGET":
            print(f"  {ts} БЮДЖЕТ ${money(o.campaign_budget.amount_micros)} → ${money(n.campaign_budget.amount_micros)}  [{who}]")
        elif rtype == "AD_GROUP":
            parts = []
            if "cpc_bid_micros" in fields:
                parts.append(f"ставка ${money(o.ad_group.cpc_bid_micros)} → ${money(n.ad_group.cpc_bid_micros)}")
            if "status" in fields:
                parts.append(f"статус {E('AdGroupStatusEnum', o.ad_group.status)} → {E('AdGroupStatusEnum', n.ad_group.status)}")
            if op == "CREATE":
                parts.insert(0, "создана")
            if parts:
                name = n.ad_group.name or o.ad_group.name or groups.get(e.change_resource_name, e.change_resource_name)
                print(f"  {ts} ГРУППА {name}: {', '.join(parts)}  [{who}]")
        elif rtype in ("AD_GROUP_CRITERION", "CAMPAIGN_CRITERION"):
            k = getattr(n if op != "REMOVE" else o, rtype.lower())
            cur = crit.get(e.change_resource_name)
            text = (cur[0] if cur else k.keyword.text).strip('"')
            match = cur[1] if cur else (E("KeywordMatchTypeEnum", k.keyword.match_type) if k.keyword.match_type else "тип ?")
            is_neg = cur[2] if cur else (k.negative or rtype == "CAMPAIGN_CRITERION")
            level = "группа" if rtype == "AD_GROUP_CRITERION" else "кампания"
            if not text:
                if rtype == "CAMPAIGN_CRITERION":
                    neg[(ts[:10], "кампания: гео/прочие критерии", op)].append(str(k.criterion_id))
                else:
                    print(f"  {ts} КРИТЕРИЙ ГРУППЫ {op} (не ключ или удалён): {', '.join(fields)[:100]}  [{who}]")
            elif "status" in fields and op == "UPDATE":
                st_o = E("AdGroupCriterionStatusEnum", o.ad_group_criterion.status)
                st_n = E("AdGroupCriterionStatusEnum", n.ad_group_criterion.status)
                print(f"  {ts} КЛЮЧ {text} [{match}]: {st_o} → {st_n}  [{who}]")
            elif any("cpc_bid" in f for f in fields) and op == "UPDATE":
                print(f"  {ts} СТАВКА КЛЮЧА {text}: ${money(o.ad_group_criterion.cpc_bid_micros)} → "
                      f"${money(n.ad_group_criterion.cpc_bid_micros)}  [{who}]")
            elif is_neg:
                neg[(ts[:10], f"минусы, {level}", op)].append(f"{text} [{match}]")
            else:
                neg[(ts[:10], f"ключи, {level}", op)].append(f"{text} [{match}]")
        elif rtype in ("AD", "AD_GROUP_AD"):
            print(f"  {ts} ОБЪЯВЛЕНИЕ {op}: {', '.join(fields)[:120]}  [{who}]")
    for (d, level, op), items in sorted(neg.items()):
        verb = "добавлено" if op == "CREATE" else ("снято" if op == "REMOVE" else op)
        print(f"  {d} {level.upper()} {verb} {len(items)}: {', '.join(items[:25])}{' …' if len(items) > 25 else ''}")
    if not ev:
        print("  изменений нет")
    print(f"\nCSV: {stats}\\{base}_keywords.csv, {base}_terms.csv")


if __name__ == "__main__":
    main()
