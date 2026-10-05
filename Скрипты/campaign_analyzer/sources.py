"""Источники данных: Google Ads API, Ringostat (через адаптер-модуль из конфига),
план из Google-таблицы. Только сбор — никаких выводов."""
import importlib
import re

import gspread
import pandas as pd
import yaml
from google.ads.googleads.client import GoogleAdsClient
from google.oauth2.service_account import Credentials

from _config import SCOPES, SERVICE_ACCOUNT_FILE, VAULT_ROOT
from gads_stats import GOOGLE_ADS_YAML, get_ads_service

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
             "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def load_config(client_folder: str) -> dict:
    path = VAULT_ROOT / "Клиенты" / client_folder / "analysis_config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ads_service():
    login = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML).login_customer_id
    return get_ads_service(login)


def fetch_ads_spend(svc, customer_id, date_from, date_to) -> pd.DataFrame:
    """Расход по кампаниям и дням (все кампании аккаунта)."""
    q = f"""
        SELECT campaign.id, campaign.name, segments.date, metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    rows = []
    for batch in svc.search_stream(customer_id=customer_id, query=q):
        for r in batch.results:
            rows.append({"campaign_id": str(r.campaign.id), "campaign": r.campaign.name,
                         "date": r.segments.date, "cost": r.metrics.cost_micros / 1e6})
    df = pd.DataFrame(rows, columns=["campaign_id", "campaign", "date", "cost"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_ads_conversions(svc, customer_id, date_from, date_to) -> pd.DataFrame:
    """Конверсии (primary) по кампаниям, дням и конверсионным действиям."""
    q = f"""
        SELECT campaign.id, campaign.name, segments.date,
               segments.conversion_action_name, metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            AND metrics.conversions > 0
    """
    rows = []
    for batch in svc.search_stream(customer_id=customer_id, query=q):
        for r in batch.results:
            rows.append({"campaign_id": str(r.campaign.id), "campaign": r.campaign.name,
                         "date": r.segments.date, "action": r.segments.conversion_action_name,
                         "conversions": r.metrics.conversions})
    df = pd.DataFrame(rows, columns=["campaign_id", "campaign", "date", "action", "conversions"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_calls(cfg: dict, date_to: str) -> pd.DataFrame:
    """Звонки Ringostat через адаптер-модуль (тот же, что в прод-логике клиента).

    Возвращает по строке на каждый сырой звонок категорий Google Ads/SEO/
    Facebook/No Source (как в прод-скрипте — только по ним считается
    уникальность). Колонки: day, caller, category, pool_name, is_static,
    campaign_id (из utm_campaign, если там id), is_new (первый звонок этого
    номера за всю историю — "уникальный" по методологии прод-таблицы)."""
    mod = importlib.import_module(cfg["ringostat"]["module"])
    raw = mod.fetch_ringostat_calls(date_to)
    raw = raw.copy()
    raw["category"] = raw.apply(mod.categorize_source, axis=1)
    raw = raw[raw["category"].isin(["Google Ads", "Google SEO", "Facebook", "No Source"])]
    local = pd.to_datetime(raw["calldate"]).dt.tz_convert(cfg["timezone"])
    raw["day"] = local.dt.tz_localize(None).dt.normalize()
    raw = raw.sort_values("calldate")
    raw["is_new"] = ~raw.duplicated("caller", keep="first")
    raw["is_static"] = raw["pool_name"] == mod.STATIC_POOL_NAME
    raw["campaign_id"] = raw["utm_campaign"].astype(str).str.extract(r"(\d{8,})", expand=False)
    return raw[["day", "caller", "category", "pool_name", "is_static", "campaign_id", "is_new"]]


def read_plan(cfg: dict, ref_date: pd.Timestamp) -> dict:
    """План клиента на месяц ref_date из Google-таблицы (лист "<Месяц> <гг>")."""
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(cfg["plan"]["sheet_id"])
    tab = f"{MONTHS_RU[ref_date.month - 1]} {ref_date.strftime('%y')}"
    rows = sh.worksheet(tab).get_all_records()
    for r in rows:
        if str(r.get("Client", "")).strip() == cfg["plan"]["client_name"]:
            num = lambda v: float(str(v).replace(",", ".").replace(" ", "") or 0)
            return {"tab": tab, "cpa": num(r["CPA"]), "leads": num(r["Conversions"]),
                    "budget": num(r[cfg["plan"]["budget_column"]])}
    raise ValueError(f"В листе '{tab}' нет строки '{cfg['plan']['client_name']}'")
