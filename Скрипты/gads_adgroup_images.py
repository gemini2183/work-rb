#!/usr/bin/env python
# coding: utf-8
"""Картинки Search-объявлений на уровне ГРУПП (ассеты AD_IMAGE). ЗАПИСЬ только с --execute (по умолчанию validate_only).

Зачем (Landver, 2026-10-28): картинки лежали на уровне кампании и доставались трём новым группам (бинты, авария, деньги).
Групповые картинки перекрывают кампанийные (как быстрые ссылки). Скрипт загружает файлы как ассеты-изображения и привязывает к группам.

План — JSON: {"campaign": "...", "groups": {"<группа>": ["путь/к/файлу.jpg", ...]}}, пути от корня вики или абсолютные.
Имя ассета = «ai_<имя файла>» (уникально; по префиксу находится при откате). Без --execute: проверка файлов и validate_only загрузки.
С --execute: снимок «до» (привязки AD_IMAGE групп) в Статистика/ клиента, загрузка, привязка, чтение обратно.
Откат: --remove --execute — отвязывает от групп плана ассеты, имена которых в плане (сами ассеты остаются в библиотеке).

ИИ-метка: в API Google Ads (клиент в этой конфигурации) поля «created or edited with AI» у Asset/ImageAsset НЕТ — галочка есть только в
интерфейсе при загрузке. Скрипт метку не ставит и выводит напоминание; происхождение каждого файла — рядом лежит <файл>.meta.json.

    python gads_adgroup_images.py --customer-id 213-621-6123 --client-folder Andverpersonalinjury --plan <план.json> [--execute] [--remove]
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from _config import client_stats_dir
from gads_stats import GOOGLE_ADS_YAML

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 5 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()

    p = Path(a.plan)
    plan = json.loads((p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8"))
    cid = a.customer_id.replace("-", "")
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = client.get_service("GoogleAdsService")
    E = client.enums

    groups = {}
    q = ("SELECT ad_group.id, ad_group.name, ad_group.resource_name FROM ad_group "
         f"WHERE campaign.name = '{plan['campaign']}' AND ad_group.status != 'REMOVED'")
    for r in ga.search(customer_id=cid, query=q):
        groups[r.ad_group.name] = (r.ad_group.id, r.ad_group.resource_name)
    missing = [g for g in plan["groups"] if g not in groups]
    if missing:
        raise SystemExit(f"Нет групп в кампании: {missing}")

    def asset_name(path):
        return "ai_" + Path(path).stem

    # снимок «до»: привязки AD_IMAGE этих групп
    names = ", ".join(f"'{g}'" for g in plan["groups"])
    before = []
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.name, ad_group.name, ad_group_asset.resource_name, ad_group_asset.status, asset.id, asset.name FROM ad_group_asset "
            f"WHERE ad_group_asset.field_type = 'AD_IMAGE' AND ad_group_asset.status != 'REMOVED' AND campaign.name = '{plan['campaign']}' "
            f"AND ad_group.name IN ({names})")):
        before.append((r.ad_group.name, r.ad_group_asset.resource_name, r.asset.id, r.asset.name))
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    snap = client_stats_dir(a.client_folder) / f"snapshot_before_adgroup_images_{stamp}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "link_resource", "asset_id", "asset_name"])
        w.writerows(before)
    print(f"Снимок «до»: {snap} (групповых привязок AD_IMAGE: {len(before)})")

    if a.remove:
        want = {(g, asset_name(f)) for g, fs in plan["groups"].items() for f in fs}
        todo = [x for x in before if (x[0], x[3]) in want]
        print(f"К отвязке: {len(todo)}")
        if not a.execute:
            return print("НИЧЕГО не изменено. Для отката: --remove --execute")
        svc = client.get_service("AdGroupAssetService")
        ops = []
        for x in todo:
            op = client.get_type("AdGroupAssetOperation")
            op.remove = x[1]
            ops.append(op)
        svc.mutate_ad_group_assets(customer_id=cid, operations=ops)
        return print("Отвязано:", len(ops))

    files = []
    for g, fs in plan["groups"].items():
        for f in fs:
            fp = Path(f)
            fp = fp if fp.is_absolute() else ROOT / fp
            if not fp.exists():
                raise SystemExit(f"Нет файла: {fp}")
            if fp.stat().st_size > MAX_BYTES:
                raise SystemExit(f"Файл больше 5 МБ: {fp}")
            files.append((g, fp))
    print("\nОбъект | Действие | Было → Станет")
    for g, fp in files:
        print(f"{g} | загрузить и привязать «{asset_name(fp)}» ({fp.stat().st_size // 1024} КБ) | нет → есть")
    print("\nИИ-метка («created or edited with AI») через API недоступна — поставить в интерфейсе, если решено.")

    uniq = {}
    for g, fp in files:
        uniq.setdefault(fp, asset_name(fp))
    ops = []
    for fp, nm in uniq.items():
        op = client.get_type("AssetOperation")
        op.create.name = nm
        op.create.image_asset.data = fp.read_bytes()
        ops.append(op)
    req = client.get_type("MutateAssetsRequest")
    req.customer_id = cid
    req.operations.extend(ops)
    req.validate_only = not a.execute
    try:
        res = client.get_service("AssetService").mutate_assets(request=req)
    except GoogleAdsException as ex:
        for e in ex.failure.errors:
            print("  ОШИБКА:", e.message)
        raise SystemExit(1)
    if not a.execute:
        return print("\nvalidate_only: ОК — Google принял файлы. НИЧЕГО не изменено. Для записи: --execute")

    rn = {fp: r.resource_name for fp, r in zip(uniq, res.results)}
    link_ops = []
    for g, fp in files:
        lo = client.get_type("AdGroupAssetOperation")
        lo.create.ad_group = groups[g][1]
        lo.create.asset = rn[fp]
        lo.create.field_type = E.AssetFieldTypeEnum.AD_IMAGE
        link_ops.append(lo)
    client.get_service("AdGroupAssetService").mutate_ad_group_assets(customer_id=cid, operations=link_ops)
    print(f"Загружено ассетов: {len(rn)}, привязок: {len(link_ops)}")

    print("\nЧтение обратно:")
    after = {}
    for r in ga.search(customer_id=cid, query=(
            "SELECT campaign.name, ad_group.name, ad_group_asset.status, asset.name, asset.image_asset.full_size.width_pixels, "
            "asset.image_asset.full_size.height_pixels FROM ad_group_asset "
            f"WHERE ad_group_asset.field_type = 'AD_IMAGE' AND ad_group_asset.status != 'REMOVED' AND campaign.name = '{plan['campaign']}' "
            f"AND ad_group.name IN ({names})")):
        after.setdefault(r.ad_group.name, []).append(
            f"{r.asset.name} {r.asset.image_asset.full_size.width_pixels}x{r.asset.image_asset.full_size.height_pixels}")
    for g, items in after.items():
        print(f"  {g}: {len(items)} картинок")
        for it in sorted(items):
            print("    ", it)
    print("\nОткат: --remove --execute с тем же планом")


if __name__ == "__main__":
    main()
