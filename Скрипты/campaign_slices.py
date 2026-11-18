#!/usr/bin/env python
# coding: utf-8
"""Все срезы кампании за точные даты окна одним заходом (Search и Performance Max).

Зачем: «Алгоритм_анализа_кампании.md» (База_знаний/Агенты/), раздел «Срезы кампании». Раньше группы, устройства, часы,
дни недели брались недельными выгрузками (gads_bayesian_*, gads_position_hours.py) и разным ручным кодом. Здесь - один
скрипт: точные даты, исключённые дни, общий формат таблиц, интервалы Гарвуда у цены конверсии, пометка «расход без
конверсий», сверка итога среза с итогом кампании, потеря показов по дням, заявки по нашему счёту там, где их можно привязать.

Только ЧТЕНИЕ: Google Ads (GAQL), Ringostat и Supabase через leads_standard.month_leads. Ничего не пишет во внешние
системы (флага --execute нет и не нужно); пишет только markdown и CSV в --out-dir. Кампании с префиксом yt_
(YouTube - отдельный проект) отклоняются.

Срезы (--slices, по умолчанию все; имена через запятую):
  group     группы объявлений (статус, потолок ставки, доли показов)     [Search]
  keyword   ключи + тип соответствия (доли показов)                      [Search]
  term      поисковые запросы (search_term_view)                         [Search]
  device    устройства
  geo       регионы (segments.geo_target_region)
  hour      час суток (+ звонки по нашему счёту: у форм Supabase времени суток нет)
  dow       день недели (+ заявки по нашему счёту)
  gender    пол (gender_view)                                            [Search]
  age       возраст (age_range_view)                                     [Search]
  network   сеть / канал (ad_network_type: Search / Search Partners; у PMax - каналы)
  ad        объявления RSA                                               [Search]
  asset     ассеты RSA (ad_group_ad_asset_view, ярлык эффективности)     [Search]
  landing   посадочные страницы (landing_page_view)
  audience  аудитории (наблюдение, campaign_/ad_group_audience_view)
  assetgroup группы ресурсов                                             [PMax]
  isday     потеря показов по бюджету и рейтингу по дням (campaign x date) [Search]
Чего API не отдаёт для типа кампании - пишется «нет в данных», скрипт не падает. Список в конце файла.

Колонки таблиц: показы, клики, CTR, цена клика, расход, доля расхода, конверсии кабинета, цена конверсии
(расход/конверсии) с интервалами Гарвуда 80 и 95 % (расход считается фиксированным), пометка. Пометки:
  РАСХОД БЕЗ КОНВ. - 0 конверсий и расход >= 2 x --target-cpa-high;
  дешевле / дороже допустимой (80 % или 95 %) - весь интервал цены конверсии ниже --target-cpa-low / выше --target-cpa-high.
Внизу каждой таблицы строка «итого» и сверка с итогом кампании за те же дни. Пометка - сигнал к проверке, не вывод
(при просмотре многих срезов уровень 80 % даёт ложные находки; см. алгоритм, раздел 4).

Заявки по нашему счёту (Ringostat + Supabase, как campaign_window_breakdown.py): привязываются к срезу «день недели» и (звонки)
«час»; к группам, ключам, запросам, посадочным, устройствам, полу и возрасту привязать нельзя (в метках заявок нет этого
признака; время суток у форм не хранится) - там остаются конверсии кабинета.

Окно: --from/--to точные даты. --exclude-days: даты через запятую; --basis clean (по умолчанию, если исключённые заданы)
считает срезы без этих дней, --basis all - по всем дням. Сравнение: --compare-from/--compare-to - второй период (без
исключений), в таблицах колонки «сравнение».

Запуск (из папки Скрипты):
  PYTHONUTF8=1 python campaign_slices.py --customer-id 7552781705 --campaign-id 19158580966 \\
      --from 2026-10-19 --to 2026-11-12 --exclude-days 2026-10-28,2026-10-29,2026-11-05 \\
      --compare-from 2026-09-21 --compare-to 2026-10-18 --client-folder ProfiMet \\
      --out-dir "../Клиенты/ProfiMet/Работы/2026-11-16_campaign_analysis"
  (вместо --campaign-id можно --campaign "Search | Poliweglan | Pl"; --slices device,dow,hour; --top 40)

Дата создания: 2026-11-16.
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

LEVELS = (0.80, 0.95)
ALL_SLICES = ["isday", "group", "keyword", "term", "device", "geo", "hour", "dow", "gender", "age", "network",
              "ad", "asset", "landing", "audience", "assetgroup"]
SEARCH_ONLY = {"group", "keyword", "term", "gender", "age", "ad", "asset", "isday"}
PMAX_ONLY = {"assetgroup"}
DOW_ORDER = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
DOW_RU = dict(zip(DOW_ORDER, ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]))
NODATA = []   # (срез, причина) - выводится в конце


# ---------- статистика ----------
def garwood(k, cl):
    a = (1 - cl) / 2
    lo = 0.0 if k <= 0 else stats.gamma.ppf(a, k)
    hi = stats.gamma.ppf(1 - a, k + 1)
    return lo, hi


def cpa_interval(cost, k, cl):
    lo, hi = garwood(k, cl)
    return cost / hi, (cost / lo if lo > 0 else float("inf"))


# ---------- GAQL ----------
_ENUM_CLIENT = None


def en(v, enum_type=None):
    """Имя значения enum Google Ads (API-клиент отдаёт int). Не получилось - строка числа."""
    global _ENUM_CLIENT
    if hasattr(v, "name"):
        return v.name
    if enum_type:
        try:
            from google.ads.googleads.client import GoogleAdsClient
            from gads_stats import GOOGLE_ADS_YAML
            if _ENUM_CLIENT is None:
                _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
            msg = getattr(_ENUM_CLIENT.enums, enum_type)
            et = msg.DESCRIPTOR.enum_types_by_name
            et = et.get(enum_type[:-4]) or list(et.values())[0]
            return et.values_by_number[int(v)].name
        except Exception:  # noqa: BLE001
            pass
    return str(v)


def q_rows(ga, cid, query):
    for b in ga.search_stream(customer_id=cid, query=query):
        for r in b.results:
            yield r


def contiguous_ranges(days):
    days = sorted(days)
    out = []
    for d in days:
        if out and d - out[-1][1] == timedelta(days=1):
            out[-1][1] = d
        else:
            out.append([d, d])
    return [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) for a, b in out]


def resolve_campaign(ga, cid, campaign_id, campaign_name):
    where = f"campaign.id = {int(campaign_id)}" if campaign_id else "campaign.name = '%s'" % campaign_name.replace("'", "\\'")
    q = f"SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type FROM campaign WHERE {where}"
    rows = list(q_rows(ga, cid, q))
    if not rows:
        raise SystemExit("Кампания не найдена в аккаунте %s" % cid)
    r = rows[0]
    return {"id": str(r.campaign.id), "name": r.campaign.name, "status": en(r.campaign.status, "CampaignStatusEnum"),
            "channel": en(r.campaign.advertising_channel_type, "AdvertisingChannelTypeEnum")}


IS_LEVELS = [
    ["search_impression_share", "search_rank_lost_impression_share", "search_budget_lost_impression_share"],
    ["search_impression_share", "search_rank_lost_impression_share"],
    [],
]


def fetch(ga, cid, camp_id, ranges, sel, from_, keyfn, where_extra="", want_is=False):
    """Выгрузка среза по диапазонам дат. keyfn(row) -> (ключ-словарь, атрибуты-словарь).
    Возвращает DataFrame: ключи, атрибуты, imp, clk, cost, conv и (если есть) доли показов, взвешенные по показам."""
    last_err = None
    for lvl in (IS_LEVELS if want_is else [[]]):
        sel_is = "".join(", metrics." + m for m in lvl)
        recs = []
        try:
            for a, b in ranges:
                q = (f"SELECT campaign.id, {', '.join(sel)}, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions{sel_is} "
                     f"FROM {from_} WHERE campaign.id = {int(camp_id)} AND segments.date BETWEEN '{a}' AND '{b}' {where_extra}")
                for r in q_rows(ga, cid, q):
                    k, at = keyfn(r)
                    d = dict(k)
                    d.update({"_a_" + x: y for x, y in at.items()})
                    imp = int(r.metrics.impressions)
                    if imp == 0 and r.metrics.cost_micros == 0 and r.metrics.conversions == 0:
                        continue
                    d.update(imp=imp, clk=int(r.metrics.clicks), cost=r.metrics.cost_micros / 1e6, conv=float(r.metrics.conversions))
                    for m in lvl:
                        d["_w_" + m] = float(getattr(r.metrics, m)) * imp
                    recs.append(d)
        except Exception as e:  # noqa: BLE001 - пробуем набор метрик поменьше
            last_err = e
            continue
        keys = [c for c in (recs[0] if recs else {}) if not c.startswith(("_a_", "_w_")) and c not in ("imp", "clk", "cost", "conv")]
        if not recs:
            return pd.DataFrame(), lvl
        df = pd.DataFrame(recs)
        agg = {c: "sum" for c in df.columns if c in ("imp", "clk", "cost", "conv") or c.startswith("_w_")}
        agg.update({c: "first" for c in df.columns if c.startswith("_a_")})
        df = df.groupby(keys, dropna=False, as_index=False).agg(agg)
        for m in lvl:
            df["is_" + m] = np.where(df.imp > 0, df["_w_" + m] / df.imp.replace(0, np.nan), np.nan)
        return df, lvl
    raise last_err


# ---------- форматирование ----------
def fi(x):
    return f"{int(x):,}".replace(",", " ")


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return out


def rng(lo, hi):
    return f"{lo:.1f}-{('inf' if hi == float('inf') else f'{hi:.1f}')}"


def cpa_cells(cost, k):
    """(цена, интервал 80, интервал 95) строками."""
    if k <= 0:
        lo80, _ = cpa_interval(cost, 0, 0.80)
        lo95, _ = cpa_interval(cost, 0, 0.95)
        return "-", f"от {lo80:.1f}", f"от {lo95:.1f}"
    return f"{cost / k:.1f}", rng(*cpa_interval(cost, k, 0.80)), rng(*cpa_interval(cost, k, 0.95))


def mark(cost, k, cpa_lo, cpa_hi):
    if k <= 0:
        return "РАСХОД БЕЗ КОНВ." if cost >= 2 * cpa_hi else ""
    out = []
    for cl in (0.95, 0.80):
        lo, hi = cpa_interval(cost, k, cl)
        if hi < cpa_lo:
            out.append(f"дешевле допустимой ({int(cl * 100)} %)")
            break
        if lo > cpa_hi:
            out.append(f"дороже допустимой ({int(cl * 100)} %)")
            break
    return "; ".join(out)


def render_slice(title, df, keycols, keyheads, tot, cpa_lo, cpa_hi, top, comp=None, attrs=(), is_cols=False,
                 leads=None, keysort=None, note=None, csv_dir=None, fname=None, order=None):
    """df: срез; tot: dict итог кампании за те же дни (imp, clk, cost, conv); comp: (df_сравнения, подпись) или None;
    leads: dict ключ->число заявок по нашему счёту (или None)."""
    out = [f"### {title}", ""]
    if df is None or df.empty:
        return out + ["Нет в данных: строк нет за окно.", ""], None
    df = df.copy()
    df["_key"] = list(zip(*[df[c] for c in keycols])) if len(keycols) > 1 else df[keycols[0]]
    if order:
        df["_o"] = df[keycols[0]].map({v: i for i, v in enumerate(order)}).fillna(99)
        df = df.sort_values("_o")
    elif keysort:
        df = df.sort_values(keysort)
    else:
        df = df.sort_values("cost", ascending=False)
    rows, flagged = [], 0
    comp_map = None
    if comp is not None and comp[0] is not None and not comp[0].empty:
        c = comp[0].copy()
        c["_key"] = list(zip(*[c[x] for x in keycols])) if len(keycols) > 1 else c[keycols[0]]
        comp_map = {k_: g_ for k_, g_ in c.groupby("_key", sort=False).agg({"clk": "sum", "cost": "sum", "conv": "sum"}).iterrows()}
    heads = list(keyheads) + [h.replace("_a_", "") for h in attrs]
    heads += ["Показы", "Клики", "CTR %", "Цена клика", "Расход", "Доля расх.", "Конв.", "Цена конв.", "80 %", "95 %"]
    if is_cols:
        heads += ["Доля показов", "Потеря рейтинг", "Потеря бюджет"]
    if leads is not None:
        heads += ["Заявки (наш счёт)", "Цена заявки", "80 %", "95 %"]
    if comp_map is not None:
        heads += [f"{comp[1]}: клики", "расход", "конв.", "цена конв."]
    heads += ["Пометка"]
    csvrows = []
    n_shown = 0
    for i, (_, r) in enumerate(df.iterrows()):
        m = mark(r.cost, r.conv, cpa_lo, cpa_hi)
        if m:
            flagged += 1
        if top and i >= top and not m and keysort is None and not order:
            continue
        n_shown += 1
        keyvals = [str(int(r[c])) if isinstance(r[c], (float, np.floating)) and float(r[c]).is_integer() else str(r[c]) for c in keycols]
        row = list(keyvals) + [str(r[a]) if pd.notna(r[a]) else "" for a in attrs]
        pr, i80, i95 = cpa_cells(r.cost, r.conv)
        row += [fi(r.imp), fi(r.clk), f"{r.clk / r.imp * 100:.2f}" if r.imp else "-", f"{r.cost / r.clk:.2f}" if r.clk else "-",
                f"{r.cost:.2f}", f"{r.cost / tot['cost'] * 100:.1f} %" if tot["cost"] else "-", f"{r.conv:.1f}", pr, i80, i95]
        if is_cols:
            for m_ in ("search_impression_share", "search_rank_lost_impression_share", "search_budget_lost_impression_share"):
                v = r.get("is_" + m_, np.nan)
                row.append("нет в данных" if pd.isna(v) else f"{v * 100:.0f} %")
        if leads is not None:
            nl = leads.get(r["_key"], 0)
            if nl > 0:
                lp = f"{r.cost / nl:.1f}"
                l80, l95 = rng(*cpa_interval(r.cost, nl, 0.80)), rng(*cpa_interval(r.cost, nl, 0.95))
            else:
                lp, l80, l95 = "-", f"от {cpa_interval(r.cost, 0, 0.80)[0]:.1f}", f"от {cpa_interval(r.cost, 0, 0.95)[0]:.1f}"
            row += [str(nl), lp, l80, l95]
        if comp_map is not None:
            if r["_key"] in comp_map:
                cr = comp_map[r["_key"]]
                row += [fi(cr.clk), f"{cr.cost:.2f}", f"{cr.conv:.1f}", f"{cr.cost / cr.conv:.1f}" if cr.conv > 0 else "-"]
            else:
                row += ["-", "-", "-", "-"]
        row += [m]
        rows.append(row)
        csvrows.append(row)
    s = {"imp": int(df.imp.sum()), "clk": int(df.clk.sum()), "cost": float(df.cost.sum()), "conv": float(df.conv.sum())}
    pr, i80, i95 = cpa_cells(s["cost"], s["conv"])
    trow = ["ИТОГО (все строки среза)"] + [""] * (len(keycols) - 1) + [""] * len(attrs) + [
        fi(s["imp"]), fi(s["clk"]), f"{s['clk'] / s['imp'] * 100:.2f}" if s["imp"] else "-", f"{s['cost'] / s['clk']:.2f}" if s["clk"] else "-",
        f"{s['cost']:.2f}", f"{s['cost'] / tot['cost'] * 100:.1f} %" if tot["cost"] else "-", f"{s['conv']:.1f}", pr, i80, i95]
    extra = len(heads) - len(trow) - 1
    trow += [""] * max(extra, 0) + [""]
    rows.append(trow)
    out += md_table(heads, rows)
    out.append("")
    d_imp, d_clk, d_cost, d_conv = s["imp"] - tot["imp"], s["clk"] - tot["clk"], s["cost"] - tot["cost"], s["conv"] - tot["conv"]
    ok = abs(d_cost) < 0.05 and d_clk == 0 and d_imp == 0
    out.append(f"Сверка с итогом кампании за те же дни (показы {fi(tot['imp'])}, клики {fi(tot['clk'])}, расход {tot['cost']:.2f}, конв. {tot['conv']:.1f}): "
               f"{'сходится' if ok else f'расхождение показы {d_imp:+d}, клики {d_clk:+d}, расход {d_cost:+.2f}, конв. {d_conv:+.1f} (срез отдаёт не все строки или иначе считает)'}.")
    if len(df) > n_shown:
        out.append(f"Показано {n_shown} из {len(df)} строк (топ по расходу + все с пометкой); полная таблица - в CSV.")
    out.append(f"Строк с пометкой: {flagged}. Конверсии - кабинет (не заявки по нашему счёту).")
    if note:
        out.append(note)
    out.append("")
    if csv_dir is not None and fname:
        full = []
        for _, r in df.iterrows():
            full.append({**{c: r[c] for c in keycols}, **{a.replace("_a_", ""): r[a] for a in attrs}, "imp": r.imp, "clk": r.clk,
                         "cost": round(r.cost, 4), "conv": r.conv, "mark": mark(r.cost, r.conv, cpa_lo, cpa_hi)})
        pd.DataFrame(full).to_csv(Path(csv_dir) / f"{fname}.csv", index=False, encoding="utf-8-sig")
    return out, s


# ---------- заявки по нашему счёту ----------
def fetch_leads(folder, d0, d1, camp_name):
    import leads_standard as L
    r = L.month_leads(folder, d0, d1, calls_from_ads="call_view")
    c, f = r["calls"], r["forms"]
    cc = c[c.camp == camp_name].copy()
    cc["day"] = pd.to_datetime(cc["day"])
    cc["ts"] = pd.to_datetime(cc["ts"])
    cc["k"] = np.where(cc.via_call_view, "ads", "site")
    ff = f[f.camp == camp_name].copy()
    ff["day"] = pd.to_datetime(ff["day"])
    return {"calls": cc, "forms": ff, "guard_cid": str(r["guard_cfg"]["customer_id"])}


# ---------- главная ----------
def main():
    ap = argparse.ArgumentParser(description="Все срезы кампании за точные даты окна (только чтение). См. docstring файла.")
    ap.add_argument("--customer-id", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--campaign-id")
    g.add_argument("--campaign", help="точное имя кампании")
    ap.add_argument("--from", dest="d0", required=True, help="YYYY-MM-DD, включительно")
    ap.add_argument("--to", dest="d1", required=True, help="YYYY-MM-DD, включительно")
    ap.add_argument("--exclude-days", default="", help="даты через запятую (грязные дни)")
    ap.add_argument("--basis", choices=["clean", "all"], help="clean = без исключённых (по умолчанию, если они заданы), all = все дни")
    ap.add_argument("--compare-from")
    ap.add_argument("--compare-to")
    ap.add_argument("--client-folder", required=True)
    ap.add_argument("--slices", default="all", help="через запятую из: " + ",".join(ALL_SLICES) + " (по умолчанию все)")
    ap.add_argument("--target-cpa-low", type=float, default=22.0)
    ap.add_argument("--target-cpa-high", type=float, default=24.0)
    ap.add_argument("--top", type=int, default=30, help="строк в markdown на таблицу (по расходу; помеченные строки показываются всегда)")
    ap.add_argument("--no-leads", action="store_true", help="не ходить в Ringostat/Supabase (только кабинет)")
    ap.add_argument("--out-dir", help="папка для markdown и CSV; без неё только консоль")
    a = ap.parse_args()

    cid = a.customer_id.replace("-", "").strip()
    from gads_stats import GOOGLE_ADS_YAML, get_ads_service
    from google.ads.googleads.client import GoogleAdsClient
    ga = get_ads_service(GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id)

    camp = resolve_campaign(ga, cid, a.campaign_id, a.campaign)
    if camp["name"].lower().startswith("yt_"):
        raise SystemExit("Кампания yt_* (YouTube) - отдельный проект, не анализируется этим скриптом.")
    ch = camp["channel"]
    is_search, is_pmax = ch == "SEARCH", ch == "PERFORMANCE_MAX"
    want = ALL_SLICES if a.slices == "all" else [s.strip() for s in a.slices.split(",") if s.strip()]
    bad = [s for s in want if s not in ALL_SLICES]
    if bad:
        raise SystemExit("Неизвестные срезы: %s. Доступны: %s" % (bad, ",".join(ALL_SLICES)))

    t0, t1 = pd.Timestamp(a.d0), pd.Timestamp(a.d1)
    excl = [pd.Timestamp(x.strip()) for x in a.exclude_days.split(",") if x.strip()]
    basis = a.basis or ("clean" if excl else "all")
    all_days = list(pd.date_range(t0, t1))
    use_days = [d for d in all_days if not (basis == "clean" and d in excl)]
    ranges = contiguous_ranges(use_days)
    cmp_on = bool(a.compare_from and a.compare_to)
    cranges = contiguous_ranges(list(pd.date_range(pd.Timestamp(a.compare_from), pd.Timestamp(a.compare_to)))) if cmp_on else None
    clab = f"сравн. {a.compare_from[5:]}..{a.compare_to[5:]}" if cmp_on else ""
    cl_, ch_ = a.target_cpa_low, a.target_cpa_high
    csv_dir = None
    if a.out_dir:
        csv_dir = Path(a.out_dir) / f"срезы_{camp['id']}_{a.d0}_{a.d1}_{basis}_csv"
        csv_dir.mkdir(parents=True, exist_ok=True)

    # --- день x кампания: итог и потеря показов ---
    day_rows = []
    lvl_day = None
    for lvl in (IS_LEVELS if is_search else [[]]):
        sel_is = "".join(", metrics." + m for m in lvl)
        try:
            q = (f"SELECT segments.date, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions{sel_is} "
                 f"FROM campaign WHERE campaign.id = {int(camp['id'])} AND segments.date BETWEEN '{a.d0}' AND '{a.d1}'")
            for r in q_rows(ga, cid, q):
                d = {"Date": pd.Timestamp(r.segments.date), "imp": int(r.metrics.impressions), "clk": int(r.metrics.clicks),
                     "cost": r.metrics.cost_micros / 1e6, "conv": float(r.metrics.conversions)}
                for m in lvl:
                    d[m] = float(getattr(r.metrics, m))
                day_rows.append(d)
            lvl_day = lvl
            break
        except Exception:  # noqa: BLE001
            day_rows = []
    day = pd.DataFrame(day_rows).groupby("Date", as_index=False).sum() if day_rows else pd.DataFrame(columns=["Date", "imp", "clk", "cost", "conv"])
    tot_all = {k: float(day[k].sum()) for k in ("imp", "clk", "cost", "conv")}
    dsel = day[day.Date.isin(use_days)]
    tot = {k: float(dsel[k].sum()) for k in ("imp", "clk", "cost", "conv")}
    tot["imp"], tot["clk"] = int(tot["imp"]), int(tot["clk"])
    spend_days = set(dsel[dsel.cost > 0].Date)
    ctot = None
    if cmp_on:
        cd = []
        for x, y in cranges:
            q = (f"SELECT metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions FROM campaign "
                 f"WHERE campaign.id = {int(camp['id'])} AND segments.date BETWEEN '{x}' AND '{y}'")
            for r in q_rows(ga, cid, q):
                cd.append((int(r.metrics.impressions), int(r.metrics.clicks), r.metrics.cost_micros / 1e6, float(r.metrics.conversions)))
        ctot = [sum(x[i] for x in cd) for i in range(4)] if cd else [0, 0, 0.0, 0.0]

    # --- заявки по нашему счёту ---
    L = None
    warn = []
    if not a.no_leads:
        try:
            L = fetch_leads(a.client_folder, a.d0, a.d1, camp["name"])
            if L["guard_cid"] != cid:
                warn.append(f"customer-id {cid} не совпадает с guard_config клиента {L['guard_cid']}: заявки могли быть взяты из другого аккаунта")
        except Exception as e:  # noqa: BLE001
            NODATA.append(("заявки по нашему счёту", "ошибка чтения Ringostat/Supabase: %s" % str(e)[:150]))
    lead_total = None
    dow_leads = hour_leads = None
    if L is not None:
        cc = L["calls"][L["calls"].day.isin(spend_days)]
        ff = L["forms"][L["forms"].day.isin(spend_days)]
        lead_total = {"site": int((cc.k == "site").sum()), "ads": int((cc.k == "ads").sum()), "forms": len(ff)}
        dow_leads = {}
        for d_ in list(cc.day) + list(ff.day):
            k = DOW_RU[DOW_ORDER[d_.dayofweek]]
            dow_leads[k] = dow_leads.get(k, 0) + 1
        hour_leads = {}
        for t_ in cc.ts:
            hour_leads[int(t_.hour)] = hour_leads.get(int(t_.hour), 0) + 1

    # --- шапка ---
    out = [f"# Срезы кампании {camp['name']} ({camp['id']}), окно {a.d0}..{a.d1}", "",
           f"Тип: {ch}, статус сейчас: {camp['status']}. Клиент: {a.client_folder}. Сформировано: {datetime.now():%Y-%m-%d %H:%M}. Только чтение, без yt_.",
           f"Основа таблиц: {'все дни окна' if basis == 'all' else 'без исключённых дней'} ({len(use_days)} дн.). "
           f"Исключённые дни: {', '.join(x.strftime('%Y-%m-%d') for x in excl) or 'нет'}"
           + (" (в таблицы НЕ входят)." if basis == "clean" and excl else (" (заданы, но --basis all: входят)." if excl else ".")),
           f"Сравнение: {a.compare_from}..{a.compare_to}, все дни, без исключений." if cmp_on else "Сравнение: не задано.",
           f"Допустимая цена конверсии {cl_:g}-{ch_:g} €; пометка «РАСХОД БЕЗ КОНВ.» при расходе >= {2 * ch_:g} € и 0 конв.",
           "Источники: показы/клики/расход/конверсии - GAQL (campaign / ad_group / keyword_view / search_term_view / gender_view / "
           "age_range_view / landing_page_view и др.) по диапазонам дат; заявки - leads_standard.month_leads (Ringostat + Supabase + call_view); "
           "интервалы - Гарвуд 80 и 95 % от конверсий кабинета, расход фиксирован.", ""]
    for w in warn:
        out.append("ВНИМАНИЕ: " + w)
    out += ["## Итог кампании (опорный для сверки срезов)", ""]
    rows = [["Все дни окна", fi(tot_all["imp"]), fi(tot_all["clk"]), f"{tot_all['cost']:.2f}", f"{tot_all['conv']:.1f}"],
            [f"Основа таблиц ({basis})", fi(tot["imp"]), fi(tot["clk"]), f"{tot['cost']:.2f}", f"{tot['conv']:.1f}"]]
    if cmp_on:
        rows.append([f"Сравнение {a.compare_from}..{a.compare_to}", fi(ctot[0]), fi(ctot[1]), f"{ctot[2]:.2f}", f"{ctot[3]:.1f}"])
    out += md_table(["Набор дней", "Показы", "Клики", "Расход, €", "Конв. кабинета"], rows)
    out.append("")
    if lead_total is not None:
        n = sum(lead_total.values())
        out.append(f"Заявки по нашему счёту (дни с расходом основы): всего {n} = сайт Ringostat {lead_total['site']} + звонки из объявлений {lead_total['ads']} "
                   f"+ формы Supabase с меткой {lead_total['forms']}; цена заявки {tot['cost'] / n:.1f} € [80 %: {rng(*cpa_interval(tot['cost'], n, .8))}; 95 %: {rng(*cpa_interval(tot['cost'], n, .95))}]." if n
                   else "Заявки по нашему счёту: 0.")
        out.append("")

    def nodata(name, why):
        NODATA.append((name, why))
        return [f"### {name}", "", f"Нет в данных: {why}", ""]

    def run_slice(name, title, sel, from_, keyfn, keycols, keyheads, where="", want_is=False, attrs=(), leads=None, keysort=None,
                  note=None, applicable=True, why_na="", order=None):
        if not applicable:
            return nodata(title, why_na)
        try:
            df, lvl = fetch(ga, cid, camp["id"], ranges, sel, from_, keyfn, where, want_is)
            cdf = None
            if cmp_on:
                try:
                    cdf, _ = fetch(ga, cid, camp["id"], cranges, sel, from_, keyfn, where, False)
                except Exception:  # noqa: BLE001
                    cdf = None
        except Exception as e:  # noqa: BLE001
            return nodata(title, "API отказал: %s" % str(e).replace("\n", " ")[:200])
        if df.empty:
            return nodata(title, "API вернул 0 строк за окно (нет показов по этому разрезу или разрез недоступен для типа %s)" % ch)
        extra_note = note
        if want_is and lvl != IS_LEVELS[0]:
            miss = "потеря по бюджету" if lvl else "доли показов"
            extra_note = (note or "") + f" Нет в данных на этом уровне: {miss}."
            NODATA.append((title, f"{miss} на этом уровне API не отдаёт"))
        o, s = render_slice(title, df, keycols, keyheads, tot, cl_, ch_, a.top, (cdf, clab) if cmp_on else None, attrs, bool(lvl),
                            leads, keysort, extra_note, csv_dir, name, order)
        return o

    n_ = lambda r: ""
    for s_name in want:
        if s_name == "isday":
            out += ["## Потеря показов по дням (кампания x день)", ""]
            if not is_search or lvl_day is None or not lvl_day:
                out += nodata("Потеря показов по дням", f"метрики Search IS недоступны для типа {ch}" if not is_search else "API не отдал метрики").copy()[1:]
                continue
            hd = ["Дата", "Показы", "Клики", "Расход", "Доля показов", "Потеря рейтинг", "Потеря бюджет"]
            has_b = "search_budget_lost_impression_share" in lvl_day
            rr = []
            for _, r in day.sort_values("Date").iterrows():
                tag = " (искл.)" if r.Date in excl else ""
                rr.append([r.Date.strftime("%Y-%m-%d") + tag, fi(r.imp), fi(r.clk), f"{r.cost:.2f}",
                           f"{r.search_impression_share * 100:.0f} %" if r.imp else "-", f"{r.search_rank_lost_impression_share * 100:.0f} %" if r.imp else "-",
                           (f"{r.search_budget_lost_impression_share * 100:.0f} %" if r.imp else "-") if has_b else "нет в данных"])
            out += md_table(hd, rr)
            w = dsel[dsel.imp > 0]
            if len(w):
                def wm(c):
                    return float((w[c] * w.imp).sum() / w.imp.sum()) * 100
                out += ["", f"Среднее за основу (взвешено по показам дня, приближение; суммарную долю API по окну не отдаёт при дневной разбивке): доля показов {wm('search_impression_share'):.0f} %, "
                        f"потеря по рейтингу {wm('search_rank_lost_impression_share'):.0f} %"
                        + (f", потеря по бюджету {wm('search_budget_lost_impression_share'):.0f} %." if has_b else ".")]
            out += ["Значения Google ниже 10 % приходят как 0,09; в день без показов метрики нет (\"-\").", ""]
        elif s_name == "group":
            out += ["## Группы объявлений"]
            out += run_slice("group", "Группы объявлений", ["ad_group.id", "ad_group.name", "ad_group.status", "ad_group.cpc_bid_micros"], "ad_group",
                             lambda r: ({"Группа": r.ad_group.name}, {"Статус": en(r.ad_group.status, "AdGroupStatusEnum"), "Потолок цены клика": round(r.ad_group.cpc_bid_micros / 1e6, 2)}),
                             ["Группа"], ["Группа"], want_is=True, attrs=["_a_Статус", "_a_Потолок цены клика"],
                             applicable=not is_pmax, why_na="у PMax нет групп объявлений (см. «Группы ресурсов»)",
                             note="Показаны только группы с показами в окне; потолок - ad_group.cpc_bid_micros сейчас (не на даты окна). Заявки по группам по нашему счёту привязать нельзя.")
        elif s_name == "keyword":
            out += ["## Ключевые слова"]
            out += run_slice("keyword", "Ключевые слова и тип соответствия",
                             ["ad_group.name", "ad_group_criterion.keyword.text", "ad_group_criterion.keyword.match_type", "ad_group_criterion.status"], "keyword_view",
                             lambda r: ({"Ключ": r.ad_group_criterion.keyword.text, "Соотв.": en(r.ad_group_criterion.keyword.match_type, "KeywordMatchTypeEnum"), "Группа": r.ad_group.name},
                                        {"Статус": en(r.ad_group_criterion.status, "AdGroupCriterionStatusEnum")}),
                             ["Группа", "Ключ", "Соотв."], ["Группа", "Ключ", "Соотв."], where="AND ad_group_criterion.negative = FALSE", want_is=True,
                             attrs=["_a_Статус"], applicable=is_search, why_na=f"у типа {ch} нет ключевых слов (keyword_view)",
                             note="Заявки по ключам по нашему счёту привязать нельзя.")
        elif s_name == "term":
            out += ["## Поисковые запросы"]
            out += run_slice("term", "Поисковые запросы", ["search_term_view.search_term", "search_term_view.status"], "search_term_view",
                             lambda r: ({"Запрос": r.search_term_view.search_term}, {"Статус": en(r.search_term_view.status, "SearchTermViewStatusEnum")}),
                             ["Запрос"], ["Запрос"], attrs=["_a_Статус"], applicable=True, why_na="",
                             note="search_term_view - только запросы, которые Google показывает отчётом (скрытые мелкие запросы в итог не входят - расхождение со сверкой ожидаемо). Заявки по запросам привязать нельзя.")
        elif s_name == "device":
            out += ["## Устройства"]
            out += run_slice("device", "Устройства", ["segments.device"], "campaign",
                             lambda r: ({"Устройство": en(r.segments.device, "DeviceEnum")}, {}), ["Устройство"], ["Устройство"],
                             note="Заявки по устройствам привязать нельзя (в метках заявок устройства нет).")
        elif s_name == "geo":
            out += ["## География (регионы)"]
            res = run_slice("geo", "Регионы", ["segments.geo_target_region"], "geographic_view",
                            lambda r: ({"Регион": r.segments.geo_target_region or "(не определён)"}, {}), ["Регион"], ["Регион (geoTargetConstants)"],
                            note="Регион пользователя по segments.geo_target_region; заявки по гео не привязываются (не нужно).")
            # подмена кодов на названия
            try:
                import re
                codes = sorted(set(re.findall(r"geoTargetConstants/(\d+)", "\n".join(res))))
                if codes:
                    nm = {}
                    qq = "SELECT geo_target_constant.id, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.id IN (%s)" % ",".join(codes)
                    for r in q_rows(ga, cid, qq):
                        nm[str(r.geo_target_constant.id)] = r.geo_target_constant.name
                    res = [re.sub(r"geoTargetConstants/(\d+)", lambda m_: f"{nm.get(m_.group(1), m_.group(1))} ({m_.group(1)})", x) for x in res]
            except Exception:  # noqa: BLE001
                pass
            out += res
        elif s_name == "hour":
            out += ["## Час суток"]
            res = run_slice("hour", "Час суток", ["segments.hour"], "campaign",
                            lambda r: ({"Час": int(r.segments.hour)}, {}), ["Час"], ["Час (пояс аккаунта)"], keysort=["Час"],
                            leads=None,
                            note="Заявки по часу: только звонки (Ringostat/call_view имеют время, формы Supabase времени суток не имеют - формы по часу привязать нельзя); см. таблицу ниже.")
            out += res
            if hour_leads is not None:
                hr = [[h, hour_leads.get(h, 0)] for h in sorted(hour_leads)]
                out += ["Звонки по нашему счёту по часу (время Варшавы, дни с расходом основы; форм здесь нет). Часы в таблице выше - в поясе аккаунта Google Ads, при расхождении поясов сдвиг:", ""]
                out += md_table(["Час", "Звонки (сайт + из объявлений)"], hr) + [""]
            else:
                NODATA.append(("Звонки по часу", "заявки не прочитаны"))
        elif s_name == "dow":
            out += ["## День недели"]
            out += run_slice("dow", "День недели", ["segments.day_of_week"], "campaign",
                             lambda r: ({"День": DOW_RU.get(en(r.segments.day_of_week, "DayOfWeekEnum"), "?")}, {}), ["День"], ["День"],
                             leads=dow_leads, keysort=None, order=list(DOW_RU.values()),
                             note="Заявки по нашему счёту (сайт + звонки из объявлений + формы с меткой) в дни с расходом основы; цена заявки - расход/интервал Гарвуда. Дни недели сравнивать с поправкой на число каждого дня в окне.")
        elif s_name == "gender":
            out += ["## Пол"]
            out += run_slice("gender", "Пол", ["ad_group_criterion.gender.type"], "gender_view",
                             lambda r: ({"Пол": en(r.ad_group_criterion.gender.type_, "GenderTypeEnum")}, {}), ["Пол"], ["Пол"],
                             applicable=True, why_na="",
                             note="Заявки по полу привязать нельзя. UNDETERMINED - пол не определён.")
        elif s_name == "age":
            out += ["## Возраст"]
            out += run_slice("age", "Возраст", ["ad_group_criterion.age_range.type"], "age_range_view",
                             lambda r: ({"Возраст": en(r.ad_group_criterion.age_range.type_, "AgeRangeTypeEnum")}, {}), ["Возраст"], ["Возраст"],
                             applicable=True, why_na="",
                             note="Заявки по возрасту привязать нельзя. AGE_RANGE_UNDETERMINED - возраст не определён.")
        elif s_name == "network":
            out += ["## Сеть / канал"]
            out += run_slice("network", "Сеть (ad_network_type)", ["segments.ad_network_type"], "campaign",
                             lambda r: ({"Сеть": en(r.segments.ad_network_type, "AdNetworkTypeEnum")}, {}), ["Сеть"], ["Сеть"],
                             note="У Search: SEARCH / SEARCH_PARTNERS / CONTENT; у PMax - каналы (MIXED, YOUTUBE и т. п.), как отдаёт API.")
        elif s_name == "ad":
            out += ["## Объявления (RSA)"]
            out += run_slice("ad", "Объявления", ["ad_group.name", "ad_group_ad.ad.id", "ad_group_ad.ad.type", "ad_group_ad.status",
                                                  "ad_group_ad.ad.responsive_search_ad.headlines"], "ad_group_ad",
                             lambda r: ({"Объявление": str(r.ad_group_ad.ad.id)},
                                        {"Группа": r.ad_group.name, "Статус": en(r.ad_group_ad.status, "AdGroupAdStatusEnum"), "Тип": en(r.ad_group_ad.ad.type_, "AdTypeEnum"),
                                         "Заголовки": " / ".join(h.text for h in list(r.ad_group_ad.ad.responsive_search_ad.headlines)[:3])}),
                             ["Объявление"], ["ID"], where="AND ad_group_ad.status != 'REMOVED'",
                             attrs=["_a_Группа", "_a_Статус", "_a_Тип", "_a_Заголовки"], applicable=is_search, why_na=f"RSA есть только у Search (тип {ch})",
                             note="Заголовки - первые три. Заявки по объявлениям привязать нельзя.")
        elif s_name == "asset":
            out += ["## Ассеты RSA"]
            if not is_search:
                out += nodata("Ассеты RSA", f"ad_group_ad_asset_view - ассеты RSA, нужен Search (тип {ch})")
                continue
            try:
                texts = {}
                res = run_slice("asset", "Ассеты RSA (заголовки/описания)", ["ad_group_ad_asset_view.asset", "ad_group_ad_asset_view.field_type", "ad_group_ad_asset_view.performance_label"],
                                "ad_group_ad_asset_view",
                                lambda r: ({"Тип": en(r.ad_group_ad_asset_view.field_type, "AssetFieldTypeEnum"), "Ассет": r.ad_group_ad_asset_view.asset},
                                           {"Ярлык": en(r.ad_group_ad_asset_view.performance_label, "AssetPerformanceLabelEnum")}),
                                ["Тип", "Ассет"], ["Тип", "Ассет (resource)"], attrs=["_a_Ярлык"],
                                note="Показы ассета считаются по каждому объявлению, где он есть; итог среза не равен итогу кампании (ожидаемо). Ярлык - Google, на момент запроса.")
                import re
                names = sorted(set(re.findall(r"customers/\d+/assets/(\d+)", "\n".join(res))))
                if names:
                    qq = "SELECT asset.id, asset.text_asset.text FROM asset WHERE asset.id IN (%s)" % ",".join(names)
                    for r in q_rows(ga, cid, qq):
                        texts[str(r.asset.id)] = r.asset.text_asset.text
                    res = [re.sub(r"customers/\d+/assets/(\d+)", lambda m_: f"{texts.get(m_.group(1), m_.group(1))}", x) for x in res]
                out += res
            except Exception as e:  # noqa: BLE001
                out += nodata("Ассеты RSA", "ошибка: %s" % str(e)[:150])
        elif s_name == "landing":
            out += ["## Посадочные страницы"]
            out += run_slice("landing", "Посадочные страницы (final URL)", ["landing_page_view.unexpanded_final_url"], "landing_page_view",
                             lambda r: ({"Страница": r.landing_page_view.unexpanded_final_url}, {}), ["Страница"], ["Страница"],
                             note="Заявки по посадочным привязать нельзя: заявка из month_leads не несёт page_url (Ringostat запрашивается без поля адреса страницы, у форм Supabase адрес в стандарт не попадает).")
        elif s_name == "audience":
            out += ["## Аудитории (наблюдение)"]
            parts = []
            for lv, sel, frm, kf in [
                ("кампания", ["campaign_criterion.display_name", "campaign_criterion.type"], "campaign_audience_view",
                 lambda r: ({"Уровень": "кампания", "Аудитория": r.campaign_criterion.display_name or en(r.campaign_criterion.type_, "CriterionTypeEnum")}, {})),
                ("группа", ["ad_group_criterion.display_name", "ad_group_criterion.type"], "ad_group_audience_view",
                 lambda r: ({"Уровень": "группа", "Аудитория": r.ad_group_criterion.display_name or en(r.ad_group_criterion.type_, "CriterionTypeEnum")}, {}))]:
                try:
                    d_, _ = fetch(ga, cid, camp["id"], ranges, sel, frm, kf, "", False)
                    if not d_.empty:
                        parts.append(d_)
                except Exception as e:  # noqa: BLE001
                    NODATA.append((f"Аудитории ({lv})", "API отказал: %s" % str(e).replace("\n", " ")[:150]))
            if parts:
                dd = pd.concat(parts, ignore_index=True).groupby(["Уровень", "Аудитория"], as_index=False).agg(imp=("imp", "sum"), clk=("clk", "sum"), cost=("cost", "sum"), conv=("conv", "sum"))
                o, _ = render_slice("Аудитории (campaign_/ad_group_audience_view)", dd, ["Уровень", "Аудитория"], ["Уровень", "Аудитория"], tot, cl_, ch_, a.top,
                                    None, (), False, None, None, "Итог среза не равен итогу кампании (аудитории - наблюдение, показы в разрезе аудитории, один показ может попасть в несколько). Заявки по аудиториям привязать нельзя.", csv_dir, "audience")
                out += o
            else:
                out += nodata("Аудитории", "campaign_audience_view / ad_group_audience_view вернули 0 строк за окно (аудиторий в наблюдении нет или нет показов)")
        elif s_name == "assetgroup":
            out += ["## PMax: группы ресурсов"]
            out += run_slice("assetgroup", "Группы ресурсов", ["asset_group.id", "asset_group.name", "asset_group.status"], "asset_group",
                             lambda r: ({"Группа ресурсов": r.asset_group.name}, {"Статус": en(r.asset_group.status, "AssetGroupStatusEnum")}),
                             ["Группа ресурсов"], ["Группа ресурсов"], attrs=["_a_Статус"], applicable=is_pmax,
                             why_na=f"группы ресурсов есть только у Performance Max (тип {ch})")

    # --- потеря показов по группам/ключам: уже в таблицах (колонки), итог ---
    out += ["## Нет в данных / нельзя привязать (по этому прогону)", ""]
    fixed = [
        "Заявки по нашему счёту по группам, ключам, запросам, устройствам, полу, возрасту, аудиториям, объявлениям, посадочным: привязать нельзя (в метках заявок нет такого признака; в стандарте нет page_url).",
        "Формы Supabase по часу суток: нельзя (в стандарте только дата).",
        "Конверсии кабинета = основная цель кампании (metrics.conversions), не заявки по нашему счёту (раздел 7 алгоритма).",
    ]
    for x in fixed:
        out.append("- " + x)
    seen = set()
    for n_, w_ in NODATA:
        if (n_, w_) in seen:
            continue
        seen.add((n_, w_))
        out.append(f"- {n_}: {w_}")
    out.append("")
    text = "\n".join(out)
    print(text)
    if a.out_dir:
        p = Path(a.out_dir)
        p.mkdir(parents=True, exist_ok=True)
        fn = p / f"campaign_slices_{camp['id']}_{a.d0}_to_{a.d1}_{basis}.md"
        fn.write_text(text + "\n", encoding="utf-8")
        print("\nСохранено:", fn)


if __name__ == "__main__":
    main()
