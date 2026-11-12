import subprocess, os
FF = "ffmpeg"
SRC = r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\Відео_\1.mp4"
OUTDIR = r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\готовое"
BUILD = os.path.dirname(os.path.abspath(__file__))
LOGO_H = r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\Картинки\logo_horizontal_transparent.png"
os.chdir(BUILD)
FONT = "C\:/Windows/Fonts/arialbd.ttf"
CARD = 6.0

# (начало, конец, x-центр ведущей в 9:16: список (до_времени_внутри_куска, x_кропа))
import sys
VAR = sys.argv[1] if len(sys.argv) > 1 else "short"   # short: до 205.92 (укладывается в 35 с); full: призыв до 213.30
SUF = "" if VAR == "short" else "full"
END = 205.92 if VAR == "short" else 213.30
SEGS = [(0.00, 3.30), (181.68, 184.62), (185.41, 187.78), (188.32, 196.98), (197.54, END)]
FADEIN = {2: 0.03, 4: 0.03}   # срезы по границам слов (см. 60_ролик.md): короткий фейд, чтобы не съесть начало слова
CROPX = {0: [(99, 1390)], 1: [(99, 1900)], 2: [(99, 1900)], 3: [(99, 1900)], 4: [(205.92 - 197.54, 1889), (99, 1275)]}
# субтитры: (абс. начало, абс. конец, текст) - слова по faster-whisper medium; ASR-описки исправлены (ProfiMet, dopasujemy)
CAPS = [
 (0.00, 1.45, "Planujesz zakup szklarni,"),
 (1.50, 3.30, "ale nie wiesz, czym się różnią modele?"),
 (181.74, 184.60, "Dlaczego warto wybrać szklarnię firmy ProfiMet?"),
 (185.44, 187.70, "Ze względu na to, że jesteśmy polskim producentem."),
 (188.48, 190.40, "Mamy różne konstrukcje."),
 (190.56, 192.90, "Mamy wiele różnych wymiarów tych szklarni."),
 (193.10, 195.40, "Mamy też stalową konstrukcję metalową."),
 (195.48, 196.95, "Mamy poliwęglan do wyboru."),
 (197.64, 200.02, "Jeśli chcesz uzyskać więcej informacji"),
 (200.04, 203.10, "albo się rozejrzeć w ofertach, które są dostępne,"),
 (203.20, 205.90, "wejdź na naszą stronę www.mocnaszklarnia.pl"),
 (205.92, 208.30, "Jeżeli nie wiesz, jaki model będzie najlepszy,"),
 (208.38, 210.80, "skontaktuj się z nami, a pomożemy w wyborze"),
 (210.82, 213.30, "i dopasujemy szklarnię do twoich potrzeb."),
]
CAPS = [c for c in CAPS if c[0] < END]

def run(args):
    r = subprocess.run([FF, "-v", "error", "-y"] + args, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("FFMPEG ERR", r.stderr[-1500:]); raise SystemExit(1)

def crop_expr(i):
    steps = CROPX[i]
    e = str(steps[-1][1])
    for t, x in reversed(steps[:-1]):
        e = f"if(lt(t,{t:.2f}),{x},{e})"
    return f"crop=1215:2160:'{e}':0,scale=1080:1920:flags=lanczos"

def build(kind):
    parts = []
    for i, (s, e) in enumerate(SEGS):
        D = e - s
        vf = "setpts=PTS-STARTPTS," + ("scale=1920:1080:flags=lanczos" if kind == "169" else crop_expr(i))
        af = f"afade=t=in:d={FADEIN.get(i, 0.05)},afade=t=out:st={D-0.08:.2f}:d=0.08"
        out = f"seg2{VAR}_{kind}_{i}.mp4"
        run(["-ss", f"{s}", "-i", SRC, "-t", f"{D:.3f}", "-vf", vf, "-af", af, "-r", "25",
             "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out])
        parts.append(out)
    run(["-loop", "1", "-framerate", "25", "-t", str(CARD), "-i", f"card2_{kind}.png", "-f", "lavfi", "-t", str(CARD), "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", "fade=t=in:st=0:d=0.3,format=yuv420p", "-r", "25", "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", f"seg2{VAR}_{kind}_card.mp4"])
    parts.append(f"seg2{VAR}_{kind}_card.mp4")
    with open(f"list2{VAR}_{kind}.txt", "w", encoding="utf-8") as f:
        for p in parts: f.write(f"file '{p}'\n")
    run(["-f", "concat", "-safe", "0", "-i", f"list2{VAR}_{kind}.txt", "-c", "copy", f"clean2{VAR}_{kind}.mp4"])

def to_out(t):
    off = 0.0
    for (s, e) in SEGS:
        if s - 0.1 <= t <= e + 0.1:
            return off + min(max(t, s), e) - s
        off += e - s
    raise ValueError(t)

def wrap(txt, width):
    if len(txt) <= width: return txt
    words = txt.split(); best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        sc = abs(len(a) - len(b))
        if best is None or sc < best[0]: best = (sc, a + "\n" + b)
    return best[1]

def final(kind):
    total = sum(e - s for s, e in SEGS)
    flt = []
    if kind == "169":
        size, y, width, box = 54, "h-230", 44, 14
    else:
        size, y, width, box = 64, "1130", 22, 16
    for i, (a, b, txt) in enumerate(CAPS):
        a, b = to_out(a), to_out(b)
        fn = f"cap2{VAR}_{kind}_{i}.txt"
        open(fn, "w", encoding="utf-8", newline="").write(wrap(txt, width))
        flt.append(f"drawtext=fontfile='{FONT}':textfile={fn}:fontsize={size}:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw={box}:line_spacing=10:x=(w-text_w)/2:y={y}:enable='between(t,{a:.2f},{b:.2f})'")
    if kind == "916":
        open("url.txt", "w", encoding="utf-8", newline="").write("mocnaszklarnia.pl")
        t0 = to_out(203.20)
        flt.append(f"drawtext=fontfile='{FONT}':textfile=url.txt:fontsize=70:fontcolor=white:box=1:boxcolor=0x1B7A3E@0.9:boxborderw=20:x=(w-text_w)/2:y=1400:enable='between(t,{t0:.2f},{total:.2f})'")
    name = {"169": f"ProfiMet_YT_cold_v2{SUF}_16x9.mp4", "916": f"ProfiMet_YT_cold_v2{SUF}_9x16.mp4"}[kind]
    lw, lx, ly = (300, 1920 - 300 - 40, 40) if kind == "169" else (320, 380, 110)
    lg_end = to_out(3.30)
    fc = "[0:v]" + ",".join(flt) + "[v0];[1:v]scale=" + str(lw) + ":-1:flags=lanczos[lg];[v0][lg]overlay=" + str(lx) + ":" + str(ly) + f":enable='between(t,0,{lg_end:.2f})'[v]"
    run(["-i", f"clean2{VAR}_{kind}.mp4", "-i", LOGO_H, "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "17", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", os.path.join(OUTDIR, name)])
    return name

if __name__ == "__main__":
    for k in ("169", "916"):
        build(k); print(final(k))
