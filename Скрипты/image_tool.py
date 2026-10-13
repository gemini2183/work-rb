"""Инструмент картинок для рекламных ассетов Google Ads.

Подкоманды:
  specs     таблица форматов и лимитов (официальная справка Google, сверено 2026-10-13)
  check     проверить файлы: формат, пропорция, минимум пикселей, размер файла, пометка ИИ
  fit       подогнать реальное фото под форматы (кадрирование или поля), без ИИ
  generate  сгенерировать картинку у внешнего сервиса (по умолчанию только план, запись с --execute)

Скрипт работает только с локальными файлами и в рекламные кабинеты ничего не пишет.
Загрузку в кабинет делают сборщики (`gads_demand_gen_builder.py` и др.) после согласования.

Примеры:
  python Скрипты/image_tool.py specs
  python Скрипты/image_tool.py check "Клиенты/ProfiMet/Креативы/DG_карусель_карточки/*.jpg"
  python Скрипты/image_tool.py fit фото.jpg --formats landscape,square,portrait --out-dir out --focus 0.5,0.4
  python Скрипты/image_tool.py generate --backend openai --model <модель> --prompt "..." \\
      --out out/bg.png --client ProfiMet --purpose "фон для баннера"            # план
  ... --execute                                                                  # запись

Ключи: OPENAI_API_KEY (openai), GEMINI_API_KEY (gemini) — только в переменной окружения,
значения нигде не печатаются и не записываются. Ключ OPENAI_ADS_API_KEY — от OpenAI Ads,
для картинок не подходит.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import glob
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

# Источник чисел: справка Google Ads «Image asset requirements for Performance Max»
# (answer/14530211) и «Demand Gen image assets specifications» (answer/17140672),
# прочитано 2026-10-13. Не проверено на практике в кабинете.
FORMATS = {
    "landscape": {"title": "Горизонтальная 1.91:1", "ratio": 1.91, "rec": (1200, 628), "min": (600, 314)},
    "square": {"title": "Квадрат 1:1", "ratio": 1.0, "rec": (1200, 1200), "min": (300, 300)},
    "portrait": {"title": "Вертикальная 4:5", "ratio": 0.8, "rec": (960, 1200), "min": (480, 600)},
    "vertical": {"title": "Вертикальная 9:16 (только Demand Gen)", "ratio": 9 / 16, "rec": (1080, 1920), "min": (600, 1067)},
    # У Demand Gen в разных разделах одной страницы минимум квадратного логотипа 128 и 144 — берём строже.
    "logo": {"title": "Логотип 1:1", "ratio": 1.0, "rec": (1200, 1200), "min": (144, 144)},
    "logo_wide": {"title": "Логотип 4:1 (только PMax)", "ratio": 4.0, "rec": (1200, 300), "min": (512, 128)},
}
CORE = ["landscape", "square", "portrait"]
MAX_KB = 5120          # общий лимит файла
DG_LOGO_MAX_KB = 150   # лимит файла логотипа Demand Gen
RATIO_TOL = 0.015      # допуск пропорции при проверке (допущение: Google допуск не публикует)


def _fmt_kb(n_bytes: int) -> str:
    return f"{n_bytes / 1024:.0f} КБ"


def cmd_specs(_args) -> int:
    print("Формат     | Пропорция | Рекомендуется | Минимум   | Примечание")
    print("-----------|-----------|---------------|-----------|-----------")
    for key, f in FORMATS.items():
        rec = f"{f['rec'][0]}x{f['rec'][1]}"
        mn = f"{f['min'][0]}x{f['min'][1]}"
        print(f"{key:<10} | {f['ratio']:<9.3f} | {rec:<13} | {mn:<9} | {f['title']}")
    print()
    print(f"Файл: JPG или PNG, до {MAX_KB // 1024} МБ ({MAX_KB} КБ); логотип Demand Gen — до {DG_LOGO_MAX_KB} КБ.")
    print("Содержимое — в центральных 80% кадра (справка PMax). На каждую пропорцию желательна хотя бы одна картинка без наложений.")
    print("Количество (PMax): горизонтальных 4+, квадратных 4+, вертикальных 2+ (по справке; API считает вертикальные необязательными).")
    print("Источник: справка Google Ads, прочитано 2026-10-13; в кабинете не проверено.")
    return 0


def _classify(w: int, h: int, path: Path | None = None, force: str | None = None) -> str | None:
    """Формат по пропорции. Квадрат 1:1 и квадратный логотип неразличимы по размерам:
    логотипом считаем файл с `logo` в пути или заданный через --as."""
    if force:
        return force
    r = w / h
    best, best_diff = None, None
    for key, f in FORMATS.items():
        diff = abs(r - f["ratio"]) / f["ratio"]
        if diff <= RATIO_TOL and (best_diff is None or diff < best_diff):
            best, best_diff = key, diff
    if best == "square" and path is not None and "logo" in str(path).lower():
        return "logo"
    return best


def _meta_path(p: Path) -> Path:
    return p.with_name(p.name + ".meta.json")


def _expand(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        out.extend(Path(h) for h in (hits or [pat]))
    return out


def cmd_check(args) -> int:
    bad = 0
    for p in _expand(args.files):
        if not p.exists():
            print(f"НЕТ ФАЙЛА | {p}")
            bad += 1
            continue
        problems, notes = [], []
        try:
            with Image.open(p) as im:
                w, h = im.size
                fmt_name = im.format
        except Exception as e:  # битый файл, не картинка
            print(f"ОШИБКА    | {p} | не читается как картинка: {e}")
            bad += 1
            continue
        kind = _classify(w, h, p, args.as_format)
        size_b = p.stat().st_size
        if fmt_name not in ("JPEG", "PNG"):
            problems.append(f"формат {fmt_name}, нужен JPG или PNG")
        elif {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}}[fmt_name].isdisjoint({p.suffix.lower()}):
            notes.append(f"расширение {p.suffix}, а содержимое {fmt_name}")
        if kind is None:
            problems.append(f"пропорция {w / h:.3f} не совпадает ни с одним форматом")
        else:
            f = FORMATS[kind]
            if w < f["min"][0] or h < f["min"][1]:
                problems.append(f"меньше минимума {f['min'][0]}x{f['min'][1]}")
            elif w < f["rec"][0] or h < f["rec"][1]:
                notes.append(f"ниже рекомендуемого {f['rec'][0]}x{f['rec'][1]}")
        if size_b > MAX_KB * 1024:
            problems.append(f"файл {_fmt_kb(size_b)} больше лимита {MAX_KB} КБ")
        elif args.target == "demand_gen" and kind == "logo" and size_b > DG_LOGO_MAX_KB * 1024:
            # Предупреждение, не ошибка: логотип ProfiMet 1145 КБ используется в dg_lookalike_test,
            # лимит из справки на практике не подтверждён.
            notes.append(f"по справке лимит логотипа Demand Gen {DG_LOGO_MAX_KB} КБ (на практике не подтверждён)")
        mp = _meta_path(p)
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
                if meta.get("ai_generated"):
                    notes.append("ИИ: при загрузке отметить «Label this asset as created or edited with AI»; "
                                 "в ЕС, Индии и Нью-Йорке Google добавит видимую метку")
            except Exception:
                notes.append("файл .meta.json не читается")
        status = "ОШИБКА" if problems else "ок"
        if problems:
            bad += 1
        txt = "; ".join(problems + notes)
        print(f"{status:<9} | {p.name} | {w}x{h} | {fmt_name} | {_fmt_kb(size_b)} | {kind or '—'}" + (f" | {txt}" if txt else ""))
    return 1 if bad else 0


def _parse_focus(s: str) -> tuple[float, float]:
    x, y = (float(v) for v in s.split(","))
    return min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)


def _crop_box(w: int, h: int, ratio: float, fx: float, fy: float) -> tuple[int, int, int, int]:
    """Наибольший прямоугольник заданной пропорции внутри (w, h), центр — в точке фокуса, в границах кадра."""
    if w / h > ratio:
        cw, ch = int(round(h * ratio)), h
    else:
        cw, ch = w, int(round(w / ratio))
    cx, cy = fx * w, fy * h
    left = int(round(min(max(cx - cw / 2, 0), w - cw)))
    top = int(round(min(max(cy - ch / 2, 0), h - ch)))
    return left, top, left + cw, top + ch


def _save_under_limit(im: Image.Image, path: Path, max_kb: int) -> tuple[Path, int]:
    if path.suffix.lower() == ".png":
        im.save(path, optimize=True)
        return path, path.stat().st_size
    im = im.convert("RGB")
    for q in (92, 88, 84, 80, 75, 70):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True)
        if len(buf.getvalue()) <= max_kb * 1024 or q == 70:
            path.write_bytes(buf.getvalue())
            return path, len(buf.getvalue())
    raise RuntimeError("недостижимо")


def cmd_fit(args) -> int:
    src = Path(args.src)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = CORE if args.formats == "core" else [n.strip() for n in args.formats.split(",") if n.strip()]
    unknown = [n for n in names if n not in FORMATS]
    if unknown:
        print(f"Неизвестные форматы: {unknown}. Доступны: {list(FORMATS)}")
        return 2
    fx, fy = _parse_focus(args.focus)
    stem = args.name or src.stem
    with Image.open(src) as opened:
        im = opened.copy()
    has_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    w, h = im.size
    print(f"Источник: {src} {w}x{h}, режим {args.mode}, фокус {fx:.2f},{fy:.2f}")
    rc = 0
    for name in names:
        f = FORMATS[name]
        tw, th = f["rec"]
        ratio = tw / th
        if args.mode == "crop":
            box = _crop_box(w, h, ratio, fx, fy)
            piece = im.crop(box)
            kept = (box[2] - box[0]) * (box[3] - box[1]) / (w * h)
            cw, ch = piece.size
            warn = []
            if cw < f["min"][0] or ch < f["min"][1]:
                print(f"ОШИБКА | {name}: после кадрирования {cw}x{ch} меньше минимума {f['min'][0]}x{f['min'][1]}")
                rc = 1
                continue
            if cw < tw or ch < th:
                warn.append(f"апскейл ×{max(tw / cw, th / ch):.2f} (кадр {cw}x{ch} < {tw}x{th})")
            if kept < 0.5:
                warn.append(f"сохранено {kept:.0%} площади — проверьте, что главное в кадре")
            result = piece.resize((tw, th), Image.LANCZOS)
            note = f"кадр {cw}x{ch}, сохранено {kept:.0%} площади"
        else:  # pad
            scale = min(tw / w, th / h)
            nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
            body = im.convert("RGBA").resize((nw, nh), Image.LANCZOS)
            canvas = Image.new("RGBA", (tw, th), args.pad_color)
            canvas.alpha_composite(body, ((tw - nw) // 2, (th - nh) // 2))
            result = canvas
            warn = []
            note = f"вписано {nw}x{nh} на поле {args.pad_color}"
            if scale > 1:
                warn.append(f"апскейл ×{scale:.2f}")
        use_png = has_alpha and name.startswith("logo")
        path = out_dir / f"{stem}_{name}_{tw}x{th}.{'png' if use_png else 'jpg'}"
        if not use_png:
            result = result.convert("RGB")
        path, size_b = _save_under_limit(result, path, args.max_kb)
        print(f"ок | {path} | {note} | {_fmt_kb(size_b)}" + ("".join(f" | ВНИМАНИЕ: {x}" for x in warn)))
        # Происхождение переносим: реальное фото остаётся реальным, ИИ-файл — ИИ.
        smp = _meta_path(src)
        meta = {"ai_generated": False, "source_file": str(src), "derived_from_real_photo": True}
        if smp.exists():
            try:
                meta = json.loads(smp.read_text(encoding="utf-8"))
                meta["derived_from"] = str(src)
            except Exception:
                pass
        _meta_path(path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Проверьте глазами: важное — в центральных 80% кадра; если на картинке есть текст или лицо — не обрезано ли.")
    return rc


def _generate_openai(model: str, prompt: str, size: str) -> bytes:
    import requests

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("Нет переменной окружения OPENAI_API_KEY (ключ OPENAI_ADS_API_KEY для картинок не подходит).")
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "prompt": prompt, "size": size, "n": 1},
        timeout=180,
    )
    if r.status_code >= 400:
        raise SystemExit(f"OpenAI Images вернул {r.status_code}: {r.text[:400]}")
    item = r.json()["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    return requests.get(item["url"], timeout=120).content


def _generate_gemini(model: str, prompt: str) -> bytes:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("Нет переменной окружения GEMINI_API_KEY.")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for cand in resp.candidates or []:
        for part in cand.content.parts or []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                return part.inline_data.data
    raise SystemExit("Gemini не вернул изображение (возможно, отказ по политике). Ответ: " + str(resp)[:400])


def cmd_generate(args) -> int:
    prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip() if args.prompt_file else args.prompt
    if not prompt:
        print("Нужен --prompt или --prompt-file")
        return 2
    out = Path(args.out)
    print("ПЛАН ГЕНЕРАЦИИ (ничего не отправлено)" if not args.execute else "ГЕНЕРАЦИЯ")
    print(f"  сервис: {args.backend} | модель: {args.model} | размер: {args.size}")
    print(f"  файл: {out}")
    print(f"  клиент: {args.client} | назначение: {args.purpose}")
    print(f"  запрос: {prompt}")
    print("  Напоминание: результат — ИИ-ассет; при загрузке в Google Ads его нужно пометить, в ЕС/Индии/Нью-Йорке метка видна в рекламе.")
    if not args.execute:
        print("Для запуска добавьте --execute (после согласования пользователя).")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    data = _generate_openai(args.model, prompt, args.size) if args.backend == "openai" else _generate_gemini(args.model, prompt)
    out.write_bytes(data)
    with Image.open(out) as im:
        w, h = im.size
    meta = {
        "ai_generated": True, "backend": args.backend, "model": args.model, "prompt": prompt,
        "client": args.client, "purpose": args.purpose, "size": f"{w}x{h}",
        "created": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _meta_path(out).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Записано: {out} ({w}x{h}, {_fmt_kb(out.stat().st_size)}); запись происхождения: {_meta_path(out).name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("specs", help="таблица форматов").set_defaults(func=cmd_specs)

    p = sub.add_parser("check", help="проверить файлы")
    p.add_argument("files", nargs="+")
    p.add_argument("--target", choices=["pmax", "demand_gen"], default="pmax",
                   help="demand_gen включает лимит 150 КБ для логотипа")
    p.add_argument("--as", dest="as_format", choices=list(FORMATS),
                   help="считать все файлы этим форматом (например logo для квадратного логотипа без `logo` в имени)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("fit", help="подогнать реальное фото под форматы")
    p.add_argument("src")
    p.add_argument("--formats", default="core", help=f"core ({','.join(CORE)}) или список через запятую из: {','.join(FORMATS)}")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--name", help="основа имени выходных файлов (по умолчанию имя источника)")
    p.add_argument("--mode", choices=["crop", "pad"], default="crop")
    p.add_argument("--focus", default="0.5,0.5", help="x,y от 0 до 1 — центр кадрирования (по умолчанию центр)")
    p.add_argument("--pad-color", default="#ffffff")
    p.add_argument("--max-kb", type=int, default=MAX_KB)
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("generate", help="сгенерировать картинку (по умолчанию только план)")
    p.add_argument("--backend", choices=["openai", "gemini"], required=True)
    p.add_argument("--model", required=True, help="имя модели у сервиса; названия меняются — сверять с документацией")
    p.add_argument("--prompt")
    p.add_argument("--prompt-file")
    p.add_argument("--size", default="1024x1024", help="для openai; у gemini размер задаётся моделью")
    p.add_argument("--out", required=True)
    p.add_argument("--client", required=True)
    p.add_argument("--purpose", required=True)
    p.add_argument("--execute", action="store_true")
    p.set_defaults(func=cmd_generate)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
