#!/usr/bin/env python
# coding: utf-8
"""Ringostat: скачать записи разговоров, расшифровать (Whisper) и перевести на русский — ТОЛЬКО ЧТЕНИЕ из Ringostat.

Зачем: прослушать звонки клиента без ручной выгрузки Excel. Список звонков и ссылки на записи (`recording`)
берутся из API `calls/list`; ссылка живёт с токеном, поэтому скрипт всегда запрашивает свежий список и токены
в транскрипты не пишет. Номер клиента: у входящих `caller`, у исходящих `dst` (в `caller` у исходящих имя менеджера).

По умолчанию — ПЛАН: печатает, какие звонки подпадают под фильтр и сколько их, ничего не скачивает.
С `--run` — скачивает аудио, расшифровывает, переводит и пишет результат.

Куда пишет:
    Клиенты/<клиент>/Звонки/Транскрипты/<дата>_<in|out>_<хвост номера>_<uniqueid>.md   — по файлу на звонок
    Клиенты/<клиент>/Звонки/index.csv                                                  — сводка по всем обработанным
    Скрипты/secrets/call_audio/<клиент>/<uniqueid>.wav                                 — аудио (папка в .gitignore, в вики не попадает)
Уже расшифрованные звонки (файл транскрипта есть) пропускаются, повторный запуск продолжает с места остановки.

Ключ Ringostat: `--monitoring-config <файл.yaml>` (из `E:\\PythonProjects\\RedBird\\monitoring scripts\\monitoring\\config\\`),
по умолчанию — `monitoring_config` из `Клиенты/<клиент>/guard_config.yaml`; запасной вариант — переменная окружения
`RINGOSTAT_AUTH_KEY`. В вывод ключ не попадает.

Язык: `--lang auto` (по умолчанию) — Whisper определяет сам для каждого звонка; можно задать `pl`, `en`, `ru`.
Перевод: `--translate-to ru` (по умолчанию) или `none`. Для пар без прямой модели (например pl→ru) перевод идёт через английский.
Первый запуск Argos скачивает модели перевода (один раз), Whisper — модель распознавания.

Зависимости: faster-whisper, argostranslate, requests, pandas, pyyaml, tqdm; ffmpeg в PATH.

Использование (из папки Скрипты):
    PYTHONUTF8=1 python ringostat_call_transcripts.py --client-folder ProfiMet --from 2026-10-27 --to 2026-10-29            # план
    PYTHONUTF8=1 python ringostat_call_transcripts.py --client-folder ProfiMet --from 2026-10-27 --direction in --min-billsec 30 --limit 5 --run
    PYTHONUTF8=1 python ringostat_call_transcripts.py --client-folder ProfiMet --from 2026-10-01 --phones 609546589 --run
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

VAULT_ROOT = Path(__file__).resolve().parent.parent
MONITORING_DIR = Path(r"E:\PythonProjects\RedBird\monitoring scripts\monitoring")
AUDIO_ROOT = Path(__file__).resolve().parent / "secrets" / "call_audio"
API = "https://api.ringostat.net/calls/list"
FIELDS = "calldate,caller,dst,call_type,disposition,billsec,duration,uniqueid,utm_source,utm_medium,utm_campaign,pool_name,recording"


def last9(x):
    d = re.sub(r"\D", "", str(x or ""))
    return d[-9:] if len(d) >= 9 else d


def resolve_auth_key(client_folder, monitoring_config):
    """Ключ из конфига мониторинга (явный или из guard_config клиента), иначе из переменной окружения."""
    cfg_name = monitoring_config
    if not cfg_name:
        guard = VAULT_ROOT / "Клиенты" / client_folder / "guard_config.yaml"
        if guard.exists():
            cfg_name = (yaml.safe_load(guard.read_text(encoding="utf-8")) or {}).get("monitoring_config")
    if cfg_name:
        path = Path(cfg_name) if Path(cfg_name).is_absolute() else MONITORING_DIR / "config" / cfg_name
        if not path.exists():
            sys.exit(f"Конфиг мониторинга не найден: {path}")
        key = ((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("ringostat") or {}).get("auth_key")
        if key:
            return key
        sys.exit(f"В {path} нет ringostat.auth_key")
    key = os.environ.get("RINGOSTAT_AUTH_KEY")
    if not key:
        sys.exit("Ключ Ringostat не найден: задайте --monitoring-config, guard_config.yaml клиента с monitoring_config "
                 "или переменную RINGOSTAT_AUTH_KEY")
    return key


def fetch_calls(key, d_from, d_to, tz):
    r = requests.get(API, params={"export_type": "json", "from": f"{d_from} 00:00:00", "to": f"{d_to} 23:59:59", "fields": FIELDS},
                     headers={"Auth-key": key, "Content-Type": "application/json; charset=utf-8"}, timeout=300)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return df
    for c in ("utm_source", "utm_medium", "utm_campaign", "pool_name", "recording"):
        df[c] = df[c].fillna("")
    df["ts"] = pd.to_datetime(df["calldate"], errors="coerce", utc=True)
    df = df[df["ts"].notna()].copy()
    df["local"] = df["ts"].dt.tz_convert(tz)
    df["client_phone"] = [d if t == "out" else c for c, d, t in zip(df["caller"], df["dst"], df["call_type"])]
    df["p9"] = df["client_phone"].map(last9)
    df["billsec"] = pd.to_numeric(df["billsec"], errors="coerce").fillna(0).astype(int)
    return df.sort_values("ts", kind="mergesort").reset_index(drop=True)


def select_calls(df, a):
    s = df[df["recording"].str.startswith("http")]
    if a.direction != "all":
        s = s[s["call_type"] == a.direction]
    s = s[s["billsec"] >= a.min_billsec]
    if a.phones:
        wanted = {last9(p) for p in a.phones.split(",") if p.strip()}
        s = s[s["p9"].isin(wanted)]
    if a.limit:
        s = s.head(a.limit)
    return s


def call_stem(row):
    uid = re.sub(r"[^\w.-]+", "_", str(row["uniqueid"]))
    return f'{row["local"].strftime("%Y-%m-%d_%H%M")}_{row["call_type"]}_{row["p9"][-4:] or "xxxx"}_{uid}'


def download(url, path, retries=5):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=60, stream=True)
            if r.status_code == 429:
                time.sleep(5 * 2 ** (attempt - 1))
                continue
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            print(f"  [ошибка скачивания, попытка {attempt}/{retries}] {e}")
            time.sleep(5 * 2 ** (attempt - 1))
    return False


def ensure_translation(src, dst):
    """Ставит модели Argos для пары src→dst; если прямой нет — через английский. Возвращает False, если перевод невозможен."""
    import argostranslate.package as pkg
    import argostranslate.translate as tr

    def installed():
        return {l.code for l in tr.get_installed_languages()}

    def has_path(s, d):
        langs = {l.code: l for l in tr.get_installed_languages()}
        return s in langs and d in langs and langs[s].get_translation(langs[d]) is not None

    if src == dst or has_path(src, dst):
        return True
    pkg.update_package_index()
    avail = pkg.get_available_packages()
    for s, d in ([(src, dst)] if any(p.from_code == src and p.to_code == dst for p in avail) else [(src, "en"), ("en", dst)]):
        if has_path(s, d):
            continue
        p = next((p for p in avail if p.from_code == s and p.to_code == d), None)
        if p is None:
            print(f"  [перевод] модели {s}→{d} нет в Argos")
            return False
        print(f"  [перевод] скачиваю модель {s}→{d} (один раз)")
        pkg.install_from_path(p.download())
    return has_path(src, dst)


def ts_fmt(sec):
    return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}"


def process(sel, a, client_dir, audio_dir):
    from faster_whisper import WhisperModel
    import argostranslate.translate as tr
    from tqdm import tqdm

    tdir = client_dir / "Транскрипты"
    tdir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    print(f"Загружаю Whisper ({a.model})…")
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)
    trans_ok = {}
    rows = []
    for _, row in tqdm(list(sel.iterrows()), desc="Звонки", unit="звонок"):
        stem = call_stem(row)
        out = tdir / f"{stem}.md"
        meta = {"uniqueid": row["uniqueid"], "дата": row["local"].strftime("%Y-%m-%d %H:%M"), "тип": row["call_type"],
                "номер_клиента": row["client_phone"], "длительность_с": row["billsec"], "статус": row["disposition"],
                "источник": row["utm_source"], "кампания": row["utm_campaign"], "файл": out.name}
        if out.exists():
            rows.append({**meta, "язык": "", "статус_обработки": "уже было"})
            continue
        wav = audio_dir / f'{re.sub(r"[^\w.-]+", "_", str(row["uniqueid"]))}.wav'
        if not wav.exists() and not download(row["recording"], wav):
            rows.append({**meta, "язык": "", "статус_обработки": "не скачалось"})
            continue
        try:
            segs, info = model.transcribe(str(wav), language=None if a.lang == "auto" else a.lang, beam_size=5, vad_filter=True)
            segs = [(s.start, s.end, s.text.strip()) for s in segs if s.text.strip()]
        except Exception as e:  # noqa: BLE001 — битая запись не должна ронять весь прогон
            print(f"  [ошибка распознавания] {stem}: {e}")
            rows.append({**meta, "язык": "", "статус_обработки": "ошибка распознавания"})
            continue
        lang = info.language
        do_tr = a.translate_to != "none" and lang != a.translate_to
        if do_tr and lang not in trans_ok:
            trans_ok[lang] = ensure_translation(lang, a.translate_to)
        do_tr = do_tr and trans_ok.get(lang)
        orig = [f"[{ts_fmt(s)} -> {ts_fmt(e)}] {t}" for s, e, t in segs]
        trn = [f"[{ts_fmt(s)} -> {ts_fmt(e)}] {tr.translate(t, lang, a.translate_to)}" for s, e, t in segs] if do_tr else []
        head = ["---"] + [f"{k}: {v}" for k, v in meta.items()] + [f"язык_записи: {lang}", "---", ""]
        body = []
        if trn:
            body += [f"## Перевод ({a.translate_to})", *trn, ""]
        body += [f"## Оригинал ({lang})", *(orig or ["(речь не распознана)"])]
        out.write_text("\n".join(head + body) + "\n", encoding="utf-8")
        rows.append({**meta, "язык": lang, "статус_обработки": "готово" if (trn or lang == a.translate_to or a.translate_to == "none") else "без перевода"})
        if not a.keep_audio:
            wav.unlink(missing_ok=True)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--client-folder", required=True, help="папка в Клиенты/, например ProfiMet")
    ap.add_argument("--monitoring-config", default=None, help="файл в monitoring/config (по умолчанию из guard_config клиента)")
    ap.add_argument("--from", dest="d_from", required=True)
    ap.add_argument("--to", dest="d_to", default=pd.Timestamp.now().strftime("%Y-%m-%d"))
    ap.add_argument("--tz", default="Europe/Warsaw")
    ap.add_argument("--direction", choices=["in", "out", "all"], default="in")
    ap.add_argument("--min-billsec", type=int, default=20, help="минимальная длительность разговора, с (короче — обычно сброс/автоответчик)")
    ap.add_argument("--phones", default="", help="через запятую; сравнение по последним 9 цифрам")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--translate-to", default="ru")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--keep-audio", action="store_true", help="не удалять .wav после расшифровки")
    ap.add_argument("--run", action="store_true", help="скачать, расшифровать, перевести (без флага — только план)")
    a = ap.parse_args()

    key = resolve_auth_key(a.client_folder, a.monitoring_config)
    df = fetch_calls(key, a.d_from, a.d_to, a.tz)
    if df.empty:
        sys.exit("За период звонков нет.")
    sel = select_calls(df, a)
    with_rec = df["recording"].str.startswith("http")
    print(f"Ringostat {a.d_from} … {a.d_to}: звонков {len(df)}, с записью {int(with_rec.sum())}; "
          f"под фильтр (тип={a.direction}, ≥{a.min_billsec} с" + (f", номера {a.phones}" if a.phones else "") + f"): {len(sel)}; "
          f"суммарно разговора {sel['billsec'].sum() / 60:.0f} мин")
    if sel.empty:
        return
    client_dir = VAULT_ROOT / "Клиенты" / a.client_folder / "Звонки"
    done = sum((client_dir / "Транскрипты" / f"{call_stem(r)}.md").exists() for _, r in sel.iterrows())
    print(f"Уже расшифровано ранее: {done}; к обработке: {len(sel) - done}")
    if not a.run:
        print("\nПлан (первые 25):")
        for _, r in sel.head(25).iterrows():
            print(f'  {r["local"].strftime("%Y-%m-%d %H:%M")} {r["call_type"]:>3} {r["billsec"]:>4} с  …{r["p9"][-4:]}  {r["utm_source"] or "—"}')
        print("\nЭто план. Для скачивания и расшифровки добавьте --run.")
        return

    rows = process(sel, a, client_dir, AUDIO_ROOT / a.client_folder)
    idx_path = client_dir / "index.csv"
    new = pd.DataFrame(rows)
    if idx_path.exists():
        old = pd.read_csv(idx_path, dtype=str, encoding="utf-8-sig")
        # строки «уже было» не затирают прежние записи о языке и статусе
        new = new[new["статус_обработки"] != "уже было"]
        old = old[~old["uniqueid"].isin(new["uniqueid"].astype(str))]
        new = pd.concat([old, new], ignore_index=True)
    new.sort_values("дата").to_csv(idx_path, index=False, encoding="utf-8-sig")
    print("\nИтог:", pd.DataFrame(rows)["статус_обработки"].value_counts().to_dict())
    print(f"Транскрипты: {client_dir / 'Транскрипты'}\nСводка: {idx_path}")


if __name__ == "__main__":
    main()
