#!/usr/bin/env python3
"""Iran-Iraq archival edit V2: REAL cited source excerpts, motion design, neural narration."""
import asyncio, math, os, random, subprocess, textwrap, urllib.parse, wave
from pathlib import Path
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'assets'
OUT=ROOT/'output'
ASSETS.mkdir(exist_ok=True,parents=True)
OUT.mkdir(exist_ok=True,parents=True)
W,H=1280,720
BG=(11,14,18); WHITE=(246,241,226); MUTED=(180,183,181); RED=(223,63,49); GOLD=(223,182,100)
FB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FR='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
def f(size,bold=False):return ImageFont.truetype(FB if bold else FR,size)
def run(args):subprocess.run(args,check=True)
def ffprobe(path):
    import json
    p=subprocess.check_output(['ffprobe','-v','quiet','-show_entries','format=duration','-of','json',str(path)])
    return float(json.loads(p)['format']['duration'])
SOURCE={
'telegram':'https://pbs.twimg.com/media/FykVBoMWcAMSzso.jpg',
'murray':'https://pbs.twimg.com/media/FykeHQhWAAEHzyz.png',
'chapter':'https://pbs.twimg.com/media/Fykg9YPWwAI7coV.png',
'banisadr':'https://pbs.twimg.com/media/Fykh8B5WcAYJw45.png',
'afp':'https://pbs.twimg.com/media/FykiJ1XWYAIUvVi.png',
'border':'https://pbs.twimg.com/media/FykkTtZXwAE1kxt.png',
'incidents':'https://pbs.twimg.com/media/Fykk4HkWcAUYjQr.png',
'demo':'https://pbs.twimg.com/ext_tw_video_thumb/1668890627482820609/pu/img/LkjX6RwWDMCU9f16.jpg',
'map':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Gu%C3%A8rra_Iran_Iraq_%281980-1988%29.png',
'war_map':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Map_of_the_frontlines_in_the_Iran-Iraq_War.jpg',
}
def fetch_assets():
 for key,url in SOURCE.items():
  ext='png' if key not in ('telegram','demo','war_map') else 'jpg'
  dest=ASSETS/(key+'.'+ext)
  if dest.exists():continue
  try:
   response=requests.get(url,timeout=24,headers={'User-Agent':'Mozilla/5.0 (historical documentary research; source attribution)'},allow_redirects=True)
   response.raise_for_status()
   if len(response.content)<2000:raise ValueError('short response')
   from io import BytesIO
   raw=Image.open(BytesIO(response.content)).convert('RGB')
   raw.save(dest,quality=95)
   print('downloaded',key,raw.size,flush=True)
  except Exception as exc:
   print('SOURCE DOWNLOAD FAILED',key,str(exc)[:200],flush=True)

BEATS=[
{"type":"impact","title":"THE WAR BEFORE THE WAR","sub":"IRAN  /  IRAQ  ·  1979—1988","media":"incidents","handle":"@xumas_iq","voice":"September twenty-second, nineteen eighty. That date is famous. But the story these two research threads tell begins earlier."},
{"type":"accounts","title":"TWO THREADS. ONE WAR.","sub":"SOURCE 001  ·  @3rab_vision     |     SOURCE 002  ·  @xumas_iq","media":"demo","handle":"@3rab_vision  +  @xumas_iq","voice":"Two accounts on X, Arab Vision and Xumas, ask whether the history of the Iran Iraq war can be understood from its opening invasion alone."},
{"type":"source","title":"APRIL 1979","sub":"An Iraqi telegram of congratulations to Iran","media":"telegram","handle":"@xumas_iq","voice":"Xumas opens with this excerpt. It says Iraq's government congratulated Iran on the declaration of the Islamic Republic in April, nineteen seventy nine."},
{"type":"source","title":"THE RHETORIC HARDENS","sub":"Murray and Woods excerpt cited in the Xumas thread","media":"murray","handle":"@xumas_iq","voice":"Another screenshot, from Williamson Murray and Kevin Woods, describes revolutionary hostility and attacks during the following year."},
{"type":"source","title":"THE ALGIERS AGREEMENT","sub":"A dispute over territory and the 1975 settlement","media":"chapter","handle":"@xumas_iq","voice":"By September nineteen eighty, the border and the nineteen seventy five Algiers Agreement had become central points of confrontation."},
{"type":"source","title":"IRAN'S PRESIDENT","sub":"An excerpt attributed to statements by Bani Sadr","media":"banisadr","handle":"@xumas_iq","voice":"The thread also reproduces passages about Iranian president Bani Sadr, and disputes over obligations inherited from the Shah."},
{"type":"source","title":"A SEPTEMBER WARNING","sub":"An AFP interview excerpt reproduced on X","media":"afp","handle":"@xumas_iq","voice":"In this excerpt from a report citing Agence France Presse, Bani Sadr is quoted on whether the Algiers agreement had actually been implemented."},
{"type":"source","title":"SHATT AL-ARAB","sub":"The waterway at the heart of the dispute","media":"border","handle":"@xumas_iq","voice":"And this photographed page alleges escalating incidents around the Shatt al Arab waterway, in the days leading to open war."},
{"type":"source","title":"21 SEPTEMBER 1980","sub":"A contemporaneous-claim list reproduced in the thread","media":"incidents","handle":"@xumas_iq","voice":"One list, shared by Xumas, alleges multiple incidents on September twenty first, including shellfire near Khanqin and shipping attacks."},
{"type":"impact","title":"22 SEPTEMBER 1980","sub":"IRAQ LAUNCHES A FULL-SCALE INVASION","media":"map","handle":"HISTORICAL TIMELINE","voice":"The next day, Iraqi forces launched a full scale invasion of Iran. That fact is not undone by arguments over the events that came before."},
{"type":"impact","title":"CLAIMS ARE NOT PROOF","sub":"Archive screenshots are evidence of a claim, not automatic verification","media":"chapter","handle":"SOURCE REVIEW","voice":"A crucial distinction. These are real excerpts reproduced by an X account. Every major allegation still needs checking against its original publication."},
{"type":"impact","title":"RESOLUTION 479","sub":"UNITED NATIONS  ·  28 SEPTEMBER 1980","media":"telegram","handle":"UNITED NATIONS","voice":"Six days after the invasion, the U N Security Council adopted Resolution four seventy nine, urging both countries to stop using force."},
{"type":"impact","title":"THE WAR CONTINUES","sub":"FOREIGN INTERESTS  /  CEASEFIRE ATTEMPTS  /  1980—1988","media":"war_map","handle":"@3rab_vision  +  @xumas_iq","voice":"The threads then move to foreign involvement, wartime diplomacy, and why the fighting continued. Their wider numerical claims require separate verification."},
{"type":"impact","title":"1988  ·  CEASEFIRE","sub":"RESOLUTION 598  ·  AUGUST 20","media":"war_map","handle":"UNITED NATIONS","voice":"Iran accepted Resolution five ninety eight in July nineteen eighty eight. The ceasefire took effect on August twentieth."},
{"type":"credits","title":"READ THE ORIGINAL SOURCES","sub":"@3rab_vision   ×   @xumas_iq","media":"telegram","handle":"LINKS IN SOURCE REGISTER","voice":"Source one, Arab Vision. Source two, Xumas. Their posts and original document images are the starting point. Read the sources, then judge the evidence."}
]
# Draw an editorial composition. Display retrieved images as images, never fabricate scan content.
def background(seed):
 rng=np.random.default_rng(seed)
 arr=np.empty((H,W,3),dtype=np.uint8)
 y,x=np.mgrid[0:H,0:W]
 glow=np.exp(-((x-W*.38)**2/(W*.86)**2+(y-H*.35)**2/(H*.88)**2))
 noise=rng.normal(0,2,(H,W))
 for c,b in enumerate(BG):
  arr[:,:,c]=np.clip(b + glow*(18 if c!=2 else 19)+noise,0,255)
 return Image.fromarray(arr,'RGB')
def tx(d,xy,s,sz=32,color=WHITE,bold=False,maxw=None,leading=14):
 font=f(sz,bold)
 if maxw:
  out=[];line=''
  for word in s.split():
   q=(line+' '+word).strip()
   if d.textbbox((0,0),q,font=font)[2]<=maxw:line=q
   else:
    if line:out.append(line)
    line=word
  if line:out.append(line)
  s='\n'.join(out)
 d.multiline_text(xy,s,font=font,fill=color,spacing=leading)
def asset(key):
 for suffix in ('jpg','png'):
  p=ASSETS/(key+'.'+suffix)
  if p.exists():
   try:return Image.open(p).convert('RGB')
   except:pass
 return None
def fitimg(src,area,crop=False):
 x,y,w,h=area
 if crop:return ImageOps.fit(src,(w,h),method=Image.Resampling.LANCZOS,centering=(.5,.5))
 im=src.copy();im.thumbnail((w,h),Image.Resampling.LANCZOS);return im
def composition(index,variation):
 b=BEATS[index]
 im=background(index*12+variation)
 d=ImageDraw.Draw(im)
 d.rectangle((0,0,13,H),fill=RED)
 d.rectangle((0,0,W,4),fill=GOLD)
 tx(d,(35,18),'ARCHIVE / IRAQ–IRAN 1980—1988',15,GOLD,True)
 tx(d,(1065,18),f'FILM 001 / {index+1:02}',14,MUTED,True)
 key=b['media']; pic=asset(key)
 src=(pic is not None)
 if b['type']=='source':
  # Genuine source excerpt occupies more than half the frame.
  d.rounded_rectangle((35,147,1245,630),radius=12,fill=(220,213,199),outline=(185,160,127),width=2)
  if pic:
   if variation==1:
    # Second shot punches into the photographed evidence, preserving original pixels.
    pw,ph=pic.size
    if ph>pw*1.2:
     region=pic.crop((int(pw*.07),int(ph*.32),int(pw*.93),int(ph*.69)))
    elif pw>ph*2.8:
     region=pic.crop((int(pw*.12),int(ph*.06),int(pw*.91),int(ph*.94)))
    else:
     region=pic.crop((int(pw*.055),int(ph*.25),int(pw*.945),int(ph*.76)))
    frame=fitimg(region,(60,170,1160,424),False)
    maxup=1160/frame.width
    if maxup>1 and frame.height*maxup<=424:
     frame=frame.resize((1160,int(frame.height*maxup)),Image.Resampling.LANCZOS)
    tx(d,(87,568),'CLOSE-UP  /  ORIGINAL DOCUMENT',15,RED,True)
   else:
    frame=fitimg(pic,(60,170,1160,424),False)
   im.paste(frame,(60+(1160-frame.width)//2,170+(424-frame.height)//2))
  else:
   tx(d,(85,280),'SOURCE IMAGE UNAVAILABLE',40,(120,54,45),True)
  d.rectangle((35,94,1245,147),fill=RED if variation==0 else (47,52,58))
  tx(d,(58,104),b['title'],30,WHITE,True)
  tx(d,(49,643),b['sub'],18,WHITE,False,maxw=1000)
  tx(d,(1040,645),b['handle'],14,GOLD,True)
 elif b['type']=='accounts':
  if pic:
   cover=fitimg(pic,(720,78,536,560),True)
   im.paste(cover,(720,78))
   layer=Image.new('RGBA',(536,560),(0,0,0,0)); ld=ImageDraw.Draw(layer);ld.rectangle((0,0,536,560),fill=(0,0,0,90));im.paste(Image.alpha_composite(im.crop((720,78,1256,638)).convert('RGBA'),layer).convert('RGB'),(720,78))
  tx(d,(61,112),'@3rab_vision',45,GOLD,True); tx(d,(61,200),'@xumas_iq',49,WHITE,True)
  d.rectangle((61,300,570,305),fill=RED)
  tx(d,(61,347),'HISTORICAL THREADS',31,WHITE,True)
  tx(d,(61,422),'ORIGINAL POSTS',20,MUTED,True)
  tx(d,(61,459),'Source 001 and Source 002',18,GOLD)
 elif b['type']=='credits':
  if pic:
   cover=fitimg(pic,(650,70,585,555),True)
   im.paste(cover,(650,70))
   d.rectangle((650,70,1235,625),outline=GOLD,width=3)
  tx(d,(58,150),'SOURCES',74,WHITE,True)
  tx(d,(58,280),'@3rab_vision',39,GOLD,True);tx(d,(58,360),'@xumas_iq',39,WHITE,True)
  tx(d,(58,480),'ORIGINAL X POSTS + SCANNED EXCERPTS',16,MUTED)
 else:
  # fast editorial title over ORIGINAL media (NOT generative imagery)
  if pic:
   cover=fitimg(pic,(560,75,665,562),True)
   im.paste(cover,(560,75))
   mask=Image.new('RGBA',(665,562),(8,10,12,130))
   bgsub=im.crop((560,75,1225,637)).convert('RGBA')
   im.paste(Image.alpha_composite(bgsub,mask).convert('RGB'),(560,75))
  d.rectangle((545,78,551,626),fill=RED)
  st=b['title']
  tx(d,(54,183),st,54 if len(st)<22 else 45,WHITE,True,maxw=500)
  d.rectangle((55,360,205,367),fill=GOLD)
  tx(d,(54,399),b['sub'],22,GOLD,True,maxw=480)
  tx(d,(54,590),b['handle'],18,MUTED,True)
 # fast punchline changes
 if variation==1:
  d.rectangle((37,657,1260,660),fill=RED)
  tx(d,(37,673),'RESEARCH / ORIGINAL SOURCE MATERIAL',13,MUTED,True)
 else:
  d.rectangle((37,657,1260,660),fill=GOLD)
  tx(d,(37,673),'@xumas_iq     /     @3rab_vision',14,MUTED,True)
 tx(d,(1110,674),f'{index+1:02} / {len(BEATS):02}',14,GOLD,True)
 return im
async def narrate():
 import edge_tts
 voice='en-GB-RyanNeural'
 for i,b in enumerate(BEATS):
  p=OUT/f'voice_{i:02}.mp3'
  if p.exists() and p.stat().st_size>2000:continue
  print('neural narration',i,flush=True)
  await edge_tts.Communicate(b['voice'],voice=voice,rate='-3%',pitch='-5Hz').save(str(p))
def audio_master():
 import soundfile as sf
 sr=24000
 segments=[]
 timing=[]
 total=0
 for i in range(len(BEATS)):
  p=OUT/f'voice_{i:02}.mp3'
  out=OUT/f'voice_{i:02}.wav'
  run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(p),'-ac','1','-ar',str(sr),str(out)])
  x,ss=sf.read(out,dtype='float32')
  if x.ndim>1:x=x.mean(1)
  # short editorial beat between statements
  pad=int((.23 if i else .15)*sr)
  x=np.concatenate([np.zeros(pad,dtype=np.float32),x,np.zeros(int(.17*sr),dtype=np.float32)])
  timing.append(len(x)/sr);segments.append(x)
  total+=len(x)
 spoken=np.concatenate(segments)
 # cinematic restrained score, rhythmic sub pulse and dark atmospheric drones
 t=np.arange(total,dtype=np.float32)/sr
 drone=(.019*np.sin(2*np.pi*55*t)+.011*np.sin(2*np.pi*82.41*t)+.007*np.sin(2*np.pi*110.0*t))
 score=drone*(0.56+0.18*np.sin(2*np.pi*.09*t))
 beat=np.zeros(total,dtype=np.float32)
 for ix in range(0,total,int(.85*sr)):
  z=np.arange(min(int(.19*sr),total-ix),dtype=np.float32)/sr
  beat[ix:ix+len(z)]+=.027*np.sin(2*np.pi*(60-23*z)*z)*np.exp(-25*z)
 score+=beat
 ramp=np.minimum(np.arange(total)/sr/1.9,1)*np.minimum((total-np.arange(total))/sr/2.2,1)
 wave=np.clip(spoken*.95+score*ramp,-.95,.95)
 sf.write(OUT/'soundtrack.wav',wave,sr,subtype='PCM_16')
 return timing

def animate(i,variant,duration):
 dest=OUT/f'shot_{i:02}_{variant}.png'
 if not dest.exists():composition(i,variant).save(dest,optimize=True)
 mov=OUT/f'shot_{i:02}_{variant}.mp4'
 # frame step gives a subtle documentary push-in. Second cut pans the other way.
 frames=int(round(duration*24))
 drift="(iw-iw/zoom)*0.12" if variant==0 else "(iw-iw/zoom)*0.80"
 vs=f"scale=1408:792,zoompan=z='min(zoom+0.00035,1.095)':x='{drift}':y='(ih-ih/zoom)/2':d=1:s=1280x720:fps=24,format=yuv420p"
 run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',str(dest),'-vf',vs,'-frames:v',str(frames),'-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-an',str(mov)])
 return mov

def main():
 fetch_assets()
 asyncio.run(narrate())
 durations=audio_master()
 visualparts=[]
 for i,d in enumerate(durations):
  # two edits per sentence; 30 cuts across the final video
  left=math.ceil(d*24*.48)/24
  right=math.ceil(d*24)/24-left
  visualparts.extend([animate(i,0,left),animate(i,1,right)])
 playlist=OUT/'playlist.txt'
 playlist.write_text(''.join("file '"+str(p.resolve())+"'\n" for p in visualparts))
 visual=OUT/'visual.mp4'
 run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(playlist),'-c','copy',str(visual)])
 final=OUT/'IRAN_IRAQ_WAR_ARCHIVAL_EDIT_V2.mp4'
 run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(visual),'-i',str(OUT/'soundtrack.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(final)])
 (OUT/'SOURCES.txt').write_text('SOURCE-001 — Arab Vision: https://x.com/3rab_vision/status/1986782578565579207\nSOURCE-002 — Xumas: https://x.com/xumas_iq/status/1668916665550094339\nFull indexed transcript: https://threadreaderapp.com/thread/1668916665550094339\nRattibha document scans: https://en.rattibha.com/thread/1668916665550094339\nUnited Nations S/RES/479(1980): https://digitallibrary.un.org/record/25614\nUnited Nations S/RES/598(1987): https://digitallibrary.un.org/record/137767\nHistorical map (CC BY-SA 3.0): Nicolas Eynaud https://commons.wikimedia.org/wiki/File:Gu%C3%A8rra_Iran_Iraq_(1980-1988).png\nScans/posts shown for sourced documentary commentary; specific historical claims attributed to the thread author remain subject to verification.\n')
 print('FINAL',final,final.stat().st_size,ffprobe(final),flush=True)
if __name__=='__main__':main()
