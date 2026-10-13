#!/usr/bin/env python
# coding: utf-8
"""Удаление остановленных экспериментов Google Ads (вместе с их пробными кампаниями). ЗАПИСЬ, по умолчанию validate_only.

Зачем: 2026-10-13 ProfiMet — четыре остановленных (HALTED) эксперимента апреля 2025 оставили включённые «пробные» кампании без показов
(статус пробной кампании менять нельзя), они шумели в аудите ассетов и текстов. Удаление эксперимента необратимо: удаляются плечо
пробных кампаний и сами пробные кампании; базовая кампания не трогается.

Использование:
    python gads_remove_experiments.py --customer-id 7552781705 --client-folder ProfiMet --experiment-ids 10058439223 10058495751 --execute
Проверки: статус эксперимента должен быть HALTED/REMOVED-совместимым; снимок «до» (имя, статус, даты, кампании плеч) — CSV в Статистике.
"""
import argparse
import csv
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML


def nm(enum, v):
    try:
        return enum.DESCRIPTOR.enum_types[0].values_by_number[v].name
    except Exception:
        return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--experiment-ids", nargs="+", required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    ids = ",".join(a.experiment_ids)
    exps = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT experiment.resource_name, experiment.experiment_id, experiment.name, experiment.status, experiment.start_date, "
            f"experiment.end_date FROM experiment WHERE experiment.experiment_id IN ({ids})")):
        e = r.experiment
        exps[str(e.experiment_id)] = {"res": e.resource_name, "name": e.name, "status": nm(client.enums.ExperimentStatusEnum, e.status),
                                      "start": e.start_date, "end": e.end_date, "campaigns": []}
    for r in ga.search(customer_id=cid, query=(
            "SELECT experiment_arm.experiment, experiment_arm.control, experiment_arm.campaigns, experiment_arm.in_design_campaigns "
            "FROM experiment_arm")):
        eid = r.experiment_arm.experiment.split("/")[-1]
        if eid in exps and not r.experiment_arm.control:
            exps[eid]["campaigns"] += [c.split("/")[-1] for c in list(r.experiment_arm.campaigns) + list(r.experiment_arm.in_design_campaigns)]
    missing = [i for i in a.experiment_ids if i not in exps]
    if missing:
        raise SystemExit(f"не найдены эксперименты: {missing}")
    bad = {i: e["status"] for i, e in exps.items() if e["status"] not in ("HALTED", "REMOVED", "GRADUATED", "PROMOTED")}
    print("К удалению:")
    for i, e in exps.items():
        print(f"  {i} | {e['status']} | {e['start']}..{e['end']} | {e['name'][:60]} | пробные кампании: {e['campaigns']}")
    if bad:
        raise SystemExit(f"статус не позволяет автоматическое удаление: {bad}")
    svc = client.get_service("ExperimentService")
    ops = []
    for e in exps.values():
        op = client.get_type("ExperimentOperation")
        op.remove = e["res"]
        ops.append(op)
    req = client.get_type("MutateExperimentsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not a.execute
    svc.mutate_experiments(request=req)
    if not a.execute:
        print("validate_only: Google принял. ПЛАН, ничего не удалено (добавьте --execute).")
        return
    path = client_stats_dir(a.client_folder) / f"snapshot_before_experiments_remove_{datetime.now():%Y%m%d_%H%M}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["experiment_id", "name", "status", "start", "end", "trial_campaign_ids"])
        for i, e in exps.items():
            w.writerow([i, e["name"], e["status"], e["start"], e["end"], " ".join(e["campaigns"])])
    print("УДАЛЕНО. Снимок «до»:", path)
    left = {r.experiment.experiment_id: nm(client.enums.ExperimentStatusEnum, r.experiment.status) for r in ga.search(
        customer_id=cid, query=f"SELECT experiment.experiment_id, experiment.status FROM experiment WHERE experiment.experiment_id IN ({ids})")}
    print("прочитано обратно:", left or "экспериментов с этими id нет")


if __name__ == "__main__":
    main()
