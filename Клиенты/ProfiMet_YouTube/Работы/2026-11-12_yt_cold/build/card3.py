from PIL import Image, ImageDraw, ImageFont
import math
LOGO = r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\Картинки\logo_horizontal_transparent.png"
FB = r"C:\Windows\Fonts\arialbd.ttf"; FR = r"C:\Windows\Fonts\arial.ttf"
DARK, GREEN, GRAY, GOLD = (23, 23, 36), (19, 125, 60), (85, 93, 109), (245, 166, 35)

def star(d, cx, cy, R, fill):
    pts = []
    for i in range(10):
        r = R if i % 2 == 0 else R * 0.40
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=fill)

def make(W, H, name, vertical):  # v3: без гарантии и оцинковки
    im = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(im)
    lg = Image.open(LOGO).convert("RGBA")
    def f(p, s): return ImageFont.truetype(p, s)
    def center(txt, font, y, fill):
        w = d.textlength(txt, font=font); d.text(((W - w) / 2, y), txt, font=font, fill=fill)
    def line(y):
        d.line([(W * 0.22, y), (W * 0.78, y)], fill=(215, 218, 224), width=3)
    if not vertical:
        lw = 480; lh = round(lg.height * lw / lg.width); lg = lg.resize((lw, lh), Image.LANCZOS)
        im.paste(lg, ((W - lw) // 2, 55), lg)
        # строка оценки: 4,9 + звёзды + Ponad 80 recenzji
        fbig, fsm = f(FB, 118), f(FB, 46)
        t1 = "4,9"; t2 = "Ponad 80 recenzji"
        w1, w2 = d.textlength(t1, font=fbig), d.textlength(t2, font=fsm)
        R = 28; gap = R * 2.4; ws = gap * 4 + 2 * R
        total = w1 + 40 + ws + 40 + w2; x = (W - total) / 2; yc = 265
        d.text((x, yc - 70), t1, font=fbig, fill=DARK); x += w1 + 40
        for i in range(5): star(d, x + R + i * gap, yc + 8, R, GOLD)
        x += ws + 40; d.text((x, yc - 10), t2, font=fsm, fill=DARK)
        center("Średnia ocena", f(FR, 36), 190, GRAY)
        line(385)
        center("Płatność przy odbiorze, bez przedpłaty", f(FB, 62), 440, DARK)
        center("Producent szklarni od 16 lat", f(FB, 54), 560, GRAY)
        line(670)
        url_size, y_url = 70, 750
    else:
        lw = 700; lh = round(lg.height * lw / lg.width); lg = lg.resize((lw, lh), Image.LANCZOS)
        im.paste(lg, ((W - lw) // 2, 200), lg)
        center("Średnia ocena", f(FR, 46), 470, GRAY)
        center("4,9", f(FB, 210), 510, DARK)
        R = 36; gap = R * 2.4; x0 = W / 2 - 2 * gap
        for i in range(5): star(d, x0 + i * gap, 820, R, GOLD)
        center("Ponad 80 recenzji", f(FB, 68), 880, DARK)
        line(1010)
        fb = f(FB, 60)
        center("Płatność przy odbiorze,", fb, 1070, DARK); center("bez przedpłaty", fb, 1150, DARK)
        center("Producent szklarni od 16 lat", f(FB, 54), 1300, GRAY)
        url_size, y_url = 76, 1450
    fu = f(FB, url_size); tw = d.textlength("mocnaszklarnia.pl", font=fu); pad = round(url_size * 0.45)
    xb = (W - tw) / 2 - pad
    d.rounded_rectangle([xb, y_url, xb + tw + 2 * pad, y_url + url_size + 2 * pad], radius=round(url_size * 0.3), fill=GREEN)
    d.text((xb + pad, y_url + pad - url_size * 0.08), "mocnaszklarnia.pl", font=fu, fill=(255, 255, 255))
    im.save(name)
make(1920, 1080, "card3_169.png", False); make(1080, 1920, "card3_916.png", True); print("ok")
