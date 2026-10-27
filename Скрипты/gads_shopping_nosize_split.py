#!/usr/bin/env python
# coding: utf-8
"""Shopping: разбор общих списков минусов «без размера» на «оставить закрытым» и «выпустить» — ТОЛЬКО ЧТЕНИЕ.

Задача (EkspertAgro, тест «весь фид без аксессуаров», вариант C, 2026-10-27): новая кампания не подключает списки «Shop - запросы
без размера 1/2», но мусор из них должен остаться закрытым. Скрипт берёт запросы этих списков (Google Ads API, по имени списка),
отбрасывает те, что уже закрывает любой другой подключаемый список (по правилам широкого/фразового/точного соответствия минусов),
остальные раскладывает по содержанию (не по результатам — иначе будет подгонка под историю):
  keep_junk      — есть признак мусора: кириллица, чужой язык, б/у и площадки, «сделай сам»/инструкции, фольга, не теплица (ганек, беседка…);
  keep_no_product — нет корня нашего товара (szklarni*, tunel*, namiot*, cieplarni*);
  keep_sheet     — только «поликарбонат» без теплицы/туннеля (листы не в тестовой выдаче: аксессуары исключены);
  release        — товарный корень и нет признаков мусора: выпускаются в тест.
История (отчёт по запросам CSV) используется только для печати итогов по группам: клики, расход, конверсии Ads.
Записывает CSV в Статистика клиента: `nosize_<bucket>_<дата>.csv`. В кабинет ничего не пишет; список мусора в новый общий список
вносится отдельно `gads_shared_negatives_add.py` (после «да»).

Использование (из папки Скрипты, PYTHONUTF8=1, без -I):
    python gads_shopping_nosize_split.py --customer-id 882-613-4558 --client-folder "EkspertAgro/Мерчант" \
        --split-lists "Shop - запросы без размера 1,Shop - запросы без размера 2" \
        --other-lists "Общий,Из запросов,folia,размеры - есть в запросах, нет в фиде" \
        --history "Клиенты/EkspertAgro/Мерчант/Статистика/shopping_searchterms_all_2025-09-24_to_2026-09-23.csv"
Ограничения: классификация по регулярным выражениям, грубая; широкие слова в «Общий»/«Из запросов» сверяются по токенам без
морфологии; в списках «Общий»/«Из запросов» кириллица и чужие языки могут быть закрыты только частично; отчёт запросов — это только
видимые запросы (по `shop_search` около 31% кликов).
"""
import argparse
import collections
import datetime
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from google.ads.googleads.client import GoogleAdsClient  # noqa: E402
from ea_sales_by_campaign import GOOGLE_ADS_YAML  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

PRODUCT = re.compile(r"szklarn|tunel|namiot|cieplarn", re.I)
SHEET = re.compile(r"poliw[ęe]glan|poliwe|polikarbon|poliw", re.I)
JUNK = [
    ("кириллица", re.compile(r"[Ѐ-ӿ]")),
    ("чужой язык", re.compile(
        r"\b(greenhouses?|garden|house|how|make|best|kit|buy|price|polycarbonate|tunnels?|hoop|plastic|small|cheap|for|the|and|with|"
        r"gew[aä]chshaus|gewaechshaus|garten|tunnelbogen|folientunnel|skleník|sklenik\w*|zahradn\w*|záhrad\w*|serra|jardin|invernadero)\b", re.I)),
    ("б/у, площадки", re.compile(r"u[żz]ywan|olx|allegro|ebay|ogłoszen|ogloszen|gratka|wynajem|wypo[żz]ycz", re.I)),
    ("сделай сам / инструкции", re.compile(
        r"\bjak\b|zr[óo]b|samodziel|\bdiy\b|instrukcj|projekt|rysunek|schemat|\bpdf\b|w[łl]asnymi|z palet|z okien|ze star|"
        r"jakie|dlaczego|co to|czym|po co|kiedy|czy ", re.I)),
    ("фольга", re.compile(r"foli", re.I)),
    ("не теплица", re.compile(r"ganek|wiata|altan|pergol|zadaszen|gara[żz]|carport|basen|piwnic|palm|kwiaciarn|grill|namiot imprez|"
                              r"namiot handlow|namiot ogrodowy imprez|namiot party", re.I)),
]


def tok(s):
    return re.findall(r"[\w'’]+", s.lower())


def blocks(neg, mt, q):
    nt, qt = tok(neg), tok(q)
    if not nt:
        return False
    if mt == 4:      # BROAD
        return all(t in qt for t in nt)
    if mt == 3:      # PHRASE
        n = len(nt)
        return any(qt[i:i + n] == nt for i in range(len(qt) - n + 1))
    return nt == qt  # EXACT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id", default="882-613-4558")
    ap.add_argument("--client-folder", default="EkspertAgro/Мерчант")
    ap.add_argument("--split-lists", required=True, help="имена списков «без размера», через запятую внутри кавычек")
    ap.add_argument("--other-lists", required=True, help="остальные подключаемые списки, разделитель — ПОДСТРОКА ';' если в имени есть запятая")
    ap.add_argument("--history", required=True, help="CSV отчёта запросов (term, clicks, cost, conversions, ...)")
    a = ap.parse_args()
    cid = a.customer_id.replace("-", "")
    ga = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).get_service("GoogleAdsService")

    sets = {}
    for b in ga.search_stream(customer_id=cid, query="SELECT shared_set.id, shared_set.name FROM shared_set WHERE shared_set.status = ENABLED"):
        for r in b.results:
            sets[r.shared_set.name] = r.shared_set.id

    def members(name):
        if name not in sets:
            sys.exit(f"список не найден: {name}")
        q = (f"SELECT shared_criterion.keyword.text, shared_criterion.keyword.match_type FROM shared_criterion "
             f"WHERE shared_set.id = {sets[name]}")
        return [(r.shared_criterion.keyword.text, int(r.shared_criterion.keyword.match_type)) for b in ga.search_stream(customer_id=cid, query=q)
                for r in b.results]

    split_names = [x.strip() for x in a.split_lists.split(",")]
    other_names = [x.strip() for x in re.split(r";|,(?=\s*(?:Общий|Из|folia|размеры|Shop))", a.other_lists) if x.strip()]
    terms = sorted({t.lower() for n in split_names for t, _ in members(n)})
    other = [(t, m) for n in other_names for t, m in members(n)]
    idx = collections.defaultdict(list)
    for t, m in other:
        k = tok(t)
        if k:
            idx[k[0]].append((t, m))

    def covered(q):
        for tk in set(tok(q)):
            for t, m in idx.get(tk, []):
                if blocks(t, m, q):
                    return t
        return None

    rows = []
    for q in terms:
        c = covered(q)
        if c:
            bucket, why = "covered_other", c
        else:
            why = ""
            bucket = None
            for name, rx in JUNK:
                if rx.search(q):
                    bucket, why = "keep_junk", name
                    break
            if bucket is None:
                if PRODUCT.search(q):
                    bucket = "release"
                elif SHEET.search(q):
                    bucket = "keep_sheet"
                else:
                    bucket = "keep_no_product"
        rows.append((q, bucket, why))
    df = pd.DataFrame(rows, columns=["term", "bucket", "why"])
    h = pd.read_csv(ROOT / a.history if not Path(a.history).is_absolute() else a.history)
    h["term"] = h["term"].astype(str).str.lower()
    g = h.groupby("term")[["impressions", "clicks", "cost", "conversions"]].sum()
    df = df.merge(g, left_on="term", right_index=True, how="left").fillna(0)

    out_dir = ROOT / "Клиенты" / a.client_folder / "Статистика"
    stamp = datetime.date.today().isoformat()
    print(f"запросов в списках «без размера»: {len(df)}; списков для сверки: {len(other_names)} ({len(other)} минусов)")
    s = df.groupby("bucket").agg(запросов=("term", "count"), клики=("clicks", "sum"), расход=("cost", "sum"), конв_Ads=("conversions", "sum"))
    s["zl/конв"] = (s["расход"] / s["конв_Ads"]).replace(float("inf"), float("nan")).round(0)
    print(s.round(1).to_string())
    for b, x in df.groupby("bucket"):
        x.sort_values(["conversions", "clicks"], ascending=False).to_csv(out_dir / f"nosize_{b}_{stamp}.csv", index=False, encoding="utf-8-sig")
    print(f"CSV записаны в {out_dir}")
    r = df[df["bucket"] == "release"].sort_values("clicks", ascending=False)
    print("\nrelease — топ-25 по кликам:")
    print(r.head(25)[["term", "clicks", "cost", "conversions"]].round(1).to_string(index=False))
    j = df[df["bucket"] == "keep_junk"]
    print("\nkeep_junk — причины:", dict(collections.Counter(j["why"])))
    print("\nkeep_junk — примеры с конверсиями Ads > 0 (проверить, не режем ли хорошее):")
    print(j[j["conversions"] > 0].sort_values("conversions", ascending=False).head(15)[["term", "why", "clicks", "cost", "conversions"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
