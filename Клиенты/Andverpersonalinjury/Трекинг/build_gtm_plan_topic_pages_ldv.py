# -*- coding: utf-8 -*-
"""План GTM 2026-10-29: тематические страницы Landver, собранные по образцу Car (id блоков ldv-…, форма с id `ldv-form-el`): Motorcycle, Pedestrian.

Проверка страниц 29.10 (`Статистика/page_tracking_check_…_2026-10-29.md`) показала две дыры в версии 15 (topic pages):
  1. Форма Pedestrian имеет id `ldv-form-el`, событие Tilda = `submit_` + id формы (код tilda-forms-1.0.min.js) = `submit_ldv-form-el`; ни `submit_form*`
     (триггер 4), ни `^submit_vb-.+-form$` (триггер «submit vb form [topic pages]») его не ловят — заявка не дошла бы до GA4 и пикселя ChatGPT.
  2. «vb block_time script [topic pages]» ищет заголовки `vb-…`; на страницах с `ldv…` их 0, а старый «ldv block_time script» на этих адресах
     заблокирован (путь `-lawyer-california`) — всё время по блокам писалось бы в «top». Селектор расширен заголовками `ldv…-h`, `-h1`, `-title`
     (проверено Playwright 29.10: Motorcycle 13, Pedestrian 14, остальные четыре страницы без изменений 13/14/13/13).
Обе правки касаются только объектов, созданных 28.10 (версия 15, папка «Topic pages (vb)»); старые объекты не трогаются.

    python build_gtm_plan_topic_pages_ldv.py   ->  gtm_plan_topic_pages_ldv_2026-10-29.json
    python Скрипты/gtm_apply_plan.py --plan Клиенты/Andverpersonalinjury/Трекинг/gtm_plan_topic_pages_ldv_2026-10-29.json [--execute]
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
SUF = " [topic pages]"
OLD_SEL = """'[id^="vb-"][id$="-h1"], [id^="vb-"][id$="-h2"], [id^="vb-"][id$="-title"]'"""
NEW_SEL = """'[id^="vb-"][id$="-h1"], [id^="vb-"][id$="-h2"], [id^="vb-"][id$="-title"], [id^="ldv"][id$="-h"], [id^="ldv"][id$="-h1"], [id^="ldv"][id$="-title"]'"""

src = (HERE / "gtm_block_time_topic.js").read_text(encoding="utf-8")
assert OLD_SEL in src
js = src.replace(OLD_SEL, NEW_SEL)
(HERE / "gtm_block_time_topic_v2.js").write_text(
    "// v2 29.10.2026: селектор заголовков расширен на ldv…-h / -h1 / -title (страницы Motorcycle, Pedestrian, собранные по образцу Car). Остальное как в gtm_block_time_topic.js.\n" + js,
    encoding="utf-8")
html = re.search(r"<script>.*</script>", js, re.S).group(0)

plan = {
    "account": "6353362488", "container": "261134482", "workspace_name": "vb-topic-pages-ldv",
    "version_name": "topic pages: форма ldv-form-el (Pedestrian) и заголовки ldv… в block_time (Motorcycle, Pedestrian)",
    "version_notes": "Правка двух объектов версии 15: триггер «submit vb form [topic pages]» — регэксп ^submit_(vb-.+-form|ldv-form-el)$; тег «vb block_time script [topic pages]» — селектор заголовков с ldv… Старые объекты не изменены.",
    "built_in_variables": [], "folders": [], "variables": [], "triggers": [], "tags": [],
    "update_tags": [{"name": "vb block_time script" + SUF, "set_html": html}],
    "update_variables": [],
    "update_triggers": [{"name": "submit vb form" + SUF, "set_custom_event_arg1": "^submit_(vb-.+-form|ldv-form-el)$"}],
}
out = HERE / "gtm_plan_topic_pages_ldv_2026-10-29.json"
out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
print("->", out)
