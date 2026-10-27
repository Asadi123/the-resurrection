#!/usr/bin/env python3
"""Non-generative documentary editor: real archive + full-page UN evidence + original graphics.

No narration or provenance = no deliverable. This is a new film, separate from THE RESURRECTION.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
MEDIA = ROOT / "assets" / "original"
OUT.mkdir(parents=True, exist_ok=True)
W, H, FPS = 1920, 1080, 30
NAVY, WHITE, RED, SOFT = "#111419", "#f3f0e9", "#b73237", "#aaa9a7"
NARR = ROOT / "assets" / "narration.mp3"
MUSIC = ROOT.parent / "assets" / "audio" / "oud-jordan.mp3"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Each shot is an intentional edit of documented material. Repetition means a
# DIFFERENT moment of a genuine recording, not a looped/sliding source card.
SHOTS = [
    ("photo", "tehran-airport-1980", 7, "22 SEPTEMBER 1980", "The Iraqi invasion of Iran", 0),
    ("video", "abadan-1980", 7, "1980 — ABADAN", "Archival footage · wartime record", 12),
    ("graphic", None, 8, "1975", "The Algiers Agreement · contested frontier", 0),
    ("video", "abadan-1980", 7, "THE SHATT AL-ARAB", "Strategic waterway between Iraq and Iran", 37),
    ("graphic", None, 7, "1979", "Revolution in Iran · political tensions rise", 0),
    ("document", "un-sg-1980", 10, "SEPTEMBER 1980", "UN Secretary-General's report · 30 Sep 1980", 0),
    ("document", "un-iraq-letter-1983", 8, "IRAQ'S POSITION", "Iraqi letter of 10 June 1983 · retrospective claim", 0),
    ("document", "un-iran-letter-1980", 8, "IRAN'S POSITION", "Iranian letter of 1 October 1980 · competing claim", 0),
    ("video", "abadan-1980", 8, "EARLY SEPTEMBER", "Competing accusations of border violations", 74),
    ("document", "un-479-1980", 9, "RESOLUTION 479", "UN Security Council · 28 Sep 1980", 0),
    ("video", "abadan-1980", 8, "THE FRONT", "Siege of Abadan · actual period footage", 115),
    ("video", "abadan-1980", 8, "THE FRONT", "No synthetic battlefield imagery", 165),
    ("graphic", None, 8, "1982", "Iran recaptures Khorramshahr · 24 May", 0),
    ("video", "abadan-1980", 7, "1980 ARCHIVE", "Earlier war footage — not depicted as 1982", 195),
    ("graphic", None, 8, "THE WAR EXPANDS", "Long-range strikes · cities · shipping", 0),
    ("video", "andimeshk-1986", 9, "25 NOVEMBER 1986", "Iranian archival recording · Andimeshk", 5),
    ("video", "andimeshk-1986", 9, "CIVILIAN CONSEQUENCES", "Wartime archival record · Andimeshk", 35),
    ("video", "khamenei-1986", 8, "1986 — IRAN", "Ali Khamenei · authentic televised address", 22),
    ("graphic", None, 7, "1987", "Diplomatic pressure for a ceasefire", 0),
    ("document", "un-598-1987", 11, "RESOLUTION 598", "UN Security Council · 20 July 1987", 0),
    ("video", "andimeshk-1986", 7, "1988", "Earlier footage · not represented as 1988", 61),
    ("graphic", None, 9, "JULY 1988", "Iran formally accepts Resolution 598", 0),
    ("document", "un-598-1987", 9, "AUGUST 1988", "Ceasefire · UN-supervised implementation", 0),
    ("video", "abadan-1980", 7, "EIGHT YEARS", "Historical recordings · authentic, not reenacted", 245),
    ("graphic", None, 8, "1980—1988", "What the documentary record can establish", 0),
]

def run(args):
    cmd = [str(x) for x in args]
    subprocess.run(cmd, check=True)

def probe_duration(path):
    p = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(p.decode().strip())

def font(size):
    return ImageFont.truetype(FONT, size)

def fitted(source, box):
    # Pillow contain preserves every boundary, page number, and original aspect ratio.
    return ImageOps.contain(source.convert("RGB"), box, Image.Resampling.LANCZOS)

def write_text(draw, pos, words, font_size, color=WHITE, max_width=1600):
    f = font(font_size)
    lines, current = [], ""
    for word in words.split():
        candidate = (current + " " + word).strip()
        if draw.textbbox((0,0), candidate, font=f)[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    y = pos[1]
    for line in lines:
        draw.text((pos[0], y), line, font=f, fill=color)
        y += font_size * 1.45
    return y

def portrait_source(asset_path):
    with Image.open(asset_path) as source:
        page = source.copy()
    canvas = Image.new("RGB", (W,H), NAVY)
    # Dedicated matte; no crop, extension, stretch, blur or synthesized pixels.
    img = fitted(page, (1510,880))
    canvas.paste(img, ((W-img.width)//2, 72))
    return canvas

def document_source(asset_path, title, subtitle):
    doc = fitz.open(asset_path)
    if not doc.page_count:
        raise ValueError("Source document has no pages")
    page_index = 0
    # Preserve an entire original printed page from each bound UN volume.
    target = None
    if "un-iraq-letter-1983" in asset_path.name:
        target = "S/15826"
    elif "un-iran-letter-1980" in asset_path.name:
        target = "S/14206"
    if target:
        hits = [i for i in range(doc.page_count) if target in doc[i].get_text()]
        if not hits:
            raise RuntimeError(f"Original UN letter {target} was not located in the source PDF")
        page_index = hits[0]
    pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
    page = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    canvas = Image.new("RGB", (W,H), NAVY)
    img = fitted(page, (820,960))
    canvas.paste(img, (70+(820-img.width)//2, 56+(960-img.height)//2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((985,155,994,890), fill=RED)
    write_text(draw, (1040,160), title, 59, max_width=765)
    write_text(draw, (1040,360), subtitle, 36, SOFT, max_width=760)
    write_text(draw, (1040,730), "ORIGINAL DOCUMENT", 25, SOFT)
    write_text(draw, (1040,780), "Complete original page shown at left", 25, SOFT)
    return canvas

def infographic(title, subtitle, index):
    canvas = Image.new("RGB", (W,H), NAVY)
    d = ImageDraw.Draw(canvas)
    d.line((130,505,1790,505), fill="#494747", width=5)
    # Dots are chronological editorial markers, not geospatial military positions.
    for i, yr in enumerate(["1975","1979","1980","1982","1986","1987","1988"]):
        x = 175 + i*260
        d.ellipse((x-10,495,x+10,515), fill=RED if yr in title else "#7b7d80")
        d.text((x-43,538), yr, font=font(27), fill=SOFT)
    write_text(d, (135,175), title, 90, max_width=1620)
    write_text(d, (135,335), subtitle, 44, SOFT, max_width=1600)
    d.rectangle((135,815,675,823), fill=RED)
    return canvas

def subtitle_overlay(title, subtitle):
    overlay = Image.new("RGBA", (W,H), (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    # Small corner lower-third; no huge panels obscuring historical evidence.
    d.rounded_rectangle((70,867,960,1021), radius=10, fill=(9,12,16,210))
    d.rectangle((70,870,79,1008), fill=RED)
    write_text(d, (105,887), title, 39, max_width=805)
    write_text(d, (105,954), subtitle, 23, color="#d3d4d7", max_width=805)
    return overlay

def encode_png(image, output, frames, overlay=None):
    png = output.with_suffix(".png")
    image.save(png)
    vf = f"scale={W}:{H},setsar=1,format=yuv420p"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", FPS, "-i", png,
        "-frames:v", frames, "-vf", vf, "-r", FPS, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", 19,
        "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", output])

def encode_video(source, overlay, output, seconds, start):
    png = output.with_suffix(".png")
    overlay.save(png)
    frames = round(seconds*FPS)
    filt = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x111419,"
        "setsar=1,format=yuv420p[archive];"
        "[1:v]format=rgba[caption];"
        "[archive][caption]overlay=0:0:format=auto,format=yuv420p[v]")
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss",start,"-i",source,"-loop","1","-i",png,
        "-filter_complex",filt,"-map","[v]","-frames:v",frames,
        "-r",FPS,"-an","-c:v","libx264","-preset","veryfast","-crf",19,
        "-pix_fmt","yuv420p","-video_track_timescale","15360",output])

def main():
    audit_path=ROOT/"source-audit.json"
    if not audit_path.is_file():
        raise RuntimeError("Source acquisition audit missing")
    audit=json.loads(audit_path.read_text())
    if audit.get("status")!="ready":
        raise RuntimeError("Source audit blocked; never use substitute footage")
    byid={a["id"]:ROOT/a["local_path"] for a in audit["original_assets"]}
    if not NARR.is_file() or NARR.stat().st_size < 20000:
        raise RuntimeError("HIGH-QUALITY HUMAN-SOUNDING NARRATION REQUIRED: missing assets/narration.mp3. Old synthetic narration must not be reused.")
    if not MUSIC.is_file():
        raise RuntimeError("Licensed original musical score missing")
    duration=probe_duration(NARR)
    if not 100 < duration < 360:
        raise RuntimeError(f"Narration length {duration} outside documented 100–360 second range")
    weights=[s[2] for s in SHOTS]
    count=round(duration*FPS)
    exact=[round(count*sum(weights[:i])/sum(weights)) for i in range(len(weights)+1)]
    segments=[]
    for i,(kind, asset_id, weight, title, subtitle, offset) in enumerate(SHOTS):
        frames=exact[i+1]-exact[i]
        length=frames/FPS
        path=OUT/f"shot-{i:02d}.mp4"
        if kind=="video":
            source=byid[asset_id]
            overlay=subtitle_overlay(title,subtitle)
            available=probe_duration(source)
            if offset+length>available:
                raise RuntimeError(f"Archive extract would exceed authentic source: {asset_id}")
            encode_video(source,overlay,path,length,offset)
        elif kind=="photo":
            canvas=portrait_source(byid[asset_id])
            d=ImageDraw.Draw(canvas)
            d.rectangle((0,950,W,H),fill=NAVY)
            write_text(d,(100,968),title+"  |  "+subtitle,33,max_width=1760)
            encode_png(canvas,path,frames)
        elif kind=="document":
            encode_png(document_source(byid[asset_id],title,subtitle),path,frames)
        else:
            encode_png(infographic(title,subtitle,i),path,frames)
        segments.append(path)
        print(f"SHOT {i+1}/{len(SHOTS)} {kind} {length:.2f}s",flush=True)
    playlist=OUT/"edit-concat.txt"
    playlist.write_text("".join("file '"+p.resolve().as_posix()+"'\\n" for p in segments))
    assembly=OUT/"archive-assembly.mp4"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","concat","-safe","0","-i",playlist,"-c","copy",assembly])
    target=OUT/"iran-iraq-war.mp4"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-i",assembly,"-i",NARR,"-stream_loop","-1","-i",MUSIC,
        "-filter_complex","[1:a]aresample=48000,loudnorm=I=-17:TP=-2:LRA=9[voice];"
        "[2:a]aresample=48000,volume=0.055[bed];"
        "[voice][bed]amix=inputs=2:duration=first:dropout_transition=1[a]",
        "-map","0:v:0","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k",
        "-ar","48000","-ac","2","-t",str(count/FPS),"-movflags","+faststart",
        "-metadata","title=Iran–Iraq War | Archival Documentary",
        target])
    actual=probe_duration(target)
    if abs(actual-count/FPS)>0.75:
        raise RuntimeError(f"Unexpected output duration {actual} vs {count/FPS}")
    verification={"status":"rendered_not_human_approved","output":str(target.relative_to(ROOT)),
      "duration":actual,"fps":FPS,"resolution":[W,H],"shots":len(segments),
      "all_originals_proportionally_contained":True,
      "open_items":["Human QC of complete film","Natural narration pronunciation and emotion",
      "Source image/document edge review","Historical editorial and rights approval",
      "Check no voice/music clipping or timing errors"]}
    (OUT/"validation.json").write_text(json.dumps(verification,indent=2))
    print("RENDERED, PENDING HUMAN VISUAL AND AUDIO QA:",target,flush=True)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("BLOCKED:",type(e).__name__,str(e),file=sys.stderr)
        raise
