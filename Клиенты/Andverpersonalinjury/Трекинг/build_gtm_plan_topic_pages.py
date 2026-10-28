# -*- coding: utf-8 -*-
"""План GTM для тематических страниц Landver, собранных вручную (блоки vb-…, формы с id vb-…-form): Wrongful Death, Brain Injury, Rideshare и будущие *-lawyer-california.

Решение пользователя 2026-10-28: измерять поведение (форма, FAQ, блоки, время по блокам) на всех таких страницах. Все объекты — НОВЫЕ, в папке «Topic pages (vb)»,
с суффиксом « [topic pages]»; общий регэксп вместо id: форма `^submit_vb-.+-form$`, страницы по Page Path `-lawyer-california/?$`.
Единственная правка старого объекта: тегу «ldv block_time script» добавлен исключающий триггер «topic pages pageview [topic pages]» (иначе он пишет всё время в блок header);
stay_10s / engaged_* на этих страницах пушит новый тег.

    python build_gtm_plan_topic_pages.py   ->  gtm_plan_topic_pages_2026-10-28.json
    python Скрипты/gtm_apply_plan.py --plan Клиенты/Andverpersonalinjury/Трекинг/gtm_plan_topic_pages_2026-10-28.json [--execute]
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
MID = "G-JPLC4Q41PS"
SUF = " [topic pages]"
FOLDER = "Topic pages (vb)"
PAGE_RE = "-lawyer-california/?$"


def t(key, value):
    return {"type": "template", "key": key, "value": value}


page_filter = {"type": "matchRegex", "parameter": [t("arg0", "{{Page Path}}"), t("arg1", PAGE_RE), t("ignore_case", "true")]}

variables = [
    {"name": "vb block name" + SUF, "type": "jsm", "folder": FOLDER, "parameter": [t("javascript",
        "function(){var e={{Click Element}};if(!e)return '';var s=(e.textContent||'').replace(/\\s+/g,' ').trim().toLowerCase()"
        ".replace(/[^a-z0-9 ]+/g,'').split(' ').slice(0,5).join('_');return s||e.id||'';}")]},
    {"name": "vb faq question" + SUF, "type": "jsm", "folder": FOLDER, "parameter": [t("javascript",
        "function(){var e={{Click Element}};var s=e&&e.closest?e.closest('summary'):null;"
        "return s?(s.textContent||'').replace(/\\s+/g,' ').trim().slice(0,100):'';}")]},
]

triggers = [
    {"name": "submit vb form" + SUF, "type": "customEvent", "folder": FOLDER,
     "customEventFilter": [{"type": "matchRegex", "parameter": [t("arg0", "{{_event}}"), t("arg1", "^submit_vb-.+-form$")]}]},
    {"name": "topic pages pageview" + SUF, "type": "pageview", "folder": FOLDER, "filter": [page_filter]},
    {"name": "vb faq click" + SUF, "type": "click", "folder": FOLDER, "filter": [
        {"type": "cssSelector", "parameter": [t("arg0", "{{Click Element}}"), t("arg1", "details > summary, details > summary *")]}, page_filter]},
    {"name": "vb block visible" + SUF, "type": "elementVisibility", "folder": FOLDER, "filter": [page_filter], "parameter": [
        t("selectorType", "CSS"), t("elementSelector", '[id^="vb-"][id$="-h1"], [id^="vb-"][id$="-h2"], [id^="vb-"][id$="-title"]'),
        t("firingFrequency", "ONCE_PER_ELEMENT"), t("onScreenRatio", "10"),
        {"type": "boolean", "key": "useOnScreenDuration", "value": "true"}, t("onScreenDuration", "1000"),
        {"type": "boolean", "key": "useDomChangeListener", "value": "false"}]},
]


def ga4(name, event, params, trigger):
    rows = [{"type": "map", "map": [t("parameter", k), t("parameterValue", v)]} for k, v in params.items()]
    return {"name": name, "type": "gaawe", "folder": FOLDER, "firingTriggerNames": [trigger], "tagFiringOption": "oncePerEvent",
            "consentSettings": {"consentStatus": "notSet"}, "parameter": [
                {"type": "boolean", "key": "sendEcommerceData", "value": "false"}, t("eventName", event), t("measurementIdOverride", MID),
                {"type": "list", "key": "eventSettingsTable", "list": rows}]}


block_time_html = re.search(r"<script>.*</script>", (HERE / "gtm_block_time_topic.js").read_text(encoding="utf-8"), re.S).group(0)

tags = [
    ga4("GA4 - form_submit" + SUF, "form_submit", {"form_place": "inline"}, "submit vb form" + SUF),
    {"name": "OpenAI Pixel — Lead Created" + SUF, "type": "cvt_NS4HN", "folder": FOLDER, "firingTriggerNames": ["submit vb form" + SUF],
     "setupTag": [{"tagName": "OpenAI Pixel — Init"}], "tagFiringOption": "oncePerEvent", "consentSettings": {"consentStatus": "notSet"},
     "parameter": [t("pixelId", "Wbtsm5RxTw9Rn4YVjh8W2Y"), {"type": "boolean", "key": "enableDebug", "value": "false"},
                   {"type": "boolean", "key": "sendEvent", "value": "true"}, t("eventName", "lead_created")]},
    ga4("GA4 - faq_open" + SUF, "faq_open", {"faq_question": "{{vb faq question" + SUF + "}}"}, "vb faq click" + SUF),
    ga4("GA4 - block_view" + SUF, "block_view", {"block_name": "{{vb block name" + SUF + "}}"}, "vb block visible" + SUF),
    {"name": "vb block_time script" + SUF, "type": "html", "folder": FOLDER, "firingTriggerNames": ["topic pages pageview" + SUF],
     "consentSettings": {"consentStatus": "notSet"},
     "parameter": [t("html", block_time_html), {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}]},
]

plan = {"account": "6353362488", "container": "261134482", "workspace_name": "vb-topic-pages",
        "version_name": "vb topic pages: form_submit, faq_open, block_view, block_time (new objects in folder, one blocking trigger on old block_time)",
        "version_notes": "Новые объекты в папке «Topic pages (vb)» для страниц *-lawyer-california. Правка старого: тег «ldv block_time script» — исключающий триггер «topic pages pageview [topic pages]». Остальное старое не тронуто.",
        "built_in_variables": ["pagePath", "clickElement"], "folders": [FOLDER], "variables": variables, "triggers": triggers, "tags": tags,
        "update_tags": [{"name": "ldv block_time script", "set_blocking_triggers": ["topic pages pageview" + SUF]}],
        "update_variables": [], "update_triggers": []}
out = HERE / "gtm_plan_topic_pages_2026-10-28.json"
out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("записано:", out)
