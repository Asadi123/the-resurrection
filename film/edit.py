#!/usr/bin/env python3
"""New multi-track archival film: full original media, varied editorial layouts and mapped evidence.

No source image is ever cropped, geometrically stretched, or overlaid by a fake source.
Each named archival asset and PDF page stays visible in full. Modern explanatory
artwork is original procedural graphics, not supposed historical photography.
"""
from __future__ import annotations
import hashlib, json, math, os, subprocess, sys
from pathlib import Path
import fitz
import numpy as np
import soundfile as sf
from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"render"
OUT.mkdir(exist_ok=True)
W,H,FPS=1920,1080,30
INK=(13,18,22); WHITE=(237,233,222); MUTED=(168,170,170); RED=(157,43,49)
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DATA=json.loads((ROOT/"production.json").read_text())
AUDIT=json.loads((ROOT/"audit.json").read_text())
CLOCK=json.loads((ROOT/"audio/timings.json").read_text())
ASSET={x["id"]:x for x in AUDIT["sources"]}

def run(argv):
    p=subprocess.run([str(a) for a in argv],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if p.returncode:
        raise RuntimeError((" ".join(str(a) for a in argv[:8]))+"\n"+p.stderr[-2400:])
    return p.stdout

def ffprobe(path):
    return json.loads(run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",path]))

def length(path):
    return float(ffprobe(path)["format"]["duration"])

def font(sz,b=False):
    return ImageFont.truetype(BOLD if b else FONT,sz)

def label(draw,xy,text,sz=28,fill=WHITE,bold=False,width=650):
    words=text.split()
    rows=[]; s=""
    f=font(sz,bold)
    for word in words:
        t=(s+" "+word).strip()
        if draw.textbbox((0,0),t,font=f)[2] > width and s:
            rows.append(s);s=word
        else:s=t
    if s:rows.append(s)
    y=xy[1]
    for row in rows:
        draw.text((xy[0],y),row,font=f,fill=fill)
        y+=int(sz*1.52)
    return y

def base():
    return Image.new("RGB",(W,H),INK)

def photo_canvas(img,beat,mode,source_info):
    canvas=base();d=ImageDraw.Draw(canvas)
    if mode==0:
        bounds=(1300,960);origin=(70,56)
        pic=ImageOps.contain(img.convert("RGB"),bounds,Image.Resampling.LANCZOS)
        x=origin[0]+(bounds[0]-pic.width)//2
        y=origin[1]+(bounds[1]-pic.height)//2
        canvas.paste(pic,(x,y))
        d.line((1400,96,1400,1000),fill=RED,width=7)
        label(d,(1460,137),beat["heading"],44,WHITE,True,410)
        label(d,(1460,410),"ORIGINAL ARCHIVE",23,MUTED,True,420)
        label(d,(1460,540),source_info.get("name",""),20,WHITE,False,400)
    else:
        bounds=(1730,870)
        pic=ImageOps.contain(img.convert("RGB"),bounds,Image.Resampling.LANCZOS)
        x=(W-pic.width)//2;y=56+(870-pic.height)//2
        canvas.paste(pic,(x,y))
        d.rectangle((73,949,85,1034),fill=RED)
        label(d,(112,947),beat["heading"],36,WHITE,True,1250)
        label(d,(112,1001),source_info.get("name","ARCHIVAL EVIDENCE"),20,MUTED,False,1680)
    return canvas

def document_canvas(path,beat,info,mode):
    file=fitz.open(path)
    symbols={"un-iraq-letter":"S/15826","un-iran-letter":"S/14206"}
    symbol=symbols.get(info["id"])
    index=0
    if symbol:
        matches=[i for i in range(file.page_count) if symbol in file[i].get_text()]
        if not matches:
            raise ValueError(f"Could not locate {symbol} in original PDF. Cannot display false page.")
        index=matches[0]
    page=file[index]
    pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
    im=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
    canvas=base();d=ImageDraw.Draw(canvas)
    bounds=(880,968)
    source=ImageOps.contain(im,bounds,Image.Resampling.LANCZOS)
    x=85+(880-source.width)//2;y=56+(968-source.height)//2
    canvas.paste(source,(x,y))
    d.line((1040,120,1040,980),fill=RED,width=6)
    label(d,(1090,160),beat["heading"],50,WHITE,True,735)
    label(d,(1090,350),info.get("symbol","UN RECORD"),37,WHITE,True,710)
    label(d,(1090,528),"COMPLETE ORIGINAL PAGE",27,MUTED,True,730)
    if info["id"] in ("un-iraq-letter","un-iran-letter"):
        label(d,(1090,618),"PARTY STATEMENT — allegations require independent corroboration",25,MUTED,False,695)
    else:
        label(d,(1090,618),"UNITED NATIONS DIGITAL LIBRARY",26,MUTED,False,690)
    label(d,(1090,914),"No excerpt crops · no altered evidence",21,MUTED,False,730)
    return canvas

CITIES=[
    ("Baghdad",33.315,44.366,0),("Basra",30.508,47.780,0),
    ("Khorramshahr",30.439,48.177,1),("Abadan",30.340,48.288,1),
    ("Ahvaz",31.321,48.669,1),("Tehran",35.689,51.389,1),
    ("Mandali",33.730,45.550,0),("Khanaqin",34.350,45.380,0)]
def projection(lat,lon):
    return int(410+(lon-43.5)*170),int(850-(lat-29.9)*139)

def map_canvas(beat,variant):
    c=base();d=ImageDraw.Draw(c)
    for u in range(8):
        x=350+u*190; d.line((x,150,x,955),fill=(28,36,40),width=2)
    for u in range(5):
        y=260+u*160; d.line((350,y,1800,y),fill=(28,36,40),width=2)
    label(d,(86,65),"THE EIGHT-YEAR FRONT",37,WHITE,True,1100)
    label(d,(86,126),"LOCATION DIAGRAM · NOT A FRONTLINE RECONSTRUCTION",22,MUTED,False,1650)
    # Guide-only geography: city positions from real coordinates, no invented military units.
    d.line((880,965,875,160),fill=(90,94,99),width=4)
    for name,lat,lon,country in CITIES:
        x,y=projection(lat,lon)
        d.ellipse((x-10,y-10,x+10,y+10),fill=(206,195,164) if not country else RED)
        dx=14 if name not in ("Khanaqin","Mandali") else -165
        label(d,(x+dx,y-39),name,25,WHITE if name in ("Baghdad","Basra","Khorramshahr") else MUTED,False,200)
    label(d,(515,955),"IRAQ",26,WHITE,True,280)
    label(d,(1250,955),"IRAN",26,WHITE,True,280)
    # The 1980 movement towards Khorramshahr is historically documented.
    if beat["id"] in (1,5):
        x0,y0=projection(30.508,47.780);x1,y1=projection(30.439,48.177)
        d.line((x0,y0,x1,y1),fill=RED,width=8)
        d.polygon([(x1,y1),(x1-25,y1-18),(x1-25,y1+18)],fill=RED)
        label(d,(1200,170),"SEPTEMBER 1980",31,WHITE,True,570)
        label(d,(1200,228),"Iraqi offensive towards the southern frontier",23,MUTED,False,570)
    d.rectangle((82,1000,1040,1008),fill=RED)
    label(d,(1090,995),beat["heading"],26,WHITE,True,740)
    return c

def video_overlay(beat,source):
    im=Image.new("RGBA",(W,H),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((62,851,1230,1030),radius=7,fill=(10,15,20,203))
    d.rectangle((62,866,70,1006),fill=RED)
    label(d,(101,871),beat["heading"],41,WHITE,True,1070)
    label(d,(101,948),"ORIGINAL WARTIME FOOTAGE · "+source["name"],21,WHITE,False,1090)
    return im

def make_picture(im,dst,secs):
    p=dst.with_suffix(".png");im.save(p)
    frames=round(secs*FPS)
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-loop","1",
        "-framerate",FPS,"-i",p,"-frames:v",frames,
        "-vf",f"scale={W}:{H},setsar=1,format=yuv420p",
        "-r",FPS,"-an","-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-video_track_timescale","15360",dst])

def make_archive_video(path,dst,secs,beat,source,seed):
    candidate=length(path)
    if candidate <= secs:offset=0
    else:offset=(seed*19)%(candidate-secs-0.3)
    panel=video_overlay(beat,source)
    png=dst.with_suffix(".png");panel.save(png)
    frames=round(secs*FPS)
    fc=(f"[0:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease:"
        "flags=lanczos,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0d1216,"
        "setsar=1,format=yuv420p[original];"
        "[1:v]format=rgba[info];"
        "[original][info]overlay=0:0:format=auto,format=yuv420p[final]")
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss",str(round(offset,2)),"-i",path,"-loop","1","-i",png,
        "-filter_complex",fc,"-map","[final]","-frames:v",frames,
        "-an","-c:v","libx264","-preset","veryfast","-crf","20",
        "-r",FPS,"-pix_fmt","yuv420p","-video_track_timescale","15360",dst])

def srt_timestamp(t):
    t=max(0.0,float(t))
    ms=round(t*1000)
    hh=ms//3600000; ms%=3600000
    mm=ms//60000; ms%=60000
    ss=ms//1000; ms%=1000
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"

def create_caption_track():
    """Optional caption track from aligned chapter durations; needs human sync QA."""
    captions=[]
    for beat,timing in zip(DATA["beats"],CLOCK["timings"]):
        words=beat["text"].split()
        # Short, readable 2-line excerpts, not a full paragraph on screen.
        groups=[words[i:i+9] for i in range(0,len(words),9)]
        usable=float(timing["speech_duration"])
        weights=[sum(len(w)+1 for w in g) for g in groups]
        total=sum(weights)
        passed=0
        for group,weight in zip(groups,weights):
            a=float(timing["start"])+usable*passed/total
            b=float(timing["start"])+usable*(passed+weight)/total
            captions.append((a,b," ".join(group)))
            passed+=weight
    text="".join(f"{n}\n{srt_timestamp(a)} --> {srt_timestamp(b)}\n{txt}\n\n"
        for n,(a,b,txt) in enumerate(captions,1))
    path=OUT/"english-captions.srt"
    path.write_text(text)
    return path

def make_score(duration,sr=24000):
    # Original restrained documentary score: sub-bass drones and sparse timed accents.
    t=np.arange(int(duration*sr),dtype=np.float32)/sr
    slow=np.sin(2*np.pi*41.2*t)*0.011
    harmonic=np.sin(2*np.pi*82.4*t)*0.004
    haze=np.sin(2*np.pi*126*t)*0.002
    music=(slow+harmonic+haze)*(0.8+0.2*np.sin(2*np.pi*0.019*t))
    for b in CLOCK["timings"]:
        ix=int(b["start"]*sr)
        n=min(sr//3,len(music)-ix)
        if n>0:
            dt=np.arange(n)/sr
            music[ix:ix+n]+=0.022*np.sin(2*np.pi*60*dt)*np.exp(-18*dt)
    n=min(3*sr,len(music)//2)
    fade=np.linspace(0,1,n,endpoint=True,dtype=np.float32)
    music[:n]*=fade
    music[-n:]*=fade[::-1]
    sf.write(OUT/"original_score.wav",np.clip(music,-0.8,0.8),sr)

def main():
    if AUDIT.get("errors"):
        raise RuntimeError("Source acquisition has unresolved original-media failures")
    durations=CLOCK["timings"]
    if len(durations)!=len(DATA["beats"]):
        raise RuntimeError("Timeline/narration beats mismatch")
    timeline=[]
    clips=[]
    for beat,clock in zip(DATA["beats"],durations):
        start=float(clock["start"]);end=float(clock["end"])
        available=end-start
        # Two authored editorial cuts per narration passage.
        durations2=[round(available*.49*FPS)/FPS,0]
        durations2[1]=round((available-durations2[0])*FPS)/FPS
        for j,(id,dt) in enumerate(zip(beat["visuals"],durations2)):
            scene=OUT/f"cut-{beat['id']:02d}-{j}.mp4"
            if id in ("border-map","front-map"):
                im=map_canvas(beat,j)
                kind="original-graphic";make_picture(im,scene,dt)
            else:
                src=ASSET[id]
                p=ROOT/src["local_file"]
                if not p.exists():
                    raise FileNotFoundError("Missing genuine media "+str(p))
                if src["kind"]=="video":
                    kind="archival-video"
                    make_archive_video(p,scene,dt,beat,src,beat["id"]+j)
                elif src["kind"]=="image":
                    kind="archival-photograph"
                    with Image.open(p) as raw:im=photo_canvas(raw,beat,j,src)
                    make_picture(im,scene,dt)
                else:
                    kind="original-document"
                    im=document_canvas(p,beat,src,j)
                    make_picture(im,scene,dt)
            clips.append(scene)
            timeline.append({"start":round(start,3),"duration":round(dt,3),
                "asset":id,"kind":kind,"chapter":beat["heading"],
                "source_url":ASSET[id].get("source_url") if id in ASSET else None})
            start+=dt
            print("CUT",len(clips),"of",2*len(DATA["beats"]),kind,id,round(dt,2),flush=True)
    lines="".join("file '"+p.resolve().as_posix()+"'\n" for p in clips)
    (OUT/"edit-list.txt").write_text(lines)
    video=OUT/"archival_master_video.mp4"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat",
        "-safe","0","-i",OUT/"edit-list.txt","-c","copy",video])
    make_score(float(CLOCK["duration"]))
    subs=create_caption_track()
    mp4=OUT/"THE-EIGHT-YEAR-FRONT-1080p.mp4"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",video,
        "-i",ROOT/"audio/narration.wav","-i",OUT/"original_score.wav",
        "-i",subs,
        "-filter_complex",
        "[1:a]aresample=48000,loudnorm=I=-17:TP=-2:LRA=9[voice];"
        "[2:a]aresample=48000,volume=0.75[score];"
        "[voice][score]amix=inputs=2:duration=first:dropout_transition=0,"
        "alimiter=limit=0.90[a]",
        "-map","0:v:0","-map","[a]","-map","3:s:0",
        "-c:s","mov_text","-metadata:s:s:0","language=eng",
        "-c:v","copy",
        "-c:a","aac","-b:a","192k","-ac","2",
        "-t",str(CLOCK["duration"]),
        "-movflags","+faststart","-metadata","title=THE EIGHT-YEAR FRONT · 1980—1988",mp4])
    info=ffprobe(mp4)
    v=next(x for x in info["streams"] if x["codec_type"]=="video")
    a=next(x for x in info["streams"] if x["codec_type"]=="audio")
    if (v.get("width"),v.get("height"))!=(W,H) or v["codec_name"]!="h264" or a["codec_name"]!="aac":
        raise RuntimeError("Master format not compliant with 1080p H264 AAC")
    if abs(length(mp4)-float(CLOCK["duration"]))>1:
        raise RuntimeError("Master length drift")
    (OUT/"edit_timeline.json").write_text(json.dumps(timeline,indent=2))
    (OUT/"machine_validation.json").write_text(json.dumps({
        "rendered_file":str(mp4),"decoded_validation_pending":True,
        "human_listening_review_required":True,
        "unique_sources":len(set(t["asset"] for t in timeline)),
        "cuts":len(timeline),"runtime_seconds":length(mp4),
        "all_source_frames_proportionally_contained":True,
        "historical_visuals_only_from_original_archive":True},indent=2))
    print("NEW FULL FILM EXPORTED:",mp4,mp4.stat().st_size,flush=True)

if __name__=="__main__":main()
