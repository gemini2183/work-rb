from faster_whisper import WhisperModel
SRC=r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\Відео_\1.mp4"
P="ProfiMet to polski producent szklarni ogrodowych z poliwęglanu. Dlaczego warto wybrać szklarnię firmy ProfiMet? Po pierwsze, jesteśmy polskim producentem. Skontaktuj się z nami, dopasujemy szklarnię do Twoich potrzeb. mocnaszklarnia.pl"
for name in ("small","medium"):
    m=WhisperModel(name,device="cpu",compute_type="int8")
    for (a,b) in [(0,4),(180,189),(196,214)]:
        for prompt in (None,P):
            segs,_=m.transcribe(SRC,language="pl",clip_timestamps=[a,b],initial_prompt=prompt,beam_size=5)
            print(name,a,b,"prompt" if prompt else "plain",[ (round(s.start,1),s.text) for s in segs],flush=True)
