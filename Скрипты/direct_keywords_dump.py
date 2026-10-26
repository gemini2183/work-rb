#!/usr/bin/env python
# coding: utf-8
"""Выгрузка всех ключевых слов клиента из Яндекс.Директа: кампания, группа, ключ (только чтение).

Берёт все кампании кабинета (включая архив), все их группы и все ключи, пишет одну таблицу
CSV (с BOM, открывается в Excel) в Клиенты/<папка>/Статистика/keywords_full.csv и печатает сводку
по кампаниям. Токен клиента — из файла (--token-file), файл не удаляется (удалить после аудита).

Использование:
    python direct_keywords_dump.py --login porg-juupcxo3 \
        --token-file "C:\\Users\\<user>\\AppData\\Local\\Temp\\novotel_direct.token.txt" \
        --client-folder Novotel_Moscow_City
"""
import argparse
import sys
from pathlib import Path
from time import sleep

import pandas as pd

from direct_express_audit import ALL_STATES, Direct, read_token

VAULT_ROOT = Path(__file__).resolve().parent.parent
KW_FIELDS = ["Id", "Keyword", "State", "Status", "ServingStatus", "AdGroupId", "CampaignId", "Bid", "StrategyPriority"]


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--client-folder", required=True)
    args = ap.parse_args()

    api = Direct(args.login, read_token(args.token_file))

    camps, err = api.get_all("campaigns", {"SelectionCriteria": {"States": ALL_STATES},
                                            "FieldNames": ["Id", "Name", "State", "Type", "StartDate"]}, "Campaigns")
    if camps is None:
        sys.exit(f"campaigns.get: {err}")
    cdf = pd.DataFrame(camps)[["Id", "Name", "State", "StartDate"]].rename(
        columns={"Id": "CampaignId", "Name": "Кампания", "State": "Состояние кампании", "StartDate": "Старт"})
    ids = [c["Id"] for c in camps]
    print(f"Кампаний: {len(ids)}")

    def get_retry(service, params, key, tries=5):
        """Запрос с повторами: код 1000 «сервис временно недоступен» бывает сбоем на стороне Директа."""
        e = None
        for i in range(tries):
            r, e = api.get_all(service, params, key)
            if r is not None:
                return r, None
            if (e or {}).get("error_code") != 1000:
                break
            sleep(5 * (i + 1))
        return None, e

    groups, kws = [], []
    for cid in ids:
        g, e = get_retry("adgroups", {"SelectionCriteria": {"CampaignIds": [cid]},
                                      "FieldNames": ["Id", "Name", "CampaignId", "Status", "ServingStatus"]}, "AdGroups")
        if g is None:
            sys.exit(f"adgroups.get кампания {cid}: {e}")
        groups += g
        k, e = get_retry("keywords", {"SelectionCriteria": {"CampaignIds": [cid]}, "FieldNames": KW_FIELDS}, "Keywords")
        if k is None and (e or {}).get("error_code") != 1000:
            print(f"  кампания {cid}: расширенные поля не прошли ({e}); повтор с минимальными")
            k, e = get_retry("keywords", {"SelectionCriteria": {"CampaignIds": [cid]},
                                          "FieldNames": ["Id", "Keyword", "State", "Status", "AdGroupId", "CampaignId"]}, "Keywords")
        if k is None:
            sys.exit(f"keywords.get кампания {cid}: {e}")
        print(f"  кампания {cid}: групп {len(g)}, ключей {len(k)}")
        kws += k

    gdf = pd.DataFrame(groups).rename(columns={"Id": "AdGroupId", "Name": "Группа", "Status": "Статус группы"})
    kdf = pd.DataFrame(kws).rename(columns={"Id": "KeywordId", "Keyword": "Ключевое слово", "State": "Состояние ключа",
                                            "Status": "Статус ключа", "Bid": "Ставка (микро)"})
    if "Ставка (микро)" in kdf.columns:
        kdf["Ставка, ₽"] = (pd.to_numeric(kdf["Ставка (микро)"], errors="coerce") / 1e6).round(2)
        kdf = kdf.drop(columns=["Ставка (микро)"])
    out = (kdf.merge(gdf[["AdGroupId", "Группа", "Статус группы"]], on="AdGroupId", how="left")
              .merge(cdf, on="CampaignId", how="left"))
    cols = ["Кампания", "CampaignId", "Состояние кампании", "Старт", "Группа", "AdGroupId", "Ключевое слово",
            "Состояние ключа", "Статус ключа"] + [c for c in ("Ставка, ₽", "StrategyPriority") if c in out.columns]
    out = out[cols].sort_values(["Старт", "Кампания", "Группа", "Ключевое слово"])
    path = VAULT_ROOT / "Клиенты" / args.client_folder / "Статистика" / "keywords_full.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 250, "display.max_colwidth", 90)
    summ = (out.groupby(["Старт", "Кампания", "Состояние кампании"])
               .agg(групп=("Группа", "nunique"), ключей=("Ключевое слово", "count"),
                    уникальных=("Ключевое слово", "nunique")).reset_index())
    print(summ.to_string(index=False))
    print(f"\nВсего ключей: {len(out)} в {out['AdGroupId'].nunique()} группах, {out['CampaignId'].nunique()} кампаниях")
    print(f"Файл: {path}")


if __name__ == "__main__":
    main()
