# coding: utf-8
"""Собирает gtm_plan_2026-10-15.json для Скрипты/gtm_apply_plan.py (GTM-KVLHDKJJ, tilda car+truck)."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MID = "G-JPLC4Q41PS"
ALL_PAGES = "2147479553"  # встроенный триггер All Pages (как у тегов Ringostat и OpenAI Pixel — Init)

BLOCK_IDS = ['ldv-ai-hero', 'ldv-your-crash', 'ldv-crash-scenarios', 'ldv-case-examples', 'ldv-truck-cases',
             'ldv-evidence', 'ldv-mid-review', 'ldv-public-library', 'ldv-injuries', 'ldv-early-offer',
             'ldv-case-value', 'ldv-case-process', 'ldv-why-landver', 'ldv-reviews', 'ldv-faq',
             'ldv-final-review', 'ldv-footer']


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


script = (HERE / "gtm_block_time.js").read_text(encoding="utf-8")
html_block_time = re.search(r"<script>.*</script>", script, re.S).group(0)
clarity = ('<script type="text/javascript">(function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};'
           't=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;y=l.getElementsByTagName(r)[0];'
           'y.parentNode.insertBefore(t,y);})(window,document,"clarity","script","yy4382dsrf");</script>')


def html_tag(name, html):
    return {"name": name, "type": "html", "parameter": [tmpl("html", html), {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}],
            "firingTriggerIds": [ALL_PAGES]}


plan = {
    "account": "6353362488", "container": "261134482",
    "workspace_name": "ldv-tracking-2026-10-15",
    "version_name": "ldv tracking: block_view, block_time, engaged, faq, email, tel place, Clarity",
    "version_notes": "Landver tilda car+truck, 2026-10-15. Откат: опубликовать версию 5.",
    "built_in_variables": ["clickElement", "clickClasses", "clickUrl", "clickText"],
    "variables": [
        jsm("ldv block name (visibility)",
            "function(){var e={{Click Element}};return ((e&&e.id)||'').replace(/^ldv-/,'').replace(/-/g,'_');}"),
        jsm("ldv tel place",
            "function(){var e={{Click Element}};var a=e&&e.closest?e.closest('a'):null;var c=(a&&a.className)||'';"
            "var m={'ldv-h__phone':'header','ldv-mob-call':'mobile_bar','ldv-ai-hero__call':'hero',"
            "'ldv-fr__phone':'final_form','ldv-ft__phone':'footer'};"
            "for(var k in m){if(String(c).indexOf(k)>-1)return m[k];}return 'other';}"),
        jsm("ldv faq question",
            "function(){var e={{Click Element}};var b=e&&e.closest?e.closest('.ldv-faq__question'):null;"
            "return b?b.innerText.replace(/^\\s*\\d+\\s*/,'').replace(/\\s+/g,' ').trim().slice(0,100):'';}"),
        dlv("dlv block_name", "block_name"),
        dlv("dlv block_seconds", "block_seconds"),
    ],
    "triggers": [
        {"name": "ldv block visible", "type": "elementVisibility", "parameter": [
            tmpl("selectorType", "CSS"), tmpl("elementSelector", ", ".join("#" + i for i in BLOCK_IDS)),
            tmpl("firingFrequency", "ONCE_PER_ELEMENT"), tmpl("onScreenRatio", "10"),
            {"type": "boolean", "key": "useOnScreenDuration", "value": "true"}, tmpl("onScreenDuration", "1000"),
            {"type": "boolean", "key": "useDomChangeListener", "value": "false"}]},
        custom_event_trigger("ldv event block_time", "block_time"),
        custom_event_trigger("ldv event stay_10s", "stay_10s"),
        custom_event_trigger("ldv event engaged_30s", "engaged_30s"),
        custom_event_trigger("ldv event engaged_90s", "engaged_90s"),
        {"name": "ldv faq question click", "type": "click",
         "filter": [{"type": "cssSelector", "parameter": [
             tmpl("arg0", "{{Click Element}}"), tmpl("arg1", ".ldv-faq__question, .ldv-faq__question *")]}]},
        {"name": "ldv mailto click", "type": "linkClick",
         "filter": [{"type": "contains", "parameter": [tmpl("arg0", "{{Click URL}}"), tmpl("arg1", "mailto:")]}]},
    ],
    "tags": [
        ga4_event("GA4 - block_view", "block_view", {"block_name": "{{ldv block name (visibility)}}"}, ["ldv block visible"]),
        ga4_event("GA4 - block_time", "block_time",
                  {"block_name": "{{dlv block_name}}", "block_seconds": "{{dlv block_seconds}}"}, ["ldv event block_time"]),
        ga4_event("GA4 - stay_10s", "stay_10s", None, ["ldv event stay_10s"]),
        ga4_event("GA4 - engaged_30s", "engaged_30s", None, ["ldv event engaged_30s"]),
        ga4_event("GA4 - engaged_90s", "engaged_90s", None, ["ldv event engaged_90s"]),
        ga4_event("GA4 - faq_open", "faq_open", {"faq_question": "{{ldv faq question}}"}, ["ldv faq question click"]),
        ga4_event("GA4 - email_click", "email_click", None, ["ldv mailto click"]),
        html_tag("ldv block_time script", html_block_time),
        html_tag("Microsoft Clarity (tilda, yy4382dsrf)", clarity),
    ],
    "update_tags": [{"name": "GA4 - click_tel", "set_event_parameters": {"click_place": "{{ldv tel place}}"}}],
}
(HERE / "gtm_plan_2026-10-15.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("plan written:", len(plan["tags"]), "tags")
