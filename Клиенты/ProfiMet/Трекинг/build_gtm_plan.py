# coding: utf-8
"""Собирает gtm_plan_2026-10-19.json для Скрипты/gtm_apply_plan.py (GTM-TKGN4NT, mocnaszklarnia.pl): block_view / block_time,
click_place у click_tel. Образец — Клиенты/Andverpersonalinjury/Трекинг/build_gtm_plan.py. Согласие новых тегов: только analytics_storage."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALL_PAGES = "2147479553"
CONSENT = {"consentStatus": "needed", "consentType": {"type": "list", "list": [{"type": "template", "value": "analytics_storage"}]}}
# по одному «якорному» блоку на имя — иначе block_view по составным блокам (reviews, faq, accessories) считался бы несколько раз
ANCHORS = ["rec2905989103", "rec2907573403", "rec2999230203", "rec2958154103", "rec3211747203", "rec3210912503", "rec3211915203",
           "rec3212364203", "rec3219096603", "rec3219324903", "rec3219455303", "rec3221657503", "rec3015645203", "rec2906074503",
           "rec2908500503", "rec2906175303", "rec3008493103", "rec2906212003", "rec2906284003", "rec2907392403", "rec2907407503"]


def tmpl(key, value):
    return {"type": "template", "key": key, "value": value}


def ga4_event(name, event, params=None, triggers=()):
    rows = [{"type": "map", "map": [tmpl("parameter", k), tmpl("parameterValue", v)]} for k, v in (params or {}).items()]
    p = [{"type": "boolean", "key": "sendEcommerceData", "value": "false"}, tmpl("eventName", event),
         tmpl("measurementIdOverride", "{{GA4 ID}}"), tmpl("measurementId", "none")]
    if rows:
        p.append({"type": "list", "key": "eventSettingsTable", "list": rows})
    return {"name": name, "type": "gaawe", "parameter": p, "firingTriggerNames": list(triggers), "consentSettings": CONSENT}


def jsm(name, code):
    return {"name": name, "type": "jsm", "parameter": [tmpl("javascript", code)]}


def dlv(name, key):
    return {"name": name, "type": "v", "parameter": [
        {"type": "integer", "key": "dataLayerVersion", "value": "2"},
        {"type": "boolean", "key": "setDefaultValue", "value": "false"}, tmpl("name", key)]}


script = (HERE / "pm_block_time.js").read_text(encoding="utf-8")
html_block_time = re.search(r"<script>.*</script>", script, re.S).group(0)

TEL_PLACE_JS = ("function(){var e={{Click Element}};var a=e&&e.closest?e.closest('a'):null;if(!a)return 'other';"
                "var r=a.closest('[id^=rec]');var rid=r?r.id:'';var el=a.closest('.tn-elem');var eid=el?el.getAttribute('data-elem-id'):'';"
                "var m={rec2905989103:'header',rec2907495403:'sticky_header',rec2940700303:'menu',rec2906074503:'discount_block'};"
                "if(rid==='rec2907407503'){return eid==='1786435131250000006'?'final_button':(eid==='1786435131495000017'?'final_footer':'other');}"
                "return m[rid]||'other';}")

plan = {
    "account": "6003760261", "container": "44158621",
    "workspace_name": "pm-behavior-2026-10-19-v3",
    "version_name": "pm behavior v3: block_time, click_place, consent analytics_storage",
    "version_notes": "ProfiMet, 2026-10-19. Откат: опубликовать версию 63.",
    "built_in_variables": ["clickElement"],
    "variables": [
        jsm("pm tel place", TEL_PLACE_JS),
        dlv("dlv block_name", "block_name"),
        dlv("dlv block_seconds", "block_seconds"),
    ],
    "triggers": [
        {"name": "pm event block_time", "type": "customEvent",
         "customEventFilter": [{"type": "equals", "parameter": [tmpl("arg0", "{{_event}}"), tmpl("arg1", "block_time")]}]},
    ],
    "tags": [
        ga4_event("GA4 - block_time", "block_time",
                  {"block_name": "{{dlv block_name}}", "block_seconds": "{{dlv block_seconds}}"}, ["pm event block_time"]),
        {"name": "pm block_time script", "type": "html",
         "parameter": [tmpl("html", html_block_time), {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}],
         "firingTriggerIds": [ALL_PAGES]},
    ],
    "update_tags": [{"name": "GA 4 - click_tel", "set_event_parameters": {"click_place": "{{pm tel place}}"},
                     "set_consent": ["analytics_storage"]}],
}
(HERE / "gtm_plan_2026-10-19.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("plan written:", len(plan["tags"]), "tags,", len(ANCHORS), "anchor blocks")
