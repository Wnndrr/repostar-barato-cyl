import json,sys,subprocess,os
from playwright.sync_api import sync_playwright
html=open('./video.html').read().replace('__DATOS__',open('./datos.json').read())
open('./v.html','w').write(html)
mode=sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1080,"height":1920}); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto("file://./v.html"); pg.wait_for_timeout(500)
    if mode=="frames":
        for t in map(float,sys.argv[2:]):
            pg.evaluate(f"render({t})"); pg.screenshot(path=f"./f_{t}.jpg",type="jpeg",quality=80)
    else:
        SC=pg.evaluate("SC"); os.makedirs("./parts",exist_ok=True); lst=[]
        for i,(sid,a,bb) in enumerate(SC):
            n0,n1=round(a*30),round(bb*30); tmp=f"./parts/tmp_{i}.mp4"; out=f"./parts/p{i}.mp4"
            ff=subprocess.Popen(["ffmpeg","-y","-loglevel","error","-f","image2pipe","-framerate","30","-c:v","mjpeg","-i","-","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-r","30",tmp],stdin=subprocess.PIPE)
            for f in range(n0,n1):
                pg.evaluate(f"render({f/30})"); ff.stdin.write(pg.screenshot(type="jpeg",quality=92))
            ff.stdin.close()
            if ff.wait()==0: os.replace(tmp,out); lst.append(out); print("escena",i+1,"ok",n1-n0,"fotogramas",flush=True)
            else: sys.exit("fallo ffmpeg escena %d"%i)
        open("./parts/lista.txt","w").write("".join(f"file '{x}'\n" for x in lst))
    print("errores:",errs)
    b.close()
