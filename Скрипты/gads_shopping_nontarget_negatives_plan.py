#!/usr/bin/env python
# coding: utf-8
"""План минусации Shopping-кампании в Поиске: «всё, что не содержит целевых размеров, — в минус». ТОЛЬКО ЧТЕНИЕ.

Правило пользователя (EkspertAgro, `shop_search`, 2026-10-13): оставить в кампании только запросы с целевыми размерами
(3x4, 3x6, 2x4, 4x6), остальное минусовать на уровне кампании; на уровне группы — только чужой целевой размер.
Google Ads не умеет «минусовать всё, кроме», поэтому минусуются только запросы, уже попавшие в отчёт.

Что делает:
  1. Читает из кабинета: запросы по группам за период, минусы кампании, минусы групп, подключённые общие списки.
  2. Для каждой пары (группа, запрос) со статусом «не исключён» проверяет по правилам Google (как в
     `gads_negatives_conflicts.py`), не закрыта ли она уже каким-то минусом. Закрытые отбрасывает.
  3. Классифицирует оставшиеся: целевой размер своей группы (оставить), чужой целевой размер (минус на уровне
     группы), размер вне целевых (фразовые минуса всех вариантов написания), без размера (точный минус).
  4. Запросы без размера, но с цифрами («3 на 6», «6mm») автоматом не минусует — кладёт в файл на ручной разбор:
     «3 на 6» — тот же размер по-русски/по-украински, «6mm» — толщина товара.
  5. Проверяет каждого кандидата на конфликт со всеми целевыми запросами из отчёта; конфликтных отбрасывает.
  6. Печатает охват отчёта по запросам относительно отчёта по товарам (скрытая часть трафика).

Результат — CSV в `Статистика/` клиента, которые затем подаются в `gads_shared_negatives_add.py`
(точные → общий список «без размера», фразы → общий список «размеры …»). Записи в кабинет скрипт не делает.

    python gads_shopping_nontarget_negatives_plan.py --customer-id 882-613-4558 --client-folder "EkspertAgro/Мерчант" \
        --campaign shop_search --target-sizes 3x4,3x6,2x4,4x6 --date-from 2026-09-28 [--date-to 2026-10-12]
"""
import argparse
import re
from datetime import date, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir
from gads_negatives_conflicts import blocks, tokens
from gads_shared_negatives_add import INVALID_CHARS, MAX_CHARS, MAX_WORDS
from gads_shopping_size_gap_monitor import extract_size_from_term
from gads_shopping_size_negatives_by_group import generate_negative_phrases
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

# «3 на 6», «4 на 10», «6 * 3» — размер словами/знаком, который parser размера не видит
NA_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:на|na|по|\*)\s*\d+(?:[.,]\d+)?\b", re.I)
MATCH_ORDER = {"EXACT": 0, "PHRASE": 1, "BROAD": 2}


def run(ga, cid, query):
    for batch in ga.search_stream(customer_id=cid, query=query):
        yield from batch.results


def read_negatives(client, ga, cid, campaign):
    """Все минуса, действующие на кампанию: [(уровень, группа, текст, тип)]."""
    mt = client.enums.KeywordMatchTypeEnum.KeywordMatchType
    out = []
    for r in run(ga, cid, f"SELECT campaign_criterion.keyword.text, campaign_criterion.keyword.match_type "
                          f"FROM campaign_criterion WHERE campaign.name = '{campaign}' "
                          f"AND campaign_criterion.type = KEYWORD AND campaign_criterion.negative = TRUE "
                          f"AND campaign_criterion.status != REMOVED"):
        k = r.campaign_criterion.keyword
        out.append(("campaign", "", k.text, mt.Name(k.match_type)))
    for r in run(ga, cid, f"SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
                          f"FROM ad_group_criterion WHERE campaign.name = '{campaign}' "
                          f"AND ad_group_criterion.type = KEYWORD AND ad_group_criterion.negative = TRUE "
                          f"AND ad_group_criterion.status != REMOVED"):
        k = r.ad_group_criterion.keyword
        out.append(("group", r.ad_group.name, k.text, mt.Name(k.match_type)))
    sets = [(r.shared_set.id, r.shared_set.name) for r in run(
        ga, cid, f"SELECT shared_set.id, shared_set.name FROM campaign_shared_set WHERE campaign.name = '{campaign}' "
                 f"AND shared_set.type = NEGATIVE_KEYWORDS AND campaign_shared_set.status = ENABLED")]
    for sid, sname in sets:
        for r in run(ga, cid, f"SELECT shared_criterion.keyword.text, shared_criterion.keyword.match_type "
                              f"FROM shared_criterion WHERE shared_set.id = {sid}"):
            k = r.shared_criterion.keyword
            out.append((f"shared:{sname}", "", k.text, mt.Name(k.match_type)))
    return out, [n for _, n in sets]


def read_terms(client, ga, cid, campaign, date_from, date_to):
    st = client.enums.SearchTermTargetingStatusEnum.SearchTermTargetingStatus
    rows = []
    for r in run(ga, cid, f"SELECT campaign.name, ad_group.name, search_term_view.search_term, search_term_view.status, "
                          f"metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
                          f"FROM search_term_view WHERE campaign.name = '{campaign}' "
                          f"AND segments.date BETWEEN '{date_from}' AND '{date_to}'"):
        m = r.metrics
        rows.append({"ag": r.ad_group.name, "term": r.search_term_view.search_term,
                     "status": st.Name(r.search_term_view.status), "imp": m.impressions, "clk": m.clicks,
                     "cost": m.cost_micros / 1e6, "conv": m.conversions})
    df = pd.DataFrame(rows, columns=["ag", "term", "status", "imp", "clk", "cost", "conv"])
    # один (группа, запрос) может прийти несколькими строками по дням/статусам — складываем
    return df.groupby(["ag", "term", "status"], as_index=False).sum(numeric_only=True)


def read_product_totals(ga, cid, campaign, date_from, date_to):
    t = {"imp": 0, "clk": 0, "cost": 0.0, "conv": 0.0}
    for r in run(ga, cid, f"SELECT campaign.name, metrics.impressions, metrics.clicks, metrics.cost_micros, "
                          f"metrics.conversions FROM shopping_performance_view WHERE campaign.name = '{campaign}' "
                          f"AND segments.date BETWEEN '{date_from}' AND '{date_to}'"):
        m = r.metrics
        t["imp"] += m.impressions
        t["clk"] += m.clicks
        t["cost"] += m.cost_micros / 1e6
        t["conv"] += m.conversions
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer-id", required=True)
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/, напр. "EkspertAgro/Мерчант"')
    ap.add_argument("--campaign", required=True, help="Точное название Shopping-кампании в Поиске")
    ap.add_argument("--target-sizes", required=True, help="Целевые размеры через запятую, в виде AxB: 3x4,3x6,2x4,4x6")
    ap.add_argument("--date-from", help="YYYY-MM-DD; по умолчанию --days назад")
    ap.add_argument("--date-to", help="YYYY-MM-DD; по умолчанию вчера")
    ap.add_argument("--days", type=int, default=15)
    ap.add_argument("--skip-group", action="append", default=[], help="Группа без целевого размера, пропустить (напр. 'all products')")
    args = ap.parse_args()

    cid = args.customer_id.replace("-", "")
    target = {s.strip().lower() for s in args.target_sizes.split(",") if s.strip()}
    date_to = args.date_to or str(date.today() - timedelta(1))
    date_from = args.date_from or str(date.fromisoformat(date_to) - timedelta(args.days - 1))
    safe = re.sub(r"[^\w-]+", "_", args.campaign)
    out_dir = client_stats_dir(args.client_folder)
    tag = f"{safe}_{date_from}_to_{date_to}"

    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = get_ads_service(client.login_customer_id)

    negs, list_names = read_negatives(client, ga, cid, args.campaign)
    print(f"Кампания «{args.campaign}», период {date_from} → {date_to}")
    print(f"Минусов в силе: {len(negs)} (кампания {sum(n[0] == 'campaign' for n in negs)}, "
          f"группы {sum(n[0] == 'group' for n in negs)}, общие списки {sum(n[0].startswith('shared') for n in negs)}; "
          f"списки: {', '.join(list_names)})")
    prepared = [(lvl, ag, tokens(t), m) for lvl, ag, t, m in negs]
    have = {(t.lower(), m) for _, _, t, m in negs}
    have_group = {(ag, t.lower(), m) for lvl, ag, t, m in negs if lvl == "group"}

    terms = read_terms(client, ga, cid, args.campaign, date_from, date_to)
    totals = read_product_totals(ga, cid, args.campaign, date_from, date_to)
    if terms.empty:
        print("Нет данных search_term_view за период.")
        return
    terms = terms[~terms.ag.isin(args.skip_group)]

    print("\n=== Охват отчёта по запросам ===")
    print(f"По товарам:  показы {totals['imp']}, клики {totals['clk']}, расход {totals['cost']:.0f}, конверсии {totals['conv']:.1f}")
    print(f"По запросам: показы {terms.imp.sum()}, клики {terms.clk.sum()}, расход {terms.cost.sum():.0f}, "
          f"конверсии {terms.conv.sum():.1f}  → видно около {100 * terms.clk.sum() / max(totals['clk'], 1):.0f}% кликов; "
          f"остальное скрыто порогом приватности Google и точными минусами не закрывается")

    terms["size"] = terms.term.apply(extract_size_from_term)
    terms["has_digit"] = terms.term.str.contains(r"\d")
    terms["na_form"] = terms.term.apply(lambda t: bool(NA_RE.search(t)))

    def is_blocked(r):
        qt = tokens(r.term)
        return any((lvl != "group" or ag == r.ag) and blocks(nt, m, qt) for lvl, ag, nt, m in prepared)

    open_df = terms[terms.status == "NONE"].copy()
    open_df["blocked"] = open_df.apply(is_blocked, axis=1)
    print(f"\nПар (группа, запрос) со статусом «не исключён»: {len(open_df)}; из них уже закрыты минусом: "
          f"{int(open_df.blocked.sum())} (показы {open_df[open_df.blocked].imp.sum()}, клики {open_df[open_df.blocked].clk.sum()})")
    open_df = open_df[~open_df.blocked]

    def kind(r):
        if r["size"] is None or pd.isna(r["size"]):
            return "no_size"
        if r["size"] not in target:
            return "other_size"
        return "own_target" if r["size"] == r.ag.lower() else "foreign_target"

    open_df["kind"] = open_df.apply(kind, axis=1)
    good_terms = terms[terms["size"].isin(target) & (terms["size"] == terms.ag.str.lower())].term.unique()
    good_tokens = [tokens(t) for t in good_terms]

    print("\n=== Незакрытое по типам (уникальных запросов / показы / клики / расход) ===")
    summ = open_df.groupby("kind").agg(terms=("term", "nunique"), imp=("imp", "sum"), clk=("clk", "sum"), cost=("cost", "sum"))
    print(summ.to_string())

    def conflicts(phrase, match):
        pt = tokens(phrase)
        return any(blocks(pt, match, gt) for gt in good_tokens)

    # 1. точные минуса запросов без размера (без цифр)
    ns = open_df[open_df.kind == "no_size"]
    review = ns[ns.has_digit | ns.na_form]
    exact = sorted({t.lower() for t in ns[~(ns.has_digit | ns.na_form)].term})
    exact = [t for t in exact if (t, "EXACT") not in have and len(t) <= MAX_CHARS and len(t.split()) <= MAX_WORDS
             and not (INVALID_CHARS & set(t)) and not conflicts(t, "EXACT")]

    # 2. фразы для размеров вне целевых — на уровне кампании (общий список)
    phrases, skipped_chars = [], 0
    for sz in sorted(open_df[open_df.kind == "other_size"]["size"].unique()):
        for ph in generate_negative_phrases(sz):
            if INVALID_CHARS & set(ph):
                skipped_chars += 1
                continue
            if (ph.lower(), "PHRASE") in have or conflicts(ph, "PHRASE"):
                continue
            phrases.append({"size": sz, "phrase": ph})

    # 3. чужой целевой размер — минус на уровне группы
    group_rows = []
    for _, r in open_df[open_df.kind == "foreign_target"].drop_duplicates(["ag", "size"]).iterrows():
        for ph in generate_negative_phrases(r["size"]):
            if INVALID_CHARS & set(ph) or (r.ag, ph.lower(), "PHRASE") in have_group:
                continue
            group_rows.append({"ad_group": r.ag, "size": r["size"], "phrase": ph})

    f_exact = out_dir / f"shop_nontarget_exact_{tag}.csv"
    f_phr = out_dir / f"shop_nontarget_size_phrases_{tag}.csv"
    f_grp = out_dir / f"shop_nontarget_group_phrases_{tag}.csv"
    f_rev = out_dir / f"shop_nontarget_review_{tag}.csv"
    pd.DataFrame({"term": exact}).to_csv(f_exact, index=False, encoding="utf-8-sig")
    pd.DataFrame(phrases, columns=["size", "phrase"]).to_csv(f_phr, index=False, encoding="utf-8-sig")
    pd.DataFrame(group_rows, columns=["ad_group", "size", "phrase"]).to_csv(f_grp, index=False, encoding="utf-8-sig")
    review.sort_values("imp", ascending=False)[["ag", "term", "imp", "clk", "cost", "na_form"]].to_csv(f_rev, index=False, encoding="utf-8-sig")

    print("\n=== Результат ===")
    print(f"Точных минусов без размера (в общий список «без размера»): {len(exact)}  → {f_exact}")
    print(f"Фразовых минусов на размеры вне целевых (в общий список «размеры»): {len(phrases)} "
          f"по {len({p['size'] for p in phrases})} размерам; отброшено из-за запятой и др. символов: {skipped_chars}  → {f_phr}")
    print(f"Фразовых минусов на уровне групп (чужой целевой размер): {len(group_rows)}  → {f_grp}")
    print(f"На ручной разбор (без размера, но с цифрами/«N на M»): {review.term.nunique()}  → {f_rev}")
    print("\nДальше: после согласования — gads_shared_negatives_add.py --csv <файл> --column term|phrase --match EXACT|PHRASE "
          "(сначала без --execute). Минусы уровня группы пишутся отдельно, скрипта для них пока нет.")


if __name__ == "__main__":
    main()
