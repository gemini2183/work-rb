# -*- coding: utf-8 -*-
"""План GTM для страницы Settlement БЕЗ правок старых объектов: только новые переменные/триггеры/теги с условием по адресу страницы.

Решение пользователя 2026-10-26: в контейнере GTM-KVLHDKJJ живут три страницы (Car, car-truck, Settlement); всё общее, поэтому
для новой страницы заводим отдельные объекты с суффиксом « [settlement]» и условием «Page Path содержит /california-car-accident-settlement»,
старые не переписываем.

    python build_gtm_plan_settlement_isolated.py   ->  gtm_plan_settlement_isolated_2026-10-26.json
    python gtm_apply_plan.py --plan Клиенты/Andverpersonalinjury/Трекинг/gtm_plan_settlement_isolated_2026-10-26.json [--execute]
"""
import json
from pathlib import Path

PATH = "/california-car-accident-settlement"
MID = "G-JPLC4Q41PS"


def t(key, value):
    return {"type": "template", "key": key, "value": value}


page_filter = {"type": "contains", "parameter": [t("arg0", "{{Page Path}}"), t("arg1", PATH)]}

# блоки Settlement, которых нет в старых списках (старые id — ldv-faq, ldv-final, … — уже считаются старым триггером)
NEW_BLOCKS = ["#ldvq-top", "#ldvq-card", "#ldv-why", "#ldv-form-2-section", ".vb-f3a#ldv-form"]
NAMES = {"ldvq-top": "hero", "ldvq-card": "quiz", "ldv-why": "why", "ldv-form-2-section": "form_b", "ldv-form": "form_a"}

variables = [{
    "name": "ldv block name [settlement]", "type": "jsm",
    "parameter": [t("javascript", "function(){var e={{Click Element}};if(!e)return '';var m=" + json.dumps(NAMES) + ";return m[e.id||'']||(e.id||'').replace(/^ldv-/,'').replace(/-/g,'_');}")],
}]

triggers = [
    {"name": "ldv block visible [settlement]", "type": "elementVisibility", "filter": [page_filter], "parameter": [
        t("selectorType", "CSS"), t("elementSelector", ", ".join(NEW_BLOCKS)), t("firingFrequency", "ONCE_PER_ELEMENT"), t("onScreenRatio", "10"),
        {"type": "boolean", "key": "useOnScreenDuration", "value": "true"}, t("onScreenDuration", "1000"),
        {"type": "boolean", "key": "useDomChangeListener", "value": "false"}]},
    {"name": "ldv faq question click [settlement]", "type": "click", "filter": [
        {"type": "cssSelector", "parameter": [t("arg0", "{{Click Element}}"), t("arg1", "#ldv-faq summary, #ldv-faq summary *")]}, page_filter]},
]


def ga4(name, event, params, trigger):
    rows = [{"type": "map", "map": [t("parameter", k), t("parameterValue", v)]} for k, v in params.items()]
    return {"name": name, "type": "gaawe", "firingTriggerNames": [trigger], "parameter": [
        {"type": "boolean", "key": "sendEcommerceData", "value": "false"}, t("eventName", event), t("measurementIdOverride", MID),
        {"type": "list", "key": "eventSettingsTable", "list": rows}]}


tags = [
    ga4("GA4 - block_view [settlement]", "block_view", {"block_name": "{{ldv block name [settlement]}}"}, "ldv block visible [settlement]"),
    ga4("GA4 - faq_open [settlement]", "faq_open", {"faq_question": "{{ldv faq question}}"}, "ldv faq question click [settlement]"),
]

plan = {"account": "6353362488", "container": "261134482", "workspace_name": "ldv-settlement-isolated",
        "version_name": "ldv settlement page: isolated objects (block_view, faq_open), old objects untouched",
        "version_notes": "Только новые объекты с условием Page Path содержит /california-car-accident-settlement. Старые теги, триггеры и переменные не изменены.",
        "built_in_variables": ["pagePath", "clickElement"], "variables": variables, "triggers": triggers, "tags": tags,
        "update_tags": [], "update_variables": [], "update_triggers": []}
out = Path(__file__).with_name("gtm_plan_settlement_isolated_2026-10-26.json")
out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("записано:", out)
