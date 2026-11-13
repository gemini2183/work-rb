import subprocess, os, re
FF = "ffmpeg"
V = "D:/GitHub/work-rb/Клиенты/ProfiMet_YouTube/видео_drive/"
SRCS = {1: V + "Відео_/1.mp4", 4: V + "Відео_/4.mp4"}
OUTDIR = V + "готовое"
BUILD = os.path.dirname(os.path.abspath(__file__))
LOGO_H = "D:/GitHub/work-rb/Клиенты/ProfiMet_YouTube/Картинки/logo_horizontal_transparent.png"
os.chdir(BUILD)
FONT = "C\\:/Windows/Fonts/arialbd.ttf"
CARD = 5.5
TARGET_LUFS = -17.5

# (ролик, начало, конец, фейд-вход, шаги x-кропа 9:16 [(до t внутри куска, x)] , последний шаг - 'остальное')
def x3(t0):  # 4.mp4 34.42: кадры каркаса без ведущей -> растворение в ведущую в профиль (как в первой нарезке)
    return None
SEGS = [
 (1, 0.00, 3.30, 0.05, [(99, 1390)]),
 (1, 181.68, 184.62, 0.05, [(99, 1900)]),
 (1, 185.41, 187.78, 0.03, [(99, 1900)]),
 (4, 34.42, 43.95, 0.02, [(37.40 - 34.42, 1313), (38.00 - 34.42, "lerp"), (99, 391)]),
 (4, 198.50, 206.02, 0.03, [(99, 545)]),
]
# субтитры: (индекс куска, абс. начало, абс. конец, текст); слова по faster-whisper medium
CAPS = [
 (0, 0.00, 1.45, "Planujesz zakup szklarni,"),
 (0, 1.50, 3.30, "ale nie wiesz, czym się różnią modele?"),
 (1, 181.74, 184.60, "Dlaczego warto wybrać szklarnię firmy ProfiMet?"),
 (2, 185.44, 187.70, "Ze względu na to, że jesteśmy polskim producentem."),
 (3, 34.48, 38.70, "W szklarniach ProfiMet stosowane są ocynkowane profile stalowe."),
 (3, 38.92, 42.40, "Ocynkowanie pomaga zabezpieczyć stal przed korozją,"),
 (3, 42.60, 43.92, "upływem wilgoci."),
 (4, 198.60, 200.60, "Jeśli masz jakiekolwiek wątpliwości,"),
 (4, 200.90, 202.15, "zapraszamy do kontaktu."),
 (4, 202.40, 204.05, "Pomożemy, dobierzemy"),
 (4, 204.10, 205.80, "i rozwiejemy wszystkie wątpliwości."),
]
PLAQUE_169 = "2 lata gwarancji na ramę · 5 lat na poliwęglan"
PLAQUE_916 = "2 lata gwarancji na ramę\n5 lat na poliwęglan"
PL_FROM, PL_TO = 0.5, 205.80 - 198.50   # внутри куска 5: с 0,5 с до конца речи

def run(args, capture=False):
    r = subprocess.run([FF, "-v", "error", "-y"] + args, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("FFMPEG ERR", r.stderr[-1500:]); raise SystemExit(1)

def measure(files):
    n = len(files); args = []
    for f in files: args += ["-i", f]
    fc = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1,ebur128"
    r = subprocess.run([FF, "-hide_banner", "-nostats"] + args + ["-filter_complex", fc, "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1])

def cut_audio_raw():
    files = {1: [], 4: []}
    for i, (src, s, e, fi, _) in enumerate(SEGS):
        out = f"raw3_{i}.wav"
        run(["-ss", f"{s}", "-i", SRCS[src], "-t", f"{e-s:.3f}", "-vn", "-ac", "2", "-ar", "48000", out])
        files[src].append(out)
    return {k: measure(v) for k, v in files.items()}

def crop_expr(i):
    steps = SEGS[i][4]
    parts = []
    # терминальное значение
    last = steps[-1][1]
    e = str(last)
    for k in range(len(steps) - 2, -1, -1):
        t, x = steps[k]
        if x == "lerp":
            t_prev, x_prev = steps[k - 1]
            nxt = steps[k + 1][1]
            e = f"if(lt(t,{t:.2f}),{x_prev}+({nxt}-{x_prev})*(t-{t_prev:.2f})/{t-t_prev:.2f},{e})"
        else:
            e = f"if(lt(t,{t:.2f}),{x},{e})"
    return f"crop=1215:2160:'{e}':0,scale=1080:1920:flags=lanczos"

def build(kind, gains):
    parts = []
    for i in range(len(SEGS)):
        parts.append(f"seg3_{kind}_{i}.mp4")
    run(["-loop", "1", "-framerate", "25", "-t", str(CARD), "-i", f"card4_{kind}.png", "-f", "lavfi", "-t", str(CARD), "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", "fade=t=in:st=0:d=0.3,format=yuv420p", "-r", "25", "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", f"seg4_{kind}_card.mp4"])
    parts.append(f"seg4_{kind}_card.mp4")
    with open(f"list4_{kind}.txt", "w", encoding="utf-8") as f:
        for p in parts: f.write(f"file '{p}'\n")
    run(["-f", "concat", "-safe", "0", "-i", f"list4_{kind}.txt", "-c", "copy", f"clean4_{kind}.mp4"])

def offsets():
    o = []; off = 0.0
    for (_, s, e, _, _) in SEGS:
        o.append(off); off += e - s
    return o, off

def wrap(txt, width):
    if len(txt) <= width: return txt
    words = txt.split(); best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        sc = abs(len(a) - len(b))
        if best is None or sc < best[0]: best = (sc, a + "\n" + b)
    return best[1]

def final(kind):
    offs, total = offsets()
    flt = []
    if kind == "169":
        size, y, width, box = 54, "h-230", 44, 14
    else:
        size, y, width, box = 64, "1130", 22, 16
    for i, (si, a, b, txt) in enumerate(CAPS):
        s0 = SEGS[si][1]
        a, b = offs[si] + a - s0, offs[si] + b - s0
        fn = f"cap3_{kind}_{i}.txt"
        open(fn, "w", encoding="utf-8", newline="").write(wrap(txt, width))
        flt.append(f"drawtext=fontfile='{FONT}':textfile={fn}:fontsize={size}:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw={box}:line_spacing=10:x=(w-text_w)/2:y={y}:enable='between(t,{a:.2f},{b:.2f})'")
    # плашка гарантий поверх речи куска 5
    pa, pb = offs[4] + PL_FROM, offs[4] + PL_TO
    fn = f"plaque3_{kind}.txt"
    open(fn, "w", encoding="utf-8", newline="").write(PLAQUE_169 if kind == "169" else PLAQUE_916)
    if kind == "169":
        flt.append(f"drawtext=fontfile='{FONT}':textfile={fn}:fontsize=50:fontcolor=white:box=1:boxcolor=0x1B7A3E@0.93:boxborderw=20:x=w-text_w-60:y=60:enable='between(t,{pa:.2f},{pb:.2f})'")
    else:
        flt.append(f"drawtext=fontfile='{FONT}':textfile={fn}:fontsize=60:fontcolor=white:box=1:boxcolor=0x1B7A3E@0.93:boxborderw=20:line_spacing=12:x=(w-text_w)/2:y=830:enable='between(t,{pa:.2f},{pb:.2f})'")
    name = "ProfiMet_YT_cold_v4_" + {"169": "16x9", "916": "9x16"}[kind] + ".mp4"
    lw, lx, ly = (300, 1920 - 300 - 40, 40) if kind == "169" else (320, 380, 110)
    fc = "[0:v]" + ",".join(flt) + "[v0];[1:v]scale=" + str(lw) + ":-1:flags=lanczos[lg];[v0][lg]overlay=" + str(lx) + ":" + str(ly) + ":enable='between(t,0,3.30)'[v]"
    run(["-i", f"clean4_{kind}.mp4", "-i", LOGO_H, "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "17", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", os.path.join(OUTDIR, name)])
    return name

if __name__ == "__main__":
    for k in ("169", "916"):
        build(k, None); print(final(k))
