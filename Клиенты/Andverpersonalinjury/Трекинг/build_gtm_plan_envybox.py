# -*- coding: utf-8 -*-
"""План GTM для виджета обратного звонка Envybox (CallbackKILLER) БЕЗ правок старых объектов.

Виджет сам пушит в dataLayer при запросе звонка: {event:"GAEvent", eventCategory:"CallbackKILLER", eventAction:"NewCall"} и
{event:"NewCall"} (читалось из boot.min.js и подтверждено на живой странице 2026-10-27 для ShowOnBtn). Глобальных gtag/ga на сайте нет,
поэтому прямые вызовы виджета в GA4 не работают — события ловит только триггер «Пользовательское событие».

Новые объекты с суффиксом « [envybox]» и условием «Page Path» (регулярное выражение: страницы, где стоит виджет). Старые не трогаем.

    python build_gtm_plan_envybox.py   ->  gtm_plan_envybox_2026-10-27.json
    python ../../../Скрипты/gtm_apply_plan.py --plan Клиенты/Andverpersonalinjury/Трекинг/gtm_plan_envybox_2026-10-27.json [--execute]
"""
import json
from pathlib import Path

MID = "G-JPLC4Q41PS"
# главная, Car, Settlement, старая car-truck; новая страница с виджетом = добавить сюда (иначе событие на ней не уйдёт)
PATH_REGEX = r"^/(california-car-accident-lawyer|california-car-accident-settlement|california-car-truck-accident)?/?$"


def t(key, value):
    return {"type": "template", "key": key, "value": value}


page_filter = {"type": "matchRegex", "parameter": [t("arg0", "{{Page Path}}"), t("arg1", PATH_REGEX), t("ignore_case", "true")]}

triggers = [
    {"name": "envybox callback requested [envybox]", "type": "customEvent",
     "customEventFilter": [{"type": "equals", "parameter": [t("arg0", "{{_event}}"), t("arg1", "NewCall")]}],
     "filter": [page_filter]},
]

tags = [
    {"name": "GA4 - callback_request [envybox]", "type": "gaawe", "firingTriggerNames": ["envybox callback requested [envybox]"],
     "parameter": [{"type": "boolean", "key": "sendEcommerceData", "value": "false"}, t("eventName", "callback_request"),
                   t("measurementIdOverride", MID),
                   {"type": "list", "key": "eventSettingsTable", "list": [
                       {"type": "map", "map": [t("parameter", "widget"), t("parameterValue", "envybox_callback")]}]}]},
]

plan = {"account": "6353362488", "container": "261134482", "workspace_name": "ldv-envybox-isolated",
        "version_name": "envybox callback widget: GA4 callback_request, isolated objects, old objects untouched",
        "version_notes": "Только новые объекты: триггер NewCall (виджет Envybox) с условием Page Path (регулярное выражение страниц с виджетом) и тег GA4 callback_request. Старые теги, триггеры и переменные не изменены.",
        "built_in_variables": ["pagePath"], "variables": [], "triggers": triggers, "tags": tags,
        "update_tags": [], "update_variables": [], "update_triggers": []}
out = Path(__file__).with_name("gtm_plan_envybox_2026-10-27.json")
out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("записано:", out)
