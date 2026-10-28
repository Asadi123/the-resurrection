#!/usr/bin/env python3
"""Build a distinct 12-chapter Iraqi-perspective film using ONLY the original two-thread archival master.
No synthetic historical images, no source cropping, no public social-platform credits.
The source master already contains every original attachment in a proportional contain layout.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, math, re, subprocess, sys
from pathlib import Path
import numpy as np
import soundfile as sf
import edge_tts

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"iraqi_perspective/output"
ASSETS=ROOT/"iraqi_perspective"
FPS,W,H=30,1920,1080
SAMPLE=24000
VOICE="en-US-AndrewMultilingualNeural"

def run(argv, quiet=False):
    cmd=[str(x) for x in argv]
    if quiet:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if p.returncode:raise RuntimeError("Failed: "+" ".join(cmd[:7])+"\n"+p.stderr[-1800:])
        return p.stdout
    subprocess.run(cmd,check=True)

def probe(path):
    return json.loads(run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",path],True))

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(4*1024*1024),b""):h.update(part)
    return h.hexdigest()

def check_source(master, report, chapter_data):
    master=Path(master)
    record=json.loads(Path(report).read_text())
    if record.get("status")!="RENDERED_VALIDATED":
        raise RuntimeError("Original footage is not validated")
    if sha256(master)!=record["sha256"]:
        raise RuntimeError("Source film hash mismatch: do not edit an unverified source film")
    segments=record["segments"]
    chapters=chapter_data["chapters"]
    if len(segments)!=98:raise RuntimeError("The complete 98-scene source film is required")
    prior=0
    for ch in chapters:
        first,last=ch["first"],ch["last"]
        if first!=prior+1 or last<first or last>98:raise RuntimeError("Chapter boundaries missing/misordered")
        prior=last
        if not ch["text"].strip() or not ch["sources"]:raise RuntimeError("Chapter lacks narrative/provenance")
        if re.search(r'@xumas|@3rab|threadreader|according to this thread|this post claims',ch["text"],re.I):
            raise RuntimeError("Unwanted social source narration")
    if prior!=98:raise RuntimeError("All original images and footage must be retained")
    info=probe(master)
    v=next(x for x in info["streams"] if x["codec_type"]=="video")
    a=next(x for x in info["streams"] if x["codec_type"]=="audio")
    if (v["width"],v["height"],v["codec_name"])!=(W,H,"h264") or a["codec_name"]!="aac":
        raise RuntimeError("Unexpected original film codec")
    total=float(info["format"]["duration"])
    if abs(total-sum(float(x["duration"]) for x in segments))>0.75:raise RuntimeError("Source timeline mismatch")
    return segments,total,record

async def tts_once(index,chapter,folder):
    target=folder/f'chapter_{index:02}.mp3'
    boundary_path=folder/f'chapter_{index:02}.words.json'
    if target.exists() and target.stat().st_size>2000 and boundary_path.exists():return
    for attempt in range(2):
        try:
            audio=[];boundaries=[]
            synth=edge_tts.Communicate(chapter["text"],VOICE,rate="+7%",pitch="-2Hz")
            async for event in synth.stream():
                if event["type"]=="audio":audio.append(event["data"])
                elif event["type"]=="WordBoundary":
                    boundaries.append({"offset":int(event["offset"]),"duration":int(event["duration"]),"text":event["text"]})
            raw=b''.join(audio)
            if len(raw)<1500 or len(boundaries)<8:
                raise RuntimeError(f'Neural voice returned insufficient data: {len(raw)} bytes, {len(boundaries)} words')
            target.write_bytes(raw)
            boundary_path.write_text(json.dumps(boundaries,ensure_ascii=False))
            print(f"GENERATED {index:02} / {len(CHAPTERS_GLOBAL)}: {len(boundaries)} timed words",flush=True)
            return
        except Exception as exc:
            if attempt:raise RuntimeError(f'Neural voice failed for chapter {index}: {exc}') from exc
            await asyncio.sleep(3)

CHAPTERS_GLOBAL=[]
async def generate_narration(chapters,folder):
    global CHAPTERS_GLOBAL
    CHAPTERS_GLOBAL=chapters
    folder.mkdir(exist_ok=True,parents=True)
    # Serial synthesis is deliberate: modest remote requests, no credit storm.
    for i,ch in enumerate(chapters,1):
        await tts_once(i,ch,folder)

def decoded_mono(mp3):
    p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(mp3),'-ar',str(SAMPLE),'-ac','1','-f','f32le','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode:raise RuntimeError(p.stderr.decode()[-1000:])
    x=np.frombuffer(p.stdout,dtype='<f4').copy()
    if len(x)<SAMPLE or not np.isfinite(x).all():raise RuntimeError('Bad narration audio')
    return x

def time_ass(secs):
    n=max(0,round(secs*100))
    return f"{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}"

def ass_safe(t):
    return t.replace('\\','').replace('{','').replace('}','').replace('\n',' ').strip()

def subtitles(events,chapters,spans,out):
    # Original material occupies only y=80..880. All text is outside these boundaries.
    head="""[Script Info]
Title: Iraq's Case — Original Perspective Narrated Cut
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,44,&H00F9F5EB,&H00FFFFFF,&H00101519,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,85,85,58,1
Style: Chapter,DejaVu Sans,29,&H00F1D09A,&H00FFFFFF,&H00101519,&H00000000,1,0,0,0,100,100,0,0,1,0,0,7,66,66,17,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    out_lines=[head]
    for (start,end,phrase) in events:
        if end-start<.08:continue
        out_lines.append(f"Dialogue: 1,{time_ass(start)},{time_ass(end)},Caption,,0,0,0,,{ass_safe(phrase)}\n")
    for ch,(start,end) in zip(chapters,spans):
        out_lines.append(f"Dialogue: 0,{time_ass(start)},{time_ass(end)},Chapter,,0,0,0,,{ass_safe(ch['title'])}\n")
    p=out/'captions_and_chapter_titles.ass'
    p.write_text(''.join(out_lines))
    return p

def generate_soundtrack(chapters,segments,total,folder,out):
    audio=np.zeros(int(math.ceil(total*SAMPLE)),dtype=np.float32)
    captions=[];spans=[];report=[]
    for idx,ch in enumerate(chapters,1):
        first,last=ch["first"],ch["last"]
        start=float(segments[first-1]["start_in_master"])
        end=float(segments[last-1]["start_in_master"])+float(segments[last-1]["duration"])
        available=end-start
        mp3=folder/f'chapter_{idx:02}.mp3'
        recorded=decoded_mono(mp3)
        boundaries=json.loads((folder/f'chapter_{idx:02}.words.json').read_text())
        # The entire chapter is spoken coherently, crossing many image cuts.
        limit=available-.22
        initial=len(recorded)/SAMPLE
        tempo=max(1.,initial/limit)
        if tempo>1.37:
            raise RuntimeError(f"Narration chapter {idx} will not fit its {available:.2f}s window without sounding robotic (needs {tempo:.2f}x). Shorten the script.")
        if tempo>1.005:
            temp=out/f'chapter_{idx:02}_fit.wav'
            run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',mp3,
                  '-af',f'atempo={tempo:.5f}','-ar',SAMPLE,'-ac','1',temp],True)
            recorded,_=sf.read(temp,dtype='float32')
            if recorded.ndim>1:recorded=recorded.mean(axis=1)
        # voice amplitude normalized by measured RMS, preserving speaker envelope.
        rms=float(np.sqrt(np.mean(np.square(recorded.astype(np.float64)))+1e-10))
        recorded=np.clip(recorded*min(4.0,.085/max(.008,rms)),-.8,.8).astype(np.float32)
        fade=min(int(.035*SAMPLE),len(recorded)//5)
        if fade>0:
            ramp=np.linspace(0,1,fade,dtype=np.float32)
            recorded[:fade]*=ramp;recorded[-fade:]*=ramp[::-1]
        placement=start+.08
        a=round(placement*SAMPLE);b=min(len(audio),a+len(recorded))
        if b<=a:raise RuntimeError('Voice placement fell outside film')
        audio[a:b]+=recorded[:b-a]
        playable=(b-a)/SAMPLE
        if playable>available+.015:raise RuntimeError('Voice overlaps following source chapter')
        spans.append((start,end))
        # Precise Edge TTS word timing. Group words for readable burn-in subtitles.
        tokens=ch["text"].split()
        word_events=boundaries
        exact_count=(len(word_events)==len(tokens))
        all_words=[]
        if exact_count:
            for k,w in enumerate(tokens):
                s=placement+word_events[k]["offset"]/1e7/tempo
                e=s+word_events[k]["duration"]/1e7/tempo
                all_words.append((w,s,e))
        else:
            # WordBoundary may split hyphenated names or contractions.
            # Preserve exact script wording with timing estimated from actual voice duration.
            total_letters=sum(max(1,len(t)) for t in tokens)
            cum=0
            for w in tokens:
                s=placement+playable*cum/total_letters
                cum+=max(1,len(w))
                e=placement+playable*cum/total_letters
                all_words.append((w,s,e))
        text=[];s0=None;e0=None
        for word,ws,we in all_words:
            if text and (len(' '.join(text+[word]))>51 or len(text)>=8):
                captions.append((s0,e0,' '.join(text)))
                text=[];s0=None;e0=None
            if s0 is None:s0=ws
            text.append(word);e0=we
        if text:captions.append((s0,e0,' '.join(text)))
        report.append({"chapter":idx,"heading":ch["title"],"start":round(start,3),"end":round(end,3),
          "visual_assets":list(range(first,last+1)),"voice_seconds":round(playable,3),
          "word_count":len(tokens),"word_boundaries":len(word_events),
          "word_timing":"exact_voice_word_boundaries" if exact_count else "script_length_estimate",
          "source_refs":ch["sources"],"voice_fit_tempo":round(tempo,3)})
        print(f"CHAPTER {idx:02}: {len(tokens)} words, {available:.1f}s slot, {playable:.1f}s voice; {len(word_events)} word marks",flush=True)
    # Preserve the source sound from original footage, ducked under our clear narrator.
    # Source media has no added music; do not insert unrelated sound.
    # A 24kHz stereo source can be handled in memory on 7GB GitHub Actions runners.
    return audio,spans,captions,report

def make_mix(master,voice_audio,out,total):
    raw=out/'source_audio.f32'
    run(['ffmpeg','-v','error','-y','-i',master,'-vn','-ac','2','-ar',SAMPLE,
         '-f','f32le',raw],True)
    src=np.fromfile(raw,dtype='<f4')
    n=len(voice_audio)
    if len(src)%2:src=src[:-1]
    src=src.reshape(-1,2)
    if len(src)<n:src=np.pad(src,((0,n-len(src)),(0,0)))
    src=src[:n]
    # Gentle crossfade for archival speech when the narrator begins/ends.
    envelope=np.clip(np.abs(voice_audio)*70,0,1)
    win=int(.13*SAMPLE)
    if win>1:
        kernel=np.ones(win,dtype=np.float32)/win
        # use convolution via same-length scipy? simple forward/reverse moving average.
        accum=np.cumsum(np.concatenate(([0.0],envelope.astype(np.float64))))
        smooth=(accum[win:]-accum[:-win])/win
        pad=np.pad(smooth,(win//2,n-len(smooth)-win//2),mode='edge')
        envelope=np.clip(pad,0,1)
    gain=(.32-.22*envelope).astype(np.float32)
    left=voice_audio*.98+src[:,0]*gain
    right=voice_audio*.98+src[:,1]*gain
    final=np.stack([left,right],axis=1)
    final=np.clip(final,-.94,.94)
    wav=out/'original_archives_plus_narrator.wav'
    sf.write(wav,final,SAMPLE,subtype='PCM_16')
    raw.unlink(missing_ok=True)
    return wav

def encode(master,mix,ass,output,total):
    filterv=("drawbox=x=0:y=0:w=1920:h=63:color=0x101314:t=fill,"
             "drawbox=x=0:y=897:w=1920:h=183:color=0x101314:t=fill,"
             f"ass='{ass.as_posix()}':fontsdir=/usr/share/fonts/truetype/dejavu")
    run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',master,
         '-i',mix,'-map','0:v:0','-map','1:a:0','-vf',filterv,
         '-c:v','libx264','-preset','veryfast','-crf','21','-r','30','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','224k','-ac','2','-ar','48000',
         '-t',str(total),'-movflags','+faststart',output])
    info=probe(output)
    v=next(s for s in info['streams'] if s['codec_type']=='video')
    a=next(s for s in info['streams'] if s['codec_type']=='audio')
    if (v['width'],v['height'],v['codec_name'])!=(W,H,'h264') or a['codec_name']!='aac':
        raise RuntimeError('Final export codec validation failed')
    if abs(float(info['format']['duration'])-total)>.4:raise RuntimeError('Duration drift')
    run(['ffmpeg','-v','error','-xerror','-i',output,'-f','null','-'],True)
    return info

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--master',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--out',type=Path,default=OUT)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    chapter_data=json.loads((ASSETS/'chapters.json').read_text())
    segments,total,prior=check_source(args.master,args.report,chapter_data)
    async_folder=args.out/'voice_assets'
    asyncio.run(generate_narration(chapter_data['chapters'],async_folder))
    audio,spans,captions,results=generate_soundtrack(chapter_data['chapters'],segments,total,async_folder,args.out)
    ass=subtitles(captions,chapter_data['chapters'],spans,args.out)
    mixed=make_mix(args.master,audio,args.out,total)
    final=args.out/'IRAQS-CASE-IRAQI-PERSPECTIVE-FINAL-CUT-1080p.mp4'
    meta=encode(args.master,mixed,ass,final,total)
    qa={'film':str(final),'sha256':sha256(final),'source_master_sha256':prior['sha256'],
        'complete_original_source_frames':98,'video_source_crop':'none; original film contained and padded in y=80..880',
        'original_media_reused_without_new_assets':True,'chapters':results,'burned_subtitles':len(captions),
        'render_decoded_without_errors':True,'runtime_seconds':float(meta['format']['duration']),
        'perspective':'Iraqi nationalist/historically Baathist framing based solely on the two commissioned source collections',
        'audio_notice':'Synthetic neural voice; human listening and source-rights review remain necessary'}
    (args.out/'FINAL-EDITORIAL-REPORT.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False))
    # Screenshot samples for manual QA, no invented sources.
    for name,at in [('beginning',8),('diplomacy',255),('arms',515),('victory',745)]:
        run(['ffmpeg','-v','error','-y','-ss',str(at),'-i',final,'-frames:v','1',args.out/f'frame_{name}.jpg'],True)
    print('FULL_VALIDATED_FILM',final,final.stat().st_size,round(total,2),'seconds',flush=True)

if __name__=='__main__':main()
