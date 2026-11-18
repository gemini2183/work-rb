#!/usr/bin/env python
# coding: utf-8
"""Универсальный разрез кампании Google Ads (Search, PMax, Demand Gen, Display, Video, Shopping) — ТОЛЬКО ЧТЕНИЕ.

Зачем: одним прогоном ответить «куда и когда уходит расход и что приносит» по любой кампании. Тип кампании
(advertising_channel_type) определяется сам, для каждого разреза выбирается подходящий ресурс GAQL; если разрез
для типа не поддерживается API - печатается одна строка «не поддерживается для <тип>: <причина>». Каждый разрез в
своём try/except (падение одного не рушит остальные, ошибка API печатается дословно). Ключи не печатаются
(secrets/google-ads.yaml через gads_stats.GOOGLE_ADS_YAML, login_customer_id - менеджер). В кабинет ничего не пишет.

Разрезы (--by, через запятую; по умолчанию все, что поддерживает тип):
  day               кампания по дням + итого: расход, показы, клики, CTR, CPC, просмотры видео, конв., all_конв.; бюджет, ставки
  hour              расход по часу суток (segments.hour)
  dow               расход по дню недели (segments.day_of_week) и матрица день x час в CSV
  device            по устройствам (segments.device)
  network           по сетям (segments.ad_network_type)
  audience          аудитории/сегменты таргета: ad_group_audience_view и campaign_audience_view (не PMax)
  ad_group          группы объявлений (ad_group) или, для PMax, группы ассетов (asset_group)
  asset             ассеты/ролики: ad_group_ad_asset_view (не PMax); для PMax - asset_group_asset (только список, без метрик)
  placement         площадки: group_placement_view + detail_placement_view (Video/Demand Gen/Display),
                    performance_max_placement_view (PMax, только показы); Search - не поддерживается
  conversion_action конверсии по действиям (segments.conversion_action_name)
  change_history    change_event по кампании: кто, когда, что менял (API отдаёт не глубже 30 дней)

Использование (из папки Скрипты):
    PYTHONUTF8=1 python gads_campaign_breakdown.py --customer-id 7552781705 --campaign-name yt_cold \
        --since 2026-11-01 --until 2026-11-17 [--by hour,dow,placement] [--csv-dir ..\\Клиенты\\ProfiMet\\Статистика] [--top 30]
    (вместо --campaign-name можно --campaign-id 123,456)
Дата создания: 2026-11-18. Общее с другими скриптами: gads_stats.GOOGLE_ADS_YAML. Остальные (gads_pmax_channel_split,
gads_pmax_placements, state_digest.change_events) печатают внутри функций и привязаны к одной кампании/типу - не импортируются.
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML

_CLIENT = None
ALL_CUTS = ["day", "hour", "dow", "device", "network", "audience", "ad_group", "asset", "placement",
            "conversion_action", "change_history"]


class Unsupported(Exception):
    pass


# ---------- утилиты ----------

def en(value, kind):
    """Enum в этой версии клиента приходит числом: переводим в имя через descriptor."""
    if hasattr(value, "name"):
        return value.name
    try:
        return getattr(_CLIENT.enums, kind + "Enum").DESCRIPTOR.enum_types_by_name[kind].values_by_number[int(value)].name
    except Exception:
        return str(value)


def err_text(e):
    try:
        return " | ".join(f"{x.error_code}: {x.message}" for x in e.failure.errors)
    except Exception:
        return f"{type(e).__name__}: {e}"


def run(ga, cid, query):
    for batch in ga.search_stream(customer_id=cid, query=query):
        for r in batch.results:
            yield r


def save(csv_dir, name, header, rows):
    if not csv_dir:
        return
    p = Path(csv_dir)
    p.mkdir(parents=True, exist_ok=True)
    p = p / name
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  (сохранено: {p})")


def pct(a, b):
    return f"{a / b:.2%}" if b else "-"


def div(a, b):
    return f"{a / b:.2f}" if b else "-"


def agg_metrics(ga, cid, query, keyfn):
    """Суммирует метрики по ключу: [расход, показы, клики, конв., all_конв., просмотры видео]."""
    agg = defaultdict(lambda: [0.0, 0, 0, 0.0, 0.0, 0])
    for r in run(ga, cid, query):
        m = r.metrics
        a = agg[keyfn(r)]
        a[0] += m.cost_micros / 1e6
        a[1] += m.impressions
        a[2] += m.clicks
        a[3] += m.conversions
        a[4] += m.all_conversions
        a[5] += m.video_trueview_views
    return agg


def fmt_row(a):
    return f"{a[0]:8.2f} {a[1]:8d} {a[2]:6d} {div(a[0], a[2]):>6} {a[5]:7d} {a[3]:6.1f} {a[4]:7.1f}"


HEAD = f"{'расход':>8} {'показы':>8} {'клики':>6} {'CPC':>6} {'просм.':>7} {'конв.':>6} {'all_кн':>7}"
CSV_HEAD = ["cost", "impressions", "clicks", "conversions", "all_conversions", "video_views"]


def csv_vals(a):
    return [round(a[0], 2), a[1], a[2], round(a[3], 2), round(a[4], 2), a[5]]


def table(title_key, agg, top, csv_dir, fname, keynames):
    rows = sorted(agg.items(), key=lambda kv: -kv[1][0])
    tot = sum(a[0] for _, a in rows)
    print(f"  строк: {len(rows)}, расход {tot:.2f}" + (f"; показаны топ-{top}" if len(rows) > top else ""))
    print(f"  {HEAD}  {title_key}")
    for k, a in rows[:top]:
        print(f"  {fmt_row(a)}  {' | '.join(str(x) for x in (k if isinstance(k, tuple) else (k,)))}")
    save(csv_dir, fname, keynames + CSV_HEAD,
         [((*k,) if isinstance(k, tuple) else (k,)) + tuple(csv_vals(a)) for k, a in rows])


# ---------- кампании ----------

def get_campaigns(ga, cid, name_sub, ids):
    if ids:
        where = "campaign.id IN (" + ",".join(str(int(i)) for i in ids) + ")"
    else:
        s = name_sub.replace("\\", "\\\\").replace("'", "\\'")
        where = f"campaign.name LIKE '%{s}%'"
    q = f"""SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
                   campaign.bidding_strategy_type, campaign.resource_name, campaign_budget.amount_micros
            FROM campaign WHERE {where} AND campaign.status != 'REMOVED'"""
    out = {}
    for r in run(ga, cid, q):
        out[r.campaign.id] = {
            "name": r.campaign.name, "status": en(r.campaign.status, "CampaignStatus"),
            "type": en(r.campaign.advertising_channel_type, "AdvertisingChannelType"),
            "bid": en(r.campaign.bidding_strategy_type, "BiddingStrategyType"),
            "res": r.campaign.resource_name, "budget": r.campaign_budget.amount_micros / 1e6,
        }
    return out


# ---------- разрезы: f(ctx) где ctx = dict(ga,cid,ids,since,until,top,csv,ctype,tag,camps) ----------

def flt(c, seg=True):
    s = f"campaign.id IN ({','.join(str(i) for i in c['ids'])})"
    if seg:
        s += f" AND segments.date BETWEEN '{c['since']}' AND '{c['until']}'"
    return s


def cut_day(c):
    for i in c["ids"]:
        k = c["camps"][i]
        print(f"  {i} {k['name']} | {k['status']} | {k['type']} | ставки: {k['bid']} | дневной бюджет: {k['budget']:.2f}")
    q = f"SELECT campaign.name, segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks, " \
        f"metrics.video_trueview_views, metrics.conversions, metrics.all_conversions FROM campaign WHERE {flt(c)}"
    agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (r.campaign.name, r.segments.date))
    tot = defaultdict(lambda: [0.0, 0, 0, 0.0, 0.0, 0])
    print(f"  {'дата':10} {HEAD} {'CTR':>7} {'view rate':>9}")
    rows = []
    for (n, d), a in sorted(agg.items()):
        for j in range(6):
            tot[n][j] += a[j]
        print(f"  {d:10} {fmt_row(a)} {pct(a[2], a[1]):>7} {pct(a[5], a[1]):>9}   {n}")
        rows.append((n, d, *csv_vals(a)))
    for n, a in tot.items():
        print(f"  ИТОГО {n}: расход {a[0]:.2f}, показы {a[1]}, клики {a[2]}, CTR {pct(a[2], a[1])}, CPC {div(a[0], a[2])}, "
              f"просмотры {a[5]}, view rate {pct(a[5], a[1])}, конв. {a[3]:.1f}, all_конв. {a[4]:.1f}")
        rows.append((n, "ИТОГО", *csv_vals(a)))
    save(c["csv"], f"breakdown_{c['tag']}_day_{c['since']}_{c['until']}.csv", ["campaign", "date"] + CSV_HEAD, rows)
    # потеряно по бюджету/рейтингу (Search/Shopping; для других типов API может не отдавать)
    try:
        q2 = f"SELECT campaign.name, metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share " \
             f"FROM campaign WHERE {flt(c)}"
        vals = defaultdict(list)
        for r in run(c["ga"], c["cid"], q2):
            vals[r.campaign.name].append((r.metrics.search_budget_lost_impression_share,
                                          r.metrics.search_rank_lost_impression_share))
        for n, v in vals.items():
            b = [x[0] for x in v if x[0]]
            rk = [x[1] for x in v if x[1]]
            print(f"  потеряно по бюджету / рейтингу ({n}): {(sum(b) / len(b) if b else 0):.1%} ({len(b)} дн. с данными) / "
                  f"{(sum(rk) / len(rk) if rk else 0):.1%} ({len(rk)} дн.); 0 дн. = API не отдаёт для типа {c['ctype']}")
    except Exception as e:
        print(f"  потеряно по бюджету: запрос не прошёл: {err_text(e)}")


def simple_seg(c, seg, kind, label, fname):
    q = f"SELECT {seg}, metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.video_trueview_views, " \
        f"metrics.conversions, metrics.all_conversions FROM campaign WHERE {flt(c)}"
    path = seg.split(".")[1]
    agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (en(getattr(r.segments, path), kind) if kind else getattr(r.segments, path),))
    table(label, agg, 100, c["csv"], f"breakdown_{c['tag']}_{fname}_{c['since']}_{c['until']}.csv", [label])


def cut_hour(c):
    simple_seg(c, "segments.hour", None, "час", "hour")


def cut_dow(c):
    simple_seg(c, "segments.day_of_week", "DayOfWeek", "день недели", "dow")
    q = f"SELECT segments.day_of_week, segments.hour, metrics.cost_micros FROM campaign WHERE {flt(c)}"
    hd = defaultdict(float)
    for r in run(c["ga"], c["cid"], q):
        hd[(en(r.segments.day_of_week, "DayOfWeek"), r.segments.hour)] += r.metrics.cost_micros / 1e6
    save(c["csv"], f"breakdown_{c['tag']}_dow_x_hour_{c['since']}_{c['until']}.csv", ["day_of_week", "hour", "cost"],
         [(d, h, round(v, 2)) for (d, h), v in sorted(hd.items())])


def cut_device(c):
    simple_seg(c, "segments.device", "Device", "устройство", "device")


def cut_network(c):
    simple_seg(c, "segments.ad_network_type", "AdNetworkType", "сеть", "network")


def cut_audience(c):
    if c["ctype"] == "PERFORMANCE_MAX":
        raise Unsupported("в PMax сигналы аудиторий (asset_group_signal) не имеют метрик, показы/расход по аудиториям API не отдаёт")
    any_rows = False
    for view in ("ad_group_audience_view", "campaign_audience_view"):
        grp = "ad_group.name, " if view == "ad_group_audience_view" else ""
        q = f"""SELECT {grp}{view}.resource_name, {('ad_group_criterion' if view == 'ad_group_audience_view' else 'campaign_criterion')}.type,
                       {('ad_group_criterion' if view == 'ad_group_audience_view' else 'campaign_criterion')}.display_name,
                       metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.video_trueview_views,
                       metrics.conversions, metrics.all_conversions
                FROM {view} WHERE {flt(c)}"""
        crit = "ad_group_criterion" if view == "ad_group_audience_view" else "campaign_criterion"
        try:
            agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (
                r.ad_group.name if view == "ad_group_audience_view" else "(кампания)",
                en(getattr(r, crit).type_, "CriterionType"), getattr(r, crit).display_name or
                getattr(r, view).resource_name.split("~")[-1]))
        except Exception as e:
            print(f"  {view}: ошибка API: {err_text(e)}")
            continue
        print(f"  {view}:")
        if agg:
            any_rows = True
            table("группа | тип | сегмент", agg, c["top"], c["csv"],
                  f"breakdown_{c['tag']}_{view}_{c['since']}_{c['until']}.csv", ["ad_group", "type", "segment"])
        else:
            print("  строк нет")
    if not any_rows:
        print("  по обоим представлениям данных нет (таргет по аудиториям может быть выключен/«наблюдение» без показов)")


def cut_ad_group(c):
    if c["ctype"] == "PERFORMANCE_MAX":
        q = f"SELECT asset_group.name, asset_group.status, metrics.cost_micros, metrics.impressions, metrics.clicks, " \
            f"metrics.conversions, metrics.all_conversions FROM asset_group WHERE {flt(c)}"
        agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (r.asset_group.name, en(r.asset_group.status, "AssetGroupStatus")))
        table("группа ассетов | статус", agg, c["top"], c["csv"],
              f"breakdown_{c['tag']}_asset_group_{c['since']}_{c['until']}.csv", ["asset_group", "status"])
        return
    q = f"SELECT campaign.name, ad_group.name, ad_group.status, metrics.cost_micros, metrics.impressions, metrics.clicks, " \
        f"metrics.video_trueview_views, metrics.conversions, metrics.all_conversions FROM ad_group WHERE {flt(c)}"
    agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (r.campaign.name, r.ad_group.name, en(r.ad_group.status, "AdGroupStatus")))
    table("кампания | группа | статус", agg, c["top"], c["csv"],
          f"breakdown_{c['tag']}_ad_group_{c['since']}_{c['until']}.csv", ["campaign", "ad_group", "status"])


def cut_asset(c):
    if c["ctype"] == "PERFORMANCE_MAX":
        q = f"""SELECT asset_group.name, asset_group_asset.field_type, asset_group_asset.status, asset_group_asset.asset
                FROM asset_group_asset WHERE campaign.id IN ({','.join(str(i) for i in c['ids'])})
                  AND asset_group_asset.status = 'ENABLED'"""
        rows = []
        for r in run(c["ga"], c["cid"], q):
            rows.append((r.asset_group.name, en(r.asset_group_asset.field_type, "AssetFieldType"),
                         en(r.asset_group_asset.status, "AssetLinkStatus"), r.asset_group_asset.asset))
        print("  PMax: метрик по ассетам API не отдаёт (performance_label в v23 недоступен); список активных ассетов:")
        print(f"  строк: {len(rows)}")
        for x in rows[:c["top"]]:
            print("  " + " | ".join(str(v) for v in x))
        save(c["csv"], f"breakdown_{c['tag']}_asset_labels_{c['since']}_{c['until']}.csv",
             ["asset_group", "field", "status", "asset"], rows)
        return
    q = f"""SELECT ad_group.name, ad_group_ad_asset_view.field_type, asset.id, asset.name, asset.type,
                   asset.youtube_video_asset.youtube_video_id, asset.youtube_video_asset.youtube_video_title,
                   metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.video_trueview_views,
                   metrics.conversions, metrics.all_conversions
            FROM ad_group_ad_asset_view WHERE {flt(c)}"""
    agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (
        r.asset.id, en(r.asset.type_, "AssetType"), en(r.ad_group_ad_asset_view.field_type, "AssetFieldType"),
        r.asset.youtube_video_asset.youtube_video_id, r.asset.youtube_video_asset.youtube_video_title or r.asset.name))
    table("asset.id | тип | поле | youtube id | название", agg, c["top"], c["csv"],
          f"breakdown_{c['tag']}_assets_{c['since']}_{c['until']}.csv",
          ["asset_id", "asset_type", "field_type", "youtube_video_id", "title"])


def cut_placement(c):
    t = c["ctype"]
    if t in ("SEARCH", "SHOPPING"):
        raise Unsupported("площадочных представлений для Search/Shopping нет (есть search_term_view, это другой разрез)")
    if t == "PERFORMANCE_MAX":
        q = f"""SELECT campaign.id, performance_max_placement_view.placement, performance_max_placement_view.display_name,
                       performance_max_placement_view.placement_type, segments.date, metrics.impressions
                FROM performance_max_placement_view WHERE {flt(c)}"""
        agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (
            en(r.performance_max_placement_view.placement_type, "PlacementType"),
            r.performance_max_placement_view.placement, r.performance_max_placement_view.display_name))
        print("  PMax: только показы (расход и клики API не отдаёт)")
        rows = sorted(agg.items(), key=lambda kv: -kv[1][1])
        print(f"  площадок: {len(rows)}, показов {sum(a[1] for _, a in rows)}")
        for k, a in rows[:c["top"]]:
            print(f"  {a[1]:8d}  {' | '.join(k)}")
        save(c["csv"], f"breakdown_{c['tag']}_pmax_placements_{c['since']}_{c['until']}.csv",
             ["type", "placement", "name", "impressions"], [(*k, a[1]) for k, a in rows])
        return
    got = False
    for view in ("group_placement_view", "detail_placement_view"):
        q = f"""SELECT {view}.placement, {view}.display_name, {view}.placement_type, metrics.cost_micros, metrics.impressions,
                       metrics.clicks, metrics.video_trueview_views, metrics.conversions, metrics.all_conversions
                FROM {view} WHERE {flt(c)}"""
        try:
            agg = agg_metrics(c["ga"], c["cid"], q, lambda r: (
                en(getattr(r, view).placement_type, "PlacementType"), getattr(r, view).placement, getattr(r, view).display_name))
        except Exception as e:
            print(f"  {view}: ошибка API: {err_text(e)}")
            continue
        print(f"  {view} (суммарно расход {sum(a[0] for a in agg.values()):.2f}, клики {sum(a[2] for a in agg.values())}, "
              f"показы {sum(a[1] for a in agg.values())}; расход < расхода кампании = API отдаёт не весь инвентарь):")
        if agg:
            got = True
            table("тип | площадка | название", agg, c["top"], c["csv"],
                  f"breakdown_{c['tag']}_{view}_{c['since']}_{c['until']}.csv", ["type", "placement", "name"])
        else:
            print("  строк нет")
    if not got:
        print("  ни одно представление не вернуло строк")


def cut_conversion_action(c):
    q = f"""SELECT segments.conversion_action_name, segments.conversion_action_category, metrics.conversions,
                   metrics.all_conversions, metrics.view_through_conversions
            FROM campaign WHERE {flt(c)}"""
    agg = defaultdict(lambda: [0.0, 0.0, 0])
    for r in run(c["ga"], c["cid"], q):
        m = r.metrics
        a = agg[(r.segments.conversion_action_name, en(r.segments.conversion_action_category, "ConversionActionCategory"))]
        a[0] += m.conversions
        a[1] += m.all_conversions
        a[2] += m.view_through_conversions
    rows = [(k, a) for k, a in agg.items() if a[0] or a[1] or a[2]]
    if not rows:
        print("  конверсий нет ни по одному действию (conversions, all_conversions, view-through = 0)")
        return
    print(f"  {'конв.':>7} {'all_конв.':>9} {'view-thr.':>9}  действие | категория")
    for (n, cat), a in sorted(rows, key=lambda kv: -kv[1][1]):
        print(f"  {a[0]:7.1f} {a[1]:9.1f} {a[2]:9d}  {n} | {cat}")
    save(c["csv"], f"breakdown_{c['tag']}_conversion_action_{c['since']}_{c['until']}.csv",
         ["action", "category", "conversions", "all_conversions", "view_through"],
         [(n, cat, round(a[0], 2), round(a[1], 2), a[2]) for (n, cat), a in rows])


def cut_change_history(c):
    lo = max(datetime.strptime(c["since"], "%Y-%m-%d").date(), date.today() - timedelta(days=29))
    if str(lo) != c["since"]:
        print(f"  change_event отдаёт не глубже 30 дней: начало сдвинуто {c['since']} -> {lo}")
    hi = datetime.strptime(c["until"], "%Y-%m-%d").date() + timedelta(days=1)
    res = ",".join(f"'{c['camps'][i]['res']}'" for i in c["ids"])
    q = f"""SELECT change_event.change_date_time, change_event.user_email, change_event.client_type,
                   change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields,
                   change_event.change_resource_name, change_event.old_resource, change_event.new_resource
            FROM change_event
            WHERE change_event.change_date_time >= '{lo} 00:00:00' AND change_event.change_date_time <= '{hi} 00:00:00'
              AND change_event.campaign IN ({res})
            ORDER BY change_event.change_date_time DESC LIMIT 1000"""
    rows = []
    for r in run(c["ga"], c["cid"], q):
        e = r.change_event
        rt = en(e.change_resource_type, "ChangeEventResourceType")
        paths = list(e.changed_fields.paths)
        extra = ""
        if rt == "CAMPAIGN" and "status" in paths:
            extra = f"статус {en(e.old_resource.campaign.status, 'CampaignStatus')} -> {en(e.new_resource.campaign.status, 'CampaignStatus')}"
        if rt == "CAMPAIGN_BUDGET" and "amount_micros" in paths:
            extra = f"бюджет {e.old_resource.campaign_budget.amount_micros / 1e6:.2f} -> {e.new_resource.campaign_budget.amount_micros / 1e6:.2f}"
        rows.append((e.change_date_time[:19], e.user_email, en(e.client_type, "ChangeClientType"), rt,
                     en(e.resource_change_operation, "ResourceChangeOperation"), extra, ", ".join(paths)))
    print(f"  событий: {len(rows)}")
    for t, u, ct, rt, op, extra, ff in rows[:200]:
        print(f"  {t} | {u} | {ct} | {rt} {op} | {extra} | поля: {ff[:100]}")
    save(c["csv"], f"breakdown_{c['tag']}_changes_{c['since']}_{c['until']}.csv",
         ["time", "user", "client", "resource_type", "operation", "detail", "changed_fields"], rows)


CUTS = {"day": ("Кампания по дням и итого", cut_day), "hour": ("По часам суток", cut_hour),
        "dow": ("По дням недели", cut_dow), "device": ("По устройствам", cut_device), "network": ("По сетям", cut_network),
        "audience": ("Аудитории / сегменты таргета", cut_audience), "ad_group": ("Группы объявлений / ассетов", cut_ad_group),
        "asset": ("Ассеты / ролики", cut_asset), "placement": ("Площадки", cut_placement),
        "conversion_action": ("Конверсии по действиям", cut_conversion_action),
        "change_history": ("История изменений", cut_change_history)}


def main():
    global _CLIENT
    ap = argparse.ArgumentParser(description="Универсальный разрез кампании Google Ads (только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--campaign-name", help="подстрока имени кампании")
    ap.add_argument("--campaign-id", help="id кампании (или несколько через запятую)")
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--by", default=",".join(ALL_CUTS), help="разрезы через запятую: " + ", ".join(ALL_CUTS))
    ap.add_argument("--csv-dir", default=None)
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()
    if not a.campaign_name and not a.campaign_id:
        ap.error("нужен --campaign-name или --campaign-id")
    by = [x.strip() for x in a.by.split(",") if x.strip()]
    bad = [x for x in by if x not in CUTS]
    if bad:
        ap.error(f"неизвестные разрезы: {bad}; допустимо: {ALL_CUTS}")
    cid = a.customer_id.replace("-", "")
    _CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = _CLIENT.get_service("GoogleAdsService")
    try:
        camps = get_campaigns(ga, cid, a.campaign_name, a.campaign_id.split(",") if a.campaign_id else None)
    except Exception as e:
        print(f"Список кампаний не получен: {err_text(e)}")
        sys.exit(1)
    if not camps:
        print("Кампаний не найдено")
        sys.exit(1)
    by_type = defaultdict(list)
    for i, k in camps.items():
        by_type[k["type"]].append(i)
    print(f"=== разрез: аккаунт {cid}, {a.since} - {a.until}; кампаний {len(camps)}, типы: "
          f"{', '.join(f'{t} x{len(v)}' for t, v in by_type.items())} ===")
    status = []
    for ctype, ids in by_type.items():
        tag = (a.campaign_name or "ids").replace(" ", "_")[:30] + ("" if len(by_type) == 1 else "_" + ctype)
        ctx = dict(ga=ga, cid=cid, ids=ids, since=a.since, until=a.until, top=a.top, csv=a.csv_dir,
                   ctype=ctype, tag=tag, camps=camps)
        for key in by:
            title, fn = CUTS[key]
            print(f"\n[{key}] {title} ({ctype}):")
            try:
                fn(ctx)
                status.append((key, ctype, "ok"))
            except Unsupported as e:
                print(f"  не поддерживается для {ctype}: {e}")
                status.append((key, ctype, f"не поддерживается: {e}"))
            except Exception as e:
                msg = err_text(e)
                print(f"  ОШИБКА API (разрез пропущен): {msg}")
                status.append((key, ctype, "ошибка: " + msg[:200]))
    print("\n=== Итог по разрезам ===")
    for k, t, s in status:
        print(f"  {k} ({t}): {s}")


if __name__ == "__main__":
    main()
