#!/usr/bin/env python
# coding: utf-8
"""Быстрый осмотр кабинета Яндекс.Директа потенциального клиента (только чтение).

Нужен до полного аудита: понять, что запускали за последний год (включая архив),
на какие цели настроены кампании, какая цена заявки на бренде и небренде, есть ли
фид и откуда он. Результат — CSV в Клиенты/<папка>/Статистика/ и сводка в консоль.

Токен клиента — только из файла (--token-file). Файл удаляется сразу после чтения,
токен остаётся только в памяти процесса: в vault, историю команд и переменные
окружения он не попадает. В кабинет скрипт ничего не пишет (только методы get и отчёты).

Использование:
    python direct_express_audit.py --login irinanovotelmc \
        --token-file "C:\\Users\\infob\\AppData\\Local\\Temp\\novotel_direct.token" \
        --client-folder Novotel_Moscow_City
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from time import sleep
from urllib.parse import urlsplit

import pandas as pd
import requests

VAULT_ROOT = Path(__file__).resolve().parent.parent
API = "https://api.direct.yandex.com/json/v5/"
ALL_STATES = ["ON", "OFF", "SUSPENDED", "ENDED", "CONVERTED", "ARCHIVED"]
DEFAULT_BRAND_RE = r"novotel|новотел|новотэл"


def read_token(path):
    token = Path(path).read_text(encoding="utf-8").strip()
    if not token:
        sys.exit("Файл токена пустой")
    return token


def delete_token_file(path):
    """Удаляем файл токена после успешного запуска (при сбое он остаётся для повтора)."""
    p = Path(path)
    p.unlink(missing_ok=True)
    print("Файл токена удалён" if not p.exists() else "ВНИМАНИЕ: файл токена не удалился, удалить вручную")


class Direct:
    def __init__(self, login, token):
        self.login = login
        self.h = {
            "Authorization": "Bearer " + token,
            "Client-Login": login,
            "Accept-Language": "ru",
        }

    def call(self, service, method, params):
        r = requests.post(API + service, json={"method": method, "params": params},
                          headers=self.h, timeout=300)
        try:
            data = r.json()
        except ValueError:
            data = {"error": {"error_string": r.text[:300]}}
        return data

    def get_all(self, service, params, key):
        out, offset = [], 0
        while True:
            p = dict(params)
            p["Page"] = {"Limit": 10000, "Offset": offset}
            d = self.call(service, "get", p)
            if "error" in d:
                return None, d["error"]
            res = d.get("result", {})
            out += res.get(key, [])
            if res.get("LimitedBy") is None:
                return out, None
            offset = res["LimitedBy"]

    def report(self, report_type, fields, date_from, date_to, goals=None,
               attribution=("LYDC",), name="x", filters=None):
        h = dict(self.h)
        h.update({"processingMode": "auto", "returnMoneyInMicros": "false",
                  "skipReportHeader": "true", "skipReportSummary": "true"})
        crit = {"DateFrom": date_from, "DateTo": date_to}
        if filters:
            crit["Filter"] = filters
        body = {"params": {
            "SelectionCriteria": crit, "FieldNames": fields,
            "ReportName": name, "ReportType": report_type,
            "DateRangeType": "CUSTOM_DATE", "Format": "TSV",
            "IncludeVAT": "YES", "IncludeDiscount": "NO"}}
        if goals:
            body["params"]["Goals"] = goals
            body["params"]["AttributionModels"] = list(attribution)
        for _ in range(60):
            r = requests.post(API + "reports", json.dumps(body), headers=h, timeout=600)
            r.encoding = "utf-8"
            if r.status_code == 200:
                if not r.text.strip():
                    return pd.DataFrame()
                return pd.read_csv(io.StringIO(r.text), sep="\t", na_values="--")
            if r.status_code in (201, 202):
                sleep(int(r.headers.get("retryIn", 20)))
                continue
            print(f"  отчёт {report_type}: ошибка {r.status_code}: {r.text[:400]}")
            return None
        return None


def flatten_campaign(c):
    row = {"Id": c.get("Id"), "Name": c.get("Name"), "Type": c.get("Type"),
           "Status": c.get("Status"), "State": c.get("State"),
           "StartDate": c.get("StartDate"), "EndDate": c.get("EndDate"),
           "DailyBudget": (c.get("DailyBudget") or {}).get("Amount")}
    for block in ("TextCampaign", "UnifiedCampaign", "SmartCampaign", "DynamicTextCampaign",
                  "MobileAppCampaign", "CpmBannerCampaign"):
        b = c.get(block)
        if not b:
            continue
        s = b.get("BiddingStrategy") or {}
        parts = []
        for plat in ("Search", "Network"):
            blk = s.get(plat) or {}
            t = blk.get("BiddingStrategyType")
            if t:
                parts.append(f"{plat}:{t}")
        row["Strategy"] = " | ".join(parts)
        row["CounterIds"] = ",".join(str(x) for x in ((b.get("CounterIds") or {}).get("Items") or []))
        goals = []
        for g in (b.get("PriorityGoals") or {}).get("Items") or []:
            goals.append(f"{g.get('GoalId')}(v={g.get('Value')})")
        row["PriorityGoals"] = ",".join(goals)
        break
    return row


def fetch_campaigns(api):
    rich = {
        "SelectionCriteria": {"States": ALL_STATES},
        "FieldNames": ["Id", "Name", "Type", "Status", "State", "StartDate", "EndDate", "DailyBudget"],
        "TextCampaignFieldNames": ["BiddingStrategy", "CounterIds", "PriorityGoals"],
        "UnifiedCampaignFieldNames": ["BiddingStrategy", "CounterIds", "PriorityGoals"],
        "SmartCampaignFieldNames": ["BiddingStrategy", "CounterId", "PriorityGoals"],
        "DynamicTextCampaignFieldNames": ["BiddingStrategy", "CounterIds", "PriorityGoals"],
    }
    camps, err = api.get_all("campaigns", rich, "Campaigns")
    if camps is None:
        print(f"  campaigns.get (расширенный набор полей) ошибка: {err}; пробую минимальный")
        base = {"SelectionCriteria": {"States": ALL_STATES},
                "FieldNames": ["Id", "Name", "Type", "Status", "State", "StartDate", "EndDate"],
                "TextCampaignFieldNames": ["BiddingStrategy"],
                "UnifiedCampaignFieldNames": ["BiddingStrategy"],
                "SmartCampaignFieldNames": ["BiddingStrategy"],
                "DynamicTextCampaignFieldNames": ["BiddingStrategy"]}
        camps, err = api.get_all("campaigns", base, "Campaigns")
    if camps is None:
        sys.exit(f"campaigns.get не отвечает: {err}")
    return camps


def fetch_feeds(api):
    params = {"SelectionCriteria": {},
              "FieldNames": ["Id", "Name", "BusinessType", "SourceType", "Status", "UpdatedAt",
                             "NumberOfItems", "CampaignIds"],
              "UrlFeedFieldNames": ["Url", "RemoveUtmTags"],
              "FileFeedFieldNames": ["Filename"]}
    feeds, err = api.get_all("feeds", params, "Feeds")
    if feeds is None:
        print(f"  feeds.get ошибка: {err}; пробую без полей источника")
        params.pop("UrlFeedFieldNames"), params.pop("FileFeedFieldNames")
        feeds, err = api.get_all("feeds", params, "Feeds")
    if feeds is None:
        print(f"  feeds.get недоступен: {err}")
        return []
    return feeds


def feed_adgroups(api, camp_ids):
    rows = []
    for i in range(0, len(camp_ids), 10):
        chunk = camp_ids[i:i + 10]
        p = {"SelectionCriteria": {"CampaignIds": chunk},
             "FieldNames": ["Id", "CampaignId", "Type", "Status", "ServingStatus"],
             "DynamicTextFeedAdGroupFieldNames": ["FeedId"],
             "SmartAdGroupFieldNames": ["FeedId"]}
        gs, err = api.get_all("adgroups", p, "AdGroups")
        if gs is None:
            print(f"  adgroups.get ошибка: {err}")
            return rows
        for g in gs:
            fid = None
            for blk in ("DynamicTextFeedAdGroup", "SmartAdGroup"):
                if g.get(blk):
                    fid = g[blk].get("FeedId")
            rows.append({"AdGroupId": g.get("Id"), "CampaignId": g.get("CampaignId"),
                         "Type": g.get("Type"), "Status": g.get("Status"), "FeedId": fid})
    return rows


def safe_url(u):
    if not u:
        return ""
    s = urlsplit(u)
    q = " (есть параметры в адресе, не сохранены)" if s.query else ""
    return f"{s.scheme}://{s.netloc}{s.path}{q}"


def goal_cols(df):
    return [c for c in df.columns if c.startswith("Conversions_")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--brand-regex", default=DEFAULT_BRAND_RE)
    args = ap.parse_args()

    token = read_token(args.token_file)
    api = Direct(args.login, token)
    try:
        run(api, args)
    except SystemExit:
        print("Запуск не завершён: файл токена оставлен для повтора, после отладки удалить вручную")
        raise
    delete_token_file(args.token_file)


def run(api, args):
    out_dir = VAULT_ROOT / "Клиенты" / args.client_folder / "Статистика"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_dir = VAULT_ROOT / "Клиенты" / args.client_folder / "Статистика"
    out_dir.mkdir(parents=True, exist_ok=True)
    d_to = date.today() - timedelta(days=1)
    d_from = d_to - timedelta(days=30 * args.months)
    print(f"Период: {d_from} — {d_to}")

    # 1. Кампании
    print("\n[1] Кампании (все статусы, включая архив)")
    camps = fetch_campaigns(api)
    if not camps:
        raw = api.call("campaigns", "get", {"SelectionCriteria": {"States": ALL_STATES},
                                            "FieldNames": ["Id", "Name", "State"]})
        sys.exit(f"Кампаний нет в ответе API. Сырой ответ (без токена): {json.dumps(raw, ensure_ascii=False)[:800]}")
    cdf = pd.DataFrame([flatten_campaign(c) for c in camps])
    print(f"Кампаний всего: {len(cdf)}")
    print(cdf.groupby(["Type", "State"]).size().to_string())
    goal_ids = sorted({g.split("(")[0] for s in cdf.get("PriorityGoals", pd.Series(dtype=str)).dropna()
                       for g in s.split(",") if g})
    print(f"ID целей в настройках кампаний: {goal_ids or 'не удалось прочитать / не заданы'}")

    # 2. Статистика по дням и кампаниям (без целей и по целям)
    print("\n[2] Статистика по кампаниям")
    rep = api.report("CAMPAIGN_PERFORMANCE_REPORT",
                     ["Date", "CampaignId", "CampaignName", "CampaignType", "Impressions", "Clicks", "Cost"],
                     str(d_from), str(d_to), name="express_camp")
    if rep is None or rep.empty:
        sys.exit("Отчёт по кампаниям пуст или недоступен")
    rep["Month"] = rep["Date"].astype(str).str[:7]
    goals_arg = None
    if goal_ids:
        goals_arg = goal_ids[:10]
        repg = api.report("CAMPAIGN_PERFORMANCE_REPORT",
                          ["Date", "CampaignId", "Conversions"], str(d_from), str(d_to),
                          goals=goals_arg, name="express_camp_goals")
        if repg is not None and not repg.empty:
            gcols = [c for c in repg.columns if c.startswith("Conversions_")]
            rep = rep.merge(repg[["Date", "CampaignId"] + gcols], on=["Date", "CampaignId"], how="left")
    # конверсии «по всем целям» отдельным запросом, чтобы увидеть цели, которых нет в настройках
    repa = api.report("CAMPAIGN_PERFORMANCE_REPORT", ["Date", "CampaignId", "Conversions"],
                      str(d_from), str(d_to), name="express_camp_all")
    if repa is not None and not repa.empty:
        repa = repa.rename(columns={"Conversions": "Conversions_all"})
        rep = rep.merge(repa, on=["Date", "CampaignId"], how="left")
    rep.to_csv(out_dir / "express_campaigns_daily.csv", index=False, encoding="utf-8")

    life = rep[rep["Impressions"] > 0].groupby(["CampaignId", "CampaignName", "CampaignType"]).agg(
        first_day=("Date", "min"), last_day=("Date", "max"),
        impressions=("Impressions", "sum"), clicks=("Clicks", "sum"), cost=("Cost", "sum")).reset_index()
    for c in goal_cols(rep) + (["Conversions_all"] if "Conversions_all" in rep.columns else []):
        life = life.merge(rep.groupby("CampaignId")[c].sum(min_count=1).reset_index(), on="CampaignId", how="left")
    life = life.merge(cdf[["Id", "State", "Strategy", "PriorityGoals"]].rename(columns={"Id": "CampaignId"}),
                      on="CampaignId", how="left")
    life = life.sort_values("cost", ascending=False)
    life.to_csv(out_dir / "express_campaigns_lifetime.csv", index=False, encoding="utf-8")
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 40)
    print(life.to_string(index=False))

    month = rep.groupby("Month").agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"),
                                     impressions=("Impressions", "sum"))
    for c in goal_cols(rep) + (["Conversions_all"] if "Conversions_all" in rep.columns else []):
        month[c] = rep.groupby("Month")[c].sum(min_count=1)
    print("\nПо месяцам (весь аккаунт, все сети):")
    print(month.round(0).to_string())
    month.to_csv(out_dir / "express_monthly.csv", encoding="utf-8")

    # 3. Бренд / небренд по поисковым запросам
    print("\n[3] Бренд против небренда (отчёт по поисковым запросам, только поисковая сеть)")
    qfields = ["Date", "CampaignId", "CampaignName", "Query", "Impressions", "Clicks", "Cost"]
    q = api.report("SEARCH_QUERY_PERFORMANCE_REPORT", qfields, str(d_from), str(d_to), name="express_q")
    if q is not None and not q.empty:
        if goals_arg:
            qg = api.report("SEARCH_QUERY_PERFORMANCE_REPORT", ["Date", "CampaignId", "Query", "Conversions"],
                            str(d_from), str(d_to), goals=goals_arg, name="express_q_goals")
            if qg is not None and not qg.empty:
                gcols = [c for c in qg.columns if c.startswith("Conversions_")]
                q = q.merge(qg[["Date", "CampaignId", "Query"] + gcols], on=["Date", "CampaignId", "Query"], how="left")
        qa = api.report("SEARCH_QUERY_PERFORMANCE_REPORT", ["Date", "CampaignId", "Query", "Conversions"],
                        str(d_from), str(d_to), name="express_q_all")
        if qa is not None and not qa.empty:
            q = q.merge(qa.rename(columns={"Conversions": "Conversions_all"}),
                        on=["Date", "CampaignId", "Query"], how="left")
        q["Month"] = q["Date"].astype(str).str[:7]
        q["Brand"] = q["Query"].astype(str).str.lower().str.contains(args.brand_regex, regex=True)
        q["Segment"] = q["Brand"].map({True: "бренд", False: "небренд"})
        q.to_csv(out_dir / "express_queries.csv", index=False, encoding="utf-8")
        cc = goal_cols(q) + (["Conversions_all"] if "Conversions_all" in q.columns else [])
        agg = {"cost": ("Cost", "sum"), "clicks": ("Clicks", "sum"), "impressions": ("Impressions", "sum")}
        for c in cc:
            agg[c] = (c, lambda s: s.sum(min_count=1))
        seg = q.groupby("Segment").agg(**agg)
        for c in cc:
            seg["CPA_" + c] = (seg["cost"] / seg[c]).where(seg[c] > 0)
        print(f"Бренд = запрос содержит /{args.brand_regex}/. Срез: поисковые запросы, {d_from} — {d_to}")
        print(seg.round(1).to_string())
        segm = q.groupby(["Month", "Segment"]).agg(**agg)
        for c in cc:
            segm["CPA_" + c] = (segm["cost"] / segm[c]).where(segm[c] > 0)
        print("\nПо месяцам:")
        print(segm.round(1).to_string())
        segm.to_csv(out_dir / "express_brand_split_monthly.csv", encoding="utf-8")
        top = q[~q["Brand"]].groupby("Query").agg(cost=("Cost", "sum"), clicks=("Clicks", "sum"))\
            .sort_values("cost", ascending=False).head(25)
        print("\nТоп-25 небрендовых запросов по расходу:")
        print(top.round(0).to_string())
    else:
        print("Отчёт по запросам пуст или недоступен")

    # 4. Фид
    print("\n[4] Фиды")
    feeds = fetch_feeds(api)
    if not feeds:
        print("Фидов нет (или недоступны)")
    frows = []
    for f in feeds:
        url = (f.get("UrlFeed") or {}).get("Url")
        frows.append({"Id": f.get("Id"), "Name": f.get("Name"), "BusinessType": f.get("BusinessType"),
                      "SourceType": f.get("SourceType"), "Status": f.get("Status"),
                      "UpdatedAt": f.get("UpdatedAt"), "NumberOfItems": f.get("NumberOfItems"),
                      "Source": safe_url(url) or (f.get("FileFeed") or {}).get("Filename", ""),
                      "CampaignIds": ",".join(str(x) for x in ((f.get("CampaignIds") or {}).get("Items") or []))})
    if frows:
        fdf = pd.DataFrame(frows)
        fdf.to_csv(out_dir / "express_feeds.csv", index=False, encoding="utf-8")
        print(fdf.to_string(index=False))
        ids = [c["Id"] for c in camps]
        groups = feed_adgroups(api, ids)
        if groups:
            gdf = pd.DataFrame(groups)
            gdf.to_csv(out_dir / "express_adgroups.csv", index=False, encoding="utf-8")
            print("\nГруппы по типам:")
            print(gdf.groupby(["Type", "Status"]).size().to_string())
            withfeed = gdf[gdf["FeedId"].notna()]
            if len(withfeed):
                print("\nКампании с группами на фиде:")
                print(withfeed.groupby(["CampaignId", "FeedId"]).size().to_string())

    print(f"\nГотово. CSV: {out_dir}")


if __name__ == "__main__":
    main()
