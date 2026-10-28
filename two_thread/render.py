"""Render only source-linked media from the two authorized Thread Reader collections.

The source image/video is always contained, never cropped or replaced. Text and
verified highlights are editorial overlays. Attached video sound is retained;
there is no generated speech, music, or synthetic historical imagery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
THREADS = {"1668916665550094339": 28, "1986782578565579207": 44}
W, H, FPS = 1920, 1080, 30
AREA = (40, 80, 1840, 800)
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


class SourceError(ValueError):
    """The edit cannot be proven to use only complete, acquired sources."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def object_digest(value: object) -> str:
    """Bind a report to the entire canonical input object, including metadata."""
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inside(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SourceError("Asset path must be a nonempty string")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise SourceError("Asset path escapes the repository")
    return path


def number(value, label: str, *, positive=False) -> float:
    if isinstance(value, bool):
        raise SourceError(f"{label} is not a number")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise SourceError(f"{label} is not a number") from None
    if not math.isfinite(value) or value < 0 or (positive and value <= 0):
        raise SourceError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def load_assets(manifest: dict, root: Path = ROOT) -> dict:
    """Prove acquisition provenance before any encoder is started."""
    if manifest.get("complete") is not True or manifest.get("missing"):
        raise SourceError("Incomplete source acquisition; rendering is blocked")
    if not isinstance(manifest.get("threads"), list):
        raise SourceError("Manifest has no source threads")
    ids = [str(t.get("id")) for t in manifest["threads"]]
    if len(ids) != 2 or set(ids) != set(THREADS):
        raise SourceError("Both authorized source threads, and only those threads, are required")
    from two_thread.acquire import inspect_media, verify_collection_sources
    try:
        verify_collection_sources(root, manifest)
    except (ValueError, KeyError, OSError) as exc:
        raise SourceError(f"Raw source proof failed: {exc}") from exc
    assets = {}
    for thread in manifest["threads"]:
        tid = str(thread["id"])
        if thread.get("url") != f"https://threadreaderapp.com/thread/{tid}.html":
            raise SourceError("Thread provenance URL does not match its authorized ID")
        posts = thread.get("posts", [])
        if len(posts) != THREADS[tid] or len({str(p["id"]) for p in posts}) != THREADS[tid]:
            raise SourceError(f"Incomplete post collection for {tid}")
        for post in posts:
            for asset in post.get("attachments", []):
                aid = asset.get("id")
                if not isinstance(aid, str) or not aid or aid in assets:
                    raise SourceError("Duplicate or missing attachment identity")
                if asset.get("kind") not in {"image", "video"}:
                    raise SourceError("Only actual image/video attachments may appear in an edit")
                source = urlparse(asset.get("source_url", ""))
                if source.scheme != "https" or source.hostname not in {"pbs.twimg.com", "video.twimg.com"} or source.username or source.password:
                    raise SourceError("Attachment URL is outside the two threads' media hosts")
                path = inside(root, asset.get("local_path"))
                allowed = (root / "two_thread" / "assets" / tid).resolve()
                if not path.is_relative_to(allowed):
                    raise SourceError("Legacy or unrelated local assets are prohibited")
                expected = asset.get("sha256", "")
                if not re.fullmatch(r"[0-9a-f]{64}", str(expected)) or not path.is_file() or sha256(path) != expected:
                    raise SourceError(f"Missing or changed attachment: {aid}")
                width = number(asset.get("width"), "image width", positive=True)
                height = number(asset.get("height"), "image height", positive=True)
                if width > 40000 or height > 40000:
                    raise SourceError("Unsupported attachment dimensions")
                actual = inspect_media(path, asset["kind"])
                if (actual["width"], actual["height"], actual["has_audio"]) != (asset["width"], asset["height"], asset.get("has_audio")):
                    raise SourceError("Attachment metadata does not match its actual media bytes")
                if asset["kind"] == "video":
                    number(asset.get("duration"), "recording duration", positive=True)
                    if abs(float(actual["duration"]) - float(asset["duration"])) > 0.01:
                        raise SourceError("Recording duration does not match its actual media bytes")
                assets[aid] = dict(asset, path=path, thread_id=tid, ordinal=post["ordinal"], tweet_url=post["tweet_url"], post_text=post["text"])
    if not assets:
        raise SourceError("No actual attachments were acquired")
    return assets


def validate_edit(edit: dict, assets: dict) -> list:
    segments = edit.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SourceError("The edit must contain actual source footage")
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise SourceError("Each edit segment must identify an actual source attachment")
        if any(k in segment for k in ("crop", "zoom", "narration", "audio_path", "generated_image", "background_image")):
            raise SourceError("Cropping, synthetic images and unrelated audio are prohibited")
        aid = segment.get("asset_id")
        if aid not in assets:
            raise SourceError(f"Unknown source attachment in segment {index + 1}: {aid}")
        asset = assets[aid]
        duration = number(segment.get("duration"), "segment duration", positive=True)
        start = number(segment.get("clip_start", 0), "recording in-point")
        if duration < 1 / FPS:
            raise SourceError("Segment must contain at least one full video frame")
        if asset["kind"] == "image" and start != 0:
            raise SourceError("A document cannot have a recording in-point")
        if asset["kind"] == "video" and start + duration > float(asset["duration"]) + 0.001:
            raise SourceError("Recording excerpt extends beyond the actual attachment")
        highlight = segment.get("highlight")
        if highlight:
            if asset["kind"] != "image" or highlight.get("image_sha256") != asset["sha256"]:
                raise SourceError("Highlight must identify the exact acquired image")
            if not isinstance(highlight.get("quote"), str) or not highlight["quote"].strip():
                raise SourceError("Highlight requires a verbatim passage")
            if not (highlight.get("verified") is True or highlight.get("verified_by")):
                raise SourceError("Unreviewed OCR cannot authorize a highlighted passage")
            rect = highlight.get("rect")
            if not isinstance(rect, list) or len(rect) != 4:
                raise SourceError("Highlight rectangle must contain x, y, width and height")
            x, y, rw, rh = [number(v, "highlight coordinate") for v in rect]
            if rw <= 0 or rh <= 0 or x + rw > asset["width"] or y + rh > asset["height"]:
                raise SourceError("Highlight falls outside the uncropped source image")
        for key in ("caption", "kicker"):
            if not isinstance(segment.get(key, ""), str):
                raise SourceError("Editorial overlay text must be a string")
            if len(segment.get(key, "")) > (420 if key == "caption" else 110):
                raise SourceError("Editorial overlay is too long to read")
    return segments


def placement(width: int, height: int) -> tuple[int, int, int, int]:
    x, y, aw, ah = AREA
    factor = min(aw / width, ah / height)
    tw = max(2, int(width * factor) // 2 * 2)
    th = max(2, int(height * factor) // 2 * 2)
    return x + (aw - tw) // 2, y + (ah - th) // 2, tw, th


def video_filter(asset: dict) -> str:
    x, y, width, height = placement(int(asset["width"]), int(asset["height"]))
    # Explicit contain-and-pad, never crop. This is also used for highlight geometry.
    return f"scale={width}:{height}:flags=lanczos:out_range=tv:out_color_matrix=bt709,pad={W}:{H}:{x}:{y}:color=0x101314,setsar=1,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,fps={FPS}"


def font(size: int, bold=False):
    file = BOLD if bold else FONT
    if not file.is_file():
        raise SourceError("DejaVu Sans is required; install fonts-dejavu-core")
    return ImageFont.truetype(str(file), size)


def wrapped(draw, text: str, ft, max_width: int) -> list[str]:
    lines = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=ft) > max_width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines


def overlay(asset: dict, segment: dict, target: Path, preview=False):
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = (229, 182, 97, 255)
    draw.rectangle((0, 0, W, 63), fill=(16, 19, 20, 255))
    draw.rectangle((40, 23, 48, 47), fill=accent)
    heading = segment.get("kicker", "SOURCE EXAMINATION")
    if preview:
        heading = "PIPELINE PREVIEW — " + heading
    draw.text((65, 20), heading.upper(), font=font(25, True), fill=(244, 242, 236, 255))
    draw.rectangle((0, 897, W, H), fill=(16, 19, 20, 255))
    draw.line((40, 903, 1880, 903), fill=accent, width=2)
    caption = segment.get("caption", "")
    ft = font(34, True)
    lines = wrapped(draw, caption, ft, 1820)
    if len(lines) > 2:
        ft = font(29, True)
        lines = wrapped(draw, caption, ft, 1820)
    if len(lines) > 3:
        raise SourceError("Caption cannot be displayed legibly in the evidence footer")
    for i, line in enumerate(lines):
        draw.text((40, 918 + i * 37), line, font=ft, fill=(244, 242, 236, 255))
    label = f"THREAD {'01' if asset['thread_id'] == '1668916665550094339' else '02'} / POST {asset['ordinal']:02d} / {asset['kind'].upper()} / {asset['id']}"
    draw.text((40, 1043), label, font=font(19), fill=(163, 177, 179, 255))
    # Precise source URL is additionally recorded in the edit decision list and report.
    url = asset["tweet_url"]
    if draw.textlength(url, font=font(18)) < 900:
        draw.text((1875 - draw.textlength(url, font=font(18)), 1043), url, font=font(18), fill=(163, 177, 179, 255))
    highlight = segment.get("highlight")
    if highlight:
        px, py, sw, sh = placement(int(asset["width"]), int(asset["height"]))
        x, y, rw, rh = highlight["rect"]
        box = (int(px + x * sw / asset["width"]), int(py + y * sh / asset["height"]), int(px + (x + rw) * sw / asset["width"]), int(py + (y + rh) * sh / asset["height"]))
        draw.rectangle(box, fill=(255, 219, 65, 55), outline=(255, 219, 65, 220), width=3)
    image.save(target)


def command(args, log: Path):
    argv = [str(x) for x in args]
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(argv, ensure_ascii=False) + "\n")
    subprocess.run(argv, check=True, stdout=subprocess.DEVNULL)


def probe(path: Path) -> dict:
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], text=True))


def validate_output(path: Path, expected_duration: float) -> dict:
    metadata = probe(path)
    streams = metadata.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    if (video.get("width"), video.get("height"), video.get("codec_name"), video.get("pix_fmt"), video.get("sample_aspect_ratio"), video.get("avg_frame_rate")) != (W, H, "h264", "yuv420p", "1:1", "30/1"):
        raise SourceError("Encoded master failed 1080p H.264 square-pixel validation")
    if (audio.get("codec_name"), audio.get("sample_rate"), audio.get("channels")) != ("aac", "48000", 2):
        raise SourceError("Encoded master failed AAC stereo validation")
    duration = number(metadata.get("format", {}).get("duration"), "output duration", positive=True)
    if abs(duration - expected_duration) > 0.2:
        raise SourceError(f"Encoded duration {duration} differs from edit duration {expected_duration}")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL)
    return metadata


def render(manifest: dict, edit: dict, output: Path, workdir: Path, *, root=ROOT, crf=20, limit=None) -> dict:
    assets = load_assets(manifest, root)
    segments = validate_edit(edit, assets)
    preview = limit is not None
    if preview:
        if not isinstance(limit, int) or limit <= 0:
            raise SourceError("Preview segment limit must be a positive integer")
        segments = segments[:limit]
        if "preview" not in output.stem.lower():
            raise SourceError("A limited smoke test must have 'preview' in its output filename")
    if not isinstance(crf, int) or not 14 <= crf <= 35:
        raise SourceError("CRF must be between 14 and 35")
    media_root = (root / "two_thread/assets").resolve()
    if output.resolve().is_relative_to(media_root) or workdir.resolve().is_relative_to(media_root):
        raise SourceError("Rendering cannot overwrite acquired source media")
    workdir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    log = workdir / "ffmpeg-commands.jsonl"
    log.write_text("", encoding="utf-8")
    receipts, paths, thumbs = [], [], []
    expected = 0.0
    for i, segment in enumerate(segments, 1):
        asset = assets[segment["asset_id"]]
        duration = round(float(segment["duration"]) * FPS) / FPS
        overlay_path, target = workdir / f"{i:03d}-overlay.png", workdir / f"{i:03d}.mov"
        overlay(asset, segment, overlay_path, preview)
        args = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y", "-threads", "2", "-filter_complex_threads", "1"]
        if asset["kind"] == "image":
            args += ["-loop", "1", "-framerate", str(FPS), "-i", asset["path"]]
        else:
            args += ["-ss", str(segment.get("clip_start", 0)), "-i", asset["path"]]
        args += ["-loop", "1", "-framerate", str(FPS), "-i", overlay_path]
        has_audio = asset["kind"] == "video" and asset.get("has_audio") is True
        if not has_audio:
            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        args += ["-filter_complex", f"[0:v]{video_filter(asset)}[source];[source][1:v]overlay=0:0:shortest=1,format=yuv420p[v]", "-map", "[v]", "-map", "0:a:0" if has_audio else "2:a:0", "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-threads", "2", "-r", str(FPS), "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-af", f"aresample=48000,apad,afade=t=in:st=0:d=0.06,afade=t=out:st={max(0, duration-0.08)}:d=0.08", "-movflags", "+faststart", target]
        command(args, log)
        thumbnail = workdir / f"{i:03d}-frame.jpg"
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", str(min(duration / 2, 2)), "-i", target, "-frames:v", "1", "-vf", "scale=640:360", thumbnail], log)
        thumbs.append(thumbnail)
        paths.append(target)
        receipts.append({"segment": i, "asset_id": asset["id"], "source_url": asset["source_url"], "tweet_url": asset["tweet_url"], "asset_sha256": asset["sha256"], "start_in_master": round(expected, 6), "duration": duration, "clip_start": segment.get("clip_start", 0), "original_audio": has_audio, "caption": segment.get("caption", ""), "highlight": segment.get("highlight"), "entire_source_contained": True})
        expected += duration
    listing = workdir / "segments.txt"
    # Segment filenames are generated internally, with no user-controlled shell syntax.
    listing.write_text("".join(f"file '{p.name}'\n" for p in paths), encoding="utf-8")
    staging = output.with_name(output.stem + ".rendering" + output.suffix)
    command(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-af", "aresample=async=1:first_pts=0", "-movflags", "+faststart", staging], log)
    metadata = validate_output(staging, expected)
    staging.replace(output)
    columns = 3
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (640 * columns, 390 * rows), (16, 19, 20))
    draw = ImageDraw.Draw(sheet)
    for i, thumb in enumerate(thumbs):
        x, y = (i % columns) * 640, (i // columns) * 390
        with Image.open(thumb) as frame:
            sheet.paste(frame.convert("RGB"), (x, y))
        draw.text((x + 10, y + 364), f"{i + 1:02d} · {receipts[i]['asset_id']}", fill="white", font=font(17))
    contact = output.with_suffix(".contact-sheet.jpg")
    sheet.save(contact, quality=92)
    report = {"edit_sha256": object_digest(edit), "collection_sha256": object_digest(manifest), "status": "PREVIEW_NOT_FINAL" if preview else "RENDERED_VALIDATED", "title": edit.get("title"), "perspective": edit.get("perspective"), "exclusive_source_threads": list(THREADS), "all_source_assets_verified": len(assets), "segment_count": len(receipts), "expected_duration_seconds": round(expected, 6), "duration_seconds": float(metadata["format"]["duration"]), "resolution": [W, H], "fps": FPS, "sha256": sha256(output), "output": str(output), "contact_sheet": str(contact), "synthetic_narration": False, "synthetic_historical_images": False, "unrelated_music": False, "decode_validation": "PASS", "segments": receipts}
    output.with_suffix(".render-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "two_thread/collection.json")
    parser.add_argument("--edit", type=Path, default=ROOT / "two_thread/edit.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output/two-thread-film.mp4")
    parser.add_argument("--workdir", type=Path, default=ROOT / "output/two-thread-render")
    parser.add_argument("--crf", type=int, default=20)
    parser.add_argument("--limit", type=int, help="Smoke test only; output filename must contain 'preview'")
    args = parser.parse_args()
    try:
        report = render(json.loads(args.manifest.read_text()), json.loads(args.edit.read_text()), args.output.resolve(), args.workdir.resolve(), crf=args.crf, limit=args.limit)
    except (SourceError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        parser.exit(2, f"RENDER BLOCKED: {exc}\n")
    print(json.dumps({k: report[k] for k in ("status", "output", "duration_seconds", "sha256", "segment_count")}, indent=2))


if __name__ == "__main__":
    main()
