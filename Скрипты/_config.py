"""Логин/токен клиента берутся напрямую из общей Google-таблицы (той же, что
питает продовый BigQuery-пайплайн в google-cloud-jobs), а не хранятся дублем
в этой вики. Здесь секретов нет — только путь к service account и id таблицы.

Требования к строке в таблице: колонка 'client' должна точно совпадать со
значением --client (это может быть не то же самое, что имя папки в Клиенты/,
которое передаётся отдельно через --client-folder).
"""
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

VAULT_ROOT = Path(__file__).resolve().parent.parent
SERVICE_ACCOUNT_FILE = Path(__file__).parent / "secrets" / "rb_cloud_service.json"

# Два агентства — две отдельные таблицы, одна и та же структура паттерна
# (login/token/client_id по клиенту на вкладку источника), разные адреса:
#   redbird (Директ)  — контекстная реклама Яндекс.Директ
#   adwhite (Google Ads) — контекстная реклама Google Ads/Merchant Center
SHEET_URLS = {
    "redbird": "https://docs.google.com/spreadsheets/d/1ymDNHkj32mYIb_ymf7t8O6H6WY1s5F1FN43-56fwiQM/edit",
    "adwhite": "https://docs.google.com/spreadsheets/d/1O6IJhCh5TN8NM8qMiUQKwS6nZnODU5tQ7vqb5XwOnQw/edit",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def _open_sheet(agency: str = "redbird"):
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_url(SHEET_URLS[agency])


def get_client_row(client_name: str, tab: str, agency: str = "redbird") -> dict:
    """Возвращает строку таблицы (словарь колонка->значение) по значению 'client'.

    agency — "redbird" (Директ, таблица по умолчанию) или "adwhite" (Google Ads).
    """
    sheet = _open_sheet(agency)
    worksheet = sheet.worksheet(tab)
    records = worksheet.get_all_records()
    for row in records:
        if str(row.get("client", "")).strip() == client_name.strip():
            return row
    raise ValueError(f"Клиент '{client_name}' не найден на вкладке '{tab}'")


def client_stats_dir(client_folder: str) -> Path:
    d = VAULT_ROOT / "Клиенты" / client_folder / "Статистика"
    d.mkdir(parents=True, exist_ok=True)
    return d


_WINDOWS_FORBIDDEN_CHARS = '<>:"/\\|?*'


def sanitize_filename(name: str) -> str:
    """Имя кампании/объекта Google Ads -> безопасное для имени файла на Windows.

    Windows запрещает символы <>:"/\\|?* в имени файла — заменяются на "-".
    Раньше в разных скриптах это делалось по месту через .replace("/", "-"),
    что пропускало "|" (частый символ в названиях кампаний, напр.
    "Search | Poliweglan | Pl") и падало с OSError [Errno 22] при попытке
    сохранить CSV. Найдено и исправлено 2026-09-28 на ProfiMet, см.
    Клиенты/ProfiMet/Решения.md. Единая функция — чтобы не чинить один и тот
    же баг по отдельности в каждом скрипте, где имя кампании идёт в путь файла.
    """
    result = name.strip()
    for ch in _WINDOWS_FORBIDDEN_CHARS:
        result = result.replace(ch, "-")
    # Схлопнуть повторяющиеся "-" и пробелы, образовавшиеся после замены
    # (напр. "Search | Poliweglan | Pl" -> "Search - Poliweglan - Pl", не
    # "Search --- Poliweglan --- Pl").
    while "  " in result:
        result = result.replace("  ", " ")
    while "--" in result:
        result = result.replace("--", "-")
    return result.strip(" -")
