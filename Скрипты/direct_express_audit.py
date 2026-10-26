#!/usr/bin/env python
# coding: utf-8
"""Быстрый осмотр кабинета Яндекс.Директа потенциального клиента (только чтение).

Нужен до полного аудита: понять, что запускали за последний год (включая архив),
на какие цели настроены кампании, какая цена заявки на бренде и небренде, есть ли
фид и откуда он. Результат — CSV в Клиенты/<папка>/Статистика/ и сводка в консоль.

Токен клиента — только из файла (--token-file), лежит вне vault (Temp): в git, историю
команд и переменные окружения он не попадает. Файл остаётся на время аудита и удаляется
по окончании (--delete-token или вручную). В кабинет скрипт ничего не пишет (только get и отчёты).

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
                sleep(11)  # лимит метода reports: не чаще 1 раза в 10 секунд
                if not r.text.strip():
                    return pd.DataFrame()
                return pd.read_csv(io.StringIO(r.text), sep="\t", na_values="--")
            if r.status_code in (201, 202):
                sleep(int(r.headers.get("retryIn", 20)))
                continue
            if r.status_code == 400 and '"error_code":"56"' in r.text:
                sleep(11)
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


def structure(api, camps, out_dir):
    """Группы, объявления и ключи по кампаниям, которые работали последние ~4 месяца: что внутри «Сем.фид» и «Ключи»."""
    cutoff = (date.today() - timedelta(days=120)).isoformat()
    sel = [c for c in camps if c.get("State") in ("ON", "SUSPENDED", "OFF")
           or (c.get("EndDate") or "9999") >= cutoff or (c.get("StartDate") or "") >= cutoff]
    ids = [c["Id"] for c in sel]
    name = {c["Id"]: c["Name"] for c in camps}
    kw_rows, ad_rows, gr_rows = [], [], []
    for i in range(0, len(ids), 10):
        chunk = ids[i:i + 10]
        gs, e = api.get_all("adgroups", {"SelectionCriteria": {"CampaignIds": chunk},
                                         "FieldNames": ["Id", "Name", "CampaignId", "Type", "Status"]}, "AdGroups")
        gr_rows += gs or []
        ks, e2 = api.get_all("keywords", {"SelectionCriteria": {"CampaignIds": chunk},
                                          "FieldNames": ["Id", "Keyword", "CampaignId", "AdGroupId", "State", "Status"]}, "Keywords")
        if ks is None:
            print(f"  keywords.get ошибка: {e2}")
        kw_rows += ks or []
        ads, e3 = api.get_all("ads", {"SelectionCriteria": {"CampaignIds": chunk},
                                      "FieldNames": ["Id", "AdGroupId", "CampaignId", "Type", "Status", "State"],
                                      "TextAdFieldNames": ["Title", "Title2", "Text", "Href"]}, "Ads")
        if ads is None:
            print(f"  ads.get ошибка: {e3}")
        ad_rows += ads or []
    kdf, adf, gdf = pd.DataFrame(kw_rows), pd.DataFrame(ad_rows), pd.DataFrame(gr_rows)
    if not kdf.empty:
        kdf.to_csv(out_dir / "express_keywords.csv", index=False, encoding="utf-8")
    if not adf.empty:
        adf.to_csv(out_dir / "express_ads.csv", index=False, encoding="utf-8")
    print(f"Кампаний в обзоре структуры: {len(ids)}")
    for cid in ids:
        ng = int((gdf["CampaignId"] == cid).sum()) if not gdf.empty else 0
        nk = int((kdf["CampaignId"] == cid).sum()) if not kdf.empty else 0
        na = int((adf["CampaignId"] == cid).sum()) if not adf.empty else 0
        print(f"  {cid} | групп {ng} | ключей {nk} | объявлений {na} | {name[cid][:90]}")
        if not kdf.empty and nk:
            print("     ключи (первые 8): " + "; ".join(kdf[kdf["CampaignId"] == cid]["Keyword"].head(8).astype(str)))
        if not adf.empty and na:
            ex = adf[adf["CampaignId"] == cid].head(2)
            for _, r in ex.iterrows():
                t = r.get("TextAd") if isinstance(r.get("TextAd"), dict) else {}
                print(f"     объявление: {t.get('Title')} | {t.get('Title2')} | {t.get('Text')} | {safe_url(t.get('Href'))}")


def fetch_feeds(api, ids=None):
    params = {"SelectionCriteria": {"Ids": ids or []},
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
    ap.add_argument("--delete-token", action="store_true",
                    help="удалить файл токена после запуска (по умолчанию остаётся до конца аудита)")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--brand-regex", default=DEFAULT_BRAND_RE)
    args = ap.parse_args()

    token = read_token(args.token_file)
    api = Direct(args.login, token)
    run(api, args)
    if args.delete_token:
        delete_token_file(args.token_file)
    else:
        print(f"Файл токена оставлен для следующих запусков: {args.token_file}. Удалить по окончании аудита (--delete-token).")


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
            repg = repg.groupby(["Date", "CampaignId"], as_index=False)[gcols].sum(min_count=1)
            rep = rep.merge(repg, on=["Date", "CampaignId"], how="left")
    # конверсии «по всем целям» отдельным запросом, чтобы увидеть цели, которых нет в настройках
    repa = api.report("CAMPAIGN_PERFORMANCE_REPORT", ["Date", "CampaignId", "Conversions"],
                      str(d_from), str(d_to), name="express_camp_all")
    if repa is not None and not repa.empty:
        repa = repa.groupby(["Date", "CampaignId"], as_index=False)[["Conversions"]].sum(min_count=1)
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
        keys = ["Date", "CampaignId", "Query"]
        q.to_csv(out_dir / "express_raw_q.csv", index=False, encoding="utf-8")
        print(f"  строк в отчёте по запросам: {len(q)}, повторов ключа (Date, CampaignId, Query): {q.duplicated(keys).sum()}")
        # строки с одним ключом — части одного целого, складываем перед слиянием, иначе слияние размножает строки
        q = q.groupby(keys + ["CampaignName"], as_index=False)[["Impressions", "Clicks", "Cost"]].sum()
        if goals_arg:
            qg = api.report("SEARCH_QUERY_PERFORMANCE_REPORT", ["Date", "CampaignId", "Query", "Conversions"],
                            str(d_from), str(d_to), goals=goals_arg, name="express_q_goals")
            if qg is not None and not qg.empty:
                qg.to_csv(out_dir / "express_raw_q_goals.csv", index=False, encoding="utf-8")
                gcols = [c for c in qg.columns if c.startswith("Conversions_")]
                qg = qg.groupby(keys, as_index=False)[gcols].sum(min_count=1)
                q = q.merge(qg, on=keys, how="left")
        qa = api.report("SEARCH_QUERY_PERFORMANCE_REPORT", ["Date", "CampaignId", "Query", "Conversions"],
                        str(d_from), str(d_to), name="express_q_all")
        if qa is not None and not qa.empty:
            qa.to_csv(out_dir / "express_raw_q_all.csv", index=False, encoding="utf-8")
            qa = qa.groupby(keys, as_index=False)[["Conversions"]].sum(min_count=1).rename(columns={"Conversions": "Conversions_all"})
            q = q.merge(qa, on=keys, how="left")
        print(f"  расход в отчёте по запросам: {q['Cost'].sum():.0f} ₽ (по кампаниям за период: {rep['Cost'].sum():.0f} ₽; "
              "запросы покрывают не весь расход — редкие запросы Директ скрывает)")
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
    print("\n[4] Фиды и структура текущих кампаний")
    structure(api, camps, out_dir)
    ids = [c["Id"] for c in camps]
    groups = feed_adgroups(api, ids)
    feed_ids = sorted({g["FeedId"] for g in groups if g.get("FeedId")})
    print(f"Групп с фидом (FeedId): {len(feed_ids)} фидов: {feed_ids or 'нет'}")
    feeds = fetch_feeds(api, feed_ids) if feed_ids else []
    if not feeds:
        print("Фидов Директа (объект «Фид») в кабинете не найдено через группы объявлений")
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
