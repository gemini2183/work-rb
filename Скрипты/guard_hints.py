#!/usr/bin/env python
# coding: utf-8
"""Подсказки сторожа «недобор расхода» и измерение их эффекта. Решение пользователя 2026-11-05
(План: База_знаний/Агенты/Сторож_жизненный_цикл_кампаний_и_план_изменений.md, раздел 3 и раздел 7).

Модуль НИЧЕГО не пишет в кабинет Google Ads. Только читает Ads, пишет `guard_signals.csv` и отправляет сообщение через `notify`.
Действие по подсказке — только после «да» пользователя (по протоколу записи в кабинеты).

Раз в сутки (первый такт после 07:30) для каждой охраняемой кампании:
  1) Чистые дни: последние `clean_days` (3) дней по логике `window_check.py` (не выходной по расписанию, не сокращённый, без правок
     режима и пауз, не сегодня, показы были). Вердикт «ЧАСТИЧНЫЙ» (показы не в каждом часу) для этой цели ДОПУСКАЕТСЯ: у кампании с
     недобором показы и должны быть неполными, иначе подсказка не сработала бы ровно там, где нужна. День без показов не берём:
     нельзя отличить паузу от пустого аукциона.
  2) Недобор: медиана расхода чистых дней < `share` (50%) текущего бюджета И потеря показов по бюджету = 0 (для PMax, Display, Demand Gen
     метрики нет — только доля расхода, это сказано в сообщении).
  3) Цена заявки: P(цена ≤ цели) ≥ `gate` (80%) по ОБЕИМ моделям (по кампании; с приором проекта, вес k0=3 заявки). История —
     `hist_days` (11) дней, заявки по единому стандарту (Ringostat + Supabase + call_view), из Ads только расход. В расчёт входят ВСЕ дни
     с расходом, в том числе дни, когда сторож ставил паузу: расход без заявок в такие дни реален, и если их выбросить, цена заявки
     выглядит ниже настоящей (`guard_threshold_calc.py` пауз-дни выбрасывает — для решения «поднимать» это опасное смещение).
  4) Рычаг: tCPA (+step_pct%), потолок цены клика («максимум кликов») или ставки групп (ручная цена клика); нет рычага — сообщение без числа.
Если условия 2–3 выполнены → сообщение в Telegram + строка `недобор_поднять`. Если недобор есть, а цена не подтверждена →
строка `недобор_цена_не_подтверждена` раз в `unconfirmed_days` дней + строка в утреннем отчёте (в Telegram отдельно не шлём).
Не предлагаем: кампании не под охраной по паспорту (hold_*), тесты с общим лимитом расхода, «незнакомые» под временной защитой,
кампании с открытым предложением (без ответа или «да» без измеренного эффекта), 7 дней после ответа «нет».
Эффект: через `effect_days` (3) чистых дня после даты применения (`guard_signals.py answer … --applied`) считаются расход, заявки и цена
заявки «до» и «после»; пометка «измерено» или «мало данных».
Не сделано (отложено по решению пользователя): заморозка на время эксперимента, коридор из раздела `course`, режим риска проекта
(порог 80% фиксирован, лежит в конфиге `underspend.gate`).
"""
import math
import statistics
from datetime import date, timedelta

import numpy as np

import guard_signals as GS
import window_check as WC

DEFAULTS = {"enabled": False, "share": 0.5, "clean_days": 3, "gate": 0.8, "k0": 3.0, "step_pct": 15.0, "effect_days": 3,
            "remind_days": 3, "no_days": 7, "unconfirmed_days": 7, "lost_zero": 0.005, "hist_days": 11, "thin_leads": 5}


def p_cpl_below(S, N, T, cpl_pool, k0=3.0, draws=20000, seed=3):
    """P(настоящая цена заявки ≤ цели T) при расходе S и N заявках. Скорость заявок ~ Gamma (Пуассон по расходу).
    А) только кампания, приор Jeffreys (Gamma(N+0.5, S)); Б) частичное объединение: приор — цена заявки проекта `cpl_pool` с весом k0
    «заявок». Возвращает (pА, pБ). Формула та же, что была в guard_threshold_calc.underspend."""
    rng = np.random.default_rng(seed)
    S = max(float(S), 1e-9)
    pa = float(np.mean(1.0 / rng.gamma(N + 0.5, 1.0 / S, draws) <= T))
    pb = float(np.mean(1.0 / rng.gamma(k0 + N, 1.0 / (k0 * cpl_pool + S), draws) <= T))
    return pa, pb


def clean_ok(verdict, cost, impr):
    """День годится для оценки недобора: ЧИСТЫЙ или ЧАСТИЧНЫЙ (см. модульный docstring), с показами и расходом."""
    return verdict in ("ЧИСТЫЙ", "ЧАСТИЧНЫЙ") and cost > 0 and impr > 0


def read_lost_shares(ga, enums, cid, ids, d_from, d_to):
    """({(id, дата): потеря показов по бюджету 0..1}, {id: метрика применима}). Применима только к Search и Shopping."""
    out, applicable = {}, {}
    ok_types = {int(enums.AdvertisingChannelTypeEnum.SEARCH), int(enums.AdvertisingChannelTypeEnum.SHOPPING)}
    q = ("SELECT campaign.id, campaign.advertising_channel_type, segments.date, metrics.search_budget_lost_impression_share, "
         "metrics.impressions FROM campaign WHERE campaign.id IN (" + ",".join(ids) + f") AND segments.date BETWEEN '{d_from}' AND '{d_to}'")
    for r in ga.search(customer_id=cid, query=q):
        cid_ = str(r.campaign.id)
        app = int(r.campaign.advertising_channel_type) in ok_types
        applicable[cid_] = app
        out[(cid_, r.segments.date)] = float(r.metrics.search_budget_lost_impression_share) if app else None
    return out, applicable


def read_cpc_levers(ga, cid, ids):
    """{id: {'ceiling': потолок цены клика у «максимума кликов» или 0, 'adgroup_max': наибольшая ставка включённых групп или 0}}."""
    out = {i: {"ceiling": 0.0, "adgroup_max": 0.0} for i in ids}
    if not ids:
        return out
    inl = ",".join(ids)
    for r in ga.search(customer_id=cid, query=f"SELECT campaign.id, campaign.target_spend.cpc_bid_ceiling_micros FROM campaign WHERE campaign.id IN ({inl})"):
        out[str(r.campaign.id)]["ceiling"] = r.campaign.target_spend.cpc_bid_ceiling_micros / 1e6
    for r in ga.search(customer_id=cid, query=("SELECT campaign.id, ad_group.cpc_bid_micros FROM ad_group "
                                               f"WHERE campaign.id IN ({inl}) AND ad_group.status = 'ENABLED'")):
        k = str(r.campaign.id)
        out[k]["adgroup_max"] = max(out[k]["adgroup_max"], r.ad_group.cpc_bid_micros / 1e6)
    return out


def pick_lever(c, cpc, step_pct):
    """→ (вид, было, станет, текст). Вид: tcpa | cpc_ceiling | cpc_manual | none."""
    b = (c.get("bidding") or "").split(",")[0].strip()
    k = 1 + step_pct / 100
    tcpa = float(c.get("tcpa") or 0)
    if tcpa > 0 and b in ("TARGET_CPA", "MAXIMIZE_CONVERSIONS"):
        new = round(tcpa * k, 1)
        return "tcpa", tcpa, new, f"поднять tCPA {tcpa:g} → {new:g} (+{step_pct:g}%)"
    if b == "TARGET_SPEND" and cpc and cpc.get("ceiling"):
        new = math.ceil(cpc["ceiling"] * k * 100) / 100
        return "cpc_ceiling", cpc["ceiling"], new, f"поднять потолок цены клика {cpc['ceiling']:.2f} → {new:.2f} (+{step_pct:g}%)"
    if b == "MANUAL_CPC" and cpc and cpc.get("adgroup_max"):
        new = math.ceil(cpc["adgroup_max"] * k * 100) / 100
        return ("cpc_manual", cpc["adgroup_max"], new,
                f"поднять ставки групп объявлений на {step_pct:g}% (наибольшая сейчас {cpc['adgroup_max']:.2f} → {new:.2f})")
    return "none", "", "", f"рычага ставок в настройках нет (стратегия: {c.get('bidding') or 'не прочитана'}); число не предлагаю, вариант — задать tCPA"


def fmt_day(iso):
    return f"{iso[8:10]}.{iso[5:7]}"


def evaluate(c, days, cfg, pool_cpl, lost_by, lost_app):
    """Оценка одной кампании. days — новые → старые: [{day, cost, impr, leads, verdict, clean}] без сегодняшнего дня.
    → dict со статусом: skip | off | early | ok_spend | budget_limited | unconfirmed | raise."""
    res = {"id": c["id"], "name": c["name"], "budget": c["budget"], "target": c["target"], "status": None, "reason": ""}
    if c.get("skip"):
        res.update(status="skip", reason=c["skip"])
        return res
    if not c.get("enabled"):
        res.update(status="off", reason="кампания не включена")
        return res
    clean = [d for d in days if d["clean"]][:cfg["clean_days"]]
    hist = [d for d in days if d["cost"] > 0]
    S, N = sum(d["cost"] for d in hist), sum(d["leads"] for d in hist)
    res.update(S=S, N=N, cpl=(S / N if N else None), hist_days=len(hist))
    if len(clean) < cfg["clean_days"]:
        res.update(status="early", reason=f"чистых дней {len(clean)} из {cfg['clean_days']} за {cfg['hist_days']} дн. (рано)",
                   verdicts={d["day"]: d["verdict"] for d in days[:cfg["clean_days"] + 3]})
        return res
    med = statistics.median(d["cost"] for d in clean)
    share = med / c["budget"] if c["budget"] else 0.0
    res.update(clean_dates=[d["day"] for d in clean], median_cost=med, median_share=share,
               cost_3d=sum(d["cost"] for d in clean), leads_3d=sum(d["leads"] for d in clean))
    if share >= cfg["share"]:
        res.update(status="ok_spend", reason=f"медиана {share:.0%} бюджета, не недобор")
        return res
    app = lost_app.get(c["id"], False)
    lost = None
    if app:
        vals = [lost_by.get((c["id"], d["day"])) for d in clean]
        lost = None if any(v is None for v in vals) else max(vals)
    res["lost"] = lost
    res["lost_applicable"] = app
    if app and lost is not None and lost > cfg["lost_zero"]:
        res.update(status="budget_limited", reason=f"потеря показов по бюджету {lost:.0%}: упирается в бюджет, это не недобор ставок")
        return res
    pool = pool_cpl if pool_cpl else (S / max(N, 1))
    pa, pb = p_cpl_below(S, N, c["target"], pool, cfg["k0"])
    res.update(pa=pa, pb=pb)
    if app and lost is None:
        res.update(status="unconfirmed", reason="потеря показов по бюджету не прочитана")
    elif pa >= cfg["gate"] and pb >= cfg["gate"]:
        res.update(status="raise")
    else:
        res.update(status="unconfirmed", reason=f"цена заявки не подтверждена: {pa:.0%} / {pb:.0%} при пороге {cfg['gate']:.0%}")
    return res


def measure_effect(row, c, days, cfg):
    """Эффект подсказки через effect_days чистых дней после даты применения → (текст, готово). Готово=False — ещё рано."""
    applied = row["applied_date"]
    after = sorted([d for d in days if d["clean"] and d["day"] > applied], key=lambda d: d["day"])[:cfg["effect_days"]]
    if len(after) < cfg["effect_days"]:
        too_old = (date.today() - date.fromisoformat(applied)).days > cfg["hist_days"]
        if too_old:
            return f"не измерено: после {applied} набралось {len(after)} чистых дней из {cfg['effect_days']}, окно данных {cfg['hist_days']} дн. истекло", True
        return "", False
    n_b = len(str(row["clean_days"]).split(","))
    cost_b, leads_b = float(row.get("cost_3d") or 0), float(row.get("leads_3d") or 0)
    cost_a, leads_a = sum(d["cost"] for d in after), sum(d["leads"] for d in after)
    bud = c["budget"] if c and c.get("budget") else float(row.get("budget") or 0)
    b_day, a_day = cost_b / n_b, cost_a / len(after)
    cpl_a = f"{cost_a / leads_a:.1f}" if leads_a else "—"
    if leads_a + leads_b < cfg["thin_leads"] or leads_a < cfg["thin_leads"]:
        price_note = f"цена заявки: мало данных (заявок после {leads_a:g} < {cfg['thin_leads']}), вывод не делаю"
    else:
        price_note = "цена заявки: измерено"
    txt = (f"до ({', '.join(fmt_day(x) for x in str(row['clean_days']).split(','))}): расход {b_day:.0f}/день ({b_day / bud:.0%} бюджета {bud:g}), "
           f"заявок {leads_b:g}; после ({', '.join(fmt_day(d['day']) for d in after)}): расход {a_day:.0f}/день ({a_day / bud:.0%}), "
           f"заявок {leads_a:g}, цена {cpl_a} (цель {row['target']}). Расход ×{(a_day / b_day if b_day else 0):.1f}: измерено; {price_note}")
    return txt, True


def run_daily(ga, client, cid, today, cands, calls_map, ad_map, forms_map, cfg, store, cur, notify, label=""):
    """Суточный разбор. cands — все охраняемые кампании: {id, name, target, budget, enabled, bidding, tcpa, auto, skip}.
    Печатает таблицу в консоль, пишет `store` (guard_signals.csv), шлёт `notify` только про предложения, напоминания и итоги.
    → список строк для утреннего отчёта."""
    cfg = {**DEFAULTS, **(cfg or {})}
    ids = [c["id"] for c in cands]
    iso = lambda d: d.isoformat()
    d_from = iso(today - timedelta(days=cfg["hist_days"] + 1))
    data = WC.collect(ga, client.enums, cid, d_from, iso(today))
    lost_by, lost_app = read_lost_shares(ga, client.enums, cid, ids, d_from, iso(today - timedelta(days=1)))
    per, S_all, N_all = {}, 0.0, 0.0
    for c in cands:
        days = []
        for i in range(1, cfg["hist_days"] + 1):
            day = today - timedelta(days=i)
            verdict, _ph, _hrs, d, _ch = WC.day_verdict(data, c["name"], day, iso(today))
            cost, impr = (d["cost"], d["impr"]) if d else (0.0, 0)
            leads = sum(m.get((iso(day), c["name"]), 0) for m in (calls_map, ad_map, forms_map))
            days.append({"day": iso(day), "cost": cost, "impr": impr, "leads": leads, "verdict": verdict,
                         "clean": clean_ok(verdict, cost, impr)})
        per[c["id"]] = days
        S_all += sum(d["cost"] for d in days)
        N_all += sum(d["leads"] for d in days)
    pool_cpl = S_all / max(N_all, 1)

    results = {c["id"]: evaluate(c, per[c["id"]], cfg, pool_cpl, lost_by, lost_app) for c in cands}
    by_id = {c["id"]: c for c in cands}
    print(f"=== подсказки «недобор расхода» {iso(today)} {label}: порог цены {cfg['gate']:.0%}, недобор < {cfg['share']:.0%} бюджета, "
          f"чистых дней {cfg['clean_days']}, проект: цена заявки {pool_cpl:.1f} ({N_all:g} заявок за {cfg['hist_days']} дн.) ===")
    for r in results.values():
        parts = [f"{r['name'][:30]:30} {r['status']:14}"]
        if "median_share" in r:
            parts.append(f"мед. {r['median_share']:.0%} бюджета {r['budget']:g} (дни {','.join(fmt_day(x) for x in r['clean_dates'])})")
        if "lost" in r:
            parts.append("потеря по бюджету " + ("нет метрики" if not r["lost_applicable"] else "?" if r["lost"] is None else f"{r['lost']:.0%}"))
        if "pa" in r:
            parts.append(f"заявок {r['N']:g} цена {r['cpl']:.1f} цель {r['target']:g} P {r['pa']:.0%}/{r['pb']:.0%}" if r["cpl"] else
                         f"заявок 0 цель {r['target']:g} P {r['pa']:.0%}/{r['pb']:.0%}")
        if r["reason"]:
            parts.append(r["reason"])
        print("  " + " | ".join(parts))

    rows = GS.load(store)   # читаем прямо перед записью: оператор мог ответить на сигнал за время расчёта
    lines = []
    cfg_today = iso(today)

    # --- 1) эффект по предложениям с ответом «да» и датой применения
    for row in rows:
        if row.get("type") == GS.TYPE_RAISE and row.get("status") == GS.ST_YES and row.get("applied_date") and not row.get("effect"):
            c = by_id.get(row["campaign_id"])
            days = per.get(row["campaign_id"])
            if days is None:
                continue
            txt, done = measure_effect(row, c, days, cfg)
            if done:
                row["effect"], row["status"] = txt, GS.ST_CLOSED
                msg = f"📊 {row['campaign']}: итог подсказки {row['id']} ({row['lever']} {row['lever_from']} → {row['lever_to']}, применено {row['applied_date']}). {txt}."
                notify(msg)
                lines.append(f"• итог {row['id']} {row['campaign']}: {txt}")

    # --- 2) новые сигналы, напоминания, справки
    for cid_, r in results.items():
        c = by_id[cid_]
        mine = [x for x in rows if x["campaign_id"] == cid_]
        open_row = next((x for x in mine if GS.is_open_raise(x)), None)
        if open_row and open_row["status"] == GS.ST_OFFERED:
            age = (today - date.fromisoformat(open_row["date"])).days
            last = open_row.get("last_reminder") or open_row["date"]
            if r["status"] != "raise":
                open_row["status"] = GS.ST_CLOSED
                open_row["effect"] = f"снят {cfg_today}: условие недобора ушло ({r['reason'] or r['status']})"
                lines.append(f"• {open_row['id']} {c['name']}: предложение снято, условие недобора ушло")
            elif (today - date.fromisoformat(last)).days >= cfg["remind_days"] and age >= cfg["remind_days"]:
                open_row["last_reminder"] = cfg_today
                notify(f"🔁 {c['name']}: предложение {open_row['id']} от {open_row['date']} без ответа ({open_row['lever']} "
                       f"{open_row['lever_from']} → {open_row['lever_to']}), недобор держится: медиана {r['median_share']:.0%} бюджета. "
                       f"Ответить: да или нет (я внесу в журнал сигналов).")
                lines.append(f"• напоминание {open_row['id']} {c['name']}: без ответа {age} дн.")
            continue
        if open_row:   # «да» без итога: ждём применения/эффекта, нового не предлагаем
            continue
        if r["status"] == "raise":
            recent_no = [x for x in mine if x["status"] == GS.ST_NO and x.get("answer_date")
                         and (today - date.fromisoformat(x["answer_date"])).days < cfg["no_days"]]
            if recent_no:
                continue
            cpc = None
            if (c.get("bidding") or "").split(",")[0].strip() in ("TARGET_SPEND", "MANUAL_CPC"):
                try:
                    cpc = read_cpc_levers(ga, cid, [cid_]).get(cid_)
                except Exception as ex:   # noqa: BLE001
                    print(f"  рычаг цены клика не прочитан: {type(ex).__name__}: {str(ex)[:100]}")
            kind, frm, to, ltxt = pick_lever(c, cpc, cfg["step_pct"])
            sid = GS.next_id(rows)
            row = {"id": sid, "date": cfg_today, "campaign_id": cid_, "campaign": c["name"], "type": GS.TYPE_RAISE, "lever": kind,
                   "lever_from": frm, "lever_to": to, "clean_days": ",".join(r["clean_dates"]), "median_share": round(r["median_share"], 3),
                   "budget": c["budget"], "lost_budget_is": ("" if r["lost"] is None else round(r["lost"], 3)),
                   "leads_hist": r["N"], "cost_hist": round(r["S"], 2), "cpl_hist": (round(r["cpl"], 1) if r["cpl"] else ""),
                   "target": c["target"], "p_campaign": round(r["pa"], 3), "p_pooled": round(r["pb"], 3), "gate": cfg["gate"],
                   "cost_3d": round(r["cost_3d"], 2), "leads_3d": r["leads_3d"], "status": GS.ST_OFFERED}
            rows.append(row)
            lost_txt = ("для этого типа кампаний метрики нет, смотрю только долю расхода" if not r["lost_applicable"]
                        else f"потеря показов по бюджету {r['lost']:.0%}")
            thin = f" Заявок мало ({r['N']:g}), оценка шаткая." if r["N"] < cfg["thin_leads"] else ""
            auto_note = (" Цель сторожа у этой кампании берётся из tCPA: после правки допустимый расход сторожа вырастет вместе с ним."
                         if (kind == "tcpa" and c.get("auto")) else "")
            notify(f"📈 Недобор расхода ({sid}): {c['name']}\n"
                   f"За 3 чистых дня ({', '.join(fmt_day(x) for x in r['clean_dates'])}) тратит в медиане {r['median_cost']:.0f} из {c['budget']:g} {cur} в день "
                   f"({r['median_share']:.0%} бюджета), {lost_txt}.\n"
                   f"Цена заявки за {r['hist_days']} дн.: {r['cpl']:.1f} {cur} по {r['N']:g} заявкам, цель {c['target']:g} {cur}. "
                   f"Вероятность, что настоящая цена не выше цели: {r['pa']:.0%} по кампании, {r['pb']:.0%} с поправкой на проект (порог {cfg['gate']:.0%}).{thin}\n"
                   f"Предложение: {ltxt}. Оценю через {cfg['effect_days']} чистых дня после правки.{auto_note}\n"
                   f"Сторож сам ничего не меняет: действие только после вашего «да».")
            lines.append(f"• предложение {sid} {c['name']}: {ltxt}")
        elif r["status"] == "unconfirmed" and "median_share" in r:
            last_info = [x for x in mine if x["type"] == GS.TYPE_UNCONFIRMED]
            if last_info and (today - date.fromisoformat(last_info[-1]["date"])).days < cfg["unconfirmed_days"]:
                continue
            sid = GS.next_id(rows)
            rows.append({"id": sid, "date": cfg_today, "campaign_id": cid_, "campaign": c["name"], "type": GS.TYPE_UNCONFIRMED,
                         "clean_days": ",".join(r["clean_dates"]), "median_share": round(r["median_share"], 3), "budget": c["budget"],
                         "lost_budget_is": ("" if r.get("lost") is None else round(r["lost"], 3)), "leads_hist": r["N"],
                         "cost_hist": round(r["S"], 2), "cpl_hist": (round(r["cpl"], 1) if r["cpl"] else ""), "target": c["target"],
                         "p_campaign": round(r["pa"], 3), "p_pooled": round(r["pb"], 3), "gate": cfg["gate"],
                         "cost_3d": round(r["cost_3d"], 2), "leads_3d": r["leads_3d"], "status": GS.ST_INFO, "effect": r["reason"]})
            lines.append(f"• {c['name']}: недобор (медиана {r['median_share']:.0%} бюджета), {r['reason']}, заявок {r['N']:g}. Ничего не двигаем")
    GS.save(store, rows)
    return lines
