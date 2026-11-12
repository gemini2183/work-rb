import subprocess
from PIL import Image
D=r"D:\GitHub\work-rb\Клиенты\ProfiMet_YouTube\видео_drive\готовое"
ts=[1,2.5,4.5,7,9,12,15,18,22,25,27,30]
for kind,w,h,cols,name in (("16x9",640,360,3,"c2_169.jpg"),("9x16",270,480,6,"c2_916.jpg")):
    ims=[]
    for t in ts:
        subprocess.run(["ffmpeg","-v","error","-y","-ss",str(t),"-i",D+"\ProfiMet_YT_cold_v2_"+kind+".mp4","-frames:v","1","-vf","scale=%d:%d"%(w,h),"t.jpg"])
        ims.append(Image.open("t.jpg").copy())
    rows=(len(ims)+cols-1)//cols
    m=Image.new("RGB",(w*cols,h*rows))
    for i,im in enumerate(ims): m.paste(im,((i%cols)*w,(i//cols)*h))
    m.save(name)
