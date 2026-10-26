# coding: utf-8
"""Собирает gtm_plan_car_2026-10-24.json для Скрипты/gtm_apply_plan.py (GTM-KVLHDKJJ, страница california-car-accident-lawyer).

Что добавляет к версии 6 (2026-10-15, страница car+truck): события квиза и CTA, которые страница уже пушит в dataLayer,
глубину прокрутки, открытие окна формы, начало заполнения формы, место и итог квиза у form_submit; переводит блоки
block_view / block_time и место клика по номеру на разметку новой страницы (старая продолжает работать).
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MID = "G-JPLC4Q41PS"
ALL_PAGES = "2147479553"

OLD_IDS = ['ldv-ai-hero', 'ldv-your-crash', 'ldv-crash-scenarios', 'ldv-case-examples', 'ldv-truck-cases',
           'ldv-evidence', 'ldv-mid-review', 'ldv-public-library', 'ldv-injuries', 'ldv-early-offer',
           'ldv-case-value', 'ldv-case-process', 'ldv-why-landver', 'ldv-reviews', 'ldv-faq',
           'ldv-final-review', 'ldv-footer']
# новая страница; форма A — по классу .ldv2-native (его добавляет скрипт страницы к блоку формы), «ldv-form-section» — только заголовок формы
NEW_IDS = ['ldvc', 'ldv-insurers', 'ldv-how', 'ldv-fee', 'ldv-team', 'ldv-situations', 'ldv-attorney', 'ldvq', 'ldv-final']
SELECTOR = ", ".join(["#" + i for i in OLD_IDS + [x for x in NEW_IDS if x not in OLD_IDS]] + [".ldv2-native"])


def tmpl(key, value):
    return {"type": "template", "key": key, "value": value}


def ga4_event(name, event, params=None, triggers=()):
    rows = [{"type": "map", "map": [tmpl("parameter", k), tmpl("parameterValue", v)]} for k, v in (params or {}).items()]
    p = [{"type": "boolean", "key": "sendEcommerceData", "value": "false"}, tmpl("eventName", event),
         tmpl("measurementIdOverride", MID)]
    if rows:
        p.append({"type": "list", "key": "eventSettingsTable", "list": rows})
    return {"name": name, "type": "gaawe", "parameter": p, "firingTriggerNames": list(triggers)}


def custom_event_trigger(name, event):
    return {"name": name, "type": "customEvent",
            "customEventFilter": [{"type": "equals", "parameter": [tmpl("arg0", "{{_event}}"), tmpl("arg1", event)]}]}


def jsm(name, code):
    return {"name": name, "type": "jsm", "parameter": [tmpl("javascript", code)]}


def dlv(name, key):
    return {"name": name, "type": "v", "parameter": [
        {"type": "integer", "key": "dataLayerVersion", "value": "2"},
        {"type": "boolean", "key": "setDefaultValue", "value": "false"}, tmpl("name", key)]}


def html_tag(name, html):
    return {"name": name, "type": "html", "parameter": [tmpl("html", html), {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}],
            "firingTriggerIds": [ALL_PAGES]}


block_time = re.search(r"<script>.*</script>", (HERE / "gtm_block_time_v2.js").read_text(encoding="utf-8"), re.S).group(0)

form_start = ("<script>(function(){if(window.__ldvFormStart)return;window.__ldvFormStart=true;var seen={};"
              "document.addEventListener('focusin',function(e){var t=e.target;if(!t||!t.closest||t.type==='hidden')return;"
              "var f=t.closest('form.t-form');if(!f)return;var id=f.id||'form';if(seen[id])return;seen[id]=1;"
              "(window.dataLayer=window.dataLayer||[]).push({event:'ldv_form_start',form_place:f.closest('.t-popup')?'popup':'inline'});},true);})();</script>")

BLOCK_NAME_JS = ("function(){var e={{Click Element}};if(!e)return '';var m={'ldvc':'hero','ldvq':'quiz','ldv-form-section':'form_a'};"
                 "if(e.classList&&e.classList.contains('ldv2-native'))return 'form_a';var id=e.id||'';"
                 "return m[id]||id.replace(/^ldv-/,'').replace(/-/g,'_');}")
TEL_PLACE_JS = ("function(){var e={{Click Element}};var d=e&&e.closest?e.closest('[data-ldv-cta]'):null;"
                "if(d)return d.getAttribute('data-ldv-cta');var a=e&&e.closest?e.closest('a'):null;var c=String((a&&a.className)||'');"
                "if(c.indexOf('ldvq5__button--call')>-1||c.indexOf('ldvq__btn--call')>-1)return 'quiz_result';"
                "var m={'ldv-h__phone':'header','ldv-mob-call':'mobile_bar','ldv-ai-hero__call':'hero',"
                "'ldv-fr__phone':'final_form','ldv-ft__phone':'footer'};"
                "for(var k in m){if(c.indexOf(k)>-1)return m[k];}return 'other';}")

plan = {
    "account": "6353362488", "container": "261134482",
    "workspace_name": "ldv-car-page-2026-10-24",
    "version_name": "ldv car page: quiz, cta, scroll_depth, form place, popup, blocks for california-car-accident-lawyer",
    "version_notes": "Landver tilda california-car-accident-lawyer, 2026-10-24. Откат: опубликовать версию 6.",
    "built_in_variables": ["scrollDepthThreshold"],
    "variables": [
        jsm("ldv form place", "function(){return document.querySelector('.t-popup_show')?'popup':'inline';}"),
        jsm("ldv quiz result",
            "function(){var i=document.querySelectorAll('input[name=\"result_tier\"]');"
            "for(var k=0;k<i.length;k++){if(i[k].value)return i[k].value;}return 'none';}"),
        dlv("dlv quiz_step", "quiz_step"),
        dlv("dlv quiz_question", "quiz_question"),
        dlv("dlv quiz_answer", "quiz_answer"),
        dlv("dlv result_tier", "result_tier"),
        dlv("dlv insurer_status", "insurer_status"),
        dlv("dlv treatment_status", "treatment_status"),
        dlv("dlv cta", "cta"),
        dlv("dlv cta_place", "cta_place"),
        dlv("dlv form_place", "form_place"),
    ],
    "triggers": [
        custom_event_trigger("ldv event quiz_start", "quiz_start"),
        custom_event_trigger("ldv event quiz_step", "quiz_step"),
        custom_event_trigger("ldv event quiz_complete", "quiz_complete"),
        custom_event_trigger("ldv event quiz_cta", "quiz_cta"),
        custom_event_trigger("ldv event quiz_restart", "quiz_restart"),
        custom_event_trigger("ldv event cta", "ldv_cta"),
        custom_event_trigger("ldv event form_start", "ldv_form_start"),
        {"name": "ldv scroll depth", "type": "scrollDepth", "parameter": [
            {"type": "boolean", "key": "verticalThresholdOn", "value": "true"},
            tmpl("verticalThresholdUnits", "PERCENT"), tmpl("verticalThresholdsPercent", "25,50,75"),
            {"type": "boolean", "key": "horizontalThresholdOn", "value": "false"},
            tmpl("triggerStartOption", "WINDOW_LOAD")]},
        {"name": "ldv form popup visible", "type": "elementVisibility", "parameter": [
            tmpl("selectorType", "CSS"), tmpl("elementSelector", '.t-popup[data-tooltip-hook="#accident-case-review"]'),
            tmpl("firingFrequency", "ONCE_PER_PAGE"), tmpl("onScreenRatio", "50"),
            {"type": "boolean", "key": "useOnScreenDuration", "value": "false"},
            {"type": "boolean", "key": "useDomChangeListener", "value": "true"}]},
    ],
    "tags": [
        ga4_event("GA4 - quiz_start", "quiz_start", None, ["ldv event quiz_start"]),
        ga4_event("GA4 - quiz_step", "quiz_step",
                  {"quiz_step": "{{dlv quiz_step}}", "quiz_question": "{{dlv quiz_question}}", "quiz_answer": "{{dlv quiz_answer}}"},
                  ["ldv event quiz_step"]),
        ga4_event("GA4 - quiz_complete", "quiz_complete",
                  {"result_tier": "{{dlv result_tier}}", "insurer_status": "{{dlv insurer_status}}",
                   "treatment_status": "{{dlv treatment_status}}"}, ["ldv event quiz_complete"]),
        ga4_event("GA4 - quiz_cta", "quiz_cta", {"cta_type": "{{dlv cta}}", "result_tier": "{{dlv result_tier}}"}, ["ldv event quiz_cta"]),
        ga4_event("GA4 - quiz_restart", "quiz_restart", None, ["ldv event quiz_restart"]),
        ga4_event("GA4 - cta_click", "cta_click", {"cta_place": "{{dlv cta_place}}"}, ["ldv event cta"]),
        ga4_event("GA4 - lead_form_start", "lead_form_start", {"form_place": "{{dlv form_place}}"}, ["ldv event form_start"]),
        ga4_event("GA4 - scroll_depth", "scroll_depth", {"scroll_percent": "{{Scroll Depth Threshold}}"}, ["ldv scroll depth"]),
        ga4_event("GA4 - form_popup_open", "form_popup_open", None, ["ldv form popup visible"]),
        html_tag("ldv form start script", form_start),
    ],
    "update_tags": [
        {"name": "GA4 - form_submit", "set_event_parameters": {"form_place": "{{ldv form place}}", "quiz_result": "{{ldv quiz result}}"}},
        {"name": "ldv block_time script", "set_html": block_time},
    ],
    "update_variables": [
        {"name": "ldv block name (visibility)", "set_parameter": {"javascript": BLOCK_NAME_JS}},
        {"name": "ldv tel place", "set_parameter": {"javascript": TEL_PLACE_JS}},
    ],
    "update_triggers": [
        {"name": "ldv block visible", "set_parameter": {"elementSelector": SELECTOR}},
    ],
}
(HERE / "gtm_plan_car_2026-10-24.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("plan written:", len(plan["tags"]), "tags,", len(plan["triggers"]), "triggers,", len(plan["variables"]), "variables")
print("selector:", SELECTOR)
