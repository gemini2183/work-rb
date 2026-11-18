"""Проверка черновиков текстов RSA (только чтение, к кабинету не обращается).

Вход: текстовый файл, строки вида `H: заголовок` или `D: описание`
(пустые строки и строки с `#` пропускаются). Или stdin, если файл не указан.

Проверки: длина (H <= 30, D <= 90 символов), дубли (в т.ч. без учёта регистра),
запрещённые подстроки (цены, регионы, валюты), совпадение с уже действующими
текстами (--existing файл в том же формате).

Запуск (из любой папки):
  python rsa_text_check.py черновик.txt [--existing текущие.txt] [--ok-out годные.txt]
Код выхода всегда 0, итог в тексте.
"""
import argparse
import re
import sys

LIMITS = {"H": 30, "D": 90}

# Решение пользователя 12.11 (И-108): без цен и без регионов в текстах.
BANNED_RE = [
    (re.compile(r"\d+\s*(zł|pln|€|eur|euro)", re.I), "цена/валюта"),
    (re.compile(r"[€$]|zł\b", re.I), "валюта"),
    (re.compile(r"\bod\s+\d", re.I), "«od N» (цена)"),
    (re.compile(r"województw|mazowiecki|małopolsk|śląsk|dolnośląsk", re.I), "регион"),
    (re.compile(r"najtańsz|najlepsz|nr\s*1|gwarantuj", re.I), "громкое обещание"),
]


def read_lines(path):
    src = open(path, encoding="utf-8") if path else sys.stdin
    out = []
    for n, raw in enumerate(src, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([HD])\s*[:.\-)]\s*(.+)$", line, re.I)
        if not m:
            out.append((n, None, line))
            continue
        out.append((n, m.group(1).upper(), m.group(2).strip().strip('"«»')))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--existing")
    ap.add_argument("--ok-out")
    a = ap.parse_args()

    existing = set()
    if a.existing:
        existing = {t.lower() for _, k, t in read_lines(a.existing) if k}

    seen, ok, bad = set(), [], []
    for n, kind, text in read_lines(a.file):
        if kind is None:
            bad.append((n, "?", text, "не разобрана строка (нужен префикс H: или D:)"))
            continue
        why = []
        if len(text) > LIMITS[kind]:
            why.append(f"длина {len(text)} > {LIMITS[kind]}")
        for rx, name in BANNED_RE:
            if rx.search(text):
                why.append(name)
        low = text.lower()
        if low in existing:
            why.append("уже действует")
        if (kind, low) in seen:
            why.append("дубль")
        seen.add((kind, low))
        (bad if why else ok).append((n, kind, text, "; ".join(why)))

    print(f"Годных: {len(ok)} (H {sum(1 for o in ok if o[1]=='H')}, D {sum(1 for o in ok if o[1]=='D')}); отклонено: {len(bad)}")
    for n, k, t, w in bad:
        print(f"  ОТКЛОНЕНО стр.{n} {k} [{len(t)}] {t!r}: {w}")
    if a.ok_out:
        with open(a.ok_out, "w", encoding="utf-8") as f:
            for _, k, t, _ in ok:
                f.write(f"{k}: {t}\n")
        print(f"Годные записаны: {a.ok_out}")
    else:
        for _, k, t, _ in ok:
            print(f"  OK {k} [{len(t)}] {t}")


if __name__ == "__main__":
    main()
