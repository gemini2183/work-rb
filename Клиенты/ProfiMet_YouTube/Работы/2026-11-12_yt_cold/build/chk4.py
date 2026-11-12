from faster_whisper import WhisperModel
SRC=r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\Відео_\4.mp4"
P1="W szklarniach ProfiMet stosowane są ocynkowane profile stalowe. Ocynkowanie pomaga zabezpieczyć stal przed korozją i utratą wilgoci."
P2="Jeśli masz jakiekolwiek wątpliwości, zapraszamy do kontaktu. Pomożemy, dobierzemy i rozwiejemy wszystkie wątpliwości."
for name in ("small","medium"):
    m=WhisperModel(name,device="cpu",compute_type="int8")
    for (a,b,P) in [(34.3,44.1,P1),(198.6,206.2,P2)]:
        for prompt in (None,P):
            segs,_=m.transcribe(SRC,language="pl",clip_timestamps=[a,b],initial_prompt=prompt,beam_size=5)
            print(name,a,"prompt" if prompt else "plain",[s.text for s in segs],flush=True)
