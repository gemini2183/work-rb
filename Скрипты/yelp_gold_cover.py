"""Золото на чёрном: обложка / квадрат для Yelp из реальных фото (Pillow, без ИИ).

Раскладки (--layout): cover_a (2 панели, текст слева), cover_b (3 панели, текст справа),
square (одно фото по центру, текст сверху и снизу). Размер, фото, фокус, тексты - аргументы.
Пример:
  python -I Скрипты/yelp_gold_cover.py --layout cover_a --size 1680x1200 \
     --photo "D:/.../o (3).jpg@0.5,0.5" --photo "D:/.../o.jpg@0.5,0.5" --out cover_A_1680x1200.jpg
Фото: путь[@fx,fy] - фокус кадрирования 0..1. Пишет .meta.json рядом (--meta-note, --variant).
"""
import argparse, json, os, datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

SERIF = "C:/Windows/Fonts/NotoSerif-Bold.ttf"
SANS = "C:/Windows/Fonts/NotoSans-Regular.ttf"
SANSB = "C:/Windows/Fonts/NotoSans-Bold.ttf"
GOLD_STOPS = [(0.0, (255, 240, 185)), (0.32, (232, 186, 84)), (0.55, (156, 108, 34)),
              (0.78, (238, 200, 104)), (1.0, (178, 128, 46))]
BG = (9, 8, 7)
# Темы: dark (по умолчанию), yellow (насыщенное золото, тёмный текст), light (шампань, тёмно-золотой текст)
THEMES = {
    "dark": {},
    "yellow": {
        "bg_top": (252, 206, 40), "bg_bot": (222, 140, 18), "glow": (255, 238, 140), "glow_a": 0.85,
        "vig": (120, 60, 6), "vig_a": 0.55,
        "head_stops": [(0.0, (92, 56, 14)), (0.5, (44, 24, 6)), (1.0, (68, 40, 10))],
        "outline": (255, 226, 120), "outline_w": 3, "shadow": (110, 60, 0), "shadow_a": 120,
        "l1c": (46, 26, 8), "l3c": (44, 24, 6), "l4c": (74, 44, 12),
        "rule": (70, 40, 10), "diamond": (44, 24, 6),
        "frame_stops": [(0.0, (92, 58, 16)), (0.5, (40, 22, 6)), (1.0, (80, 50, 14))], "mat": (22, 14, 6),
        "inner": (236, 190, 80)},
    "light": {
        "bg_top": (250, 242, 222), "bg_bot": (232, 210, 160), "glow": (255, 252, 240), "glow_a": 0.9,
        "vig": (176, 134, 56), "vig_a": 0.45,
        "head_stops": [(0.0, (150, 100, 24)), (0.5, (92, 56, 10)), (1.0, (122, 80, 18))],
        "outline": None, "outline_w": 0, "shadow": (120, 80, 20), "shadow_a": 90,
        "l1c": (84, 52, 12), "l3c": (74, 46, 10), "l4c": (104, 74, 28),
        "rule": (150, 104, 30), "diamond": (122, 80, 18),
        "frame_stops": [(0.0, (206, 158, 64)), (0.5, (140, 96, 26)), (1.0, (196, 148, 56))], "mat": (252, 247, 236),
        "inner": (150, 104, 30)},
}
T = {}
WEBUY_RATIO = 0.8  # высота WE BUY относительно JEWELRY (Noto Serif Bold, золотой градиент)


def lerp_stops(t, stops):
    t = max(0.0, min(1.0, t))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            u = (t - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * u) for i in range(3))
    return stops[-1][1]


def gold_gradient(w, h, diagonal=False, stops=None):
    stops = stops or GOLD_STOPS
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(w):
            t = (y / max(h - 1, 1)) if not diagonal else ((x / w) * 0.5 + (y / h) * 0.5)
            px[x, y] = lerp_stops(t, stops)
    return g


def background_themed(W, H, glow_xy):
    col = Image.new("RGB", (1, 256))
    for i in range(256):
        a, b, u = T["bg_top"], T["bg_bot"], i / 255
        col.putpixel((0, i), tuple(int(a[k] + (b[k] - a[k]) * u) for k in range(3)))
    bg = col.resize((W, H), Image.BILINEAR)
    glow = Image.new("L", (W, H), 0)
    r = int(min(W, H) * 0.42)
    ImageDraw.Draw(glow).ellipse([glow_xy[0] - r, glow_xy[1] - r, glow_xy[0] + r, glow_xy[1] + r], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(int(min(W, H) * 0.2)))
    bg = Image.composite(Image.new("RGB", (W, H), T["glow"]), bg, glow.point(lambda v: int(v * T["glow_a"])))
    edge = Image.new("L", (W, H), 255)
    ImageDraw.Draw(edge).ellipse([-W * 0.2, -H * 0.2, W * 1.2, H * 1.2], fill=0)
    edge = edge.filter(ImageFilter.GaussianBlur(int(min(W, H) * 0.18)))
    return Image.composite(Image.new("RGB", (W, H), T["vig"]), bg, edge.point(lambda v: int(v * T["vig_a"])))


def background(W, H, glow_xy):
    if T:
        return background_themed(W, H, glow_xy)
    bg = Image.new("RGB", (W, H), BG)
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    r = int(min(W, H) * 0.55)
    d.ellipse([glow_xy[0] - r, glow_xy[1] - r, glow_xy[0] + r, glow_xy[1] + r], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(int(min(W, H) * 0.22)))
    gold = Image.new("RGB", (W, H), (120, 84, 26))
    bg = Image.composite(gold, bg, glow.point(lambda v: int(v * 0.42)))
    # лёгкая виньетка
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.15, -H * 0.15, W * 1.15, H * 1.15], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(int(min(W, H) * 0.2)))
    return Image.composite(bg, Image.new("RGB", (W, H), (0, 0, 0)), vig.point(lambda v: 120 + v * 135 // 255))


def text_width(txt, font, track):
    return sum(font.getlength(c) for c in txt) + track * (len(txt) - 1)


def fit_font(path, txt, track_ratio, max_w, start):
    s = start
    while s > 10:
        f = ImageFont.truetype(path, s)
        if text_width(txt, f, s * track_ratio) <= max_w:
            return f
        s -= 2
    return ImageFont.truetype(path, 10)


def draw_tracked(base, xy, txt, font, track, gold=True, color=(225, 210, 170), anchor_x="left"):
    W, H = base.size
    tw = int(text_width(txt, font, track))
    x0, y0 = xy
    if anchor_x == "center":
        x0 -= tw // 2
    asc, desc = font.getmetrics()
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    x = x0
    for c in txt:
        d.text((x, y0), c, font=font, fill=255)
        x += font.getlength(c) + track
    box = (x0 - 4, y0 - 4, x0 + tw + 4, y0 + asc + desc + 4)
    if gold:
        bw, bh = box[2] - box[0], box[3] - box[1]
        grad = gold_gradient(bw, bh, stops=T.get("head_stops"))
        layer = Image.new("RGB", (W, H), color)
        layer.paste(grad, (box[0], box[1]))
    else:
        layer = Image.new("RGB", (W, H), color)
    # мягкая тень под текстом
    sa = T.get("shadow_a", 160)
    sh = mask.filter(ImageFilter.GaussianBlur(6)).point(lambda v: v * sa // 255)
    base.paste(Image.new("RGB", (W, H), T.get("shadow", (0, 0, 0))), (6, 8), sh)
    if gold and T.get("outline"):
        ow = T["outline_w"]
        big = mask.filter(ImageFilter.MaxFilter(2 * ow + 1))
        base.paste(Image.new("RGB", (W, H), T["outline"]), (0, 0), big)
    base.paste(layer, (0, 0), mask)
    return tw, asc + desc


def rule_with_diamond(base, x, y, length, align="left"):
    d = ImageDraw.Draw(base)
    x0 = x if align == "left" else x - length // 2
    mid = x0 + length // 2
    col = T.get("rule", (214, 168, 78))
    d.line([(x0, y), (mid - 16, y)], fill=col, width=2)
    d.line([(mid + 16, y), (x0 + length, y)], fill=col, width=2)
    d.polygon([(mid, y - 8), (mid + 8, y), (mid, y + 8), (mid - 8, y)], fill=T.get("diamond", (240, 205, 120)))


def crop_to(img, w, h, focus):
    iw, ih = img.size
    scale = max(w / iw, h / ih) * (focus[2] if len(focus) > 2 else 1.0)
    img = img.resize((max(w, round(iw * scale)), max(h, round(ih * scale))), Image.LANCZOS)
    iw, ih = img.size
    left = min(max(int(focus[0] * iw - w / 2), 0), iw - w)
    top = min(max(int(focus[1] * ih - h / 2), 0), ih - h)
    return img.crop((left, top, left + w, top + h))


def framed_panel(base, photo, focus, x, y, w, h, bw=5, mat=10):
    W, H = base.size
    # тень
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rectangle([x + 14, y + 22, x + w + 14, y + h + 22], fill=200)
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    base.paste(Image.new("RGB", (W, H), T.get("shadow", (0, 0, 0))), (0, 0), sh)
    # рамка
    base.paste(gold_gradient(w, h, diagonal=True, stops=T.get("frame_stops")), (x, y))
    ImageDraw.Draw(base).rectangle([x + bw, y + bw, x + w - bw - 1, y + h - bw - 1], fill=T.get("mat", (12, 10, 8)))
    iw, ih = w - 2 * (bw + mat), h - 2 * (bw + mat)
    base.paste(crop_to(photo, iw, ih, focus), (x + bw + mat, y + bw + mat))
    ImageDraw.Draw(base).rectangle([x + bw + mat - 1, y + bw + mat - 1, x + bw + mat + iw, y + bw + mat + ih],
                                   outline=T.get("inner", (200, 154, 66)), width=1)


def parse_photo(s):
    if "@" in s:
        p, f = s.rsplit("@", 1)
        return p, tuple(float(v) for v in f.split(","))  # fx,fy[,zoom]
    return s, (0.5, 0.5)


def build(layout, W, H, photos):
    sx, sy = int(W * 0.1), int(H * 0.1)  # безопасная зона 80%
    imgs = [(Image.open(p).convert("RGB"), f) for p, f in photos]
    texts = {"l1": "WE BUY", "l2": "JEWELRY", "l3": "FREE EVALUATION \u2022 NO FEES",
             "l4": "Deals up to 10 min \u2022 Beverly Hills"}
    if layout in ("cover_a", "cover_b"):
        text_right = layout == "cover_b"
        s = H / 1200
        if layout == "cover_a":
            base = background(W, H, (int(W * 0.72), int(H * 0.5)))
            tx, tw_max = sx, int(W * 0.37)
            panels = [(imgs[0], int(W * .512), int(H * .10), int(W * .21), int(H * .68)),
                      (imgs[1], int(W * .70), int(H * .245), int(W * .2), int(H * .655))]
            panels[0] = (imgs[0], 840, 130, 360, 800)
            panels[1] = (imgs[1], 1170, 290, 342, 780)
        else:
            base = background(W, H, (int(W * 0.3), int(H * 0.5)))
            tx, tw_max = int(W * .60), W - sx - int(W * .60)
            panels = [(imgs[0], sx, 200, 272, 620), (imgs[1], sx + 250, 330, 272, 620),
                      (imgs[2], sx + 500, 200, 272, 620)]
            # третья поверх второй - ступенчатый сдвиг
        order = [1, 2, 0] if len(panels) == 3 else range(len(panels))
        for i in order:
            (img, f), x, y, w, h = panels[i]
            framed_panel(base, img, f, x, y, w, h)
        f2 = fit_font(SERIF, texts["l2"], 0.04, tw_max, int(190 * s))
        f1 = None
        f3 = fit_font(SANSB, texts["l3"], 0.12, tw_max, int(30 * s))
        f4 = fit_font(SANS, texts["l4"], 0.06, tw_max, int(28 * s))
        f1 = ImageFont.truetype(SERIF, int(f2.size * WEBUY_RATIO))
        y = int(H * 0.20)
        _, h1 = draw_tracked(base, (tx, y), texts["l1"], f1, f1.size * 0.03)
        y += int(h1 * 0.92)
        _, hh = draw_tracked(base, (tx, y), texts["l2"], f2, f2.size * 0.04)
        y += int(hh * 1.0)
        rule_with_diamond(base, tx, y, min(tw_max, int(360 * s)))
        y += int(46 * s)
        draw_tracked(base, (tx, y), texts["l3"], f3, f3.size * 0.12, gold=False, color=T.get("l3c", (236, 218, 170)))
        y += int(f3.size * 1.9)
        draw_tracked(base, (tx, y), texts["l4"], f4, f4.size * 0.06, gold=False, color=T.get("l4c", (190, 176, 140)))
        return base
    # square
    base = background(W, H, (W // 2, int(H * .55)))
    cx = W // 2
    tw_max = int(W * .8)
    f2 = fit_font(SERIF, texts["l2"], 0.04, tw_max, 150)
    f1 = ImageFont.truetype(SERIF, int(f2.size * WEBUY_RATIO))
    f3 = fit_font(SANSB, texts["l3"], 0.12, tw_max, 30)
    f4 = fit_font(SANS, texts["l4"], 0.06, tw_max, 28)
    y = sy + 4
    _, h1 = draw_tracked(base, (cx, y), texts["l1"], f1, f1.size * 0.03, anchor_x="center")
    y += int(h1 * 0.86)
    _, hh = draw_tracked(base, (cx, y), texts["l2"], f2, f2.size * 0.04, anchor_x="center")
    y += int(hh * 0.95)
    rule_with_diamond(base, cx, y, 340, align="center")
    ph_y = y + 30
    bottom_y = H - sy - int(f3.size * 1.9 + f4.size * 1.4)
    ph_h = bottom_y - ph_y - 24
    if len(imgs) > 1:  # несколько фото в ряд (для square)
        n, gap = len(imgs), 26
        total = tw_max
        pw = (total - gap * (n - 1)) // n
        x0 = cx - total // 2
        for i, (img, f) in enumerate(imgs):
            framed_panel(base, img, f, x0 + i * (pw + gap), ph_y, pw, ph_h)
    else:
        ph_w = min(int(W * .56), tw_max)
        img, f = imgs[0]
        framed_panel(base, img, f, cx - ph_w // 2, ph_y, ph_w, ph_h)
    yb = bottom_y
    draw_tracked(base, (cx, yb), texts["l3"], f3, f3.size * 0.12, gold=False, color=T.get("l3c", (236, 218, 170)), anchor_x="center")
    yb += int(f3.size * 1.9)
    draw_tracked(base, (cx, yb), texts["l4"], f4, f4.size * 0.06, gold=False, color=T.get("l4c", (190, 176, 140)), anchor_x="center")
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", required=True, choices=["cover_a", "cover_b", "square"])
    ap.add_argument("--size", required=True)
    ap.add_argument("--photo", action="append", required=True, help="путь[@fx,fy]")
    ap.add_argument("--out", required=True)
    ap.add_argument("--theme", default="dark", choices=list(THEMES))
    ap.add_argument("--variant", default="")
    ap.add_argument("--purpose", default="Yelp image")
    ap.add_argument("--client", default="LuxeBrokers")
    ap.add_argument("--origin", default="фото клиента, предоставил пользователь 23.11, права не подтверждены письменно")
    a = ap.parse_args()
    T.clear(); T.update(THEMES[a.theme])
    W, H = (int(v) for v in a.size.lower().split("x"))
    photos = [parse_photo(p) for p in a.photo]
    img = build(a.layout, W, H, photos)
    img.save(a.out, "JPEG", quality=93, subsampling=0)
    meta = {
        "ai_generated": False, "derived_from_real_photo": True,
        "created": datetime.date.today().isoformat(), "client": a.client, "purpose": a.purpose,
        "variant": a.variant, "size": f"{W}x{H}",
        "source_files": [os.path.abspath(p) for p, _ in photos],
        "origin_of_photos": a.origin + "; фон, рамки, текст нарисованы кодом (Pillow)",
        "text_on_banner": ["WE BUY", "JEWELRY", "FREE EVALUATION \u2022 NO FEES",
                           "Deals up to 10 min \u2022 Beverly Hills"],
        "text_facts_source": "как в jewelry_v2: jewelryfastsale.com (free evaluation, no fees, up to 10 minutes), пакет Э-8; не сверено с facts_registry (файла нет)",
        "fonts": "Noto Serif Bold (заголовок), Noto Sans Regular/Bold (строки); SIL OFL 1.1 (C:/Windows/Fonts)",
        "safe_zone": "весь текст внутри центральных 80% по каждой оси (поля 10%)",
        "ai_label_needed": False, "generator": "Скрипты/yelp_gold_cover.py (Pillow, не ИИ)",
    }
    with open(a.out + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    print("saved", a.out, img.size)


if __name__ == "__main__":
    main()
