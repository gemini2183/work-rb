#!/usr/bin/env python
# coding: utf-8
"""Google Ads: смена ОДНОГО параметра запроса (например utm_campaign) в шаблоне отслеживания объявлений (ad.tracking_url_template).
ЗАПИСЬ только с --execute; без него - чтение, план «было -> станет» и проверка Google (validate_only), ничего не меняется.

Зачем (EkspertAgro, 2026-11-24): у объявлений новой кампании метка utm_campaign должна совпадать с названием кампании
(«general_demand_gen / inmarket»), а остальная строка шаблона ({lpurl}, utm_source, utm_medium, utm_content с {valuetrack}) не должна
измениться ни на символ. Скрипт универсальный: клиент, объявления, имя параметра и значение - аргументы.

Что делает:
  1. Читает ad.tracking_url_template у объявлений --ad-id (любой статус, кроме отсутствующих в аккаунте).
  2. Заменяет значение параметра ИМЯ в строке запроса шаблона (после первого «?», разделитель «&»), остальной текст не трогает.
     Нет «?» или нет такого параметра - объявление пропускается (параметр можно добавить в конец ключом --add-missing).
  3. Печатает построчно «было -> станет».
  4. Без --execute: вызывает validate_only для каждого объявления отдельно и для КАЖДОГО варианта записи значения:
       raw      - как есть («general_demand_gen / inmarket», с пробелом и слэшем);
       encoded  - в закодированном виде (urllib.parse.quote, safe=''): general_demand_gen%20%2F%20inmarket.
     Отказ API печатается дословно (код ошибки + сообщение). Какой вариант выбрать, скрипт не решает.
  5. С --execute: нужен --value-mode raw|encoded (выбор вручную, молча не выбирается) и --client-folder (снимок «до» в CSV);
     пишет одной мутацией, читает обратно и печатает фактическое значение и совпало ли оно с планом.
Откат: команда с прежним значением параметра (печатается в конце) и --execute.
Публикации/включения кампаний скрипт не делает: меняет только tracking_url_template у указанных объявлений.
Операции учитываются в gads_quota_ledger (чтение через wrap_ga, мутации через record_mutate).

    python gads_ad_tracking_set.py --customer-id 882-613-4558 --ad-id 832534446385 --ad-id 832534446388 \
        --set-param "utm_campaign=general_demand_gen / inmarket"
    python gads_ad_tracking_set.py --customer-id 882-613-4558 --ad-id 832534446385 --ad-id 832534446388 \
        --set-param "utm_campaign=general_demand_gen / inmarket" --value-mode encoded --client-folder EkspertAgro --execute

Дата создания: 2026-11-24.
"""
import argparse
import csv
from datetime import datetime
from urllib.parse import quote

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML
from gads_quota_ledger import wrap_ga, record_mutate

SCRIPT = "gads_ad_tracking_set"
MODES = ("raw", "encoded")


def encode_value(value, mode):
    return value if mode == "raw" else quote(value, safe="")


def replace_param(template, name, new_value, add_missing=False):
    """Вернуть (новый_шаблон, причина_пропуска). Меняется только значение параметра `name` в строке запроса."""
    if "?" not in template:
        return None, "в шаблоне нет «?» (нет строки запроса)"
    head, query = template.split("?", 1)
    parts = query.split("&")
    hit = [i for i, p in enumerate(parts) if p.split("=", 1)[0] == name]
    if len(hit) > 1:
        return None, f"параметр {name} встречается {len(hit)} раза"
    if hit:
        parts[hit[0]] = f"{name}={new_value}"
    elif add_missing:
        parts.append(f"{name}={new_value}")
    else:
        return None, f"параметра {name} в шаблоне нет (добавить: --add-missing)"
    return head + "?" + "&".join(parts), None


def read_ads(ga, E, cid, ad_ids):
    q = ("SELECT ad_group_ad.ad.id, ad_group_ad.ad.resource_name, ad_group_ad.ad.tracking_url_template, ad_group_ad.status, "
         "campaign.id, campaign.name, ad_group.name FROM ad_group_ad "
         "WHERE ad_group_ad.ad.id IN (" + ", ".join(str(i) for i in ad_ids) + ")")
    out = {}
    for r in ga.search(customer_id=cid, query=q):
        ad = r.ad_group_ad.ad
        out[ad.id] = {"resource": ad.resource_name, "template": ad.tracking_url_template,
                      "campaign": f"{r.campaign.id} {r.campaign.name}", "group": r.ad_group.name,
                      "status": E.AdGroupAdStatusEnum.AdGroupAdStatus.Name(r.ad_group_ad.status)}
    return out


def mutate(client, svc, cid, items, validate_only):
    """items: [(resource_name, new_template)]. Вернуть список строк ошибок (пусто = принято)."""
    ops = []
    for res, tmpl in items:
        op = client.get_type("AdOperation")
        op.update.resource_name = res
        op.update.tracking_url_template = tmpl
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["tracking_url_template"]))
        ops.append(op)
    req = client.get_type("MutateAdsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = validate_only
    record_mutate(SCRIPT, len(ops), validate_only=validate_only)
    try:
        svc.mutate_ads(request=req)
    except GoogleAdsException as ex:
        return [f"{e.error_code} | {e.message}" for e in ex.failure.errors]
    return []


def main():
    ap = argparse.ArgumentParser(description="Смена одного параметра в ad.tracking_url_template (по умолчанию validate_only)")
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--ad-id", action="append", type=int, required=True, help="id объявления, повторяемый")
    ap.add_argument("--set-param", action="append", required=True, metavar="ИМЯ=ЗНАЧЕНИЕ",
                    help="параметр запроса и новое значение (повторяемый); значение дословно, без кодирования")
    ap.add_argument("--value-mode", choices=MODES, help="как записывать значение при --execute: raw (как есть) или encoded (%%20, %%2F)")
    ap.add_argument("--add-missing", action="store_true", help="если параметра в шаблоне нет - добавить в конец строки запроса")
    ap.add_argument("--client-folder", help="папка клиента для снимка «до» (Статистика/); обязателен с --execute")
    ap.add_argument("--execute", action="store_true", help="реально записать; без флага - только план и validate_only")
    a = ap.parse_args()
    pairs = []
    for s in a.set_param:
        if "=" not in s or not s.split("=", 1)[0]:
            ap.error(f"--set-param {s!r}: нужен вид ИМЯ=ЗНАЧЕНИЕ")
        pairs.append(tuple(s.split("=", 1)))
    if a.execute and not a.value_mode:
        ap.error("с --execute нужен --value-mode raw|encoded: вариант записи выбирается явно (сначала прогон без --execute)")
    if a.execute and not a.client_folder:
        ap.error("с --execute нужен --client-folder (снимок «до»)")
    cid = a.customer_id.replace("-", "").strip()

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = wrap_ga(client.get_service("GoogleAdsService"), SCRIPT)
    svc = client.get_service("AdService")

    before = read_ads(ga, client.enums, cid, a.ad_id)
    missing = [i for i in a.ad_id if i not in before]
    if missing:
        raise SystemExit(f"объявлений нет в аккаунте {cid}: {missing}")

    modes = [a.value_mode] if a.execute else list(MODES)
    # план по каждому режиму: {mode: {ad_id: новый_шаблон}}
    plan = {m: {} for m in modes}
    print(f"Аккаунт {cid}; объявлений: {len(a.ad_id)}; параметры: {[p[0] for p in pairs]}; режим: "
          f"{'ЗАПИСЬ (--execute)' if a.execute else 'только план и validate_only'}\n")
    skipped = {}
    for ad_id in a.ad_id:
        b = before[ad_id]
        print(f"объявление {ad_id} | {b['campaign']} | {b['group']} | {b['status']}")
        print(f"  было: {b['template']!r}")
        for m in modes:
            tmpl = b["template"]
            reason = None
            for name, val in pairs:
                tmpl, reason = replace_param(tmpl, name, encode_value(val, m), a.add_missing)
                if reason:
                    break
            if reason:
                skipped[ad_id] = reason
                print(f"  [{m}] ПРОПУСК: {reason}")
                continue
            if tmpl == b["template"]:
                skipped[ad_id] = "шаблон уже содержит это значение"
                print(f"  [{m}] без изменений: шаблон уже содержит это значение")
                continue
            plan[m][ad_id] = tmpl
            print(f"  [{m}] станет: {tmpl!r}")
        print()

    # проверка Google
    verdict = {}
    for m in modes:
        if not plan[m]:
            continue
        if not a.execute:
            for ad_id, tmpl in plan[m].items():
                errs = mutate(client, svc, cid, [(before[ad_id]["resource"], tmpl)], validate_only=True)
                verdict[(m, ad_id)] = errs
                print(f"validate_only [{m}] объявление {ad_id}: " + ("ПРИНЯТО" if not errs else "ОТКАЗ API: " + " || ".join(errs)))
    if not a.execute:
        print("\nНичего не изменено (validate_only). Как значение хранится после записи, validate_only не показывает: "
              "ожидаем, что строка сохранится ровно такой, какой отправлена; подтвердить можно только записью и чтением обратно.")
        ok_modes = [m for m in MODES if plan[m] and all(not verdict.get((m, i)) for i in plan[m])]
        print("Варианты, принятые API для всех объявлений:", ok_modes or "нет")
        print("Для записи: те же аргументы + --value-mode <вариант> --client-folder <Имя> --execute")
        return

    m = a.value_mode
    todo = plan[m]
    if not todo:
        raise SystemExit("нечего менять")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_ad_tracking_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(snap, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ad_id", "campaign", "group", "status", "tracking_url_template_before"])
        for ad_id in a.ad_id:
            b = before[ad_id]
            w.writerow([ad_id, b["campaign"], b["group"], b["status"], b["template"]])
    print("Снимок «до»:", snap)
    errs = mutate(client, svc, cid, [(before[i]["resource"], t) for i, t in todo.items()], validate_only=False)
    if errs:
        print("ОТКАЗ API:", " || ".join(errs))
        raise SystemExit(1)
    after = read_ads(ga, client.enums, cid, list(todo))
    allok = True
    print("\nЧтение обратно:")
    for ad_id, want in todo.items():
        got = after[ad_id]["template"]
        good = got == want
        allok &= good
        print(f"  {ad_id}: {got!r} | {'OK' if good else 'НЕ СОВПАЛО, ожидалось ' + repr(want)}")
    print("\nОткат: восстановить значения из снимка:", snap)
    if not allok:
        raise SystemExit("часть объявлений не совпала с планом")


if __name__ == "__main__":
    main()
