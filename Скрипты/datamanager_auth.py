#!/usr/bin/env python
# coding: utf-8
"""Одноразовая авторизация для Data Manager API (область `https://www.googleapis.com/auth/datamanager`).

Берёт OAuth-клиент из secrets/google-ads.yaml, открывает браузер на этом компьютере, ждёт «Разрешить» (адрес возврата —
localhost, копировать код не нужно) и сохраняет токен в secrets/datamanager_token.json (папка secrets/ в .gitignore).
Секреты в вывод не печатаются.

Использование:
    python datamanager_auth.py
"""
import json
from pathlib import Path

import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/datamanager"]
SECRETS = Path(__file__).resolve().parent / "secrets"


def main():
    cfg = yaml.safe_load(open(SECRETS / "google-ads.yaml", encoding="utf-8"))
    client_config = {"installed": {
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"]}}
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline",
                                  authorization_prompt_message="Открываю браузер для входа…",
                                  success_message="Готово, можно закрыть вкладку и вернуться в Claude Code.")
    out = SECRETS / "datamanager_token.json"
    out.write_text(json.dumps({"refresh_token": creds.refresh_token, "client_id": cfg["client_id"],
                               "client_secret": cfg["client_secret"], "scopes": SCOPES}, ensure_ascii=False), encoding="utf-8")
    print("Токен сохранён:", out, "| refresh_token получен:", bool(creds.refresh_token))


if __name__ == "__main__":
    main()
