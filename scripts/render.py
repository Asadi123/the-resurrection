#!/usr/bin/env python3
"""Render cleared archival stills, shaped Arabic cards, and the approved mix.

No image/video generation service is used. All photographic input comes from
the checked provenance manifest. Text is rasterized with HarfBuzz/FriBidi (RAQM).
FFmpeg commands are preserved as argument arrays in output/ffmpeg-commands.jsonl.
"""
from __future__ import annotations
import argparse
import json
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, features
from common import ROOT, read_json, write_json, run, safe_path, probe

W, H, FPS = 1920, 1080, 30
CARDS = ROOT / "output/cards"
SEGMENTS = ROOT / "output/segments"


def font_path(arabic=False):
    if arabic:
        return str(ROOT / "assets/fonts/NotoNaskhArabic-Regular.ttf")
    family = "Noto Naskh Arabic" if arabic else "DejaVu Serif"
    path = subprocess.check_output(["fc-match", "-f", "%{file}", family], text=True).strip()
    if not Path(path).is_file():
        raise RuntimeError(f"Missing font: {family}")
    return path


def font(size, arabic=False):
    return ImageFont.truetype(font_path(arabic), size, layout_engine=ImageFont.Layout.RAQM)


def text_width(draw, text, fnt, arabic=False):
    return draw.textlength(text, font=fnt, **({"direction": "rtl", "language": "ar"} if arabic else {}))


def wrap(draw, text, fnt, max_width):
    lines, line = [], ""
    for word in text.split():
        candidate = (line + " " + word).strip()
        if line and text_width(draw, candidate, fnt) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + ([line] if line else [])


def centered(draw, text, y, size=65, color="white", arabic=False):
    fnt = font(size, arabic)
    while text_width(draw, text, fnt, arabic) > W - 220:
        size -= 1
        fnt = font(size, arabic)
    draw.text((W // 2, y), text, font=fnt, fill=color, anchor="mm",
              **({"direction": "rtl", "language": "ar"} if arabic else {}))


def generate_cards(cfg):
    if not features.check("raqm"):
        raise RuntimeError("Pillow RAQM support required for correctly joined, RTL Arabic")
    CARDS.mkdir(parents=True, exist_ok=True)
    for i, card in enumerate(cfg["opening"]):
        im = Image.new("RGB", (W, H), "black")
        d = ImageDraw.Draw(im)
        centered(d, card["text"], H // 2, 60)
        im.save(CARDS / f"opening-{i}.png")
    im = Image.new("RGB", (W, H), "black")
    centered(ImageDraw.Draw(im), cfg["final_text"], H // 2, 106, "#d4ae64", True)
    im.save(CARDS / "final.png")
    # Transparent title belongs over authentic Baghdad photography.
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 260, W, 820), fill=(0, 0, 0, 90))
    centered(d, "البعث", 455, 138, "#f3e7ce", True)
    centered(d, "THE RESURRECTION", 625, 68)
    centered(d, cfg["editorial_attribution"], 755, 27, "#e0d6c8")
    im.save(CARDS / "title.png")
    write_json("output/arabic-rendering.json", {
        "text": cfg["final_text"], "direction": "rtl", "language": "ar",
        "raqm": features.check("raqm"), "font": font_path(True),
        "image": "output/cards/final.png", "hold_seconds": 8,
        "note": "RAQM shapes Unicode Arabic; final image also requires visual inspection."
    })


def overlay_image(path, lines, heading=None):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fnt = font(30)
    rendered = []
    for line in lines:
        rendered += wrap(d, line, fnt, W - 220)
    if len(rendered) > 5:
        raise ValueError("Correction too long to read on screen; shorten editorial caption")
    y = H - 95 - 43 * len(rendered)
    d.rectangle((65, y - 60 if heading else y - 18, W - 65, H - 60), fill=(0, 0, 0, 214))
    if heading:
        d.text((100, y - 48), heading, font=font(24), fill="#d4ae64")
    for line in rendered:
        d.text((100, y), line, font=fnt, fill="#f2eee5")
        y += 43
    im.save(path)


def encode_card(card, frames, dst, fade_in=0, fade_out=0):
    seconds = frames / FPS
    vf = [f"fps={FPS}", "setsar=1", "format=yuv420p"]
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={seconds-fade_out}:d={fade_out}")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", card,
         "-vf", ",".join(vf), "-frames:v", frames, "-an", "-c:v", "libx264", "-preset", "fast",
         "-crf", "18", "-threads", "2", "-video_track_timescale", "15360", dst])


def encode_shot(shot, asset, dst):
    frames = round((shot["end"] - shot["start"]) * FPS)
    length = frames / FPS
    z = f"1+0.045*on/{max(1,frames-1)}" if shot.get("motion", "in") == "in" else f"1.045-0.045*on/{max(1,frames-1)}"
    focus_x, focus_y = shot.get("focus", [0.5, 0.5])
    filters = [
        "scale=3840:2160:force_original_aspect_ratio=increase:flags=lanczos",
        f"crop=3840:2160:(iw-ow)*{focus_x}:(ih-oh)*{focus_y}",
        f"zoompan=z='{z}':x='(iw-iw/zoom)*{focus_x}':y='(ih-ih/zoom)*{focus_y}':d={frames}:s={W}x{H}:fps={FPS}",
        "setsar=1", "format=yuv420p"
    ]
    grade = shot.get("grade", "natural")
    if grade == "sepia":
        filters += ["colorchannelmixer=.86:.12:.02:0:.06:.86:.03:0:.02:.10:.78", "eq=saturation=.55:contrast=1.04"]
    elif grade == "golden":
        filters += ["colorbalance=rs=.055:gs=.018:bs=-.04", "eq=saturation=.90:contrast=1.025"]
    inputs = ["-i", safe_path(asset["filename"])]
    prefix = "[0:v]"
    if shot.get("source_crop"):
        x, y, width, height = shot["source_crop"]
        prefix += f"crop={width}:{height}:{x}:{y},"
    if shot.get("layout") == "portrait":
        # The portrait remains proportional and uncropped over a blurred extension
        # of the same cleared photo. No image synthesis or invented detail.
        prefix += "split[pbg][pfg];[pbg]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,gblur=sigma=55[bg];[pfg]scale=3400:1960:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
    filter_complex = f"{prefix}{','.join(filters)}[base];"
    if shot.get("title"):
        inputs += ["-i", CARDS / "title.png"]
        filter_complex += "[base][1:v]overlay=0:0:format=auto[composed];"
    else:
        filter_complex = filter_complex[:-7] + "[composed];"
    filter_complex += f"[composed]fade=t=in:st=0:d=0.35,fade=t=out:st={length-.35}:d=0.35[v]"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex_threads", "1", "-filter_complex", filter_complex,
         "-map", "[v]", "-frames:v", frames, "-an", "-c:v", "libx264", "-preset", "fast",
         "-crf", "18", "-threads", "2", "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", dst])


def documentary_overlays(cfg, manifest):
    """Use explicit speech-relative editorial timing; never invent forced alignment."""
    overlays = []
    by_id = {a["id"]: a for a in manifest["assets"]}
    for n, shot in enumerate(cfg["shots"]):
        a = by_id[shot["asset"]]
        path = CARDS / f"source-{n:02}.png"
        # Visible provenance/date gives archival pictures their actual context.
        text = shot.get("label") or f'{a.get("title", a["id"])} • {a.get("date", "date unknown")}'
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fnt = font(25)
        while text_width(d, text, fnt) > W - 180:
            fnt = font(fnt.size - 1)
        d.rectangle((60, 50, W - 60, 110), fill=(0, 0, 0, 175))
        d.text((90, 67), text, font=fnt, fill="#f2eee5")
        im.save(path)
        overlays.append({"file": path, "start": shot["start"] + .5, "end": min(shot["end"]-.5, shot["start"]+4.5)})
    editorial = read_json("config/editorial-review.json")
    for n, caption in enumerate(editorial.get("timed_captions", [])):
        if caption["start"] < 13 or caption["end"] > 150 or caption["end"] <= caption["start"]:
            raise ValueError("Editorial correction outside narration/archival interval")
        path = CARDS / f"context-{n:02}.png"
        overlay_image(path, [caption["text"]], caption.get("heading", "HISTORICAL CONTEXT"))
        overlays.append({"file": path, "start": caption["start"], "end": caption["end"]})
    return overlays


def compose_master(assembly, overlays, outpath):
    """Decode once; alpha-paste only active text rectangles; encode once.

    Static image inputs in delayed FFmpeg timeline filters can expire before
    their enable interval. Compositing cached rasters over actual decoded RGB
    frames makes both timing and alpha handling explicit and testable.
    """
    prepared = []
    for item in overlays:
        with Image.open(item["file"]) as raster:
            rgba = raster.convert("RGBA")
            bounds = rgba.getbbox()
            if bounds:
                prepared.append((round(item["start"] * FPS), round(item["end"] * FPS),
                                 rgba.crop(bounds), bounds[:2]))
    decode = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "2", "-i", str(assembly),
              "-an", "-filter_threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    encode = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
              "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "pipe:0",
              "-i", str(ROOT / "output/audio_mix.wav"), "-map", "0:v:0", "-map", "1:a:0",
              "-vf", "scale=in_range=full:out_range=limited:out_color_matrix=bt709,format=yuv420p",
              "-frames:v", "4800", "-t", "160", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
              "-threads", "2", "-filter_threads", "1", "-color_range", "tv", "-colorspace", "bt709",
              "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k",
              "-ar", "48000", "-ac", "2", "-metadata", "title=THE RESURRECTION — البعث",
              "-metadata", "copyright=CC BY-SA 4.0; accompanying CREDITS.md and manifests provide source attribution",
              "-movflags", "+faststart", str(outpath)]
    with (ROOT / "output/ffmpeg-commands.jsonl").open("a") as log:
        for args in (decode, encode):
            log.write(json.dumps(args, ensure_ascii=False) + "\n")
    frame_bytes = W * H * 3
    with (ROOT / "output/decode.log").open("w") as dec_log, (ROOT / "output/encode.log").open("w") as enc_log:
        decoder = subprocess.Popen(decode, stdout=subprocess.PIPE, stderr=dec_log)
        encoder = subprocess.Popen(encode, stdin=subprocess.PIPE, stderr=enc_log)
        try:
            for n in range(4800):
                data = decoder.stdout.read(frame_bytes)
                if len(data) != frame_bytes:
                    raise RuntimeError(f"Archival assembly ended early at frame {n}; expected 4800")
                if n == 4799:
                    data = bytes(frame_bytes)
                else:
                    active = [o for o in prepared if o[0] <= n < o[1]]
                    if active:
                        frame = Image.frombytes("RGB", (W, H), data)
                        for _, _, raster, position in active:
                            frame.paste(raster, position, raster)
                        data = frame.tobytes()
                encoder.stdin.write(data)
                if n % 300 == 0:
                    print(f"Composited frame {n}/4800 ({n/FPS:.0f}s)", flush=True)
            encoder.stdin.close()
            if decoder.stdout.read(1):
                raise RuntimeError("Archival assembly contains more than 4800 frames")
            if decoder.wait() or encoder.wait():
                raise RuntimeError("FFmpeg composition failed; inspect output/decode.log and encode.log")
        finally:
            for proc in (decoder, encoder):
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()


def render(cfg, output, composite_only=False):
    # Enforce gates even when invoked outside CI.
    subprocess.run(["python", str(ROOT / "scripts/preflight.py")], check=True, cwd=ROOT)
    generate_cards(cfg)
    SEGMENTS.mkdir(parents=True, exist_ok=True)
    manifest = read_json("research/asset-manifest.json")
    assets = {a["id"]: a for a in manifest["assets"]}
    assembly = ROOT / "output/assembly.mp4"
    if composite_only:
        previous = read_json("output/render.json")
        if previous.get("timeline") != cfg or float(probe(assembly)["format"]["duration"]) != 160:
            raise ValueError("Cannot reuse assembly: story/timing changed or assembly duration is invalid")
        overlays = documentary_overlays(cfg, manifest)
        destination = safe_path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        compose_master(assembly, overlays, destination)
        write_json("output/render.json", {"output": str(destination.relative_to(ROOT)), "timeline": cfg,
                    "composition": "Decoded archival RGB frames with active cached PNG alpha masks",
                    "overlays": [{**o, "file": str(o["file"].relative_to(ROOT))} for o in overlays]})
        return
    segments = []
    for i, item in enumerate(cfg["opening"]):
        dst = SEGMENTS / f"{len(segments):03}.mp4"
        encode_card(CARDS / f"opening-{i}.png", round((item["end"]-item["start"])*FPS), dst,
                    fade_in=.25 if i else 0, fade_out=.25 if i else 0)
        segments.append(dst)
    for shot in cfg["shots"]:
        dst = SEGMENTS / f"{len(segments):03}.mp4"
        encode_shot(shot, assets[shot["asset"]], dst)
        segments.append(dst)
    for image, frames, fade_out in [("opening-0.png", 30, 0), ("final.png", 240, 0), ("final.png", 30, .967)]:
        dst = SEGMENTS / f"{len(segments):03}.mp4"
        encode_card(CARDS / image, frames, dst, fade_out=fade_out)
        segments.append(dst)
    concat = ROOT / "output/concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments))
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", concat,
         "-c", "copy", assembly])
    # All overlays are fixed text; content and enable intervals are recorded for inspection.
    overlays = documentary_overlays(cfg, manifest)
    outpath = safe_path(output)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    compose_master(assembly, overlays, outpath)
    write_json("output/render.json", {"output": str(outpath.relative_to(ROOT)), "timeline": cfg,
                                        "overlays": [{**o, "file": str(o["file"].relative_to(ROOT))} for o in overlays]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/the-resurrection.mp4")
    parser.add_argument("--cards-only", action="store_true")
    parser.add_argument("--composite-only", action="store_true", help="Reuse a completed assembly only when its recorded timeline matches")
    args = parser.parse_args()
    cfg = read_json("config/film.json")
    if args.cards_only:
        generate_cards(cfg)
    else:
        render(cfg, args.output, args.composite_only)


if __name__ == "__main__":
    main()
