#!/usr/bin/env python
# coding: utf-8
"""Чтение статистики и смена ставок в OpenAI Ads (реклама в ChatGPT) через Ads API.

Подкоманды:
    groups   — группы кампании: статус и ставка;
    insights — показы/клики/расход/CTR/CPC по группам (или кампании) за период;
    set-bid  — смена fixed_bid у групп кампании.
    set-maxclicks — перевод групп на maximize_clicks (без ставки; формат взят у групп dog bite).
    ads      — объявления кампании: статус, модерация, заголовок, file_id, обрезка картинки;
    activate — включить группы и их объявления (paused → active; объявления только approved); без --execute план;
    create-groups — создать группы с подсказками и объявлениями по JSON-плану (всё на паузе; без --execute только план
                с проверками: имя уникально, лимиты 3–50 / до 100 знаков, file_id есть в аккаунте); активация — отдельно;
    set-image — замена картинки у объявлений по файлу соответствий (ad_id → файл); загрузка
                файла (POST /upload) и обновление creative (POST /ads/{id}); без --execute план.

БЕЗОПАСНОСТЬ: set-bid и set-image по умолчанию только показывают план «было → станет» и ничего
не пишут. Реальная запись — только с флагом --execute, после неё группы читаются
обратно и печатается фактическое состояние. Другие записи (создание, активация,
бюджеты) сюда сознательно не входят.

Ключ: переменная окружения OPENAI_ADS_API_KEY; если процесс её не видит (VS Code не
перезапускали после setx) — читается из пользовательской области Windows. Значение
ключа нигде не печатается. HTTP — через curl: Python urllib получает 403 (блок по
User-Agent).

Использование:
    python openai_ads.py groups   --campaign cmpn_...
    python openai_ads.py insights --campaign cmpn_... --since 2026-10-07 --until 2026-10-08
    python openai_ads.py insights --campaign cmpn_... --since 2026-10-07 --until 2026-10-08 --granularity hourly --level campaign
    python openai_ads.py set-bid  --campaign cmpn_... --bid 7              # план
    python openai_ads.py set-bid  --campaign cmpn_... --bid 7 --execute    # запись
"""
import argparse
import functools
import json
import os
import subprocess
import sys
import time

BASE = "https://api.ads.openai.com/v1"
KEY_ENV = "OPENAI_ADS_API_KEY"


@functools.lru_cache(maxsize=1)
def get_key():
    key = os.environ.get(KEY_ENV)
    if not key and sys.platform == "win32":
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"[Environment]::GetEnvironmentVariable('{KEY_ENV}','User')"],
            capture_output=True, text=True)
        key = out.stdout.strip()
    if not key:
        sys.exit(f"Нет ключа: задайте переменную {KEY_ENV} (setx) и перезапустите VS Code")
    return key


def call(method, path, params=None, body=None, idem=None):
    cmd = ["curl", "-sS", "-X", method, "-w", "\n%{http_code}",
           "-H", f"Authorization: Bearer {get_key()}"]
    if idem:  # POST создания групп maximize_clicks требует Idempotency-Key (400 без него); ключ детерминированный
        cmd += ["-H", f"Idempotency-Key: {idem}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    url = BASE + path
    if params:
        cmd.append("-G")
        for k, v in params:
            cmd += ["--data-urlencode", f"{k}={v}"]
    cmd.append(url)
    for attempt in range(8):  # 429: лимит частоты, ждём и повторяем
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        text, _, code = res.stdout.rpartition("\n")
        if code != "429":
            break
        time.sleep(1 + attempt)
    if not code.startswith("2"):
        sys.exit(f"HTTP {code} {method} {path}: {text[:500]}")
    return json.loads(text)


def list_groups(campaign):
    return call("GET", "/ad_groups", [("campaign_id", campaign)])["data"]


def bid_text(g):
    b = g.get("bidding_config") or {}
    return f"{b.get('strategy')} ${(b.get('max_bid_micros') or 0) / 1e6:g}"


def cmd_groups(a):
    for g in list_groups(a.campaign):
        print(f"{g['id']}  {g['name']}  {g['status']}  {bid_text(g)}")


def cmd_insights(a):
    level = a.level
    fields = ["campaign.name", "impressions", "clicks", "spend", "ctr", "cpc"]
    if a.granularity != "none":  # при none поле времени API не принимает
        fields.insert(0, "metadata.readable_time")
    if level == "ad_group":
        fields[1:1] = ["ad_group.id", "ad_group.name"]
    params = [("time_granularity", a.granularity), ("aggregation_level", level)]
    params += [("fields[]", f) for f in fields]
    params.append(("time_ranges[]", json.dumps(
        {"type": "date_range", "since": a.since, "until": a.until})))
    params.append(("filters[]", json.dumps(
        {"field": "campaign.id", "operator": "IN", "value": [a.campaign]})))
    rows = call("GET", "/ad_account/insights", params)["data"]
    tot = {"impressions": 0, "clicks": 0, "spend": 0.0}
    for r in rows:
        name = r.get("ad_group_name") or r.get("campaign_name")
        print(f"{r.get('readable_time') or ''}  {name}  показы {r['impressions']}  клики {r['clicks']}  "
              f"расход ${r['spend']:.2f}  CTR {r['ctr']}  CPC ${r['cpc']:.2f}")
        for k in tot:
            tot[k] += r[k]
    print(f"ИТОГО строк {len(rows)}: показы {tot['impressions']}, клики {tot['clicks']}, расход ${tot['spend']:.2f}")


def cmd_set_bid(a):
    micros = int(round(a.bid * 1_000_000))
    groups = list_groups(a.campaign)
    if a.groups:
        wanted = set(a.groups)
        groups = [g for g in groups if g["id"] in wanted]
    if not groups:
        sys.exit("Группы не найдены")
    print("Объект | Действие | Было → Станет")
    for g in groups:
        print(f"{g['name']} ({g['id']}) | fixed_bid | {bid_text(g)} → fixed_bid ${a.bid:g}")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    for g in groups:
        call("POST", f"/ad_groups/{g['id']}", body={"bidding_config": {
            "strategy": "fixed_bid", "billing_event_type": "click", "max_bid_micros": micros}})
    print("\nПрочитано обратно из аккаунта:")
    after = {g["id"]: g for g in list_groups(a.campaign)}
    for g in groups:
        print(f"{after[g['id']]['name']}  {after[g['id']]['status']}  {bid_text(after[g['id']])}")


def cmd_create_groups(a):
    """Создание групп (context_hints, maximize_clicks) и объявлений (chat_card) на паузе по файлу плана.

    Формат плана: {campaign_id, bidding, query_string_template, groups: [{group, context_hints[], ads: [{ad_name, title,
    copy, link, file_id, image_crop}]}]}. Активация сюда сознательно не входит (отдельное «да»)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = a.plan if os.path.isabs(a.plan) else os.path.join(root, a.plan)
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    camp = spec["campaign_id"]
    qs = spec.get("query_string_template") or "campaign_id={campaign_id}&ad_group_id={ad_group_id}&ad_id={ad_id}"
    have = {g["name"] for g in list_groups(camp)}
    used_files = set()
    for ad in list_ads(camp):
        fid = (ad.get("creative") or {}).get("file_id")
        if fid:
            used_files.add(fid)
    errors = []
    print("Группа | Объявление | Заголовок | Текст | file_id")
    for g in spec["groups"]:
        if g["group"] in have:
            errors.append(f"группа «{g['group']}» уже есть")
        if not g.get("context_hints"):
            errors.append(f"у «{g['group']}» нет context_hints")
        for ad in g["ads"]:
            t, c = ad["title"], ad["copy"]
            if not 3 <= len(t) <= 50:
                errors.append(f"{ad['ad_name']}: заголовок {len(t)} знаков (нужно 3–50)")
            if len(c) > 100:
                errors.append(f"{ad['ad_name']}: текст {len(c)} знаков (до 100)")
            if ad.get("file_id") not in used_files:
                errors.append(f"{ad['ad_name']}: file_id {ad.get('file_id')} нет среди картинок кампании")
            print(f"{g['group']} | {ad['ad_name']} | {t} [{len(t)}] | {c} [{len(c)}] | ...{str(ad.get('file_id'))[-8:]}")
    print(f"\nГрупп {len(spec['groups'])}, объявлений {sum(len(g['ads']) for g in spec['groups'])}; "
          f"ставка: {spec.get('bidding', 'maximize_clicks')}; статус после создания: paused")
    if errors:
        sys.exit("ОСТАНОВКА:\n  - " + "\n  - ".join(errors))
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    created = []
    for g in spec["groups"]:
        body = {"campaign_id": camp, "name": g["group"], "status": "paused", "context_hints": g["context_hints"],
                "bidding_config": {"strategy": spec.get("bidding", "maximize_clicks"), "billing_event_type": "click"},
                "landing_page_configuration": {"query_string_template": qs}}
        import hashlib
        idem_g = "ldv-" + hashlib.sha1((camp + "|" + g["group"]).encode("utf-8")).hexdigest()[:32]
        gid = call("POST", "/ad_groups", body=body, idem=idem_g)["id"]
        created.append(gid)
        print(f"создана группа {g['group']} {gid}")
        for ad in g["ads"]:
            cr = {"type": "chat_card", "title": ad["title"], "body": ad["copy"], "target_url": ad["link"],
                  "file_id": ad["file_id"], "image_crop": ad.get("image_crop") or {"x": 0, "y": 0, "width": 1, "height": 1}}
            idem_a = "ldv-" + hashlib.sha1((gid + "|" + ad["ad_name"]).encode("utf-8")).hexdigest()[:32]
            aid = call("POST", "/ads", body={"ad_group_id": gid, "name": ad["ad_name"], "creative": cr,
                                             "status": "paused"}, idem=idem_a)["id"]
            print(f"   объявление {ad['ad_name']} {aid}")
    time.sleep(5)  # чтение сразу после записи может отдать старое состояние
    print("\nПрочитано обратно из аккаунта (группы и объявления кампании):")
    groups = {g["id"]: g for g in list_groups(camp)}
    for gid in created:
        g = groups.get(gid)
        print(f"  {g['name'] if g else gid}  {g['status'] if g else 'НЕ НАЙДЕНА'}  {bid_text(g) if g else ''}  "
              f"hints {len(g.get('context_hints') or []) if g else 0}")
    for ad in list_ads(camp):
        if ad["id"] and any(ad.get("_group_name") == g["group"] for g in spec["groups"]):
            print(f"  {ad['_group_name']} | {ad.get('name')} | {ad['status']}/{ad.get('review_status')} | "
                  f"{(ad.get('creative') or {}).get('title')}")


def cmd_activate(a):
    """Включение групп и их объявлений: POST /ad_groups/{id}/activate и /ads/{id}/activate. Берёт только paused;
    объявления — только approved (in_review/rejected пропускаются и печатаются). Без --execute — план."""
    groups = [g for g in list_groups(a.campaign) if g["id"] in set(a.groups)]
    if len(groups) != len(set(a.groups)):
        sys.exit("Часть групп не найдена в кампании: " + ", ".join(sorted(set(a.groups) - {g["id"] for g in groups})))
    ads = [ad for ad in list_ads(a.campaign) if ad.get("_group_name") in {g["name"] for g in groups}]
    print("Объект | Действие | Было → Станет")
    todo_g = [g for g in groups if g["status"] == "paused"]
    for g in groups:
        print(f"группа {g['name']} ({g['id']}) | включить | {g['status']} → "
              f"{'active' if g['status'] == 'paused' else g['status'] + ' (без изменений)'}")
    todo_a, skipped = [], []
    for ad in ads:
        if ad["status"] == "paused" and ad.get("review_status") == "approved":
            todo_a.append(ad)
            print(f"объявление {ad['_group_name']} | {ad.get('name')} ({ad['id']}) | включить | paused/approved → active")
        else:
            skipped.append(ad)
            print(f"объявление {ad['_group_name']} | {ad.get('name')} | ПРОПУСК | {ad['status']}/{ad.get('review_status')}")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    for g in todo_g:
        call("POST", f"/ad_groups/{g['id']}/activate")
    for ad in todo_a:
        call("POST", f"/ads/{ad['id']}/activate")
    time.sleep(5)
    print("\nПрочитано обратно из аккаунта:")
    after_g = {g["id"]: g for g in list_groups(a.campaign)}
    for g in groups:
        print(f"  {after_g[g['id']]['name']}  {after_g[g['id']]['status']}  {bid_text(after_g[g['id']])}")
    names = {g["name"] for g in groups}
    for ad in list_ads(a.campaign):
        if ad.get("_group_name") in names:
            print(f"  {ad['_group_name']} | {ad.get('name')} | {ad['status']}/{ad.get('review_status')}")


def cmd_set_maxclicks(a):
    groups = list_groups(a.campaign)
    if a.groups:
        wanted = set(a.groups)
        groups = [g for g in groups if g["id"] in wanted]
    if not groups:
        sys.exit("Группы не найдены")
    print("Объект | Действие | Было → Станет")
    for g in groups:
        print(f"{g['name']} ({g['id']}) | тип ставки | {bid_text(g)} → maximize_clicks (без ставки)")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute).")
        return
    for g in groups:
        call("POST", f"/ad_groups/{g['id']}", body={"bidding_config": {
            "strategy": "maximize_clicks", "billing_event_type": "click"}})
    print("\nПрочитано обратно из аккаунта:")
    after = {g["id"]: g for g in list_groups(a.campaign)}
    for g in groups:
        print(f"{after[g['id']]['name']}  {after[g['id']]['status']}  {bid_text(after[g['id']])}")


def list_ads(campaign):
    """Объявления всех групп кампании (фильтр campaign_id на /ads не срабатывает — идём по группам)."""
    out = []
    for g in list_groups(campaign):
        for ad in call("GET", "/ads", [("ad_group_id", g["id"])]).get("data", []):
            ad["_group_name"] = g["name"]
            out.append(ad)
    return out


def crop_text(cr):
    c = cr.get("image_crop") or {}
    return f"x{c.get('x', 0):.2f} y{c.get('y', 0):.2f} w{c.get('width', 1):.2f} h{c.get('height', 1):.2f}"


def cmd_ads(a):
    for ad in list_ads(a.campaign):
        cr = ad.get("creative", {})
        print(f"{ad['id']}  {ad['_group_name']}  {ad['status']}/{ad.get('review_status')}  "
              f"{ad.get('name')} | {cr.get('title')} | {cr.get('file_id')} | {crop_text(cr)}")


def upload_image(path):
    """POST /upload (multipart). Путь копируется под ASCII-имя: curl на Windows путается в кириллице."""
    import shutil
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "oai_ads_upload_" + str(int(time.time() * 1000)) + os.path.splitext(path)[1])
    shutil.copyfile(path, tmp)
    try:
        cmd = ["curl", "-sS", "-X", "POST", "-w", "\n%{http_code}", "-H", f"Authorization: Bearer {get_key()}",
               "-F", f"file=@{tmp}", BASE + "/upload"]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        text, _, code = res.stdout.rpartition("\n")
    finally:
        os.remove(tmp)
    if not code.startswith("2"):
        sys.exit(f"HTTP {code} POST /upload: {text[:500]}")
    data = json.loads(text)
    fid = data.get("file_id") or data.get("id") or (data.get("data") or {}).get("file_id")
    if not fid:
        sys.exit(f"В ответе /upload нет file_id: {text[:300]}")
    return fid


def cmd_set_image(a):
    """Замена картинки у объявлений. Файл соответствий: JSON {"ad_id": "путь к файлу от корня вики"}.
    Остальные поля creative берутся из текущего объявления без изменений; картинка кадрируется
    целиком (квадрат 1:1). Снимок «до» пишется в Клиенты/<клиент>/Статистика при --execute."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mapping = json.load(open(a.map, encoding="utf-8"))
    ads = {ad["id"]: ad for ad in list_ads(a.campaign)}
    unknown = [k for k in mapping if k not in ads]
    if unknown:
        sys.exit(f"Объявления не найдены в кампании: {unknown}")
    only = set(a.only) if a.only else set(mapping)
    todo = [(ads[k], os.path.join(root, v)) for k, v in mapping.items() if k in only]
    for ad, path in todo:
        if not os.path.exists(path):
            sys.exit(f"Нет файла {path}")
    print("Объект | Действие | Было → Станет")
    for ad, path in todo:
        cr = ad["creative"]
        print(f"{ad['name']} ({ad['id']}, {ad['_group_name']}, {ad['status']}/{ad.get('review_status')}) | картинка | "
              f"{cr.get('file_id')} {crop_text(cr)} → {os.path.basename(path)} (целиком 1:1)")
    if not a.execute:
        print("\nПлан. Записи не было (добавьте --execute). Текст, ссылка и статус объявлений не меняются.")
        return
    snap_dir = os.path.join(root, "Клиенты", a.client_folder, "Статистика")
    os.makedirs(snap_dir, exist_ok=True)
    snap = os.path.join(snap_dir, f"openai_ads_creatives_before_{time.strftime('%Y%m%d_%H%M')}.json")
    json.dump([{k: v for k, v in ad.items() if k != "_group_name"} for ad in ads.values()],
              open(snap, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nСнимок «до»: {snap}")
    for ad, path in todo:
        cr = ad["creative"]
        fid = upload_image(path)
        new = {"type": cr["type"], "title": cr["title"], "body": cr["body"], "target_url": cr["target_url"],
               "file_id": fid, "image_crop": {"x": 0, "y": 0, "width": 1, "height": 1}}
        if cr.get("price"):
            new["price"] = cr["price"]
        call("POST", f"/ads/{ad['id']}", body={"creative": new})
        print(f"записано: {ad['name']} → {fid}")
    time.sleep(3)
    print("\nПрочитано обратно из аккаунта:")
    for ad, _ in todo:
        # прямое чтение объявления: сразу после записи список по группе мог не отдать объявление (13.10 — CT-L2)
        x = call("GET", f"/ads/{ad['id']}")
        cr = x["creative"]
        print(f"{x['name']}  {x['status']}/{x.get('review_status')}  {cr.get('title')} | {cr.get('file_id')} | {crop_text(cr)}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("groups"); g.add_argument("--campaign", required=True); g.set_defaults(f=cmd_groups)
    i = sub.add_parser("insights"); i.add_argument("--campaign", required=True)
    i.add_argument("--since", required=True); i.add_argument("--until", required=True)
    i.add_argument("--level", default="ad_group", choices=["campaign", "ad_group", "ad"])
    i.add_argument("--granularity", default="none", choices=["none", "daily", "hourly", "monthly"])
    i.set_defaults(f=cmd_insights)
    s = sub.add_parser("set-bid"); s.add_argument("--campaign", required=True)
    s.add_argument("--bid", required=True, type=float, help="ставка в долларах")
    s.add_argument("--groups", nargs="*", help="ID групп; по умолчанию все группы кампании")
    s.add_argument("--execute", action="store_true"); s.set_defaults(f=cmd_set_bid)
    m = sub.add_parser("set-maxclicks"); m.add_argument("--campaign", required=True)
    m.add_argument("--groups", nargs="*", help="ID групп; по умолчанию все группы кампании")
    m.add_argument("--execute", action="store_true"); m.set_defaults(f=cmd_set_maxclicks)
    d = sub.add_parser("ads"); d.add_argument("--campaign", required=True); d.set_defaults(f=cmd_ads)
    ac = sub.add_parser("activate"); ac.add_argument("--campaign", required=True)
    ac.add_argument("--groups", nargs="+", required=True, help="ID групп (adgrp_…)")
    ac.add_argument("--execute", action="store_true"); ac.set_defaults(f=cmd_activate)
    cg = sub.add_parser("create-groups")
    cg.add_argument("--plan", required=True, help="JSON-план (путь от корня вики или абсолютный)")
    cg.add_argument("--execute", action="store_true"); cg.set_defaults(f=cmd_create_groups)
    im = sub.add_parser("set-image"); im.add_argument("--campaign", required=True)
    im.add_argument("--map", required=True, help="JSON {ad_id: путь к картинке от корня вики}")
    im.add_argument("--only", nargs="*", help="ad_id из файла соответствий; по умолчанию все")
    im.add_argument("--client-folder", default="Andverpersonalinjury", help="куда писать снимок «до»")
    im.add_argument("--execute", action="store_true"); im.set_defaults(f=cmd_set_image)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
