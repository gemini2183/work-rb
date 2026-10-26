#!/usr/bin/env python
# coding: utf-8
"""Генератор JSON-плана GTM для посадочной страницы с квизом/формами/кнопками звонка. ТОЛЬКО ЧТЕНИЕ контейнера, пишет только файл плана.

Зачем: на Landver (2026-10-15 и 2026-10-24) теги/триггеры/переменные поведения страницы собирались двумя ручными сборщиками
(`Клиенты/Andverpersonalinjury/Трекинг/build_gtm_plan*.py`). Здесь тот же набор по описанию страницы (spec), идемпотентно:
читает живую версию контейнера и для каждого объекта по имени решает — создать, поправить (если селекторы/код изменились) или пропустить.
Дальше план применяется стандартной цепочкой: `gtm_apply_plan.py` (проверка → --execute) → `gtm_test_version.py` (временная среда) → `gtm_publish_version.py`.

Что собирает (имена как у Landver, чтобы отчёты разных клиентов читались одинаково):
  • GA4-теги: click_tel (место = атрибут кнопки), form_submit (+form_place, quiz_result), email_click, faq_open, block_view, block_time,
    stay_10s / engaged_30s / engaged_90s, scroll_depth 25/50/75, form_popup_open, lead_form_start, cta_click и события страницы из spec.events
    (квиз: quiz_start / quiz_step / quiz_complete / quiz_cta / quiz_restart);
  • HTML-теги: «ldv block_time script» (время на блоках и активное время) и «ldv form start script» (начало заполнения формы Tilda).
Не создаёт: тег Google (GA4 config), Ringostat, Clarity, пиксели — только предупреждает, если их нет.

Spec: JSON с любыми из ключей DEFAULT_SPEC ниже (остальные берутся по умолчанию); минимум — account, container, measurement_id, block_ids.
Id блоков, селекторы окна и FAQ, имена событий страницы берутся из отчёта `page_tracking_check.py` (раздел «события страницы», якоря, блоки с id).

    python gtm_landing_plan.py --spec "Клиенты/<Имя>/Трекинг/spec_<страница>.json" --out "Клиенты/<Имя>/Трекинг/gtm_plan_<дата>.json"
"""
import argparse
import io
import json
import sys
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parent.parent
KEY = Path(__file__).resolve().parent / "secrets" / "rb_cloud_service.json"
BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.readonly"]
ALL_PAGES = "2147479553"

DEFAULT_SPEC = {
    "account": "", "container": "", "measurement_id": "",
    "workspace_name": "landing-tracking", "version_name": "landing tracking: quiz, cta, scroll_depth, form place, popup, blocks",
    "version_notes": "",
    "block_ids": [],                       # id секций по порядку страницы, например ["ldvc", "ldv-how", "ldv-faq", "ldv-footer"]
    "block_names": {},                     # особые имена блоков: {"ldvc": "hero", ".form-record": "form_a"}
    "block_prefix": "ldv-",                # префикс id, который отрезается от имени блока
    "extra_block_selectors": [],           # CSS-селекторы блоков без id (например форма: ".ldv2-native")
    "cta_attr": "data-ldv-cta",            # атрибут кнопки со своим «местом»
    "tel_place_map": {},                   # {часть класса ссылки: место} для кнопок без атрибута (создаются скриптом страницы), например {"quiz__call": "quiz_result"}
    "faq_selector": "details summary",     # вопрос FAQ (клик); строка или список (контейнер общий — перечислять селекторы ВСЕХ страниц, иначе старые перестанут срабатывать)
    "form_place_events": {},               # {"submit_formA": "inline_a", "submit_formB": "inline_b"}: если на странице несколько форм в потоке — место формы по имени события Tilda; пусто = как раньше (popup / inline)
    "popup_hook": "",                      # хук окна формы Tilda, например "#accident-case-review"; пусто = не создавать
    "scroll_thresholds": "25,50,75",
    "events": [                            # события, которые страница пушит в dataLayer -> GA4 (параметры: {GA4: dataLayer})
        {"dl": "quiz_start", "ga4": "quiz_start", "params": {}},
        {"dl": "quiz_step", "ga4": "quiz_step", "params": {"quiz_step": "quiz_step", "quiz_question": "quiz_question", "quiz_answer": "quiz_answer"}},
        {"dl": "quiz_complete", "ga4": "quiz_complete", "params": {"result_tier": "result_tier", "insurer_status": "insurer_status", "treatment_status": "treatment_status"}},
        {"dl": "quiz_cta", "ga4": "quiz_cta", "params": {"cta_type": "cta", "result_tier": "result_tier"}},
        {"dl": "quiz_restart", "ga4": "quiz_restart", "params": {}},
        {"dl": "ldv_cta", "ga4": "cta_click", "params": {"cta_place": "cta_place"}, "trigger": "ldv event cta"},
    ],
    "result_tier_field": "result_tier",    # скрытое поле формы с итогом квиза (для form_submit.quiz_result); "" = не использовать
}


def tmpl(key, value):
    return {"type": "template", "key": key, "value": value}


def call(s, path):
    r = s.get(BASE + path)
    if r.status_code != 200:
        raise SystemExit(f"GTM API GET {path}: {r.status_code} {r.text[:300]}")
    return r.json()


def block_time_script(spec):
    ids = list(spec["block_ids"]) + list(spec["extra_block_selectors"])
    names = dict(spec["block_names"])
    for sel in spec["extra_block_selectors"]:
        names.setdefault(sel, "form_a")
    return ("<script>\n(function () {\n  if (window.__ldvBlockTime) return;\n  window.__ldvBlockTime = true;\n"
            f"  var NAMES = {json.dumps(names, ensure_ascii=False)};\n  var IDS = {json.dumps(ids, ensure_ascii=False)};\n"
            f"  var PREFIX = {json.dumps(spec['block_prefix'])};\n"
            "  var STEPS = [[10, 'stay_10s'], [30, 'engaged_30s'], [90, 'engaged_90s']];\n"
            "  var TICK = 500, IDLE = 10000, FLUSH = 30000;\n"
            "  var acc = {}, total = 0, current = 'header', lastTick = Date.now(), lastActive = Date.now(), lastFlush = Date.now();\n"
            "  window.dataLayer = window.dataLayer || [];\n"
            "  function nameOf(id) { return NAMES[id] || id.replace(new RegExp('^' + PREFIX), '').replace(/-/g, '_'); }\n"
            "  function find(id) { return /^[.#\\[]/.test(id) ? document.querySelector(id) : document.getElementById(id); }\n"
            "  function currentBlock() {\n    var mid = window.innerHeight / 2, name = 'header', best = -1e9;\n"
            "    for (var i = 0; i < IDS.length; i++) {\n      var el = find(IDS[i]);\n      if (!el) continue;\n"
            "      var top = el.getBoundingClientRect().top;\n      if (top <= mid && top > best) { best = top; name = nameOf(IDS[i]); }\n    }\n    return name;\n  }\n"
            "  function flush(final) {\n    for (var k in acc) {\n      var s = final ? Math.round(acc[k]) : Math.floor(acc[k]);\n"
            "      if (s >= 1) { window.dataLayer.push({ event: 'block_time', block_name: k, block_seconds: s }); acc[k] -= s; }\n    }\n    lastFlush = Date.now();\n  }\n"
            "  function active() { lastActive = Date.now(); }\n"
            "  ['scroll', 'mousemove', 'keydown', 'touchstart', 'click', 'wheel'].forEach(function (e) { window.addEventListener(e, active, { passive: true }); });\n"
            "  setInterval(function () {\n    var now = Date.now(), dt = now - lastTick;\n    lastTick = now;\n    var block = currentBlock();\n"
            "    if (document.visibilityState === 'visible' && now - lastActive <= IDLE && dt < 5000) {\n"
            "      acc[block] = (acc[block] || 0) + dt / 1000;\n      total += dt / 1000;\n"
            "      while (STEPS.length && total >= STEPS[0][0]) { window.dataLayer.push({ event: STEPS[0][1] }); STEPS.shift(); }\n    }\n"
            "    if (block !== current) { flush(false); current = block; }\n    else if (now - lastFlush >= FLUSH) { flush(false); }\n  }, TICK);\n"
            "  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') flush(true); });\n"
            "  window.addEventListener('pagehide', function () { flush(true); });\n})();\n</script>")


FORM_START = ("<script>(function(){if(window.__ldvFormStart)return;window.__ldvFormStart=true;var seen={};"
              "document.addEventListener('focusin',function(e){var t=e.target;if(!t||!t.closest||t.type==='hidden')return;"
              "var f=t.closest('form.t-form');if(!f)return;var id=f.id||'form';if(seen[id])return;seen[id]=1;"
              "(window.dataLayer=window.dataLayer||[]).push({event:'ldv_form_start',form_place:f.closest('.t-popup')?'popup':'inline'});},true);})();</script>")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sp = Path(a.spec)
    spec = dict(DEFAULT_SPEC)
    spec.update(json.loads((sp if sp.is_absolute() else ROOT / sp).read_text(encoding="utf-8")))
    for k in ("account", "container", "measurement_id"):
        if not spec[k]:
            raise SystemExit(f"в spec нет «{k}»")
    MID = spec["measurement_id"]
    s = AuthorizedSession(service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES))
    live = call(s, f"accounts/{spec['account']}/containers/{spec['container']}/versions:live")
    have_tag = {t["name"]: t for t in live.get("tag", [])}
    have_trg = {t["name"]: t for t in live.get("trigger", [])}
    have_var = {v["name"]: v for v in live.get("variable", [])}
    print(f"Живая версия {live.get('containerVersionId')} «{live.get('name', '')}»: тегов {len(have_tag)}, триггеров {len(have_trg)}, переменных {len(have_var)}")
    if not any(t.get("type") == "googtag" and any(p.get("value") == MID for p in t.get("parameter", [])) for t in have_tag.values()):
        print(f"ВНИМАНИЕ: в контейнере нет Google-тега с {MID}; теги GA4 используют measurementIdOverride, но тег конфигурации нужен (создать вручную).")
    for need, label in (("ringo", "Ringostat"), ("clarity", "Clarity")):
        if not any(need in json.dumps(t, ensure_ascii=False).lower() for t in have_tag.values()):
            print(f"Заметка: в контейнере не найден {label} (если нужен — добавить отдельно).")

    plan = {"account": spec["account"], "container": spec["container"], "workspace_name": spec["workspace_name"],
            "version_name": spec["version_name"], "version_notes": spec["version_notes"], "built_in_variables": ["clickElement", "clickClasses", "clickUrl", "clickText", "scrollDepthThreshold"],
            "variables": [], "triggers": [], "tags": [], "update_tags": [], "update_variables": [], "update_triggers": []}
    created, updated, skipped = [], [], []

    def ensure_var(v):
        if v["name"] in have_var:
            skipped.append("переменная " + v["name"]); return
        plan["variables"].append(v); created.append("переменная " + v["name"])

    def ensure_trg(t):
        if t["name"] in have_trg:
            skipped.append("триггер " + t["name"]); return
        plan["triggers"].append(t); created.append("триггер " + t["name"])

    def ensure_tag(name, event, params, triggers, update_params=False):
        if name in have_tag:
            if update_params and params:
                plan["update_tags"].append({"name": name, "set_event_parameters": params}); updated.append("тег " + name + " (параметры)")
            else:
                skipped.append("тег " + name)
            return
        rows = [{"type": "map", "map": [tmpl("parameter", k), tmpl("parameterValue", v)]} for k, v in (params or {}).items()]
        p = [{"type": "boolean", "key": "sendEcommerceData", "value": "false"}, tmpl("eventName", event), tmpl("measurementIdOverride", MID)]
        if rows:
            p.append({"type": "list", "key": "eventSettingsTable", "list": rows})
        plan["tags"].append({"name": name, "type": "gaawe", "parameter": p, "firingTriggerNames": triggers})
        created.append("тег " + name)

    def custom_event(name, ev):
        return {"name": name, "type": "customEvent", "customEventFilter": [{"type": "equals", "parameter": [tmpl("arg0", "{{_event}}"), tmpl("arg1", ev)]}]}

    def jsm(name, code):
        return {"name": name, "type": "jsm", "parameter": [tmpl("javascript", code)]}

    def dlv(name, key):
        return {"name": name, "type": "v", "parameter": [{"type": "integer", "key": "dataLayerVersion", "value": "2"},
                                                          {"type": "boolean", "key": "setDefaultValue", "value": "false"}, tmpl("name", key)]}

    # ---- переменные места клика и имени блока (правятся, если уже есть: у страницы могли смениться атрибуты и блоки)
    names_js = json.dumps(spec["block_names"], ensure_ascii=False)
    extra = spec["extra_block_selectors"]
    cls_check = "".join(f"if(e.matches&&e.matches({json.dumps(x)}))return 'form_a';" for x in extra)
    block_js = (f"function(){{var e={{{{Click Element}}}};if(!e)return '';var m={names_js};{cls_check}var id=e.id||'';"
                f"return m[id]||id.replace(/^{spec['block_prefix']}/,'').replace(/-/g,'_');}}")
    tel_js = (f"function(){{var e={{{{Click Element}}}};var d=e&&e.closest?e.closest('[{spec['cta_attr']}]'):null;"
              f"if(d)return d.getAttribute('{spec['cta_attr']}');var a=e&&e.closest?e.closest('a'):null;var c=String((a&&a.className)||'');"
              f"var m={json.dumps(spec['tel_place_map'], ensure_ascii=False)};for(var k in m){{if(c.indexOf(k)>-1)return m[k];}}return 'other';}}")
    for name, code in (("ldv block name (visibility)", block_js), ("ldv tel place", tel_js)):
        if name in have_var:
            plan["update_variables"].append({"name": name, "set_parameter": {"javascript": code}}); updated.append("переменная " + name)
        else:
            ensure_var(jsm(name, code))
    if spec["form_place_events"]:
        fp_code = ("function(){if(document.querySelector('.t-popup_show'))return 'popup';var m=" + json.dumps(spec["form_place_events"]) +
                   ";return m[{{_event}}]||'inline';}")
        if "ldv form place" in have_var:
            plan["update_variables"].append({"name": "ldv form place", "set_parameter": {"javascript": fp_code}}); updated.append("переменная ldv form place (форма A/B по событию)")
        else:
            ensure_var(jsm("ldv form place", fp_code))
    else:
        ensure_var(jsm("ldv form place", "function(){return document.querySelector('.t-popup_show')?'popup':'inline';}"))
    if spec["result_tier_field"]:
        ensure_var(jsm("ldv quiz result", "function(){var i=document.querySelectorAll('input[name=\"" + spec["result_tier_field"] + "\"]');"
                                           "for(var k=0;k<i.length;k++){if(i[k].value)return i[k].value;}return 'none';}"))
    faq_list = spec["faq_selector"] if isinstance(spec["faq_selector"], list) else [spec["faq_selector"]]
    ensure_var(jsm("ldv faq question", "function(){var e={{Click Element}};var b=e&&e.closest?e.closest('" + faq_list[0].split()[-1] + "'):null;"
                                       "return b?b.innerText.replace(/^\\s*\\d+\\s*/,'').replace(/\\s+/g,' ').trim().slice(0,100):'';}"))
    for v in ("block_name", "block_seconds", "form_place", "cta_place"):
        ensure_var(dlv("dlv " + v, v))
    for ev in spec["events"]:
        for dl in ev["params"].values():
            ensure_var(dlv("dlv " + dl, dl))

    # ---- видимость блоков
    sel = ", ".join(["#" + i for i in spec["block_ids"] if not i.startswith((".", "#", "["))] + [i for i in spec["block_ids"] if i.startswith((".", "#", "["))] + spec["extra_block_selectors"])
    if "ldv block visible" in have_trg:
        plan["update_triggers"].append({"name": "ldv block visible", "set_parameter": {"elementSelector": sel}}); updated.append("триггер ldv block visible (селектор блоков)")
    else:
        ensure_trg({"name": "ldv block visible", "type": "elementVisibility", "parameter": [
            tmpl("selectorType", "CSS"), tmpl("elementSelector", sel), tmpl("firingFrequency", "ONCE_PER_ELEMENT"), tmpl("onScreenRatio", "10"),
            {"type": "boolean", "key": "useOnScreenDuration", "value": "true"}, tmpl("onScreenDuration", "1000"),
            {"type": "boolean", "key": "useDomChangeListener", "value": "false"}]})
    ensure_tag("GA4 - block_view", "block_view", {"block_name": "{{ldv block name (visibility)}}"}, ["ldv block visible"])
    for ev in ("block_time", "stay_10s", "engaged_30s", "engaged_90s"):
        ensure_trg(custom_event(f"ldv event {ev}", ev))
    ensure_tag("GA4 - block_time", "block_time", {"block_name": "{{dlv block_name}}", "block_seconds": "{{dlv block_seconds}}"}, ["ldv event block_time"])
    for ev in ("stay_10s", "engaged_30s", "engaged_90s"):
        ensure_tag(f"GA4 - {ev}", ev, None, [f"ldv event {ev}"])
    html_bt = block_time_script(spec)
    if "ldv block_time script" in have_tag:
        plan["update_tags"].append({"name": "ldv block_time script", "set_html": html_bt}); updated.append("тег ldv block_time script (список блоков)")
    else:
        plan["tags"].append({"name": "ldv block_time script", "type": "html", "parameter": [tmpl("html", html_bt), {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}], "firingTriggerIds": [ALL_PAGES]})
        created.append("тег ldv block_time script")

    # ---- клики: номер, почта, FAQ
    ensure_trg({"name": "click_tel 2", "type": "linkClick", "filter": [{"type": "contains", "parameter": [tmpl("arg0", "{{Click URL}}"), tmpl("arg1", "tel:")]}]})
    if "GA4 - click_tel" in have_tag:
        skipped.append("тег GA4 - click_tel (место клика берётся из переменной «ldv tel place», она обновлена)")
    else:
        ensure_tag("GA4 - click_tel", "click_tel", {"click_place": "{{ldv tel place}}"}, ["click_tel 2"])
    ensure_trg({"name": "ldv mailto click", "type": "linkClick", "filter": [{"type": "contains", "parameter": [tmpl("arg0", "{{Click URL}}"), tmpl("arg1", "mailto:")]}]})
    ensure_tag("GA4 - email_click", "email_click", None, ["ldv mailto click"])
    faq_sel = ", ".join(f"{x}, {x} *" for x in faq_list)
    if "ldv faq question click" in have_trg:
        plan["update_triggers"].append({"name": "ldv faq question click", "set_filter_arg1": faq_sel + ", .ldv-faq__question, .ldv-faq__question *"}); updated.append("триггер ldv faq question click")
    else:
        ensure_trg({"name": "ldv faq question click", "type": "click", "filter": [{"type": "cssSelector", "parameter": [tmpl("arg0", "{{Click Element}}"), tmpl("arg1", faq_sel)]}]})
    ensure_tag("GA4 - faq_open", "faq_open", {"faq_question": "{{ldv faq question}}"}, ["ldv faq question click"])

    # ---- форма: отправка Tilda = submit_<id формы>; место и итог квиза
    ensure_trg({"name": "submit_form", "type": "customEvent", "customEventFilter": [{"type": "matchRegex", "parameter": [tmpl("arg0", "{{_event}}"), tmpl("arg1", "submit_form*")]}]})
    fs = {"form_place": "{{ldv form place}}"}
    if spec["result_tier_field"]:
        fs["quiz_result"] = "{{ldv quiz result}}"
    ensure_tag("GA4 - form_submit", "form_submit", fs, ["submit_form"], update_params=True)
    if "ldv form start script" not in have_tag:
        plan["tags"].append({"name": "ldv form start script", "type": "html", "parameter": [tmpl("html", FORM_START), {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}], "firingTriggerIds": [ALL_PAGES]})
        created.append("тег ldv form start script")
    ensure_trg(custom_event("ldv event form_start", "ldv_form_start"))
    ensure_tag("GA4 - lead_form_start", "lead_form_start", {"form_place": "{{dlv form_place}}"}, ["ldv event form_start"])
    if spec["popup_hook"]:
        ensure_trg({"name": "ldv form popup visible", "type": "elementVisibility", "parameter": [
            tmpl("selectorType", "CSS"), tmpl("elementSelector", f'.t-popup[data-tooltip-hook="{spec["popup_hook"]}"]'), tmpl("firingFrequency", "ONCE_PER_PAGE"),
            tmpl("onScreenRatio", "50"), {"type": "boolean", "key": "useOnScreenDuration", "value": "false"}, {"type": "boolean", "key": "useDomChangeListener", "value": "true"}]})
        ensure_tag("GA4 - form_popup_open", "form_popup_open", None, ["ldv form popup visible"])

    # ---- прокрутка и события страницы
    ensure_trg({"name": "ldv scroll depth", "type": "scrollDepth", "parameter": [
        {"type": "boolean", "key": "verticalThresholdOn", "value": "true"}, tmpl("verticalThresholdUnits", "PERCENT"),
        tmpl("verticalThresholdsPercent", spec["scroll_thresholds"]), {"type": "boolean", "key": "horizontalThresholdOn", "value": "false"},
        tmpl("triggerStartOption", "WINDOW_LOAD")]})
    ensure_tag("GA4 - scroll_depth", "scroll_depth", {"scroll_percent": "{{Scroll Depth Threshold}}"}, ["ldv scroll depth"])
    for ev in spec["events"]:
        tn = ev.get("trigger") or f"ldv event {ev['dl']}"
        ensure_trg(custom_event(tn, ev["dl"]))
        ensure_tag(f"GA4 - {ev['ga4']}", ev["ga4"], {g: "{{dlv " + d + "}}" for g, d in ev["params"].items()}, [tn])

    out = Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nСоздать: {len(created)}; поправить: {len(updated)}; уже есть: {len(skipped)}")
    for x in created:
        print("  + ", x)
    for x in updated:
        print("  ~ ", x)
    print(f"\nПлан записан: {out}\nДальше: gtm_apply_plan.py --plan … (проверка) → --execute → gtm_test_version.py → gtm_publish_version.py")
    print("GA4: параметры событий зарегистрировать — ga4_custom_definitions.py (список параметров: "
          + ", ".join(sorted({g for ev in spec['events'] for g in ev['params']} | {'cta_place', 'form_place', 'quiz_result', 'scroll_percent', 'click_place', 'block_name', 'faq_question'})) + ")")


if __name__ == "__main__":
    main()
