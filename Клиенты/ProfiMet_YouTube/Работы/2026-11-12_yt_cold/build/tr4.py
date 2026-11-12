import json
from faster_whisper import WhisperModel
SRC=r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\Відео_\4.mp4"
m=WhisperModel("medium",device="cpu",compute_type="int8")
segs,_=m.transcribe(SRC,language="pl",word_timestamps=True,beam_size=5,clip_timestamps=[30,48,194,207.4])
out=[]
for s in segs:
    out.append({"s":s.start,"e":s.end,"words":[{"w":w.word,"s":w.start,"e":w.end} for w in s.words]})
    print(" ".join(f"{w.word.strip()}[{w.start:.2f}-{w.end:.2f}]" for w in s.words),flush=True)
json.dump(out,open("words4.json","w",encoding="utf-8"),ensure_ascii=False)
