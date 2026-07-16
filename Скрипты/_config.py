"""Общая загрузка секретов клиента из .env в корне вики.

Секреты именуются по конвенции: <CLIENT_KEY>_DIRECT_LOGIN, _DIRECT_TOKEN,
_YM_COUNTER, _YM_TOKEN. CLIENT_KEY передаётся в скрипты через --client-key
и не связан с названием папки клиента (оно передаётся отдельно через
--client-folder, так как может содержать пробелы/кириллицу).
"""
from pathlib import Path
from dotenv import dotenv_values

VAULT_ROOT = Path(__file__).resolve().parent.parent


def load_client_env(client_key: str) -> dict:
    values = dotenv_values(VAULT_ROOT / ".env")
    prefix = client_key.upper() + "_"
    result = {k[len(prefix):]: v for k, v in values.items() if k.startswith(prefix)}
    return result


def client_stats_dir(client_folder: str) -> Path:
    d = VAULT_ROOT / "Клиенты" / client_folder / "Статистика"
    d.mkdir(parents=True, exist_ok=True)
    return d
