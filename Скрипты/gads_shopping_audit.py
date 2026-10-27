#!/usr/bin/env python
# coding: utf-8
"""Аудит Shopping-кампании Google Ads одним запуском — ТОЛЬКО ЧТЕНИЕ.

Печатает по одной кампании (по имени или id):
  1) настройки: статус, ставки и потолок клика, бюджет, Merchant Center, приоритет, сети, расписание, исключённые аудитории;
  2) структура: группы объявлений, дерево товарных групп (что включено, что исключено), сколько товаров фида под ними;
  3) минусы: уровня кампании и групп (по типам соответствия), подключённые общие списки (имя, число фраз, типы соответствия);
  4) фид (shopping_product): товары по типу и статусу показа, какая доля фида покрыта включёнными группами;
  5) динамика по неделям: показы, клики, расход, цена клика, CTR, конверсии Ads;
  6) куда уходят деньги: по типу товара и по размеру из названия («3x6», «2,5x4»), топ товаров по расходу, расход на товары
     без конверсий, топ запросов по расходу без конверсий (если отчёт доступен).
Конверсии — только Ads (занижают звонки и формы вне Ads): годятся для сравнения товаров и размеров между собой, не для цены заявки.
Пишет CSV по товарам в `Клиенты/<папка>/Статистика/shopping_audit_<кампания>_<дата>.csv`, если указан --client-folder.

Использование (из папки Скрипты, PYTHONUTF8=1):
    python gads_shopping_audit.py --customer-id 882-613-4558 --campaign shop_tail [--days 30] [--client-folder "EkspertAgro/Мерчант"]
Ограничения: отчёт по запросам Shopping показывает только видимые запросы (у `shop_search` около 31% кликов); размер берётся
из названия товара регулярным выражением; кампания, созданная только что, даст пустую динамику.
"""
import argparse
import collections
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML

ROOT = Path(__file__).resolve().parent.parent
SIZE_RX = re.compile(r"(?<!\d)(\d+(?:[.,]\d)?)\s*[x×х]\s*(\d+(?:[.,]\d)?)\s*m?(?!\d)", re.I)


SIZE_M_RX = re.compile(r"(?<!\d)(\d+(?:[.,]\d)?)\s*[x×х]\s*(\d+(?:[.,]\d)?)\s*m" + chr(92) + "b", re.I)


def size_of(title):
    """Размер товара из названия: сначала «3x4m» (с буквой m — размер изделия), иначе первая пара чисел (профиль «40x20» не в приоритете)."""
    m = SIZE_M_RX.search(title or "") or SIZE_RX.search(title or "")
    return f"{m.group(1).replace('.', ',')}x{m.group(2).replace('.', ',')}" if m else "—"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign", required=True, help="имя или числовой id кампании")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--client-folder", default=None)
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    def q(query):
        return [r for b in ga.search_stream(customer_id=cid, query=query) for r in b.results]

    cond = f"campaign.id = {a.campaign}" if a.campaign.isdigit() else f"campaign.name = '{a.campaign}'"
    rows = q(f"""SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, campaign.bidding_strategy_type,
        campaign.target_spend.cpc_bid_ceiling_micros, campaign.shopping_setting.merchant_id, campaign.shopping_setting.campaign_priority,
        campaign.shopping_setting.enable_local, campaign.network_settings.target_google_search, campaign.network_settings.target_search_network,
        campaign.network_settings.target_content_network, campaign.network_settings.target_partner_search_network,
        campaign_budget.amount_micros, campaign_budget.explicitly_shared FROM campaign WHERE {cond} AND campaign.status != 'REMOVED'""")
    if not rows:
        raise SystemExit(f"Кампания «{a.campaign}» не найдена")
    r = rows[0]
    c, camp_id = r.campaign, r.campaign.id
    n = c.network_settings
    print(f"=== АУДИТ {c.name} (id {camp_id}) на {date.today()}, период метрик — {a.days} дн. ===")
    print("\n[1] Настройки")
    print(f"  статус {E.CampaignStatusEnum.CampaignStatus.Name(c.status)}; ставки {E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(c.bidding_strategy_type)}, "
          f"потолок клика {c.target_spend.cpc_bid_ceiling_micros / 1e6:g}; бюджет {r.campaign_budget.amount_micros / 1e6:g}"
          f"{' (общий)' if r.campaign_budget.explicitly_shared else ''}")
    print(f"  Merchant {c.shopping_setting.merchant_id}, приоритет {c.shopping_setting.campaign_priority}, local {c.shopping_setting.enable_local}; "
          f"сети: Google Search {n.target_google_search}, поисковые партнёры {n.target_search_network}, контент {n.target_content_network}")
    crit = collections.Counter()
    sched = []
    for x in q(f"""SELECT campaign_criterion.type, campaign_criterion.negative, campaign_criterion.ad_schedule.day_of_week,
        campaign_criterion.ad_schedule.start_hour, campaign_criterion.ad_schedule.end_hour, campaign_criterion.user_list.user_list
        FROM campaign_criterion WHERE campaign.id = {camp_id} AND campaign_criterion.status != 'REMOVED'"""):
        k = x.campaign_criterion
        t = E.CriterionTypeEnum.CriterionType.Name(k.type_)
        crit[(t, k.negative)] += 1
        if t == "AD_SCHEDULE":
            sched.append(f"{E.DayOfWeekEnum.DayOfWeek.Name(k.ad_schedule.day_of_week)[:3]} {k.ad_schedule.start_hour}-{k.ad_schedule.end_hour}")
    print("  расписание:", ", ".join(sched) or "круглосуточно")
    print("  критерии:", {f"{t}{' (минус)' if neg else ''}": v for (t, neg), v in crit.items()})

    print("\n[2] Структура")
    groups = {x.ad_group.id: (x.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(x.ad_group.status))
              for x in q(f"SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.id = {camp_id} AND ad_group.status != 'REMOVED'")}
    included_items, included_types, excluded, paused_included = {}, set(), [], []
    for x in q(f"""SELECT ad_group.id, ad_group.name, ad_group_criterion.negative, ad_group_criterion.status, ad_group_criterion.listing_group.type,
        ad_group_criterion.listing_group.case_value.product_item_id.value, ad_group_criterion.listing_group.case_value.product_type.value
        FROM ad_group_criterion WHERE campaign.id = {camp_id} AND ad_group_criterion.type = LISTING_GROUP AND ad_group_criterion.status != 'REMOVED'"""):
        k = x.ad_group_criterion
        if k.listing_group.type_ != E.ListingGroupTypeEnum.UNIT:
            continue
        item, ptype = k.listing_group.case_value.product_item_id.value, k.listing_group.case_value.product_type.value
        gname = groups.get(x.ad_group.id, ("?", "?"))
        if k.negative:
            excluded.append((gname[0], item or ptype or "всё остальное"))
            continue
        if gname[1] != "ENABLED":      # группа на паузе товары не показывает
            paused_included.append((gname[0], item or ptype or "ВСЕ товары"))
            continue
        if False:
            excluded.append((gname[0], item or ptype or "всё остальное"))
        elif item:
            included_items[item] = gname[0]
        elif ptype:
            included_types.add((gname[0], ptype))
        else:
            included_types.add((gname[0], "ВСЕ товары"))
    print("  группы объявлений:", "; ".join(f"{nm} [{st}]" for nm, st in groups.values()))
    print(f"  включено (в работающих группах): товаров по id {len(included_items)}, по типу {sorted(t for _, t in included_types) or '—'}; исключений {len(excluded)}")
    if paused_included:
        print(f"  включено, но группа на паузе (не показывается): {len(paused_included)}", sorted({t for _, t in paused_included})[:8])

    print("\n[3] Минусы")
    kw = collections.Counter()
    for x in q(f"""SELECT campaign_criterion.keyword.match_type FROM campaign_criterion WHERE campaign.id = {camp_id}
        AND campaign_criterion.negative = TRUE AND campaign_criterion.type = KEYWORD AND campaign_criterion.status != 'REMOVED'"""):
        kw[E.KeywordMatchTypeEnum.KeywordMatchType.Name(x.campaign_criterion.keyword.match_type)] += 1
    print("  минусов кампании:", sum(kw.values()), dict(kw))
    gk = collections.Counter()
    for x in q(f"""SELECT ad_group.name, ad_group_criterion.keyword.match_type FROM ad_group_criterion WHERE campaign.id = {camp_id}
        AND ad_group_criterion.negative = TRUE AND ad_group_criterion.type = KEYWORD AND ad_group_criterion.status != 'REMOVED'"""):
        gk[x.ad_group.name] += 1
    print("  минусов групп:", sum(gk.values()), dict(gk))
    for x in q(f"SELECT shared_set.id, shared_set.name, shared_set.member_count FROM campaign_shared_set WHERE campaign.id = {camp_id} AND campaign_shared_set.status = 'ENABLED'"):
        mt = collections.Counter(E.KeywordMatchTypeEnum.KeywordMatchType.Name(y.shared_criterion.keyword.match_type)
                                 for y in q(f"SELECT shared_criterion.keyword.match_type FROM shared_criterion WHERE shared_set.id = {x.shared_set.id}"))
        print(f"  общий список «{x.shared_set.name}»: {x.shared_set.member_count} {dict(mt)}")

    print("\n[4] Фид (товары в Merchant Center через Ads)")
    feed = {}
    for x in q("SELECT shopping_product.item_id, shopping_product.title, shopping_product.status, shopping_product.product_type_level1, shopping_product.price_micros FROM shopping_product"):
        p = x.shopping_product
        feed[p.item_id] = dict(title=p.title, type=p.product_type_level1 or "(без типа)", status=E.ProductStatusEnum.ProductStatus.Name(p.status), price=p.price_micros / 1e6)
    cnt = collections.Counter((v["type"], v["status"]) for v in feed.values())
    print(f"  товаров {len(feed)}:", "; ".join(f"{t} / {s}: {n_}" for (t, s), n_ in sorted(cnt.items())))
    types_in = {t for _, t in included_types}
    covered = [i for i, v in feed.items() if i in included_items or v["type"] in types_in or "ВСЕ товары" in types_in]
    print(f"  под включёнными группами {len(covered)} из {len(feed)} ({len(covered) / max(len(feed), 1):.0%})")

    since, until = date.today() - timedelta(days=a.days), date.today()
    print(f"\n[5] Динамика по неделям ({since} .. {until})")
    d = pd.DataFrame([(pd.Timestamp(x.segments.date), x.metrics.impressions, x.metrics.clicks, x.metrics.cost_micros / 1e6, x.metrics.conversions)
                      for x in q(f"SELECT segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions FROM campaign "
                                 f"WHERE campaign.id = {camp_id} AND segments.date >= '{since}' AND segments.date <= '{until}'")],
                     columns=["date", "impr", "clicks", "cost", "conv"])
    if d.empty:
        print("  показов за период нет")
    else:
        d["week"] = d["date"].dt.to_period("W-SUN").dt.start_time.dt.date
        w = d.groupby("week")[["impr", "clicks", "cost", "conv"]].sum()
        w["zl/клик"] = (w["cost"] / w["clicks"]).round(2)
        w["CTR %"] = (w["clicks"] / w["impr"] * 100).round(2)
        w["zl/конв"] = (w["cost"] / w["conv"]).replace(float("inf"), float("nan")).round(0)
        print(w.round(1).to_string())

    print("\n[6] Куда уходят деньги (товары)")
    pr = pd.DataFrame([(x.segments.product_item_id, x.segments.product_title, x.metrics.impressions, x.metrics.clicks,
                        x.metrics.cost_micros / 1e6, x.metrics.conversions)
                       for x in q(f"SELECT campaign.id, segments.product_item_id, segments.product_title, metrics.impressions, metrics.clicks, "
                                  f"metrics.cost_micros, metrics.conversions FROM shopping_performance_view WHERE campaign.id = {camp_id} "
                                  f"AND segments.date >= '{since}' AND segments.date <= '{until}'")],
                      columns=["item", "title", "impr", "clicks", "cost", "conv"])
    if pr.empty:
        print("  данных по товарам нет")
    else:
        pr = pr.groupby(["item", "title"], as_index=False).sum()
        pr["type"] = [feed.get(i, {}).get("type", "(нет в фиде)") for i in pr["item"]]
        pr["size"] = pr["title"].map(size_of)
        pr["в_группах"] = pr["item"].isin(included_items) | pr["type"].isin(types_in)
        tot = pr["cost"].sum()
        print(f"  расход {tot:.0f}, клики {int(pr.clicks.sum())}, конверсии Ads {pr.conv.sum():.1f}; на товары без конверсий {pr[pr.conv == 0].cost.sum():.0f} ({pr[pr.conv == 0].cost.sum() / max(tot, 1):.0%})")
        for key, label in (("type", "по типу товара"), ("size", "по размеру")):
            g = pr.groupby(key)[["impr", "clicks", "cost", "conv"]].sum().sort_values("cost", ascending=False)
            g["zl/клик"] = (g["cost"] / g["clicks"]).round(2)
            g["zl/конв"] = (g["cost"] / g["conv"]).replace(float("inf"), float("nan")).round(0)
            print(f"\n  {label}:")
            print(g.head(12).round(1).to_string())
        print("\n  топ-10 товаров по расходу:")
        print(pr.sort_values("cost", ascending=False).head(10)[["title", "clicks", "cost", "conv"]].round(1).to_string(index=False))
        if a.client_folder:
            out = ROOT / "Клиенты" / a.client_folder / "Статистика" / f"shopping_audit_{c.name}_{date.today()}.csv"
            pr.sort_values("cost", ascending=False).to_csv(out, index=False, encoding="utf-8-sig")
            print("\n  CSV по товарам:", out)
    try:
        st = pd.DataFrame([(x.search_term_view.search_term, x.metrics.clicks, x.metrics.cost_micros / 1e6, x.metrics.conversions)
                           for x in q(f"SELECT search_term_view.search_term, metrics.clicks, metrics.cost_micros, metrics.conversions FROM search_term_view "
                                      f"WHERE campaign.id = {camp_id} AND segments.date >= '{since}' AND segments.date <= '{until}'")],
                          columns=["term", "clicks", "cost", "conv"]).groupby("term", as_index=False).sum()
        z = st[st.conv == 0].sort_values("cost", ascending=False).head(10)
        print(f"\n  запросов {len(st)}, расход {st.cost.sum():.0f}; топ-10 по расходу без конверсий:")
        print(z.round(1).to_string(index=False) if len(z) else "  нет")
    except Exception as e:  # noqa: BLE001
        print("\n  отчёт по запросам недоступен:", str(e)[:120])


if __name__ == "__main__":
    main()
