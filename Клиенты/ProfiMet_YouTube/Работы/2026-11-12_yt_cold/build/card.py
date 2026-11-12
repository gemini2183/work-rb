from PIL import Image, ImageDraw, ImageFont
import math
LOGO = r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\Картинки\logo_horizontal_transparent.png"
FONT = r"C:\Windows\Fonts\arialbd.ttf"
FONT_R = r"C:\Windows\Fonts\arial.ttf"
DARK, GREEN, GRAY, GOLD = (23, 23, 36), (19, 125, 60), (85, 93, 109), (245, 166, 35)

def star(d, cx, cy, R, fill):
    pts = []
    for i in range(10):
        r = R if i % 2 == 0 else R * 0.40
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=fill)

def card(W, H, name, logo_w, y_logo, size_lab, y_lab, size_big, y_big, star_R, y_star, size_rev, y_rev, size_sub, y_sub, size_url, y_url):
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    lg = Image.open(LOGO).convert("RGBA")
    lh = round(lg.height * logo_w / lg.width)
    lg = lg.resize((logo_w, lh), Image.LANCZOS)
    im.paste(lg, ((W - logo_w) // 2, y_logo), lg)
    def centered(txt, font, y, fill):
        w = d.textlength(txt, font=font)
        d.text(((W - w) / 2, y), txt, font=font, fill=fill)
    centered("Średnia ocena", ImageFont.truetype(FONT_R, size_lab), y_lab, GRAY)
    centered("4,9", ImageFont.truetype(FONT, size_big), y_big, DARK)
    gap = star_R * 2.4
    x0 = W / 2 - 2 * gap
    for i in range(5):
        star(d, x0 + i * gap, y_star, star_R, GOLD)
    centered("Ponad 80 recenzji", ImageFont.truetype(FONT, size_rev), y_rev, DARK)
    centered("Producent szklarni od 16 lat", ImageFont.truetype(FONT_R, size_sub), y_sub, GRAY)
    fu = ImageFont.truetype(FONT, size_url)
    tw = d.textlength("mocnaszklarnia.pl", font=fu)
    pad = round(size_url * 0.45)
    xb = (W - tw) / 2 - pad
    d.rounded_rectangle([xb, y_url, xb + tw + 2 * pad, y_url + size_url + 2 * pad], radius=round(size_url * 0.3), fill=GREEN)
    d.text((xb + pad, y_url + pad - size_url * 0.08), "mocnaszklarnia.pl", font=fu, fill=(255, 255, 255))
    im.save(name)

card(1920, 1080, "card_169.png", 700, 70, 44, 270, 210, 310, 34, 590, 66, 650, 46, 760, 62, 860)
card(1080, 1920, "card_916.png", 760, 330, 54, 650, 250, 700, 40, 1030, 78, 1100, 54, 1240, 72, 1380)
print("ok")
