import subprocess
from PIL import Image
D="D:/GitHub/work-rb/Клиенты/ProfiMet_YouTube/видео_drive/готовое/"
ts=[1,4.5,7.5,8.7,9.5,11,13,16,17.8,18.4,19.5,21,23,25,27]
for kind,w,h,cols,name in (("16x9",480,270,3,"c3_169.jpg"),("9x16",216,384,8,"c3_916.jpg")):
    ims=[]
    for t in ts:
        subprocess.run(["ffmpeg","-v","error","-y","-ss",str(t),"-i",D+"ProfiMet_YT_cold_v3_"+kind+".mp4","-frames:v","1","-vf","scale=%d:%d"%(w,h),"t.jpg"])
        ims.append(Image.open("t.jpg").copy())
    rows=(len(ims)+cols-1)//cols
    m=Image.new("RGB",(w*cols,h*rows))
    for i,im in enumerate(ims): m.paste(im,((i%cols)*w,(i//cols)*h))
    m.save(name)
