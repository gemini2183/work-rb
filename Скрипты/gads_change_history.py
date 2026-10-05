#!/usr/bin/env python
# coding: utf-8
"""История изменений кампании Google Ads (change_event) — для проверки
Gate-проверки 2 из База_знаний/Паттерны/Алгоритм-анализа-эффективности-
кампании-блок-схема.md: любое колебание метрики на участке ряда в первую
очередь объясняется изменением, которое человек внёс в кампанию в этот же
момент (ставка/бюджет/таргетинг/статус), а не внешней причиной — пока это не
проверено. Без этого скрипта причинные выводы о трендах кампании оставались
недоказуемыми гипотезами (см. Клиенты/ProfiMet/Решения.md, запись 2026-09-30,
Ошибка 6 в Google-Ads-аудит-кампании-алгоритм-и-ошибки-смешения-данных.md).

ВАЖНОЕ ОГРАНИЧЕНИЕ API, не устранимое на нашей стороне (проверено WebSearch +
developers.google.com/google-ads/api/docs/change-event, 2026-09-30):
resource change_event отдаёт историю МАКСИМУМ за последние 30 дней от текущей
даты запроса, максимум 10 000 строк за раз. Для периода анализа шире 30 дней
(типичный случай для Шага 1 блок-схемы — 30/90-дневные горизонты) часть
истории физически недоступна через этот ресурс — скрипт явно предупреждает
об этом в выводе, не подменяет отсутствующие данные молчанием. Не путать с
change_status (90 дней, но не даёт old/new значения полей — только факт "что
изменилось", без "как именно").

Использование:
    python gads_change_history.py --customer-id 7552781705 \
        --client-folder "ProfiMet" --campaign "Search | Poliweglan | Pl"

    python gads_change_history.py --client "Клиент - Google Ads" \
        --client-folder "Клиент" --date-from 2026-09-15 --date-to 2026-09-29
"""
import argparse
from datetime import date, datetime, timedelta

import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

from _config import client_stats_dir, get_client_row, sanitize_filename
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

_ENUM_CLIENT = None
# API отдаёт "START_DATE_TOO_OLD" уже на ровно 30 днях назад (проверено эмпирически
# 2026-09-30, ProfiMet) - реальная граница на 1 день строже официально заявленной
# "30 дней" в документации, поэтому берём запас в 29 дней, не 30.
MAX_HISTORY_DAYS = 29


def _enum_name(enum_type_name: str, field_name: str, value: int) -> str:
    global _ENUM_CLIENT
    if _ENUM_CLIENT is None:
        _ENUM_CLIENT = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    enum_msg = getattr(_ENUM_CLIENT.enums, enum_type_name)
    return enum_msg.DESCRIPTOR.enum_types_by_name[field_name].values_by_number[value].name


# Поля, интересные для диагностики Gate-проверки 2 (ставки/бюджет/таргетинг/
# статус) — не весь возможный набор changed_fields, а то, что реально может
# объяснить скачок метрики. Ключ — имя protobuf-поля в campaign/campaign_budget/
# ad_group/ad_group_criterion, как оно приходит в FieldMask changed_fields.
_RELEVANT_FIELD_KEYWORDS = (
    "status", "bidding_strategy", "target_cpa", "target_roas", "cpc_bid",
    "cpm_bid", "amount_micros", "budget", "geo_target", "network_settings",
    "ad_schedule",
)


# (тип ресурса или "*", путь поля) -> (имя enum-типа, имя поля enum) для расшифровки int -> имя
_ENUM_FIELDS = {
    ("CAMPAIGN", "status"): ("CampaignStatusEnum", "CampaignStatus"),
    ("AD_GROUP", "status"): ("AdGroupStatusEnum", "AdGroupStatus"),
    ("*", "ad_schedule.day_of_week"): ("DayOfWeekEnum", "DayOfWeek"),
    ("*", "ad_schedule.start_minute"): ("MinuteOfHourEnum", "MinuteOfHour"),
    ("*", "ad_schedule.end_minute"): ("MinuteOfHourEnum", "MinuteOfHour"),
}

# change_resource_type -> имя oneof-поля внутри change_event.old_resource/new_resource
_RESOURCE_ONEOF_FIELD = {
    "CAMPAIGN": "campaign",
    "CAMPAIGN_BUDGET": "campaign_budget",
    "AD_GROUP": "ad_group",
    "CAMPAIGN_CRITERION": "campaign_criterion",
    "AD_GROUP_CRITERION": "ad_group_criterion",
}


def _extract_value(changed_resource, resource_type: str, changed_field_path: str):
    """Достаёт значение изменённого поля из change_event.old_resource /
    new_resource. Пути в changed_fields ОТНОСИТЕЛЬНЫ к самому ресурсу (проверено
    2026-10-05, ProfiMet: "amount_micros" для CAMPAIGN_BUDGET,
    "maximize_conversions.target_cpa_micros" для CAMPAIGN) — первый компонент
    НЕ имя ресурса, его не пропускаем. Возвращает None, если ресурс/поле не
    удалось достать (напр. тип ресурса не в _RESOURCE_ONEOF_FIELD) — вызывающий
    код показывает это как "?", не как 0."""
    oneof = _RESOURCE_ONEOF_FIELD.get(resource_type)
    if oneof is None:
        return None
    obj = getattr(changed_resource, oneof, None)
    try:
        for part in changed_field_path.split("."):
            obj = getattr(obj, part)
    except AttributeError:
        return None
    # enum -> имя (в nested-сообщениях change_event они приходят голым int —
    # без расшифровки "status: 3 -> 2" читается неверно); *_micros -> единицы валюты
    enum_spec = _ENUM_FIELDS.get((resource_type, changed_field_path)) or _ENUM_FIELDS.get(("*", changed_field_path))
    if enum_spec and isinstance(obj, int):
        return _enum_name(enum_spec[0], enum_spec[1], obj)
    if hasattr(obj, "name") and not isinstance(obj, (str, bytes)):
        return obj.name
    if changed_field_path.endswith("_micros") and isinstance(obj, (int, float)):
        return round(obj / 1_000_000, 2)
    return obj


def _format_change(old_resource, new_resource, resource_type: str, relevant_fields: list) -> str:
    """'поле: старое -> новое' для каждого relevant-поля. CREATE даёт пустое
    old, REMOVE — пустое new (это нормально, не ошибка извлечения)."""
    parts = []
    for f in relevant_fields:
        old = _extract_value(old_resource, resource_type, f)
        new = _extract_value(new_resource, resource_type, f)
        parts.append(f"{f}: {'?' if old is None else old} -> {'?' if new is None else new}")
    return "; ".join(parts)


def fetch_change_history(ga_service, customer_id, date_from, date_to, campaign_name=None):
    """change_event -> DataFrame. date_from ограничен MAX_HISTORY_DAYS от сегодня
    на стороне API — если запрошенный date_from старше, часть истории будет
    молча отсутствовать в ответе API (не в этом скрипте) — проверяется и
    сообщается пользователю отдельно в main()."""
    query = f"""
        SELECT
            change_event.change_date_time,
            change_event.change_resource_type,
            change_event.change_resource_name,
            change_event.user_email,
            change_event.client_type,
            change_event.resource_change_operation,
            change_event.changed_fields,
            change_event.campaign,
            change_event.ad_group,
            change_event.old_resource,
            change_event.new_resource
        FROM change_event
        WHERE change_event.change_date_time >= '{date_from} 00:00:00'
            AND change_event.change_date_time <= '{date_to} 23:59:59'
        ORDER BY change_event.change_date_time DESC
        LIMIT 10000
    """

    rows = []
    for batch in ga_service.search_stream(customer_id=customer_id, query=query):
        for row in batch.results:
            ce = row.change_event
            resource_type = _enum_name(
                "ChangeEventResourceTypeEnum", "ChangeEventResourceType", ce.change_resource_type
            )
            operation = _enum_name(
                "ResourceChangeOperationEnum", "ResourceChangeOperation", ce.resource_change_operation
            )
            client_type = _enum_name("ChangeClientTypeEnum", "ChangeClientType", ce.client_type)

            changed_fields = list(ce.changed_fields.paths) if ce.changed_fields else []
            relevant = [f for f in changed_fields if any(k in f for k in _RELEVANT_FIELD_KEYWORDS)]

            rows.append({
                "Datetime": ce.change_date_time,
                "Campaign_resource": ce.campaign or "",
                "Ad_group_resource": ce.ad_group or "",
                "Resource_type": resource_type,
                "Operation": operation,
                "Client_type": client_type,
                "User_email": ce.user_email or "",
                "Changed_fields": ", ".join(changed_fields),
                "Relevant_fields": ", ".join(relevant),
                "Is_relevant": bool(relevant),
                "Value_changes": _format_change(ce.old_resource, ce.new_resource, resource_type, relevant),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if campaign_name:
        # change_event.campaign — resource name вида "customers/123/campaigns/456",
        # не содержит имя кампании напрямую -> отдельным запросом резолвим id->name
        # и фильтруем; кампании без campaign resource (напр. account-level изменения)
        # исключаются этим фильтром намеренно - они не относятся к конкретной кампании.
        camp_query = "SELECT campaign.id, campaign.name FROM campaign"
        id_to_name = {}
        for batch in ga_service.search_stream(customer_id=customer_id, query=camp_query):
            for row in batch.results:
                id_to_name[str(row.campaign.id)] = row.campaign.name
        df["Campaign_name"] = df["Campaign_resource"].apply(
            lambda r: id_to_name.get(r.rsplit("/", 1)[-1], "") if r else ""
        )
        df = df[df["Campaign_name"] == campaign_name]

    # Имя группы объявлений для правок уровня ad_group (напр. target CPA на группе)
    if "Ad_group_resource" in df.columns and (df["Ad_group_resource"] != "").any():
        ag_query = "SELECT ad_group.id, ad_group.name FROM ad_group"
        ag_names = {}
        for batch in ga_service.search_stream(customer_id=customer_id, query=ag_query):
            for row in batch.results:
                ag_names[str(row.ad_group.id)] = row.ad_group.name
        df["Ad_group_name"] = df["Ad_group_resource"].apply(
            lambda r: ag_names.get(r.rsplit("/", 1)[-1], "") if r else ""
        )

    return df.sort_values("Datetime", ascending=False).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="Значение колонки 'client' на вкладке Google_Ads_API (альтернатива --customer-id)")
    ap.add_argument("--customer-id", help="customer_id напрямую (с дефисами или без)")
    ap.add_argument("--client-folder", required=True, help='Папка клиента в Клиенты/')
    ap.add_argument("--campaign", help="Имя кампании — отфильтровать только её изменения (без флага — весь аккаунт)")
    ap.add_argument("--date-from", help="YYYY-MM-DD, по умолчанию 30 дней назад (жёсткий лимит API)")
    ap.add_argument("--date-to", help="YYYY-MM-DD, по умолчанию сегодня")
    args = ap.parse_args()

    if args.customer_id:
        customer_id = args.customer_id.replace("-", "").strip()
    elif args.client:
        row = get_client_row(args.client, tab="Google_Ads_API", agency="adwhite")
        customer_id = str(row.get("client_id", "")).replace("-", "").strip()
        if not customer_id:
            print(f"У клиента '{args.client}' на вкладке 'Google_Ads_API' пустой client_id")
            return
    else:
        print("Нужен либо --client, либо --customer-id напрямую")
        return

    date_to = args.date_to or str(date.today())
    earliest_allowed = date.today() - timedelta(days=MAX_HISTORY_DAYS)
    requested_from = date.fromisoformat(args.date_from) if args.date_from else earliest_allowed

    if requested_from < earliest_allowed:
        print(
            f"ВНИМАНИЕ: запрошено {requested_from}, но change_event отдаёт историю "
            f"максимум за {MAX_HISTORY_DAYS} дней от сегодня — реально будут получены "
            f"данные только с {earliest_allowed}. Изменения ДО {earliest_allowed} "
            f"физически недоступны через этот ресурс API (не ограничение скрипта)."
        )
        date_from = str(earliest_allowed)
    else:
        date_from = str(requested_from)

    login_customer_id = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    ga_service = get_ads_service(login_customer_id)

    print(f"Клиент: {args.client_folder} | период {date_from} -> {date_to}"
          + (f" | кампания: {args.campaign}" if args.campaign else " | весь аккаунт"))

    df = fetch_change_history(ga_service, customer_id, date_from, date_to, args.campaign)

    out_dir = client_stats_dir(args.client_folder)
    suffix = f"_{sanitize_filename(args.campaign)}" if args.campaign else ""
    out_path = out_dir / f"gads_change_history{suffix}_{date_from}_to_{date_to}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Сохранено: {out_path} ({len(df)} изменений)")

    if df.empty:
        print("Изменений за период не найдено — участок можно считать стабильным "
              "по параметрам кампании (в пределах доступной истории API, см. предупреждение выше).")
        return

    relevant_df = df[df["Is_relevant"]]
    print(f"\nИз них потенциально влияющих на метрики (ставки/бюджет/таргетинг/статус): {len(relevant_df)}")
    if not relevant_df.empty:
        cols = ["Datetime", "Resource_type", "Operation", "Value_changes", "User_email"]
        if "Ad_group_name" in relevant_df.columns:
            cols.insert(2, "Ad_group_name")
        print(relevant_df[cols].to_string(index=False))

        # Группировка по дню — для быстрой сверки "сколько правок в какой день"
        # (диагностика хаотичных частых правок, см. блок-схема, раздел
        # "неконтролируемые условия").
        relevant_df = relevant_df.copy()
        relevant_df["Date"] = relevant_df["Datetime"].str[:10]
        by_day = relevant_df.groupby("Date").size().reset_index(name="Changes_count")
        print("\nПравок по дням:")
        print(by_day.to_string(index=False))


if __name__ == "__main__":
    main()
