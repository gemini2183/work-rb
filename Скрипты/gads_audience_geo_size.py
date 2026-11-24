#!/usr/bin/env python
# coding: utf-8
"""Размер аудиторий (списки пользователей) в границах гео: оценка по Reach Planner API (ТОЛЬКО ЧТЕНИЕ), любой клиент.

Зачем: перед Demand Gen / Display понять, сколько людей из списка попадёт в выбранные регионы (размер списка в кабинете -
по всей стране, без гео). Скрипт:
  1. читает размеры списков целиком (user_list.size_for_display / size_for_search; Google округляет до 2 значащих цифр);
  2. проверяет, что регионы и списки «plannable» для ReachPlanService (ListPlannableLocations, ListPlannableUserLists);
  3. для каждого списка просит у ReachPlanService.GenerateReachForecast прогноз по продукту (по умолч. DEMAND_GEN) с
     targeting = регионы (plannable_location_ids) + audience_targeting.user_lists и берёт
     on_target_audience_metrics.youtube_audience_size / census_audience_size - «референсный размер аудитории под таргетинг».
     Для сравнения тот же запрос без списка (только гео) даёт размер всей аудитории региона.
ВАЖНО (ограничения метода, не скрывать в отчёте): youtube_audience_size - размер именно для YouTube; по документации типа только это
поле учитывает audience_targeting. Это оценка охвата планировщика, а не число людей в сети Display/Discover; сравнивать списки
между собой можно, абсолютное число для Discover/Gmail/Display - ориентир. Если метод отказывает (регион/список не plannable,
продукт недоступен, нет доступа), печатается «Пробел» с дословной причиной, число не придумывается.
Не используется: AudienceInsightsService (для Польши на 2026-11-24 отказывает «Location [2616] is not supported for insights»).

Режим: только чтение, записи и --execute нет. Прогнозы не создают объектов в кабинете. Вызовы пишутся в журнал gads_quota_ledger.
Ключи берутся из gads_stats.GOOGLE_ADS_YAML, в вывод не печатаются.

Использование (из папки Скрипты):
    python gads_audience_geo_size.py --customer-id <ID> --user-list-id 8699804100 8575354546 --geo-id 20847 20852 20853 20859
    [--per-geo] [--product DEMAND_GEN] [--budget 1000] [--conversion-rate 0.02] [--client-folder <Имя>]
    --per-geo: дополнительно размер по каждому региону отдельно; --client-folder: CSV в Клиенты/<Имя>/Статистика/
Дата создания: 2026-11-24.
"""
import argparse
import sys
from datetime import date

from google.ads.googleads.client import GoogleAdsClient

from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import record_mutate, wrap_ga

SCRIPT = "gads_audience_geo_size"


def read_lists(client, cid, ids):
    ga = wrap_ga(client.get_service("GoogleAdsService"), SCRIPT)
    out = {}
    q = ("SELECT user_list.id, user_list.name, user_list.type, user_list.size_for_display, user_list.size_for_search, "
         "user_list.membership_status FROM user_list WHERE user_list.id IN (" + ",".join(str(i) for i in ids) + ")")
    for r in ga.search(customer_id=cid, query=q):
        u = r.user_list
        out[u.id] = {"name": u.name, "type": client.enums.UserListTypeEnum.UserListType.Name(u.type_),
                     "display": u.size_for_display, "search": u.size_for_search,
                     "status": client.enums.UserListMembershipStatusEnum.UserListMembershipStatus.Name(u.membership_status)}
    cur = next(iter(ga.search(customer_id=cid, query="SELECT customer.currency_code FROM customer")), None)
    return out, (cur.customer.currency_code if cur else "EUR")


def forecast_size(client, cid, currency, geo_ids, list_id, product, budget, conv_rate, days):
    """-> (youtube_audience_size, census_audience_size). Бросает исключение API при отказе."""
    svc = client.get_service("ReachPlanService")
    req = client.get_type("GenerateReachForecastRequest")
    req.customer_id = cid
    req.currency_code = currency
    req.campaign_duration.duration_in_days = days
    req.targeting.plannable_location_ids.extend([str(g) for g in geo_ids])
    if list_id:
        ul = client.get_type("UserListInfo")
        ul.user_list = f"customers/{cid}/userLists/{list_id}"
        req.targeting.audience_targeting.user_lists.append(ul)
    pp = client.get_type("PlannedProduct")
    pp.plannable_product_code = product
    pp.budget_micros = int(budget * 1_000_000)
    if product == "DEMAND_GEN":
        pp.conversion_rate = conv_rate
    req.planned_products.append(pp)
    record_mutate(SCRIPT, 1)
    resp = svc.generate_reach_forecast(request=req)
    m = resp.on_target_audience_metrics
    return m.youtube_audience_size, m.census_audience_size


def err_text(e):
    """Короткий дословный текст ошибки Google Ads (без обёртки grpc)."""
    fail = getattr(e, "failure", None)
    if fail is not None and fail.errors:
        return "; ".join(x.message for x in fail.errors)[:400]
    return str(e).replace(chr(10), " ")[:400]


def fmt(n):
    return f"{int(n):,}".replace(",", " ") if n else "0"


def main():
    ap = argparse.ArgumentParser(description="Размер списков аудитории целиком и в гео (Reach Planner API, только чтение)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--user-list-id", nargs="+", required=True, type=int, help="id списков пользователей (несколько)")
    ap.add_argument("--geo-id", nargs="+", required=True, help="id регионов (geoTargetConstants), для которых нужна оценка")
    ap.add_argument("--per-geo", action="store_true", help="ещё и по каждому региону отдельно")
    ap.add_argument("--product", default="DEMAND_GEN", help="код продукта планировщика (по умолч. DEMAND_GEN)")
    ap.add_argument("--budget", type=float, default=1000.0, help="бюджет прогноза в валюте аккаунта (на размер аудитории почти не влияет)")
    ap.add_argument("--conversion-rate", type=float, default=0.02, help="нужен продукту DEMAND_GEN (0..1)")
    ap.add_argument("--days", type=int, default=30, help="длительность прогноза, дней")
    ap.add_argument("--client-folder", help="если задан - CSV в Клиенты/<Имя>/Статистика/")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    lists, currency = read_lists(client, cid, args.user_list_id)
    geos = [str(g) for g in args.geo_id]
    print(f"Аккаунт {cid} ({currency}); регионы: {geos}; продукт {args.product}; прогноз {args.days} дн., бюджет {args.budget:g}")
    print("Размеры Google округляет до 2 значащих цифр. «Список целиком» - по всей стране; «в гео» - оценка Reach Planner (YouTube/census).")

    svc = client.get_service("ReachPlanService")
    try:  # регионы plannable?
        record_mutate(SCRIPT, 1)
        locs = {l.id: (l.name, l.location_type, l.parent_country_id)
                for l in svc.list_plannable_locations(request={}).plannable_locations}
        for g in geos:
            if g in locs:
                print(f"   регион {g}: {locs[g][0]} ({locs[g][1]}), страна {locs[g][2]}")
            else:
                print(f"   регион {g}: НЕ plannable в ReachPlanService - оценка по нему невозможна (Пробел)")
        geos_ok = [g for g in geos if g in locs]
    except Exception as e:  # noqa: BLE001
        print(f"   Пробел: ListPlannableLocations отказал (дословно): {err_text(e)}")
        geos_ok = geos
        if "Developer Token not enabled" in err_text(e) or "not authorized" in err_text(e):
            print("\nВывод: оценка по гео через Reach Planner НЕДОСТУПНА для этого developer token (ReachPlanService не включён). "
                  "Размеры списков целиком (без гео):")
            for lid in args.user_list_id:
                i = lists.get(lid)
                if i:
                    print(f"   {lid} | {i['name']} | {i['type']} | Display {fmt(i['display'])} / Search {fmt(i['search'])}")
            print("Как получить оценку в гео: интерфейс Google Ads (Audience manager -> сегмент, размер с гео при создании кампании/группы) "
                  "или запросить доступ к Reach Planning для токена (заявка в Google Ads API Center).")
            return
    plannable = {}
    try:
        record_mutate(SCRIPT, 1)
        for p in svc.list_plannable_user_lists(customer_id=cid).plannable_user_lists:
            plannable[int(p.user_list_info.user_list.split("/")[-1])] = client.enums.ReachPlanPlannableUserListStatusEnum.ReachPlanPlannableUserListStatus.Name(p.plannable_status)
    except Exception as e:  # noqa: BLE001
        print(f"   Пробел: ListPlannableUserLists отказал (дословно): {err_text(e)}")

    rows = []
    if geos_ok:
        try:
            yt0, ce0 = forecast_size(client, cid, currency, geos_ok, None, args.product, args.budget, args.conversion_rate, args.days)
            print(f"\nВсе люди в регионах (без списка): YouTube-аудитория ~{fmt(yt0)}, census ~{fmt(ce0)}")
        except Exception as e:  # noqa: BLE001
            print(f"\nПробел: прогноз по гео без списка отказал (дословно): {err_text(e)}")
            yt0 = ce0 = None
    for lid in args.user_list_id:
        info = lists.get(lid)
        if not info:
            print(f"\nсписок {lid}: в аккаунте не найден")
            continue
        print(f"\nсписок {lid} | {info['name']} | {info['type']} | {info['status']} | целиком Display {fmt(info['display'])} / Search {fmt(info['search'])} | "
              f"plannable: {plannable.get(lid, 'нет данных')}")
        row = {"list_id": lid, "name": info["name"], "display_total": info["display"], "search_total": info["search"],
               "plannable": plannable.get(lid, ""), "geo": ",".join(geos_ok), "yt_audience_geo": "", "census_geo": "", "note": ""}
        for label, gset in [("все регионы", geos_ok)] + ([(f"регион {g}", [g]) for g in geos_ok] if args.per_geo else []):
            if not gset:
                continue
            try:
                yt, ce = forecast_size(client, cid, currency, gset, lid, args.product, args.budget, args.conversion_rate, args.days)
            except Exception as e:  # noqa: BLE001
                msg = str(e).replace("\n", " ")[:400]
                print(f"   {label}: Пробел - API отказал (дословно): {msg}")
                row["note"] = "нет: " + msg[:150]
                break
            print(f"   {label}: YouTube-аудитория в гео ~{fmt(yt)}, census ~{fmt(ce)}")
            if label == "все регионы":
                row["yt_audience_geo"], row["census_geo"] = yt, ce
        rows.append(row)
    if args.client_folder and rows:
        import pandas as pd
        from _config import client_stats_dir
        out = client_stats_dir(args.client_folder) / f"gads_audience_geo_size_{date.today()}.csv"
        pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
        print(f"\nCSV: {out}")


if __name__ == "__main__":
    sys.exit(main())
