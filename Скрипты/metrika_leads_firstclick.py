#!/usr/bin/env python
# coding: utf-8
"""Заявки (достижения цели) из Яндекс.Метрики по ПЕРВОМУ клику (firstUTM*).

Зачем: фильтр по ym:s:UTMSource (как в metrika_stats_mokry_nos_dzen.py) берёт
последний UTM визита и занижает заявки, пришедшие с рекламы, но оформленные
повторным визитом. Здесь источник/кампания/content/term - first-click
(ym:s:firstUTMSource и т.д.), см. reference_metrika_first_click_filter.

Что делает: читает Reporting API Метрики (stat/v1/data.csv), только чтение.
Режимы --level:
  day   - по дням: дата, firstUTMSource/Campaign/Content, число заявок (достижений цели);
  visit - по визитам: дата-время, ClientID, first источник/кампания/content/term,
          URL входа, устройство, город.
Фильтр: визиты, где достигнута цель (ym:s:goal<ID>reaches>0) и, если задан
--first-utm-source-regex, firstUTMSource =~ regex (пусто = все источники).

Без --run - сухой режим: печатает план запроса (без токена), в API не ходит и
таблицу с токенами не открывает. С --run - читает данные и пишет CSV в
Клиенты/<--client-folder>/Статистика/. Записей в Метрику/кабинеты скрипт не делает.

Токен: из таблицы агентства (Скрипты/_config.py, вкладка Metrika, столбец token)
по строке --token-client (имя клиента в таблице; токен общий на аккаунт).
Ключи в вывод не печатаются.

Пример:
  python metrika_leads_firstclick.py --counter-id 66145201 --goal-id 143150284 \\
      --from 2026-10-01 --to 2026-11-18 --first-utm-source-regex promopages \\
      --client-folder "Франшиза Мокрый Нос Дзен" \\
      --token-client "Мокрый Нос - Груминг Франшиза" --level day --run

Дата создания: 2026-11-18.
"""
import argparse
import io
from datetime import date

DAY_DIMS = ("ym:s:date,ym:s:firstUTMSource,ym:s:firstUTMCampaign,"
            "ym:s:firstUTMContent")
VISIT_DIMS = ("ym:s:dateTime,ym:s:clientID,ym:s:firstUTMSource,"
              "ym:s:firstUTMCampaign,ym:s:firstUTMContent,ym:s:firstUTMTerm,"
              "ym:s:startURL,ym:s:deviceCategory,ym:s:regionCity")
API_URL = "https://api-metrika.yandex.ru/stat/v1/data.csv"
PAGE = 10000


def build_params(args, offset=1):
    flt = f"ym:s:goal{args.goal_id}reaches>0"
    if args.first_utm_source_regex:
        rx = args.first_utm_source_regex.replace("'", "\\'")
        flt += f" AND ym:s:firstUTMSource=~'{rx}'"
    return {
        "ids": args.counter_id,
        "dimensions": DAY_DIMS if args.level == "day" else VISIT_DIMS,
        "metrics": f"ym:s:visits,ym:s:goal{args.goal_id}reaches",
        "filters": flt,
        "date1": args.date_from,
        "date2": args.date_to,
        "sort": "ym:s:dateTime" if args.level == "visit" else "ym:s:date",
        "limit": PAGE,
        "offset": offset,
        "language": "ru",
        "accuracy": "full",
    }


def fetch_all(args, token):
    import pandas as pd
    import requests
    frames, offset = [], 1
    while True:
        r = requests.get(API_URL, params=build_params(args, offset),
                         headers={"Authorization": f"OAuth {token}"}, timeout=300)
        if r.status_code != 200:
            raise SystemExit(f"Ошибка {r.status_code}: {r.text[:500]}")
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
        df = df[df.iloc[:, 0].astype(str) != "Итого и средние"]
        frames.append(df)
        if len(df) < PAGE:
            break
        offset += PAGE
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser(description="Заявки Метрики по первому клику (только чтение)")
    ap.add_argument("--counter-id", required=True)
    ap.add_argument("--goal-id", required=True)
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--first-utm-source-regex", default="",
                    help="regex по firstUTMSource; пусто = все источники (пример: promopages)")
    ap.add_argument("--client-folder", required=True, help="папка клиента в Клиенты/ (CSV в Статистика/)")
    ap.add_argument("--level", choices=["day", "visit"], default="day")
    ap.add_argument("--token-client", default="",
                    help="строка таблицы агентства (вкладка Metrika), откуда брать token; нужна для --run")
    ap.add_argument("--run", action="store_true", help="выполнить чтение API (без флага - только план)")
    args = ap.parse_args()
    date.fromisoformat(args.date_from)
    date.fromisoformat(args.date_to)

    p = build_params(args)
    print("План (только чтение Reporting API Метрики):")
    for k in ("ids", "dimensions", "metrics", "filters", "date1", "date2"):
        print(f"  {k}: {p[k]}")
    out_name = (f"metrika_leads_firstclick_{args.level}_goal{args.goal_id}_"
                f"{args.date_from}_to_{args.date_to}.csv")
    print(f"  файл: Клиенты/{args.client_folder}/Статистика/{out_name}")
    if not args.run:
        print("Сухой режим: запрос не выполнялся. Для выполнения добавьте --run.")
        return
    if not args.token_client:
        raise SystemExit("Для --run нужен --token-client (строка вкладки Metrika)")

    from _config import get_client_row, client_stats_dir
    row = get_client_row(args.token_client, tab="Metrika")
    token = str(row.get("token", "")).strip()
    if not token:
        raise SystemExit(f"У '{args.token_client}' пустой token")

    df = fetch_all(args, token)
    # последняя колонка - достижения цели (заявки); визиты в группе - справочно
    leads_col = df.columns[-1] if len(df) else None
    if leads_col:
        df[leads_col] = pd_numeric(df[leads_col])
        df = df.rename(columns={leads_col: "Заявки (достижения цели)"})
        df = df[df["Заявки (достижения цели)"] > 0]
    path = client_stats_dir(args.client_folder) / out_name
    df.to_csv(path, index=False, encoding="utf-8")
    total = int(df["Заявки (достижения цели)"].sum()) if len(df) else 0
    print(f"Сохранено: {path} ({len(df)} строк, заявок: {total})")
    if args.level == "day" and len(df):
        by_day = df.groupby(df.columns[0])["Заявки (достижения цели)"].sum()
        print("По дням (заявки):")
        for d, v in by_day.items():
            print(f"  {d}: {int(v)}")


def pd_numeric(s):
    import pandas as pd
    return pd.to_numeric(s, errors="coerce").fillna(0)


if __name__ == "__main__":
    main()
