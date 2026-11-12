from faster_whisper import WhisperModel
SRC=r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\Відео_\1.mp4"
P="Mamy różne konstrukcje. Mamy też stalową konstrukcję metalową. Mamy poliwęglan do wyboru."
for name in ("small","medium"):
    m=WhisperModel(name,device="cpu",compute_type="int8")
    for prompt in (None,P):
        segs,_=m.transcribe(SRC,language="pl",clip_timestamps=[187.8,197.4],initial_prompt=prompt,beam_size=5,word_timestamps=True)
        print(name,"prompt" if prompt else "plain",[(round(s.start,1),s.text) for s in segs],flush=True)
        if prompt is None:
            pass
