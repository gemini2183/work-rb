#!/usr/bin/env python
# coding: utf-8
"""Landver: новая испанская Search-кампания (решение 10.11.2026), создаётся на ПАУЗЕ. ЗАПИСЬ только с --execute; по умолчанию validate_only.

План и допущения — Клиенты/Andverpersonalinjury/Креативы/spanish_campaign_plan_2026-11-11.md. Все параметры — константы ниже.
  --plan              без API: печатает таблицы текстов, ключей, минусов, ассетов и считает операции (ничего не читает и не пишет).
  --part new          (по умолчанию) кампания + бюджет + гео + язык + перекрёстные и испанские минусы + 3 общих списка + группа + ключи +
                      RSA + быстрые ссылки + callouts + подпись + звонок + логотип + картинки. Читает 1 запрос (шаблон отслеживания основной).
  --part negatives    копия кампанийных минусов основной (без «near me» и без испанских блокировщиков abogado/abogados), порциями --chunk.
  --part shared-negatives  то же слово-в-слово, но ОБЩИМ СПИСКОМ минус-слов (решение пользователя 11.11: планируются ещё кампании по юристам):
                      создание списка (1 операция), наполнение (1 697, порциями --chunk), привязка к новой кампании (1) = 1 699 операций.
                      Список потом привязывается к следующим кампаниям 1 операцией на каждую. Лимиты (справка 6372658, не проверено): 20 списков на аккаунт, 5 000 слов.
  --read-back-only    чтение состояния новой кампании.
  --remove-new        удалить новую кампанию (откат).
Флаги для проверки: --no-language (если Google не принимает языковой критерий: с сентября 2026 язык у Search убирают),
  --snippet-header X (заголовок подписи; по умолчанию «Tipos», запасной «Types»), --exempt-health (исключения политики HEALTH_IN_PERSONALIZED_ADS у ключей).
Журнал операций API — через gads_quota_ledger (П-001).

    python gads_landver_spanish_build.py --plan
    python gads_landver_spanish_build.py --customer-id 213-621-6123 [--part new|negatives] [--execute]
"""
import argparse
import sys
from datetime import datetime

NEW_NAME = "search / car accident / es ca / lp - tilda"
GROUP_NAME = "Abogado Accidentes Auto - Exact"
MAIN_CAMPAIGN_ID = 24331208797
BUDGET_USD = 50
BID_USD = 80
GEO_CALIFORNIA = "geoTargetConstants/21137"
LANG_ES, LANG_EN = "languageConstants/1003", "languageConstants/1000"
URL = "https://landverpersonalinjury.tilda.ws/abogado-accidentes-auto-lawyer-california"
KEYWORDS = [  # все EXACT; объёмы Planner 11.11 (Калифорния, испанский)
    "abogado de accidentes de carro", "abogado de accidentes", "abogado de accidentes de auto", "abogado de accidentes los angeles",
    "abogado de accidentes automovilisticos", "abogado para accidentes de carro", "abogado accidente de carro",
]
SHARED_COPY_NAME = "main negatives copy (es, law firms)"
SHARED_SETS = [12099348931, 12186238091, 12186251357]            # gen / init, names, rivals (как у LA+BH)
CALL_ASSET_OK = 411032321136
LOGO_ASSET = 367221514317
IMAGES_CAR = [434394643289, 434394652385, 434394652397, 434394641063, 433442950841, 433630815477, 434394643274, 434394631925]  # 8 действующих у LA+BH
NEAR_ME = ("near me", "nearby", "close to me", "near by")
ES_BLOCKERS = {"abogado", "abogados"}   # BROAD-минусы основной, блокирующие все испанские ключи: в копию не берём

# перекрёстные (другие темы и вид транспорта) — PHRASE; испанские собственные — PHRASE
CROSS_NEGATIVES = ["moto", "motocicleta", "motocicletas", "peaton", "peatón", "peatones", "bicicleta", "bicicletas", "bici",
                   "camion", "camión", "camiones"]
ES_NEGATIVES = [
    "empleo", "empleos", "salario", "curso", "cursos", "universidad", "estudiar derecho", "pasante",
    "seguro de auto", "cotizar", "cotizacion", "cotización", "taller", "mecanico", "mecánico", "grua", "grúa",
    "renta de carros", "carros usados", "licencia de conducir", "multa", "multas", "escuela de manejo",
    "inmigracion", "inmigración", "migratorio", "divorcio", "custodia", "dui", "manejar ebrio", "bancarrota", "testamento",
    "compensacion laboral", "compensación laboral", "workers comp", "negligencia medica", "negligencia médica", "mala praxis",
    "abogado de oficio", "defensor publico", "defensor público", "legal aid",
    "texas", "houston", "dallas", "florida", "miami", "nueva york", "new york", "chicago", "atlanta", "arizona", "phoenix",
    "nevada", "las vegas", "mexico", "méxico", "tijuana", "españa", "colombia", "argentina", "peru", "perú", "puerto rico",
]

# (текст, закрепление: None / "H1" / "H2" / "D1")
HEADLINES = [
    ("Abogado de Accidentes de Auto", "H1"), ("Abogado de Accidentes de Carro", "H1"), ("Abogado de Accidentes en CA", "H1"),
    ("Consulta Gratis · 24/7", "H2"), ("No Paga a Menos Que Ganemos", "H2"), ("Atención en Español", "H2"),
    ("Llame a Landver Law 24/7", None), ("¿Lesionado en un Accidente?", None), ("Más de 20 Años en California", None),
    ("4.8 Estrellas en Google", None), ("Experiencia en Tribunales", None), ("Oficina en Beverly Hills", None),
    ("Revisión Gratuita de su Caso", None), ("Sin Costos por Adelantado", None), ("Conocemos a las Aseguradoras", None),
]
DESCRIPTIONS = [
    ("Consulta gratis después de un accidente de auto. Ayudamos a personas lesionadas.", "D1"),
    ("Cuéntenos qué pasó. Un abogado revisa su caso sin costo. Atención en español.", None),
    ("Consulta gratis. No paga honorarios a menos que ganemos. Llame a Landver Law 24/7.", None),
    ("Más de 20 años en tribunales de California. Experiencia del lado de la defensa.", None),
]
PATHS = ("abogado", "accidentes-auto")
SITELINKS = [  # (текст <=25, описание1 <=35, описание2 <=35, якорь)
    ("Consulta gratuita", "Cuéntenos qué pasó.", "Gratis y sin compromiso.", "#ldv-form-section"),
    ("Honorarios del abogado", "La primera consulta es gratis.", "Sin costos por adelantado.", "#ldv-fee"),
    ("Conozca a su abogada", "Alina Landver, Esq., MBA.", "Más de 20 años en California.", "#ldv-attorney"),
    ("Reseñas de clientes", "4.8 estrellas en Google.", "45 reseñas de clientes.", "#ldv-reviews"),
    ("Cómo funciona", "Cuéntenos qué pasó.", "Revisión gratuita de su caso.", "#ldv-how"),
    ("Preguntas frecuentes", "Costos, plazos y culpa.", "Respuestas tras un accidente.", "#ldv-faq"),
]
CALLOUTS = ["Consulta gratis 24/7", "Atención en español", "No paga si no ganamos", "20+ años en California",
            "Atendemos todo California", "Abogada litigante", "Sin costos por adelantado"]
SNIPPET_VALUES = ["Choque por detrás", "Choque en un cruce", "Cambio de carril", "Conductor distraído",
                  "Fuga del conductor", "Choque con camión", "Pasajero en transporte"]


def check_limits():
    assert len(HEADLINES) <= 15 and len(DESCRIPTIONS) <= 4
    for t, _ in HEADLINES:
        assert len(t) <= 30, (t, len(t))
    for t, _ in DESCRIPTIONS:
        assert len(t) <= 90, (t, len(t))
    assert all(len(p) <= 15 for p in PATHS)
    for a, b, c, _ in SITELINKS:
        assert len(a) <= 25 and len(b) <= 35 and len(c) <= 35, (a, b, c)
    assert all(len(x) <= 25 for x in CALLOUTS + SNIPPET_VALUES)
    assert len(CALLOUTS) == len(set(CALLOUTS)) and 3 <= len(SNIPPET_VALUES) <= 10
    assert sum(1 for _, p in HEADLINES if p == "H1") == 3 and sum(1 for _, p in HEADLINES if p == "H2") == 3


def count_ops(n_neg_copy=1697, language=True):
    parts = {
        "бюджет + кампания": 2, "гео": 1, "язык": 2 if language else 0,
        "перекрёстные минусы": len(CROSS_NEGATIVES), "испанские минусы": len(ES_NEGATIVES), "общие списки": len(SHARED_SETS),
        "группа": 1, "ключи": len(KEYWORDS), "RSA": 1,
        "быстрые ссылки (ассет + привязка)": 2 * len(SITELINKS), "callouts (ассет + привязка)": 2 * len(CALLOUTS),
        "подпись (ассет + привязка)": 2, "звонок + логотип (привязки)": 2, "картинки (привязки)": len(IMAGES_CAR),
    }
    return parts, sum(parts.values()), n_neg_copy


def print_plan():
    check_limits()
    print("## RSA")
    for i, (t, p) in enumerate(HEADLINES, 1):
        print(f"H{i} | {t} | {len(t)}/30 | {p or '-'}")
    for i, (t, p) in enumerate(DESCRIPTIONS, 1):
        print(f"D{i} | {t} | {len(t)}/90 | {p or '-'}")
    print("path:", "/".join(PATHS))
    parts, total, neg = count_ops()
    print("\n## Операции")
    for k, v in parts.items():
        print(f"{k}: {v}")
    print(f"ИТОГО часть new: {total}; копия минусов основной (--part negatives): {neg}; всего {total + neg}")
    print(f"ключей {len(KEYWORDS)}, испанских минусов {len(ES_NEGATIVES)}, перекрёстных {len(CROSS_NEGATIVES)}")
    # перекрёстная проверка: ни один минус не блокирует свои ключи (PHRASE)
    for kw in KEYWORDS:
        kt = kw.split()
        for n in CROSS_NEGATIVES + ES_NEGATIVES:
            nt = n.split()
            if any(kt[i:i + len(nt)] == nt for i in range(len(kt) - len(nt) + 1)):
                raise SystemExit(f"минус «{n}» блокирует ключ «{kw}»")
    print("минусы не блокируют ключи: OK")


# ---------------------------------------------------------------- API
def mm(usd):
    return int(usd * 1_000_000)


def build_new_ops(client, cid, ga, a):
    E = client.enums
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    main = list(ga.search(customer_id=cid, query="SELECT campaign.id, campaign.tracking_url_template FROM campaign "
                                                 f"WHERE campaign.id = {MAIN_CAMPAIGN_ID}"))[0].campaign
    budget_rn = f"customers/{cid}/campaignBudgets/-1"
    campaign_rn = f"customers/{cid}/campaigns/-2"
    ag_rn = f"customers/{cid}/adGroups/-3"
    ops = []
    tmp = [-10]

    def new_op():
        op = client.get_type("MutateOperation")
        ops.append(op)
        return op

    def new_asset():
        tmp[0] -= 1
        return f"customers/{cid}/assets/{tmp[0]}"

    b = new_op().campaign_budget_operation.create
    b.resource_name = budget_rn
    b.name = f"{NEW_NAME} budget {ts}"
    b.amount_micros = mm(BUDGET_USD)
    b.delivery_method = E.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False

    c = new_op().campaign_operation.create
    c.resource_name = campaign_rn
    c.name = NEW_NAME
    c.status = E.CampaignStatusEnum.PAUSED
    c.advertising_channel_type = E.AdvertisingChannelTypeEnum.SEARCH
    c.campaign_budget = budget_rn
    c.manual_cpc.enhanced_cpc_enabled = False
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = False
    c.network_settings.target_content_network = False
    c.geo_target_type_setting.positive_geo_target_type = E.PositiveGeoTargetTypeEnum.PRESENCE
    c.geo_target_type_setting.negative_geo_target_type = E.NegativeGeoTargetTypeEnum.PRESENCE
    c.contains_eu_political_advertising = E.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    c.tracking_url_template = main.tracking_url_template
    c.ai_max_setting.enable_ai_max = False
    for t in (E.AssetAutomationTypeEnum.TEXT_ASSET_AUTOMATION, E.AssetAutomationTypeEnum.FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION):
        s = c.asset_automation_settings.add()
        s.asset_automation_type = t
        s.asset_automation_status = E.AssetAutomationStatusEnum.OPTED_OUT

    cc = new_op().campaign_criterion_operation.create
    cc.campaign = campaign_rn
    cc.location.geo_target_constant = GEO_CALIFORNIA
    if not a.no_language:
        for lang in (LANG_ES, LANG_EN):
            cc = new_op().campaign_criterion_operation.create
            cc.campaign = campaign_rn
            cc.language.language_constant = lang
    for text in CROSS_NEGATIVES + ES_NEGATIVES:
        cc = new_op().campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = E.KeywordMatchTypeEnum.PHRASE
    for sid in SHARED_SETS:
        css = new_op().campaign_shared_set_operation.create
        css.campaign = campaign_rn
        css.shared_set = f"customers/{cid}/sharedSets/{sid}"

    ag = new_op().ad_group_operation.create
    ag.resource_name = ag_rn
    ag.name = GROUP_NAME
    ag.campaign = campaign_rn
    ag.status = E.AdGroupStatusEnum.ENABLED
    ag.type_ = E.AdGroupTypeEnum.SEARCH_STANDARD
    ag.cpc_bid_micros = mm(BID_USD)
    for kw in KEYWORDS:
        kop = new_op().ad_group_criterion_operation
        agc = kop.create
        agc.ad_group = ag_rn
        agc.status = E.AdGroupCriterionStatusEnum.ENABLED
        agc.keyword.text = kw
        agc.keyword.match_type = E.KeywordMatchTypeEnum.EXACT
        if a.exempt_health:
            k = kop.exempt_policy_violation_keys.add()
            k.policy_name = "HEALTH_IN_PERSONALIZED_ADS"
            k.violating_text = kw

    aga = new_op().ad_group_ad_operation.create
    aga.ad_group = ag_rn
    aga.status = E.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(URL)
    rsa = aga.ad.responsive_search_ad
    pin = {"H1": E.ServedAssetFieldTypeEnum.HEADLINE_1, "H2": E.ServedAssetFieldTypeEnum.HEADLINE_2, "D1": E.ServedAssetFieldTypeEnum.DESCRIPTION_1}
    for lst, tgt in ((HEADLINES, rsa.headlines), (DESCRIPTIONS, rsa.descriptions)):
        for text, p in lst:
            t = client.get_type("AdTextAsset")
            t.text = text
            if p:
                t.pinned_field = pin[p]
            tgt.append(t)
    rsa.path1, rsa.path2 = PATHS

    for text, d1, d2, anchor in SITELINKS:
        rn = new_asset()
        asset = new_op().asset_operation.create
        asset.resource_name = rn
        asset.final_urls.append(URL + anchor)
        asset.sitelink_asset.link_text = text
        asset.sitelink_asset.description1 = d1
        asset.sitelink_asset.description2 = d2
        x = new_op().campaign_asset_operation.create
        x.campaign = campaign_rn
        x.asset = rn
        x.field_type = E.AssetFieldTypeEnum.SITELINK
    for text in CALLOUTS:
        rn = new_asset()
        asset = new_op().asset_operation.create
        asset.resource_name = rn
        asset.callout_asset.callout_text = text
        x = new_op().campaign_asset_operation.create
        x.campaign = campaign_rn
        x.asset = rn
        x.field_type = E.AssetFieldTypeEnum.CALLOUT
    rn = new_asset()
    asset = new_op().asset_operation.create
    asset.resource_name = rn
    asset.structured_snippet_asset.header = a.snippet_header
    asset.structured_snippet_asset.values.extend(SNIPPET_VALUES)
    x = new_op().campaign_asset_operation.create
    x.campaign = campaign_rn
    x.asset = rn
    x.field_type = E.AssetFieldTypeEnum.STRUCTURED_SNIPPET
    for aid, ft in ((CALL_ASSET_OK, E.AssetFieldTypeEnum.CALL), (LOGO_ASSET, E.AssetFieldTypeEnum.BUSINESS_LOGO)):
        x = new_op().campaign_asset_operation.create
        x.campaign = campaign_rn
        x.asset = f"customers/{cid}/assets/{aid}"
        x.field_type = ft
    for aid in IMAGES_CAR:
        x = new_op().ad_group_asset_operation.create
        x.ad_group = ag_rn
        x.asset = f"customers/{cid}/assets/{aid}"
        x.field_type = E.AssetFieldTypeEnum.AD_IMAGE
    print(f"[new] операций: {len(ops)}")
    return ops


def find_new_campaign(ga, cid):
    rows = list(ga.search(customer_id=cid, query=f"SELECT campaign.id FROM campaign WHERE campaign.name = '{NEW_NAME}' AND campaign.status != REMOVED"))
    return rows[0].campaign.id if rows else None


def build_neg_ops(client, cid, ga, new_id, limit):
    """Недостающие кампанийные минусы новой кампании (копия основной без «near me» и без abogado/abogados). Идемпотентно."""
    E = client.enums
    q = ("SELECT campaign.id, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type FROM campaign_criterion "
         "WHERE campaign.id = {} AND campaign_criterion.type = KEYWORD AND campaign_criterion.negative = TRUE")
    have = {(r.campaign_criterion.keyword.text, r.campaign_criterion.keyword.match_type) for r in ga.search(customer_id=cid, query=q.format(new_id))}
    want, skipped, blockers = [], 0, 0
    for r in ga.search(customer_id=cid, query=q.format(MAIN_CAMPAIGN_ID)):
        text, mt = r.campaign_criterion.keyword.text, r.campaign_criterion.keyword.match_type
        if mt == E.KeywordMatchTypeEnum.EXACT and any(w in text for w in NEAR_ME):
            skipped += 1
            continue
        if text.lower() in ES_BLOCKERS:
            blockers += 1
            continue
        want.append((text, mt))
    missing = [x for x in want if x not in have]
    print(f"[negatives] основная: near me пропущено {skipped}, блокировщиков {blockers}; нужно {len(want)}, уже есть {len(want) - len(missing)}, добавить {len(missing)} (за шаг ≤ {limit})")
    ops = []
    for text, mt in missing[:limit]:
        op = client.get_type("MutateOperation")
        cc = op.campaign_criterion_operation.create
        cc.campaign = f"customers/{cid}/campaigns/{new_id}"
        cc.negative = True
        cc.keyword.text = text
        cc.keyword.match_type = mt
        ops.append(op)
    return ops


def shared_copy_words(client, cid, ga):
    """Слова для общего списка: кампанийные минусы основной без «near me» и без abogado/abogados."""
    E = client.enums
    q = ("SELECT campaign.id, campaign_criterion.keyword.text, campaign_criterion.keyword.match_type FROM campaign_criterion "
         f"WHERE campaign.id = {MAIN_CAMPAIGN_ID} AND campaign_criterion.type = KEYWORD AND campaign_criterion.negative = TRUE")
    words = []
    for r in ga.search(customer_id=cid, query=q):
        text, mt = r.campaign_criterion.keyword.text, r.campaign_criterion.keyword.match_type
        if mt == E.KeywordMatchTypeEnum.EXACT and any(w in text for w in NEAR_ME):
            continue
        if text.lower() in ES_BLOCKERS:
            continue
        words.append((text, mt))
    return words


def run_shared_negatives(client, cid, ga, a):
    """Общий список: создать (если нет) -> наполнить недостающим -> привязать к новой кампании. validate_only: одним запросом с временным id."""
    E = client.enums
    words = shared_copy_words(client, cid, ga)
    nid = find_new_campaign(ga, cid)
    found = list(ga.search(customer_id=cid, query=f"SELECT shared_set.id, shared_set.resource_name FROM shared_set WHERE shared_set.name = '{SHARED_COPY_NAME}' AND shared_set.status = ENABLED AND shared_set.type = NEGATIVE_KEYWORDS"))
    cnt = list(ga.search(customer_id=cid, query="SELECT shared_set.id FROM shared_set WHERE shared_set.type = NEGATIVE_KEYWORDS AND shared_set.status = ENABLED"))
    print(f"[shared] слов для списка {len(words)}; списков минусов в аккаунте {len(cnt)} из 20; список «{SHARED_COPY_NAME}» {'есть' if found else 'не создан'}; новая кампания {nid or 'нет'}")

    def crit_op(rn, text, mt):
        op = client.get_type("MutateOperation")
        sc = op.shared_criterion_operation.create
        sc.shared_set = rn
        sc.keyword.text = text
        sc.keyword.match_type = mt
        return op

    if not a.execute:
        rn = f"customers/{cid}/sharedSets/-1"
        ops = []
        op = client.get_type("MutateOperation")
        ss = op.shared_set_operation.create
        ss.resource_name = rn
        ss.name = SHARED_COPY_NAME
        ss.type_ = E.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        ops.append(op)
        ops += [crit_op(rn, t, m) for t, m in words]
        if nid:
            op = client.get_type("MutateOperation")
            css = op.campaign_shared_set_operation.create
            css.campaign = f"customers/{cid}/campaigns/{nid}"
            css.shared_set = rn
            ops.append(op)
        print(f"[shared] операций в проверке: {len(ops)} (список 1 + слова {len(words)} + привязка {1 if nid else 0}; без кампании привязку не проверить)")
        run(client, cid, ops, False, "shared-negatives")
        return
    assert nid, "новой кампании нет — сначала --part new"
    if found:
        rn = found[0].shared_set.resource_name
    else:
        op = client.get_type("MutateOperation")
        ss = op.shared_set_operation.create
        ss.name = SHARED_COPY_NAME
        ss.type_ = E.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        resp = run(client, cid, [op], True, "shared-create")
        rn = resp.mutate_operation_responses[0].shared_set_result.resource_name
    sid = rn.split("/")[-1]
    have = {(r.shared_criterion.keyword.text, r.shared_criterion.keyword.match_type) for r in ga.search(
        customer_id=cid, query=f"SELECT shared_set.id, shared_criterion.keyword.text, shared_criterion.keyword.match_type FROM shared_criterion WHERE shared_set.id = {sid}")}
    missing = [w for w in words if w not in have]
    print(f"[shared] уже в списке {len(have)}, добавить {len(missing)}")
    for i in range(0, len(missing), a.chunk):
        run(client, cid, [crit_op(rn, t, m) for t, m in missing[i:i + a.chunk]], True, f"shared-fill {i // a.chunk + 1}")
    linked = list(ga.search(customer_id=cid, query=f"SELECT campaign.id, shared_set.id FROM campaign_shared_set WHERE campaign.id = {nid} AND shared_set.id = {sid}"))
    if not linked:
        op = client.get_type("MutateOperation")
        css = op.campaign_shared_set_operation.create
        css.campaign = f"customers/{cid}/campaigns/{nid}"
        css.shared_set = rn
        run(client, cid, [op], True, "shared-link")
    read_back(client, cid, ga)


def run(client, cid, ops, execute, label):
    from google.ads.googleads.errors import GoogleAdsException
    from google.api_core.exceptions import ResourceExhausted
    from gads_quota_ledger import record_mutate
    svc = client.get_service("GoogleAdsService")
    req = client.get_type("MutateGoogleAdsRequest")
    req.customer_id = cid
    req.mutate_operations.extend(ops)
    req.validate_only = not execute
    record_mutate("gads_landver_spanish_build", len(ops), validate_only=not execute)
    try:
        resp = svc.mutate(request=req)
    except ResourceExhausted as ex:
        print(f"ЛИМИТ ОПЕРАЦИЙ Google Ads ({label}): {str(ex)[:300]}")
        raise SystemExit(2)
    except GoogleAdsException as ex:
        print(f"ОШИБКА от Google Ads ({label}):")
        for err in ex.failure.errors:
            loc = " > ".join(str(e.field_name) + (f"[{e.index}]" if e.index is not None and str(e.index) != "" else "") for e in err.location.field_path_elements)
            print(f"  - {err.message} [{loc}]")
            d = err.details.policy_violation_details
            if d.key.policy_name:
                print(f"      политика: {d.key.policy_name}; текст: {d.key.violating_text}; исключаемо: {d.is_exemptible}; {d.external_policy_name}")
        raise SystemExit(1)
    if not execute:
        print(f"[{label}] проверка пройдена ({len(ops)} операций), ничего не записано (validate_only).")
        return None
    print(f"[{label}] записано, ответов: {len(resp.mutate_operation_responses)}")
    return resp


def read_back(client, cid, ga):
    E = client.enums
    nid = find_new_campaign(ga, cid)
    if not nid:
        print("новой кампании нет")
        return
    q = lambda s: list(ga.search(customer_id=cid, query=s))
    print(f"-- кампания {nid}")
    for r in q(f"SELECT campaign.id, campaign.name, campaign.status, campaign.bidding_strategy_type, campaign_budget.amount_micros, campaign.tracking_url_template FROM campaign WHERE campaign.id = {nid}"):
        print(r.campaign.name, E.CampaignStatusEnum.CampaignStatus.Name(r.campaign.status), "бюджет", r.campaign_budget.amount_micros / 1e6,
              E.BiddingStrategyTypeEnum.BiddingStrategyType.Name(r.campaign.bidding_strategy_type), "| шаблон:", r.campaign.tracking_url_template[:60])
    crit = {}
    for r in q(f"SELECT campaign.id, campaign_criterion.type, campaign_criterion.negative, campaign_criterion.keyword.match_type, campaign_criterion.language.language_constant, campaign_criterion.location.geo_target_constant FROM campaign_criterion WHERE campaign.id = {nid}"):
        c = r.campaign_criterion
        key = (E.CriterionTypeEnum.CriterionType.Name(c.type_), c.negative, E.KeywordMatchTypeEnum.KeywordMatchType.Name(c.keyword.match_type) if c.negative else "")
        crit[key] = crit.get(key, 0) + 1
        if c.location.geo_target_constant or c.language.language_constant:
            print("  ", c.location.geo_target_constant or c.language.language_constant)
    print("критерии (тип, минус?, соответствие):", crit)
    for r in q(f"SELECT campaign.id, shared_set.name FROM campaign_shared_set WHERE campaign.id = {nid}"):
        print("  общий список:", r.shared_set.name)
    for r in q(f"SELECT campaign.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros FROM ad_group WHERE campaign.id = {nid}"):
        print("  группа:", r.ad_group.name, E.AdGroupStatusEnum.AdGroupStatus.Name(r.ad_group.status), "ставка", r.ad_group.cpc_bid_micros / 1e6)
    for r in q(f"SELECT campaign.id, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status, ad_group_criterion.approval_status FROM ad_group_criterion WHERE campaign.id = {nid} AND ad_group_criterion.type = KEYWORD"):
        c = r.ad_group_criterion
        print("  ключ:", c.keyword.text, E.KeywordMatchTypeEnum.KeywordMatchType.Name(c.keyword.match_type), c.status, c.approval_status)
    for r in q(f"SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.policy_summary.approval_status, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad WHERE campaign.id = {nid}"):
        a = r.ad_group_ad
        print(f"  объявление {a.ad.id} {a.status} approval={a.policy_summary.approval_status} url={list(a.ad.final_urls)}")
        for i, h in enumerate(a.ad.responsive_search_ad.headlines, 1):
            print(f"     H{i} [{len(h.text)}] {E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(h.pinned_field) if h.pinned_field else '-'}: {h.text}")
        for i, d in enumerate(a.ad.responsive_search_ad.descriptions, 1):
            print(f"     D{i} [{len(d.text)}] {E.ServedAssetFieldTypeEnum.ServedAssetFieldType.Name(d.pinned_field) if d.pinned_field else '-'}: {d.text}")
    for r in q(f"SELECT campaign.id, campaign_asset.field_type, campaign_asset.status, campaign_asset.primary_status, campaign_asset.primary_status_reasons, asset.id FROM campaign_asset WHERE campaign.id = {nid}"):
        ca = r.campaign_asset
        print("  кампанийный ассет:", E.AssetFieldTypeEnum.AssetFieldType.Name(ca.field_type), r.asset.id, ca.status, ca.primary_status, list(ca.primary_status_reasons))
    cnt = {}
    for r in q(f"SELECT campaign.id, ad_group_asset.field_type, ad_group_asset.status FROM ad_group_asset WHERE campaign.id = {nid}"):
        key = (E.AssetFieldTypeEnum.AssetFieldType.Name(r.ad_group_asset.field_type), r.ad_group_asset.status)
        cnt[key] = cnt.get(key, 0) + 1
    print("  ассеты группы:", cnt)
    for r in q(f"SELECT campaign.id, conversion_goal_campaign_config.goal_config_level FROM conversion_goal_campaign_config WHERE campaign.id = {nid}"):
        print("  уровень целей:", E.GoalConfigLevelEnum.GoalConfigLevel.Name(r.conversion_goal_campaign_config.goal_config_level))
    for r in q(f"SELECT campaign.id, campaign_conversion_goal.category, campaign_conversion_goal.origin, campaign_conversion_goal.biddable FROM campaign_conversion_goal WHERE campaign.id = {nid}"):
        g = r.campaign_conversion_goal
        print("  цель:", E.ConversionActionCategoryEnum.ConversionActionCategory.Name(g.category), E.ConversionOriginEnum.ConversionOrigin.Name(g.origin), g.biddable)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer-id")
    ap.add_argument("--part", choices=["new", "negatives", "shared-negatives"], default="new")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--chunk", type=int, default=400)
    ap.add_argument("--read-back-only", action="store_true")
    ap.add_argument("--remove-new", action="store_true")
    ap.add_argument("--no-language", action="store_true")
    ap.add_argument("--snippet-header", default="Tipos")
    ap.add_argument("--exempt-health", action="store_true")
    a = ap.parse_args()
    check_limits()
    if a.plan:
        print_plan()
        return
    if not a.customer_id:
        sys.exit("нужен --customer-id (или --plan)")
    from google.ads.googleads.client import GoogleAdsClient
    from gads_stats import GOOGLE_ADS_YAML
    from gads_quota_ledger import wrap_ga
    cid = a.customer_id.replace("-", "").strip()
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    ga = wrap_ga(client.get_service("GoogleAdsService"), "gads_landver_spanish_build")
    if a.read_back_only:
        read_back(client, cid, ga)
        return
    if a.remove_new:
        nid = find_new_campaign(ga, cid)
        assert nid, "новой кампании нет"
        op = client.get_type("MutateOperation")
        op.campaign_operation.remove = f"customers/{cid}/campaigns/{nid}"
        run(client, cid, [op], a.execute, "remove-new")
        return
    if a.part == "shared-negatives":
        run_shared_negatives(client, cid, ga, a)
        return
    if a.part == "negatives":
        nid = find_new_campaign(ga, cid)
        assert nid, "новой кампании нет — сначала --part new"
        while True:
            ops = build_neg_ops(client, cid, ga, nid, a.chunk)
            if not ops:
                break
            run(client, cid, ops, a.execute, "negatives")
            if not a.execute:
                break
        if a.execute:
            read_back(client, cid, ga)
        return
    if find_new_campaign(ga, cid):
        raise SystemExit("Новая кампания уже существует — повторное создание остановлено.")
    run(client, cid, build_new_ops(client, cid, ga, a), a.execute, "new")
    if a.execute:
        read_back(client, cid, ga)


if __name__ == "__main__":
    main()
