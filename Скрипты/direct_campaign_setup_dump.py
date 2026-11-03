#!/usr/bin/env python
# coding: utf-8
"""Полнота настройки кампании Директа (только чтение): параметры кампании, расписание, корректировки ставок, объявления
(заголовок 2, картинки, быстрые ссылки, уточнения, визитка, организация), автотаргетинг. Сырой дамп в JSON и сводка в консоль.

Запуск: PYTHONUTF8=1 python direct_campaign_setup_dump.py --login porg-juupcxo3 --token-file ../.secrets/novotel_direct.token \
    --client-folder Novotel_Moscow_City --campaign-id 705894438
"""
import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_express_audit import Direct, read_token, VAULT_ROOT  # noqa: E402

STATES = ["ON", "OFF", "SUSPENDED", "ENDED", "CONVERTED", "ARCHIVED"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--campaign-id", required=True, type=int)
    a = ap.parse_args()
    api = Direct(a.login, read_token(a.token_file))
    cid = a.campaign_id
    dump = {}

    cs, e = api.get_all("campaigns", {
        "SelectionCriteria": {"Ids": [cid], "States": STATES},
        "FieldNames": ["Id", "Name", "Type", "State", "Status", "StartDate", "EndDate", "TimeZone", "TimeTargeting", "DailyBudget",
                       "NegativeKeywords", "BlockedIps", "ExcludedSites", "ClientInfo", "Notification", "Currency"],
        "TextCampaignFieldNames": ["CounterIds", "RelevantKeywords", "Settings", "BiddingStrategy", "PriorityGoals", "AttributionModel",
                                   "TrackingParams", "NegativeKeywordSharedSetIds"]}, "Campaigns")
    print("campaigns:", e)
    c = cs[0]
    dump["campaign"] = c
    t = c.get("TextCampaign", {})
    st = {s["Option"]: s["Value"] for s in t.get("Settings", [])}
    print(f"\n== Кампания {c['Name']}\nСостояние {c['State']}, старт {c.get('StartDate')}, конец {c.get('EndDate')}, часовой пояс {c.get('TimeZone')}")
    print("Дневной бюджет:", c.get("DailyBudget"))
    print("Стратегия:", json.dumps(t.get("BiddingStrategy"), ensure_ascii=False))
    print("Счётчики:", t.get("CounterIds"), "| модель атрибуции:", t.get("AttributionModel"))
    pg = t.get("PriorityGoals")
    print("Приоритетные цели:", [(g["GoalId"], g["Value"]) for g in pg.get("Items", [])] if pg else None)
    print("Метки (TrackingParams):", t.get("TrackingParams"))
    print("Доп. релевантные фразы:", t.get("RelevantKeywords"))
    print("Настройки ДА:", sorted(k for k, v in st.items() if v == "YES"))
    print("Настройки НЕТ:", sorted(k for k, v in st.items() if v == "NO"))
    tt = c.get("TimeTargeting") or {}
    print("Расписание: учитывать праздники", tt.get("ConsiderWorkingWeekends"), "| расписание:",
          json.dumps(tt.get("Schedule"), ensure_ascii=False)[:700] if tt else None)
    print("Минус-фраз:", len((c.get("NegativeKeywords") or {}).get("Items", [])), "| заблок. IP:", c.get("BlockedIps"),
          "| исключ. площадки:", c.get("ExcludedSites"), "| уведомления:", json.dumps(c.get("Notification"), ensure_ascii=False)[:300])

    bm, e = api.get_all("bidmodifiers", {
        "SelectionCriteria": {"CampaignIds": [cid], "Levels": ["CAMPAIGN", "AD_GROUP"]},
        "FieldNames": ["Id", "CampaignId", "AdGroupId", "Level", "Type"],
        "MobileAdjustmentFieldNames": ["BidModifier"], "DesktopAdjustmentFieldNames": ["BidModifier"],
        "DesktopOnlyAdjustmentFieldNames": ["BidModifier"], "TabletAdjustmentFieldNames": ["BidModifier"],
        "DemographicsAdjustmentFieldNames": ["Gender", "Age", "BidModifier", "Enabled"],
        "RetargetingAdjustmentFieldNames": ["RetargetingConditionId", "BidModifier", "Accessible", "Enabled"],
        "RegionalAdjustmentFieldNames": ["RegionId", "BidModifier", "Enabled"],
        "IncomeGradeAdjustmentFieldNames": ["Grade", "BidModifier", "Enabled"],
        "SerpLayoutAdjustmentFieldNames": ["SerpLayout", "BidModifier"],
        "AdGroupAdjustmentFieldNames": ["BidModifier"]}, "BidModifiers")
    dump["bidmodifiers"] = bm
    print("\n== Корректировки ставок:", e if e else f"{len(bm)} шт.")
    print(dict(collections.Counter((x.get("Level"), x.get("Type")) for x in bm or [])))
    for x in (bm or [])[:40]:
        body = {k: v for k, v in x.items() if k not in ("Id", "CampaignId", "AdGroupId", "Level", "Type")}
        print(" ", x.get("Level"), x.get("Type"), json.dumps(body, ensure_ascii=False)[:260])

    ads, e = api.get_all("ads", {
        "SelectionCriteria": {"CampaignIds": [cid]},
        "FieldNames": ["Id", "AdGroupId", "State", "Status", "Type"],
        "TextAdFieldNames": ["Title", "Title2", "Text", "Href", "DisplayDomain", "DisplayUrlPath", "Mobile", "AdImageHash", "SitelinkSetId",
                             "AdExtensions", "VCardId", "BusinessId", "PreferVCardOverBusiness", "TurboPageId", "VideoExtension",
                             "LogoExtensionHash", "ButtonExtension", "TrackingPhoneId"]}, "Ads")
    print("\n== Объявления:", e if e else len(ads))
    if ads:
        dump["ads"] = ads
        ta = [x.get("TextAd") or {} for x in ads]
        n = len(ta)
        by_group = collections.Counter(x["AdGroupId"] for x in ads)
        print("объявлений на группу:", dict(collections.Counter(by_group.values())))
        print("состояния:", dict(collections.Counter(x["State"] for x in ads)))

        def cnt(f):
            return sum(1 for x in ta if f(x))

        print(f"Заголовок 2: {cnt(lambda x: x.get('Title2'))}/{n}; путь в ссылке: {cnt(lambda x: x.get('DisplayUrlPath'))}/{n}; "
              f"картинка: {cnt(lambda x: x.get('AdImageHash'))}/{n}; быстрые ссылки: {cnt(lambda x: x.get('SitelinkSetId'))}/{n}; "
              f"визитка: {cnt(lambda x: x.get('VCardId'))}/{n}; организация: {cnt(lambda x: x.get('BusinessId'))}/{n}; "
              f"уточнения: {cnt(lambda x: x.get('AdExtensions'))}/{n}; видео: {cnt(lambda x: x.get('VideoExtension'))}/{n}; "
              f"турбо: {cnt(lambda x: x.get('TurboPageId'))}/{n}; логотип: {cnt(lambda x: x.get('LogoExtensionHash'))}/{n}; "
              f"кнопка: {cnt(lambda x: x.get('ButtonExtension'))}/{n}; подмена номера: {cnt(lambda x: x.get('TrackingPhoneId'))}/{n}")
        for f, lim in (("Title", 56), ("Title2", 30), ("Text", 81)):
            v = [len(x.get(f) or "") for x in ta if x.get(f)]
            if v:
                print(f"{f}: длина мин/ср/макс {min(v)}/{sum(v) / len(v):.0f}/{max(v)} (лимит {lim})")
        print("ссылки:", dict(collections.Counter((x.get("Href") or "").split("?")[0] for x in ta).most_common(4)))
        sl_ids = sorted({x["SitelinkSetId"] for x in ta if x.get("SitelinkSetId")})
        ext_ids = sorted({e2["AdExtensionId"] for x in ta for e2 in (x.get("AdExtensions") or [])})
        vc_ids = sorted({x["VCardId"] for x in ta if x.get("VCardId")})
        print("наборов быстрых ссылок:", len(sl_ids), "| уточнений:", len(ext_ids), "| визиток:", len(vc_ids))
        if sl_ids:
            sls, e = api.get_all("sitelinks", {"SelectionCriteria": {"Ids": sl_ids[:10000]}, "FieldNames": ["Id", "Sitelinks"]},
                                 "SitelinksSets")
            dump["sitelinks"] = sls
            print("быстрые ссылки:", e if e else dict(collections.Counter(len(s["Sitelinks"]) for s in sls)))
            for s in (sls or [])[:2]:
                for lnk in s["Sitelinks"]:
                    print("  ", lnk.get("Title"), "|", lnk.get("Description"), "|", (lnk.get("Href") or "")[:70])
        if ext_ids:
            ex = api.call("adextensions", "get", {"SelectionCriteria": {"Ids": ext_ids[:10000]},
                                                  "FieldNames": ["Id", "Type", "State", "Status"], "CalloutFieldNames": ["CalloutText"]})
            dump["adextensions"] = ex
            items = ex.get("result", {}).get("AdExtensions", [])
            print("уточнения:", ex.get("error") or [(i["Id"], (i.get("Callout") or {}).get("CalloutText"), i.get("State")) for i in items][:12])
        if vc_ids:
            vc = api.call("vcards", "get", {"SelectionCriteria": {"Ids": vc_ids[:10000]},
                                            "FieldNames": ["Id", "Country", "City", "Street", "House", "Phone", "WorkTime", "CompanyName"]})
            dump["vcards"] = vc
            print("визитки:", json.dumps(vc.get("result", vc), ensure_ascii=False)[:500])

    ks, e = api.get_all("keywords", {"SelectionCriteria": {"CampaignIds": [cid], "States": ["ON", "SUSPENDED", "OFF"]},
                                     "FieldNames": ["Id", "Keyword", "State", "AutotargetingCategories"]}, "Keywords")
    print("\n== Автотаргетинг:", e if e else "")
    auto = [k for k in (ks or []) if str(k.get("Keyword", "")).startswith("---autotargeting")]
    dump["autotargeting"] = auto
    cats = collections.Counter()
    for k in auto:
        raw = k.get("AutotargetingCategories")
        items = raw.get("Items", raw) if isinstance(raw, dict) else (raw or [])
        key = json.dumps(sorted((x.get("Category"), x.get("Value")) for x in items if isinstance(x, dict)), ensure_ascii=False)
        cats[key] += 1
    print(f"условий автотаргетинга {len(auto)}; наборы категорий:", dict(cats))

    out = VAULT_ROOT / "Клиенты" / a.client_folder / "Статистика" / f"setup_dump_{cid}.json"
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nсырой дамп:", out)


if __name__ == "__main__":
    main()
