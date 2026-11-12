import json, sys
from faster_whisper import WhisperModel
SRC=r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\Відео_\1.mp4"
try:
    raise Exception("skip gpu")
except Exception as e:
    print("cuda fail",e); m=WhisperModel("medium",device="cpu",compute_type="int8"); dev="cpu"
print(dev)
segs,info=m.transcribe(SRC,language="pl",word_timestamps=True,vad_filter=False,beam_size=5)
out=[]
for s in segs:
    out.append({"s":s.start,"e":s.end,"t":s.text,"words":[{"w":w.word,"s":w.start,"e":w.end} for w in s.words]})
    print(f"{s.start:7.2f}-{s.end:7.2f} {s.text}",flush=True)
json.dump(out,open("words.json","w",encoding="utf-8"),ensure_ascii=False)
