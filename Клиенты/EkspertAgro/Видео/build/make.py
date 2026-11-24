# Сборка ролика B v3 (EkspertAgro) из фото. Запуск: python -I make.py [169|916|all]
# v3.1 (23.11): плавный зум (zoompan по увеличенному в 4 раза кадру, слой не двигается), логотип в углу всю дорогу,
# длинный финал (цена, кнопка, условия, подарок), музыка из Видео/музыка/ (если файл лежит) с затуханием.
import subprocess, os, sys, glob, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
HERE = os.path.dirname(os.path.abspath(__file__)); VID = os.path.dirname(HERE)
PH = os.path.join(VID, "Фото_с_сайта"); LOGO = os.path.join(VID, "logo_ekspertagro_500.png")
OUT = os.path.join(VID, "готовое"); TMP = os.path.join(HERE, "tmp"); MUS = os.path.join(VID, "музыка")
os.makedirs(TMP, exist_ok=True); os.makedirs(OUT, exist_ok=True)
FB = r"C:\Windows\Fonts\arialbd.ttf"
DARK, GREEN, GOLD = (20, 28, 24), (25, 130, 62), (245, 176, 35)
T = 0.4  # длительность растворения
# Темы оформления плашек (python make.py 916 --theme green|dark). По умолчанию "classic" = как в v3.
THEMES = {
    "classic": {},
    "green": {"std": (GREEN + (238,), (255, 255, 255)), "head": (GOLD + (245,), DARK),
              "gift": ((255, 255, 255, 240), (18, 105, 50))},
    "allgreen": {"std": (GREEN + (245,), (255, 255, 255)), "head": (GREEN + (245,), (255, 255, 255)),
                 "gift": (GREEN + (245,), (255, 255, 255)), "c_price": (GREEN + (255,), (255, 255, 255))},
    "dark": {"std": ((14, 20, 17, 225), (255, 255, 255)), "head": ((14, 20, 17, 235), GOLD),
             "gift": ((14, 20, 17, 225), (255, 255, 255))},
}
THEME = "classic"
SCENES = [("02_NORDIS", 2.5), ("64_Tytan", 2.5), ("29_Tunel4020", 2.5), ("39_Tunel4020_detal", 2.5),
          ("85_Szeroka", 2), ("91_Szeroka", 2), ("38_Tunel4020_wnetrze", 3), ("94_Szeroka_wnetrze", 3),
          ("09_NORDIS", 6), ("21_DomekMaly", 2), ("14_GRANIT", 2), ("91_Szeroka", 2.5), ("CARD", 6)]
CS = sum(s for _, s in SCENES[:-1])  # начало финальной карточки (32.5 с)
SMALL = {"64_Tytan"}  # 1024x768: зум минимальный
ZOOM = 0.06
CAPS = [("", 0.2, CS - 0.1, "corner"),
        ("Szklarnie z poliwęglanu z dostawą w całej Polsce", 0.3, 2.9, "std"),
        ("Producent od 2008 roku", 3.0, 4.9, "std"),
        ("Ocynkowany profil 40×20 mm. Poliwęglan 6 mm z ochroną UV", 5.2, 9.8, "std"),
        ("Żywotność ponad 15 lat", 10.2, 13.8, "std"),
        ("Własne warzywa od wiosny do jesieni", 14.2, 16.8, "std"),
        ("Wcześniejszy siew, dłuższy sezon, ochrona przed wiatrem i deszczem", 17.0, 19.8, "std"),
        ("Tylko dziś – prezenty o wartości 249 zł!", 20.2, 25.8, "head"),
        ("Okno boczne", 21.4, 25.8, "gift0"), ("Taśma paroprzepuszczalna", 22.3, 25.8, "gift1"),
        ("Dysza do wkrętarki", 23.2, 25.8, "gift2"), ("Profil końcowy U", 24.1, 25.8, "gift3"),
        ("Płatność przy odbiorze. Bezpłatna dostawa w 3–7 dni", 26.3, 29.8, "std"),
        ("Szklarnia na 15+ lat. Prosto od producenta", CS + 0.5, 99, "c_price"),
        ("Zamów na ekspertagro.pl  ›", CS + 1.3, 99, "c_btn"),
        ("Płatność przy odbiorze · Bezpłatna dostawa w 3–7 dni", CS + 2.4, 99, "c_note"),
        ("4 prezenty gratis", CS + 3.2, 99, "c_note2")]


# Короткая версия 18 с (23.11, по «да» пользователя): python -I make.py all --set short
SUFFIX = ""
SHORT_SCENES = [("02_NORDIS", 2), ("64_Tytan", 2), ("29_Tunel4020", 2), ("39_Tunel4020_detal", 2),
                ("09_NORDIS", 5), ("CARD", 6)]
_CS2 = sum(s for _, s in SHORT_SCENES[:-1])  # 12 с
SHORT_CAPS = [("", 0.2, _CS2 - 0.1, "corner"),
              ("Szklarnie z poliwęglanu z dostawą w całej Polsce", 0.3, 3.7, "std"),
              ("Ocynkowany profil 40×20 mm. Poliwęglan 6 mm z ochroną UV", 4.2, 7.8, "std"),
              ("4 prezenty gratis: okno boczne, taśma, dysza, profil U", 8.3, 12.8, "std"),
              ("Szklarnia na 15+ lat. Prosto od producenta", _CS2 + 0.5, 99, "c_price"),
              ("Zamów na ekspertagro.pl  ›", _CS2 + 1.3, 99, "c_btn"),
              ("Płatność przy odbiorze · Bezpłatna dostawa w 3–7 dni", _CS2 + 2.4, 99, "c_note")]


def font(s):
    return ImageFont.truetype(FB, s)


def wrap(d, txt, f, maxw):
    lines, cur = [], ""
    for w in txt.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    return lines


def cap_png(txt, style, W, H, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    v = H > W
    if style == "corner":  # логотип в правом верхнем углу на белой плашке
        bs = 210 if v else 190; ls = bs - 30; m = 40
        d.rounded_rectangle([W - bs - m, m, W - m, m + bs], radius=28, fill=(255, 255, 255, 235))
        lg = Image.open(LOGO).convert("RGBA").resize((ls, ls), Image.LANCZOS)
        im.paste(lg, (W - bs - m + 15, m + 15), lg); im.save(path); return
    TH = THEMES[THEME]
    size = 62 if v else 54
    maxw = int(W * (0.86 if v else 0.92))
    if style.startswith("gift"):
        size = 52 if v else 46
    if style == "c_price":
        size = 60 if v else 72
    elif style == "c_btn":
        size = 64 if v else 76
    elif style in ("c_note", "c_note2"):
        size = 48 if v else 44
    f = font(size); lines = wrap(d, txt, f, maxw)
    lh = int(size * 1.25); tw = max(d.textlength(l, font=f) for l in lines)
    pad = int(size * 0.45); bw, bh = tw + 2 * pad, lh * len(lines) + pad * 0.9
    x0 = (W - bw) / 2; fill = None; tc = (255, 255, 255)
    if style == "std":
        y = int(H * (0.72 if v else 0.80)); fill = (0, 0, 0, 170)
        if "std" in TH: fill, tc = TH["std"]
    elif style == "head":
        y = int(H * (0.17 if v else 0.12)); fill = GOLD + (245,); tc = DARK
        if "head" in TH: fill, tc = TH["head"]
    elif style == "c_price":
        y = int(H * (0.44 if v else 0.47)); fill = None; tc = DARK
    elif style == "c_btn":
        y = int(H * (0.545 if v else 0.645)); fill = GREEN + (255,)
    elif style == "c_note":
        y = int(H * (0.665 if v else 0.82)); tc = DARK
    elif style == "c_note2":
        y = int(H * (0.76 if v else 0.90)); tc = GREEN
    else:
        k = int(style[-1]); gap = int(bh * 1.3)
        y = int(H * (0.745 if v else 0.30)) + k * gap; fill = GREEN + (240,)
        if "gift" in TH: fill, tc = TH["gift"]
        if not v:
            x0 = W * 0.05
    if fill:
        d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=int(size * 0.35), fill=fill)
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text((x0 + (bw - w) / 2, y + pad * 0.4 + i * lh), l, font=f, fill=tc)
    im.save(path)


def bg_and_fg(name, W, H):
    if name == "CARD":
        bg = Image.new("RGB", (W, H), (255, 255, 255)); lw = 380
        lg = Image.open(LOGO).convert("RGBA").resize((lw, lw), Image.LANCZOS)
        bg.paste(lg, ((W - lw) // 2, int(H * (0.14 if H > W else 0.05))), lg)
        p = os.path.join(TMP, f"bg_CARD_{W}.png"); bg.save(p)
        return p, None
    im = Image.open(os.path.join(PH, name + ".jpg")).convert("RGB")
    s = max(W / im.width, H / im.height)
    b = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (b.width - W) // 2, (b.height - H) // 2
    b = b.crop((l, t, l + W, t + H))
    b = ImageEnhance.Brightness(b.filter(ImageFilter.GaussianBlur(35))).enhance(0.75)
    p = os.path.join(TMP, f"bg_{name}_{W}.png"); b.save(p)
    if W > H:
        fw, fh = round(im.width * H / im.height), H
    else:
        fw, fh = W, round(im.height * W / im.width)
    fw -= fw % 2; fh -= fh % 2
    fp = os.path.join(TMP, f"fg4_{name}_{W}.png")  # в 4 раза больше: зум идёт по долям пикселя, без дрожи
    im.resize((fw * 4, fh * 4), Image.LANCZOS).save(fp)
    return p, (fp, fw, fh)


def run(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print("FFMPEG ERR", r.stderr[-2000:]); sys.exit(1)


def build(kind, music_file=None, out_dir=None, reuse_base=False, preset="slow"):
    outd = out_dir or OUT; os.makedirs(outd, exist_ok=True)
    W, H = (1920, 1080) if kind == "169" else (1080, 1920)
    FPS = 25; clips = []
    for i, (name, slot) in enumerate(SCENES if not reuse_base else []):
        L = slot + (T if i < len(SCENES) - 1 else 0)
        bgp, fg = bg_and_fg(name, W, H); out = os.path.join(TMP, f"c_{kind}_{i}.mp4")
        if fg is None:
            run(["-loop", "1", "-framerate", str(FPS), "-t", f"{L}", "-i", bgp, "-vf", "format=yuv420p",
                 "-c:v", "libx264", "-crf", "16", "-r", str(FPS), out])
        else:
            fp, fw, fh = fg; z = 0.025 if name in SMALL else ZOOM
            N = math.ceil(L * FPS) + 2
            vy = "(H-h)/2" if W > H else "(H-h)/2-H*0.06"
            fc = (f"[1:v]zoompan=z='1+{z}*on/{N}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={N}:s={fw}x{fh}:fps={FPS}[f];"
                  f"[0:v][f]overlay=x='(W-w)/2':y='{vy}':shortest=1,format=yuv420p[v]")
            run(["-loop", "1", "-framerate", str(FPS), "-t", f"{L}", "-i", bgp, "-i", fp,
                 "-filter_complex", fc, "-map", "[v]", "-t", f"{L}", "-c:v", "libx264", "-crf", "16", "-r", str(FPS), out])
        clips.append(out)
    inp = []
    for c in (clips if not reuse_base else []):
        inp += ["-i", c]
    chain, last, S = [], "[0:v]", 0.0
    for i in range(1, len(clips) if not reuse_base else 1):
        S += SCENES[i - 1][1]; o = f"[x{i}]"
        chain.append(f"{last}[{i}:v]xfade=transition=fade:duration={T}:offset={S:.2f}{o}"); last = o
    base = os.path.join(TMP, f"base_{kind}.mp4")
    if not reuse_base:
        run(inp + ["-filter_complex", ";".join(chain), "-map", last, "-c:v", "libx264", "-crf", "16",
                   "-r", str(FPS), "-pix_fmt", "yuv420p", base])
    total = sum(s for _, s in SCENES)
    ins = ["-i", base]; fc = []; cur = "[0:v]"
    for i, (txt, a, b, st) in enumerate(CAPS):
        p = os.path.join(TMP, f"cap_{kind}_{i}.png"); cap_png(txt, st, W, H, p)
        ins += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total}", "-i", p]
        fc.append(f"[{i+1}:v]format=rgba,fade=t=in:st={a}:d=0.25:alpha=1,fade=t=out:st={b-0.25:.2f}:d=0.25:alpha=1[o{i}]")
        fc.append(f"{cur}[o{i}]overlay=0:0:format=auto[m{i}]"); cur = f"[m{i}]"
    music = [music_file] if music_file else sorted(glob.glob(os.path.join(MUS, "*.mp3")) + glob.glob(os.path.join(MUS, "*.wav")) + glob.glob(os.path.join(MUS, "*.m4a")))
    if music and music_file:  # явный файл: выравниваем громкость до -16 LUFS и плавные края
        ins += ["-stream_loop", "-1", "-i", music[0]]
        af = ["-af", f"atrim=0:{total},loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=1.5,afade=t=out:st={total-2.5:.1f}:d=2.5"]
    elif music:
        ins += ["-stream_loop", "-1", "-i", music[0]]
        af = ["-af", f"afade=t=in:st=0:d=1.5,afade=t=out:st={total-2.5:.1f}:d=2.5,volume=0.5"]
    else:
        ins += ["-f", "lavfi", "-t", f"{total}", "-i", "anullsrc=r=48000:cl=stereo"]; af = []
    name = f"EkspertAgro_YT_B_v3_{'16x9' if kind == '169' else '9x16'}_green_bez_ceny{SUFFIX}.mp4"
    run(ins + ["-filter_complex", ";".join(fc) + f";{cur}format=yuv420p[v]", "-map", "[v]", "-map", f"{len(CAPS)+1}:a"] + af +
        ["-c:v", "libx264", "-crf", "17", "-preset", preset, "-c:a", "aac", "-b:a", "128k",
         "-t", f"{total}", "-movflags", "+faststart", os.path.join(outd, name)])
    print(name, "музыка:" , music[0] if music else "нет")


if __name__ == "__main__":
    # python -I make.py [169|916|all] [--theme classic|green|dark] [--music файл] [--out папка] [--reuse-base] [--preset fast]
    av = sys.argv[1:]
    def opt(n, d=None):
        return av[av.index(n) + 1] if n in av else d
    a = av[0] if av and not av[0].startswith("--") else "all"
    THEME = opt("--theme", "classic")
    if opt("--set") == "short":
        SCENES, CAPS, SUFFIX = SHORT_SCENES, SHORT_CAPS, "_15s"
    for k in (["169", "916"] if a == "all" else [a]):
        build(k, opt("--music"), opt("--out"), "--reuse-base" in av, opt("--preset", "slow"))
