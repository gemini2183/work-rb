#!/usr/bin/env python
# coding: utf-8
"""Выносит «монтажные» широкие минус-слова из больших общих списков в отдельный список `montaz-block`.

Зачем (ProfiMet, 2026-11-12): для теста семантики с монтажом нужна кампания, которой не мешают широкие минуса
`montaż`, `montaz`, `z montażem` из общих списков «Общий» и «Из запросов». Эти списки подключены к 24 кампаниям.
Копировать 785 фраз в новый список дорого по операциям API (П-001), поэтому наоборот: три термина переезжают в
`montaz-block`, список подключается ко ВСЕМ кампаниям, у которых есть «Общий» или «Из запросов», и только потом три
термина удаляются из больших списков. Для старых кампаний набор минусов не меняется. Новая кампания подключает
большие списки, а `montaz-block` и `montaz` — нет.

Одна атомарная транзакция (GoogleAdsService.mutate): создать список, добавить 3 критерия, подключить к кампаниям,
удалить 4 критерия из «Общий»/«Из запросов». Идемпотентно: существующий список и связи переиспользуются.

БЕЗОПАСНОСТЬ: по умолчанию validate_only. Запись только с --execute. Перед записью — снимок «до» в
Клиенты/ProfiMet/Статистика/montaz_block_before_<время>.json. После записи — чтение обратно.
Откат: см. поле `rollback` в снимке (вернуть 4 критерия в списки, снять связи, удалить список).

    python gads_montaz_block_list.py                # проверка
    python gads_montaz_block_list.py --execute      # запись
    python gads_montaz_block_list.py --read-back-only
"""
import argparse
import json
from datetime import datetime

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_quota_ledger import record_mutate, wrap_ga
from gads_stats import GOOGLE_ADS_YAML

CID = "7552781705"
BLOCK_NAME = "Монтаж широкие"   # до 12.11 назывался montaz-block
NEW_NAME = "Монтаж широкие"
BIG_LISTS = ("Общий", "Из запросов")
# (текст, тип) — все широкие, как в исходных списках
MOVE_TERMS = ["montaż", "montaz", "z montażem"]
SCRIPT = "gads_montaz_block_list"


def read_state(ga, E):
    """Возвращает: id списков, критерии монтажа в больших списках, кампании со связями, существующий montaz-block."""
    sets = {}
    for r in ga.search(customer_id=CID, query=(
            "SELECT shared_set.id, shared_set.name FROM shared_set "
            "WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND shared_set.status = 'ENABLED'")):
        sets[r.shared_set.name] = r.shared_set.id
    crit = []   # (list_name, set_id, criterion_id, text, resource_name)
    for r in ga.search(customer_id=CID, query=(
            "SELECT shared_set.id, shared_set.name, shared_criterion.criterion_id, shared_criterion.keyword.text, "
            "shared_criterion.keyword.match_type, shared_criterion.resource_name FROM shared_criterion "
            "WHERE shared_criterion.keyword.text LIKE '%mont%'")):
        if r.shared_set.name in BIG_LISTS or r.shared_set.name == BLOCK_NAME:
            crit.append((r.shared_set.name, r.shared_set.id, r.shared_criterion.criterion_id,
                         r.shared_criterion.keyword.text,
                         E.KeywordMatchTypeEnum.KeywordMatchType.Name(r.shared_criterion.keyword.match_type),
                         r.shared_criterion.resource_name))
    links = {}  # campaign_id -> {"name":..., "status":..., "lists": set(names)}
    for r in ga.search(customer_id=CID, query=(
            "SELECT campaign.id, campaign.name, campaign.status, shared_set.name, campaign_shared_set.status "
            "FROM campaign_shared_set WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND campaign.status != 'REMOVED'")):
        d = links.setdefault(r.campaign.id, {"name": r.campaign.name,
                                              "status": E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status),
                                              "lists": set()})
        d["lists"].add(r.shared_set.name)
    return sets, crit, links


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Реально записать. Без флага — validate_only")
    ap.add_argument("--read-back-only", action="store_true")
    ap.add_argument("--rename", action="store_true", help=f"Переименовать {BLOCK_NAME} в «{NEW_NAME}» (одна операция; с --execute)")
    args = ap.parse_args()

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    E = client.enums
    ga = wrap_ga(client.get_service("GoogleAdsService"), SCRIPT)
    if args.rename:
        rows = [(r.shared_set.id, r.shared_set.name) for r in ga.search(customer_id=CID, query=(
            "SELECT shared_set.id, shared_set.name FROM shared_set WHERE shared_set.type = 'NEGATIVE_KEYWORDS' "
            "AND shared_set.status = 'ENABLED'")) if r.shared_set.name in (BLOCK_NAME, NEW_NAME)]
        if not rows:
            raise SystemExit("Список не найден")
        sid, name = rows[0]
        print(f"Список {sid}: «{name}» -> «{NEW_NAME}»")
        if name == NEW_NAME:
            print("Уже переименован.")
            return
        from google.protobuf import field_mask_pb2
        op = client.get_type("SharedSetOperation")
        op.update.resource_name = f"customers/{CID}/sharedSets/{sid}"
        op.update.name = NEW_NAME
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["name"]))
        record_mutate(SCRIPT, 1, validate_only=not args.execute)
        req = client.get_type("MutateSharedSetsRequest")
        req.customer_id = CID
        req.operations.append(op)
        req.validate_only = not args.execute
        client.get_service("SharedSetService").mutate_shared_sets(request=req)
        print("Записано." if args.execute else "Проверка пройдена, ничего не записано.")
        return
    sets, crit, links = read_state(ga, E)

    block_id = sets.get(BLOCK_NAME)
    big_ids = {n: sets[n] for n in BIG_LISTS}
    targets = sorted(cid_ for cid_, d in links.items() if d["lists"] & set(BIG_LISTS))
    have_block = {cid_ for cid_, d in links.items() if BLOCK_NAME in d["lists"]}
    to_remove = [c for c in crit if c[0] in BIG_LISTS and c[3] in MOVE_TERMS and c[4] == "BROAD"]
    existing_block_terms = {c[3] for c in crit if c[0] == BLOCK_NAME}

    print(f"Список {BLOCK_NAME}: {'есть, id ' + str(block_id) if block_id else 'будет создан'}")
    print(f"Кампаний с «Общий» или «Из запросов» (не удалённые): {len(targets)}; уже подключён {BLOCK_NAME}: {len(have_block & set(targets))}")
    print("Критерии, которые переедут (удаляются из больших списков):")
    for c in to_remove:
        print(f"  {c[0]}: «{c[3]}» [{c[4]}] id {c[2]}")

    if args.read_back_only:
        print("\nКритерии монтажа в списках сейчас:")
        for c in crit:
            print(f"  {c[0]}: «{c[3]}» [{c[4]}]")
        print(f"Кампаний со связью {BLOCK_NAME}: {len(have_block)}; без связи, но с большими списками: "
              f"{[links[c]['name'] for c in targets if c not in have_block]}")
        return

    # снимок «до»
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = {
        "time": ts, "block_set_id": block_id, "big_sets": big_ids,
        "removed_criteria": [{"list": c[0], "set_id": c[1], "criterion_id": c[2], "text": c[3], "match": c[4]} for c in to_remove],
        "campaigns": [{"id": cid_, "name": links[cid_]["name"], "status": links[cid_]["status"],
                       "lists": sorted(links[cid_]["lists"])} for cid_ in targets],
        "rollback": f"вернуть removed_criteria (BROAD) в списки big_sets; снять связи {BLOCK_NAME} с campaigns; удалить список {BLOCK_NAME}",
    }
    snap_path = client_stats_dir("ProfiMet") / f"montaz_block_before_{ts}.json"
    snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Снимок «до»:", snap_path)

    ops = []

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    set_rn = f"customers/{CID}/sharedSets/{block_id}" if block_id else f"customers/{CID}/sharedSets/-1"
    if not block_id:
        s = new_op().shared_set_operation.create
        s.resource_name = set_rn
        s.name = BLOCK_NAME
        s.type_ = E.SharedSetTypeEnum.NEGATIVE_KEYWORDS
    for t in MOVE_TERMS:
        if t in existing_block_terms:
            continue
        sc = new_op().shared_criterion_operation.create
        sc.shared_set = set_rn
        sc.keyword.text = t
        sc.keyword.match_type = E.KeywordMatchTypeEnum.BROAD
    for cid_ in targets:
        if cid_ in have_block:
            continue
        css = new_op().campaign_shared_set_operation.create
        css.campaign = f"customers/{CID}/campaigns/{cid_}"
        css.shared_set = set_rn
    for c in to_remove:                       # удаляем в самом конце, после подключения блока
        new_op().shared_criterion_operation.remove = c[5]

    print(f"Операций в транзакции: {len(ops)}")
    try:
        svc = client.get_service("GoogleAdsService")
        req = client.get_type("MutateGoogleAdsRequest")
        req.customer_id = CID
        req.mutate_operations.extend(ops)
        req.validate_only = not args.execute
        record_mutate(SCRIPT, len(ops), validate_only=not args.execute)
        svc.mutate(request=req)
    except GoogleAdsException as ex:
        print("ОШИБКА от Google Ads:")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
        raise SystemExit(1)

    if not args.execute:
        print("Проверка пройдена. НИЧЕГО не записано (validate_only).")
        return
    print("Записано. Чтение обратно:")
    sets2, crit2, links2 = read_state(ga, E)
    for c in crit2:
        print(f"  {c[0]}: «{c[3]}» [{c[4]}]")
    t2 = sorted(cid_ for cid_, d in links2.items() if d["lists"] & set(BIG_LISTS))
    miss = [links2[c]["name"] for c in t2 if BLOCK_NAME not in links2[c]["lists"]]
    print(f"Кампаний с большими списками: {len(t2)}; без {BLOCK_NAME}: {miss}")


if __name__ == "__main__":
    main()
