#!/usr/bin/env python3
"""New narrator: CPU-native neural speech, not the V2 voice or previous Kokoro/Edge audio.

Draft narration is flagged as speech-synthesis until human-listened approval.
"""
import json, math, os
from pathlib import Path
import numpy as np
from pocket_tts import TTSModel
import soundfile as sf

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"audio"
OUT.mkdir(exist_ok=True)
DATA=json.loads((ROOT/"production.json").read_text())
VOICE=os.environ.get("DOCUMENTARY_VOICE","peter_yearsley")
model=TTSModel.load_model()
state=model.get_state_for_audio_prompt(VOICE)
sr=model.sample_rate
narrations=[]
timings=[]
offset=0.0
for i,beat in enumerate(DATA["beats"]):
    dest=OUT/f"narration-{i+1:02}.wav"
    if dest.exists() and dest.stat().st_size>5000:
        y,existing_sr=sf.read(dest,dtype="float32")
        if existing_sr != sr:raise ValueError("Existing narration sample rate invalid")
    else:
        raw=model.generate_audio(state,beat["text"])
        y=raw.detach().float().cpu().numpy().reshape(-1)
        if not np.all(np.isfinite(y)) or np.max(np.abs(y))<0.008:
            raise RuntimeError(f"TTS generated invalid/silent narration beat {i+1}")
        y=np.clip(y,-0.97,0.97).astype("float32")
        sf.write(dest,y,sr)
    # A sentence-ending beat gets a real editorial breath, not a pitch-shift.
    pause=0.85 if i in (0,3,6,9,12) else 0.43
    pad=np.zeros(int(sr*pause),dtype="float32")
    segment=np.concatenate([y,pad])
    start=offset
    offset+=len(segment)/sr
    if not 3.0 < len(y)/sr < 50:
        raise RuntimeError(f"Unexpected neural speech duration for scene {i+1}: {len(y)/sr:.1f}s")
    narrations.append(segment)
    timings.append({"index":i+1,"start":round(start,4),"end":round(offset,4),
        "speech_duration":round(len(y)/sr,4),"silent_tail":pause,
        "voice":VOICE,"heading":beat["heading"],"spoken_text":beat["text"]})
    print("NARRATED",i+1,"of",len(DATA["beats"]),round(len(y)/sr,2),"s",flush=True)
combined=np.concatenate(narrations)
if not 120 < len(combined)/sr < 600:
    raise RuntimeError("Feature-length narration failed sanity check")
sf.write(OUT/"narration.wav",combined,sr,subtype="PCM_16")
(OUT/"timings.json").write_text(json.dumps({"engine":"Kyutai Pocket TTS", "voice":VOICE,
    "sample_rate":sr,"duration":len(combined)/sr,"status":"SYNTHETIC_NEEDS_HUMAN_AUDIO_REVIEW",
    "timings":timings},indent=2,ensure_ascii=False))
print("NARRATION MASTER",len(combined)/sr,"s",flush=True)
