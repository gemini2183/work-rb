#!/usr/bin/env python
# coding: utf-8
"""Проверки `guard_hints.py` и `guard_signals.py` без Google Ads и Telegram (синтетические ряды). Запуск из папки Скрипты:
    python test_guard_hints.py
Ничего не пишет в Клиенты/: журнал сигналов — во временной папке."""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import guard_hints as GH
import guard_signals as GS

CFG = {**GH.DEFAULTS}
TODAY = date(2026, 11, 10)


def mk_days(spec):
    """spec: список (расход, заявки, вердикт, показы) от вчера назад; → days для evaluate."""
    out = []
    for i, (cost, leads, verdict, impr) in enumerate(spec, start=1):
        out.append({"day": (TODAY - timedelta(days=i)).isoformat(), "cost": cost, "impr": impr, "leads": leads, "verdict": verdict,
                    "clean": GH.clean_ok(verdict, cost, impr)})
    return out


def cand(**kw):
    c = {"id": "1", "name": "кампания", "target": 110.0, "budget": 100.0, "enabled": True, "bidding": "TARGET_CPA, tCPA 90",
         "tcpa": 90.0, "auto": False, "skip": None}
    c.update(kw)
    return c


def ev(days, c=None, lost=0.0, app=True, pool=80.0):
    c = c or cand()
    lost_by = {(c["id"], d["day"]): lost for d in days} if lost is not None else {}
    return GH.evaluate(c, days, CFG, pool, lost_by, {c["id"]: app})


def test_probability():
    pa, pb = GH.p_cpl_below(620, 8, 110, 85)      # 8 заявок, цена ≈ 77 при цели 110
    assert 0.75 < pa < 0.92 and 0.75 < pb < 0.92, (pa, pb)
    pa, pb = GH.p_cpl_below(258, 1, 110, 85)      # 1 заявка на 258
    assert pa < 0.4, pa
    pa0, _ = GH.p_cpl_below(100, 0, 100, 85)
    assert pa0 < 0.3, pa0
    # дни без заявок (пауза сторожа) обязаны ухудшать оценку
    good = GH.p_cpl_below(450, 5, 100, 100)[0]
    with_bad_day = GH.p_cpl_below(550, 5, 100, 100)[0]
    assert with_bad_day < good, (good, with_bad_day)


def test_clean_days_rules():
    assert GH.clean_ok("ЧИСТЫЙ", 10, 5)
    assert GH.clean_ok("ЧАСТИЧНЫЙ", 10, 5)          # недобор = неполные часы показов, это допустимо
    assert not GH.clean_ok("ПЕРЕХОДНЫЙ", 10, 5)
    assert not GH.clean_ok("ВЫХОДНОЙ", 0, 0)
    assert not GH.clean_ok("СОКРАЩЁННЫЙ (по расписанию, сравнивать только с такими же днями)", 10, 5)
    assert not GH.clean_ok("ЧАСТИЧНЫЙ", 0, 0)       # день без показов: нельзя отличить паузу от пустого аукциона
    assert not GH.clean_ok("ПОКАЗЫ ВНЕ РАСПИСАНИЯ", 10, 5)


def test_evaluate_statuses():
    ok = ("ЧИСТЫЙ",)
    # рано: два чистых дня из трёх (воскресенье выходной, правка бюджета)
    days = mk_days([(30, 1, "ЧИСТЫЙ", 50), (0, 0, "ВЫХОДНОЙ", 0), (30, 1, "ПЕРЕХОДНЫЙ", 50), (30, 1, "ЧИСТЫЙ", 50)])
    assert ev(days)["status"] == "early"
    # три чистых дня, недобор 30%, много заявок -> предложение
    good = mk_days([(30, 1, "ЧИСТЫЙ", 50)] * 3 + [(30, 1, "ЧАСТИЧНЫЙ", 50)] * 5)
    r = ev(good)
    assert r["status"] == "raise" and abs(r["median_share"] - 0.3) < 1e-9, r
    # ровно 50% бюджета — не недобор
    half = mk_days([(50, 1, "ЧИСТЫЙ", 50)] * 3 + [(50, 1, "ЧИСТЫЙ", 50)] * 5)
    assert ev(half)["status"] == "ok_spend"
    # 49% — недобор
    just = mk_days([(49, 3, "ЧИСТЫЙ", 50)] * 3 + [(49, 3, "ЧИСТЫЙ", 50)] * 5)
    assert ev(just)["status"] == "raise"
    # потеря по бюджету 10% -> упирается в бюджет
    assert ev(good, lost=0.10)["status"] == "budget_limited"
    # Search без прочитанной метрики -> не предлагаем
    assert ev(good, lost=None)["status"] == "unconfirmed"
    # PMax: метрики нет по определению, решает расход и цена
    r = ev(good, app=False)
    assert r["status"] == "raise" and r["lost_applicable"] is False
    # мало заявок: 1 заявка на 240 -> цена не подтверждена
    thin = mk_days([(30, 0, "ЧИСТЫЙ", 50)] * 3 + [(30, 0, "ЧИСТЫЙ", 50)] * 5 + [(30, 1, "ЧИСТЫЙ", 50)] * 0)
    assert ev(thin)["status"] == "unconfirmed"
    # дорогая кампания: цена 150 при цели 110
    dear = mk_days([(30, 0, "ЧИСТЫЙ", 50), (30, 0, "ЧИСТЫЙ", 50), (30, 1, "ЧИСТЫЙ", 50)] + [(30, 0, "ЧИСТЫЙ", 50)] * 5)
    assert ev(dear)["status"] == "unconfirmed"
    # день паузы сторожа с расходом без заявок входит в историю цены (ухудшает оценку), но не в чистые дни
    base = mk_days([(30, 1, "ЧИСТЫЙ", 50)] * 3 + [(30, 1, "ЧИСТЫЙ", 50)] * 4)
    paused = mk_days([(30, 1, "ЧИСТЫЙ", 50)] * 3 + [(30, 1, "ЧИСТЫЙ", 50)] * 4 + [(100, 0, "ПЕРЕХОДНЫЙ", 80)])
    assert ev(paused)["pa"] < ev(base)["pa"]
    # служебные статусы
    assert ev(good, c=cand(skip="тест"))["status"] == "skip"
    assert ev(good, c=cand(enabled=False))["status"] == "off"


def test_levers():
    assert GH.pick_lever(cand(), None, 15)[:3] == ("tcpa", 90.0, 103.5)
    k = GH.pick_lever(cand(bidding="TARGET_SPEND", tcpa=0), {"ceiling": 2.0, "adgroup_max": 0}, 15)
    assert k[0] == "cpc_ceiling" and k[2] == 2.3
    k = GH.pick_lever(cand(bidding="MANUAL_CPC", tcpa=0), {"ceiling": 0, "adgroup_max": 1.5}, 15)
    assert k[0] == "cpc_manual" and k[2] == 1.73
    assert GH.pick_lever(cand(bidding="MAXIMIZE_CONVERSIONS", tcpa=0), None, 15)[0] == "none"


def test_effect():
    row = {"applied_date": (TODAY - timedelta(days=5)).isoformat(), "clean_days": "2026-11-03,2026-11-02,2026-11-01", "cost_3d": 90,
           "leads_3d": 3, "budget": 100, "target": 110}
    after = mk_days([(60, 2, "ЧИСТЫЙ", 50), (70, 2, "ЧИСТЫЙ", 50), (65, 1, "ПЕРЕХОДНЫЙ", 50), (62, 1, "ЧИСТЫЙ", 50)])
    # окно после применения: дни > applied (5 дней назад = 05.11): вчера, 2, 3 (переходный) и 4 дня назад
    txt, done = GH.measure_effect(row, cand(), after, CFG)
    assert done and txt.endswith("цена заявки: измерено"), txt   # после: 2+2+1 = 5 заявок, порог «мало данных» — меньше 5
    thin = mk_days([(60, 1, "ЧИСТЫЙ", 50), (70, 1, "ЧИСТЫЙ", 50), (65, 0, "ПЕРЕХОДНЫЙ", 50), (62, 0, "ЧИСТЫЙ", 50)])
    txt2, done2 = GH.measure_effect(row, cand(), thin, CFG)
    assert done2 and "мало данных" in txt2, txt2
    assert "Расход ×" in txt
    # рано: после применения чистых дней меньше трёх
    row2 = dict(row, applied_date=(TODAY - timedelta(days=2)).isoformat())
    txt, done = GH.measure_effect(row2, cand(), after, CFG)
    assert not done and txt == ""


def test_run_daily_lifecycle():
    tmp = Path(tempfile.mkdtemp()) / "guard_signals.csv"
    sent = []
    state = {"days": None}

    GH.WC.collect = lambda *a, **k: {}
    class ZeroLost:   # потеря по бюджету 0 за любой день
        def get(self, key, default=None):
            return 0.0
    GH.read_lost_shares = lambda ga, enums, cid, ids, d0, d1: (ZeroLost(), {i: True for i in ids})

    def fake_verdict(data, name, day, today):
        s = state["days"].get(day.isoformat())
        if not s:
            return "ВЫХОДНОЙ", 0, 0, None, []
        return s[2], 10, 8, {"cost": s[0], "impr": s[3], "hours": set()}, []
    GH.WC.day_verdict = fake_verdict

    def days_map(today, spec):
        return {(today - timedelta(days=i)).isoformat(): v for i, v in enumerate(spec, start=1)}
    leads_maps = lambda today, spec: ({(d, "кампания"): v[1] for d, v in days_map(today, spec).items()}, {}, {})

    def run(today, spec, notify_list=sent):
        state["days"] = days_map(today, spec)
        calls, ad, forms = leads_maps(today, spec)
        return GH.run_daily(None, type("C", (), {"enums": None})(), "1", today, [cand()], calls, ad, forms, CFG, tmp, "€",
                            lambda m: notify_list.append(m), label="тест")

    spec = [(30, 1, "ЧИСТЫЙ", 50)] * 9
    # день 1: предложение
    lines = run(TODAY, spec)
    rows = GS.load(tmp)
    assert len(rows) == 1 and rows[0]["type"] == GS.TYPE_RAISE and rows[0]["status"] == GS.ST_OFFERED and rows[0]["id"] == "С-001", rows
    assert len(sent) == 1 and "С-001" in sent[0] and "103.5" in sent[0] and "«да»" in sent[0], sent
    # тот же день повторно: дубля нет
    run(TODAY, spec)
    assert len(GS.load(tmp)) == 1 and len(sent) == 1
    # через 3 дня без ответа и недобор держится: одно напоминание
    run(TODAY + timedelta(days=3), spec)
    assert len(sent) == 2 and "без ответа" in sent[1] and GS.load(tmp)[0]["last_reminder"], sent
    run(TODAY + timedelta(days=4), spec)
    assert len(sent) == 2, "напоминание не чаще раза в remind_days"
    # ответ «да» + дата применения; после правки расход вырос, нужны 3 чистых дня
    rows = GS.load(tmp)
    rows[0]["status"], rows[0]["answer_date"], rows[0]["applied_date"] = GS.ST_YES, (TODAY + timedelta(days=4)).isoformat(), (TODAY + timedelta(days=4)).isoformat()
    GS.save(tmp, rows)
    t7 = TODAY + timedelta(days=7)   # применено 4-го; чистые дни 5, 6, 7-1=6.. нужны дни после 4-го: 5, 6 -> всего 2 → рано
    spec7 = [(60, 2, "ЧИСТЫЙ", 80)] * 2 + [(30, 1, "ПЕРЕХОДНЫЙ", 80)] * 1 + [(30, 1, "ЧИСТЫЙ", 50)] * 8
    n_before = len(sent)
    run(t7, spec7)
    assert GS.load(tmp)[0]["status"] == GS.ST_YES and len(sent) == n_before, "рано: итога ещё нет"
    # через день три чистых дня после применения -> итог, статус «закрыт»
    t8 = TODAY + timedelta(days=8)
    spec8 = [(60, 2, "ЧИСТЫЙ", 80)] * 3 + [(30, 1, "ПЕРЕХОДНЫЙ", 80)] + [(30, 1, "ЧИСТЫЙ", 50)] * 7
    run(t8, spec8)
    r0 = GS.load(tmp)[0]
    assert r0["status"] == GS.ST_CLOSED and "Расход ×" in r0["effect"], r0
    assert any("итог подсказки С-001" in m for m in sent), sent
    # после «нет» 7 дней молчим
    tmp.unlink()
    sent.clear()
    run(TODAY, spec)
    rows = GS.load(tmp)
    rows[0]["status"], rows[0]["answer_date"] = GS.ST_NO, TODAY.isoformat()
    GS.save(tmp, rows)
    run(TODAY + timedelta(days=3), spec)
    assert len(GS.load(tmp)) == 1, "7 дней после «нет» нового сигнала нет"
    run(TODAY + timedelta(days=8), spec)
    assert len(GS.load(tmp)) == 2, "через 7+ дней можно снова"


def test_store():
    tmp = Path(tempfile.mkdtemp()) / "s.csv"
    assert GS.load(tmp) == [] and GS.next_id([]) == "С-001"
    GS.save(tmp, [{"id": "С-001", "campaign": "кампания, с запятой", "effect": "а; б"}])
    assert GS.load(tmp)[0]["campaign"] == "кампания, с запятой"
    assert GS.next_id(GS.load(tmp)) == "С-002" and GS.norm_id("3") == "С-003" and GS.norm_id("С-012") == "С-012"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
