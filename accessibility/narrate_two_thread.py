#!/usr/bin/env python3
"""Upgrade the validated 98-segment film: narration + burned captions, original images untouched."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, math, re, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
import edge_tts

ROOT=Path(__file__).resolve().parents[1]
W,H,FPS=1920,1080,30
def run(args, **kw):
    return subprocess.run([str(a) for a in args],check=True,**kw)
def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))
def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def validate_inputs(master,report,script,edit):
    metadata=probe(master)
    v=next(s for s in metadata['streams'] if s['codec_type']=='video')
    a=next(s for s in metadata['streams'] if s['codec_type']=='audio')
    assert (v['width'],v['height'],v['codec_name'])==(W,H,'h264'), 'Unexpected visual source encoding'
    assert a['codec_name']=='aac', 'Original source audio missing'
    assert report['sha256']==sha256(master), 'Original validated film has an unexpected hash'
    receipts=report['segments']
    lines=script['lines']
    assert len(receipts)==len(lines)==len(edit['segments'])==98, '98 media associations are mandatory'
    assert all(s['asset_id']==r['asset_id'] for s,r in zip(edit['segments'],receipts))
    assert all(float(r['duration'])>0 for r in receipts)
    duration=float(metadata['format']['duration'])
    assert abs(sum(float(r['duration']) for r in receipts)-duration)<0.5
    for line in lines:
        assert isinstance(line,str) and 10<len(line)<410, 'Voice line too short/long'
        assert not re.search(r'@\w+|twitter|threadreader|xumas_iq|3rab_vision|source bundle',line,re.I), 'Social account leaked into narration'
    return receipts,duration

async def synthesize(lines,dest,voice):
    dest.mkdir(exist_ok=True,parents=True)
    for i,line in enumerate(lines):
        path=dest/f'line-{i+1:03}.mp3'
        if path.is_file() and path.stat().st_size>700:continue
        last=None
        for attempt in range(3):
            try:
                await edge_tts.Communicate(text=line,voice=voice,rate='+4%',pitch='-3Hz').save(str(path))
                if path.stat().st_size<700:raise RuntimeError('Empty TTS clip')
                print(f'VOICE {i+1:03}/{len(lines)}',flush=True)
                last=None;break
            except Exception as e:
                last=e
                await asyncio.sleep(2+attempt*3)
        if last is not None:raise RuntimeError(f'Neural narrator failed on segment {i+1}: {last}')

def speech(path,sr):
    p=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-ac','1','-ar',str(sr),'-f','f32le','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode:raise RuntimeError('Cannot decode synthesized speech: '+p.stderr.decode()[-500:])
    x=np.frombuffer(p.stdout,dtype=np.float32).copy()
    if not len(x) or not np.isfinite(x).all():raise RuntimeError('Invalid generated voice audio')
    return x

def ass_time(t):
    t=max(0.0,t);cs=round(t*100)
    return f'{cs//360000:01}:{(cs//6000)%60:02}:{(cs//100)%60:02}.{cs%100:02}'
def captions_ass(events,path):
    head='''[Script Info]
Title: THE WAR THEY WOULD NOT END | Narrated English Captions
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,40,&H00FFFFFF,&H00FFFFFF,&H000D1217,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,90,90,53,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[]
    for t0,t1,phrase in events:
        phrase=phrase.replace('{','').replace('}','').replace('\n',' ')
        lines.append(f'Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Default,,0,0,0,,{phrase}')
    path.write_text(head+'\n'.join(lines)+'\n',encoding='utf-8')

def audio_and_timing(lines,receipts,speechdir,out,duration,sr=24000):
    samples=np.zeros(int(math.ceil(duration*sr))+sr,dtype=np.float32)
    events=[];summary=[]
    for i,(line,receipt) in enumerate(zip(lines,receipts)):
        start=float(receipt['start_in_master']);slot=float(receipt['duration'])
        clip=speech(speechdir/f'line-{i+1:03}.mp3',sr)
        # Drop only leading encoder silence, not natural speech pauses.
        indices=np.flatnonzero(np.abs(clip)>0.0009)
        if len(indices):clip=clip[max(0,int(indices[0])-int(.025*sr)):]
        reserved=max(1,int((slot-.18)*sr))
        if len(clip)>reserved:
            speed=len(clip)/reserved
            if speed>1.65:
                raise RuntimeError(f'Voice {i+1} substantially exceeds its {slot:.2f}s source shot ({speed:.2f}x); revise the script without chopping its sentence.')
            temp=out/f'tight-{i+1:03}.wav'
            run(['ffmpeg','-v','error','-y','-i',speechdir/f'line-{i+1:03}.mp3','-af',f'atempo={speed:.4f}','-ar',sr,'-ac','1',temp],stdout=subprocess.DEVNULL)
            clip,_=sf.read(temp,dtype='float32')
            if clip.ndim>1:clip=clip.mean(axis=1)
            clip=clip[:reserved]
        if len(clip)==0:raise RuntimeError('Empty synthesized sentence')
        rms=float(np.sqrt(np.mean(np.square(clip.astype(np.float64)))+1e-10))
        clip=clip*min(4.2,.077/max(rms,.007))
        clip=np.clip(clip,-.82,.82).astype(np.float32)
        fade=min(len(clip)//5,int(.045*sr))
        if fade>0:
            a=np.linspace(0,1,fade,dtype=np.float32)
            clip[:fade]*=a;clip[-fade:]*=a[::-1]
        start_sample=int((start+.08)*sr)
        stop=min(len(samples),start_sample+len(clip))
        samples[start_sample:stop]+=clip[:stop-start_sample]
        spoken_duration=(stop-start_sample)/sr
        if spoken_duration<1.2:raise RuntimeError('Voice sequence unexpectedly short')
        words=line.split()
        # Captions are timed to the actual new narration, not the original visual footer.
        groups=[];g=[]
        for word in words:
            if len(' '.join(g+[word]))>53 or len(g)>=8:
                if g:groups.append(g)
                g=[word]
            else:g.append(word)
        if g:groups.append(g)
        weights=[max(2,sum(len(w) for w in g)) for g in groups]
        tot=sum(weights);passed=0
        for group,weight in zip(groups,weights):
            a=start+.08+spoken_duration*passed/tot
            b=start+.08+spoken_duration*(passed+weight)/tot
            events.append((a,b,' '.join(group)));passed+=weight
        summary.append({'scene':i+1,'source_asset':receipt['asset_id'],'visual_start':start,'visual_duration':slot,'speech_duration':round(spoken_duration,2),'caption_count':len(groups)})
    samples=np.clip(samples[:int(round(duration*sr))],-.93,.93)
    wav=out/'english_narration.wav'
    sf.write(wav,samples,sr,subtype='PCM_16')
    ass=out/'english_captions_burned.ass';captions_ass(events,ass)
    (out/'narration_timing.json').write_text(json.dumps({'voice':'en-GB-RyanNeural','language':'English','synchronized_captions':len(events),'scenes':summary},indent=2))
    print('COMPLETE NARRATION',round(duration,2),'seconds,',len(events),'caption cards',flush=True)
    return wav,ass

def render(master,wav,ass,out,duration):
    video=out/'IRAQS-CASE-NARRATED-ENGLISH-CAPTIONS-1080p.mp4'
    # Media is ALREADY fully contained between y=63..897; only opaque source-interface
    # headers and footers are replaced, without hiding ANY source image pixels.
    filt=("[0:v]drawbox=x=0:y=0:w=1920:h=63:color=0x101314:t=fill,"
          "drawbox=x=0:y=897:w=1920:h=183:color=0x101314:t=fill,"
          "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
          "text='IRAQS CASE  /  1980-1988':fontsize=27:fontcolor=white:x=60:y=16,"
          f"ass='{ass.as_posix()}'[v];"
          "[0:a]aresample=48000,volume=0.16[archive];"
          "[1:a]aresample=48000,highpass=f=65,volume=1.15[speech];"
          "[archive][speech]amix=inputs=2:duration=first:normalize=0,"
          "loudnorm=I=-16:TP=-1.5:LRA=9[a]")
    args=['ffmpeg','-hide_banner','-nostdin','-y','-i',master,'-i',wav,
          '-filter_complex',filt,'-map','[v]','-map','[a]',
          '-c:v','libx264','-preset','veryfast','-crf','21','-r','30',
          '-pix_fmt','yuv420p','-c:a','aac','-b:a','224k','-ar','48000','-ac','2',
          '-t',str(duration),'-movflags','+faststart',
          '-metadata','title=IRAQS CASE - Narrated Edition with English Captions',
          video]
    run(args)
    meta=probe(video)
    typ=[s['codec_type'] for s in meta['streams']]
    assert 'video' in typ and 'audio' in typ
    assert abs(float(meta['format']['duration'])-duration)<.6
    assert video.stat().st_size>5_000_000
    run(['ffmpeg','-v','error','-xerror','-i',video,'-f','null','-'],stdout=subprocess.DEVNULL)
    shot=out/'caption_preview.jpg'
    run(['ffmpeg','-v','error','-y','-ss','4','-i',video,'-frames:v','1',shot],stdout=subprocess.DEVNULL)
    return video

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--master',required=True,type=Path)
    ap.add_argument('--report',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    edit=json.loads((ROOT/'two_thread/edit.json').read_text())
    script=json.loads((ROOT/'two_thread/narration_script.json').read_text())
    report=json.loads(args.report.read_text())
    receipts,duration=validate_inputs(args.master,report,script,edit)
    asyncio.run(synthesize(script['lines'],args.out/'neural_voice',script['narrator']))
    wav,ass=audio_and_timing(script['lines'],receipts,args.out/'neural_voice',args.out,duration)
    result=render(args.master,wav,ass,args.out,duration)
    print('FINAL_NARRATED_CAPTIONED_FILM',result,result.stat().st_size,flush=True)

if __name__=='__main__':main()
