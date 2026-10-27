#!/usr/bin/env python3
"""Validate a finished master, including decoded media and the Arabic end card.

This program never treats the existence of an MP4 as publication approval.
Editorial and source clearance are checked again by scripts/preflight.py.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]


def probe_media(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_format", "-show_streams",
         "-of", "json", str(path)], check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


def _duration_ok(value, target=160.0, tolerance=0.001):
    try:
        parsed = float(value)
        return math.isfinite(parsed) and abs(parsed - target) <= tolerance
    except (TypeError, ValueError):
        return False


def metadata_errors(info: dict) -> list[str]:
    """Pure structural checks, with no rounding away missing frames or streams."""
    errors = []
    streams = info.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if len(video) != 1:
        errors.append(f"Expected exactly one video stream; found {len(video)}")
    if len(audio) != 1:
        errors.append(f"Expected exactly one audio stream; found {len(audio)}")
    if not _duration_ok(info.get("format", {}).get("duration")):
        errors.append("Container duration must be 160.000 seconds (tolerance 0.001)")
    if video:
        v = video[0]
        if v.get("codec_name") != "h264":
            errors.append("Video codec must be H.264")
        if (v.get("width"), v.get("height")) != (1920, 1080):
            errors.append("Video resolution must be 1920 × 1080")
        if v.get("sample_aspect_ratio") != "1:1":
            errors.append("Video must use square pixels (SAR 1:1)")
        for field in ("avg_frame_rate", "r_frame_rate"):
            try:
                valid = Fraction(v.get(field, "0/1")) == 30
            except (ValueError, ZeroDivisionError, TypeError):
                valid = False
            if not valid:
                errors.append(f"{field} must be exactly 30 FPS")
        if str(v.get("nb_read_frames")) != "4800":
            errors.append("Decoded video must contain exactly 4800 frames")
        if not _duration_ok(v.get("duration")):
            errors.append("Video stream duration must be 160.000 seconds")
        if v.get("pix_fmt") != "yuv420p":
            errors.append("Video pixel format must be yuv420p for phone compatibility")
    if audio:
        a = audio[0]
        if a.get("codec_name") != "aac":
            errors.append("Audio codec must be AAC")
        if not _duration_ok(a.get("duration"), tolerance=0.025):
            errors.append("Audio stream duration must be 160 seconds (tolerance 0.025)")
        if int(a.get("channels") or 0) < 1:
            errors.append("Audio stream has no channels")
        if int(a.get("sample_rate") or 0) < 44100:
            errors.append("Audio sampling rate must be at least 44100 Hz")
    return errors


def extract_frame(video: Path, frame_number: int, output: Path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", f"select=eq(n\\,{frame_number})", "-frames:v", "1", str(output)],
        check=True, capture_output=True, text=True,
    )


def image_mae(left: Image.Image, right: Image.Image) -> float:
    if left.size != right.size:
        raise ValueError("Image dimensions differ")
    return sum(ImageStat.Stat(ImageChops.difference(left.convert("RGB"), right.convert("RGB"))).mean) / 3


def check_encoded_overlays(path: Path, root: Path, result: dict):
    """Check actual encoded glyphs and their dark panels, not just render intent."""
    render_record = root / "output/render.json"
    if not render_record.is_file():
        result["errors"].append("Missing output/render.json; encoded corrections cannot be verified")
        return
    overlays = json.loads(render_record.read_text())["overlays"]
    if not overlays:
        result["errors"].append("No historical correction/source overlays recorded")
        return
    samples = []
    for overlay in overlays:
        frame = round((overlay["start"] + overlay["end"]) / 2 * 30)
        samples.append((frame, overlay))
    selected = sorted({frame for frame, _ in samples})
    expression = "+".join(f"eq(n\\,{frame})" for frame in selected)
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
             "-vf", f"select={expression}", "-fps_mode", "vfr", "-frames:v", str(len(selected)),
             str(temp / "frame-%04d.png")], check=True, capture_output=True, text=True,
        )
        files = {frame: temp / f"frame-{index+1:04d}.png" for index, frame in enumerate(selected)}
        for frame, overlay in samples:
            card = Image.open(root / overlay["file"]).convert("RGBA")
            actual = Image.open(files[frame]).convert("RGB")
            red, green, blue, alpha = card.split()
            # Panels have alpha 175/214 and black RGB. Letter interiors have
            # nearly opaque alpha; compare those without including antialias edges.
            opaque = alpha.point(lambda value: 255 if value >= 250 else 0)
            bright = ImageChops.lighter(red, ImageChops.lighter(green, blue)).point(
                lambda value: 255 if value > 100 else 0)
            glyph_mask = ImageChops.multiply(opaque, bright)
            count = ImageStat.Stat(glyph_mask).sum[0] / 255
            name = Path(overlay["file"]).stem
            if count < 100:
                result["errors"].append(f"Overlay {name} has no substantial opaque text")
                continue
            differences = ImageChops.difference(actual, card.convert("RGB"))
            glyph_mae = sum(ImageStat.Stat(differences, mask=glyph_mask).mean) / 3
            # White/cream letters are an additional presence check. The design's
            # cream is RGB(242,238,229), so a 230 threshold on all channels would
            # incorrectly exclude the reference's blue channel.
            white_reference = ImageChops.multiply(
                red.point(lambda value: 255 if value >= 230 else 0),
                ImageChops.multiply(
                    green.point(lambda value: 255 if value >= 225 else 0),
                    blue.point(lambda value: 255 if value >= 220 else 0),
                ),
            )
            white_reference = ImageChops.multiply(white_reference, opaque)
            white_count = ImageStat.Stat(white_reference).sum[0] / 255
            actual_red, actual_green, actual_blue = actual.split()
            actual_white = ImageChops.darker(actual_red, ImageChops.darker(actual_green, actual_blue)).point(
                lambda value: 255 if value >= 205 else 0)
            white_fraction = (
                ImageStat.Stat(ImageChops.multiply(actual_white, white_reference)).sum[0] / 255 / white_count
                if white_count >= 100 else 0
            )
            panel_alpha = alpha.point(lambda value: 255 if 170 <= value <= 240 else 0)
            black = ImageChops.lighter(red, ImageChops.lighter(green, blue)).point(
                lambda value: 255 if value == 0 else 0)
            panel_mask = ImageChops.multiply(panel_alpha, black)
            panel_pixels = ImageStat.Stat(panel_mask).sum[0] / 255
            if panel_pixels < 1000:
                result["errors"].append(f"Overlay {name} lacks its expected dark reading panel")
                continue
            panel_mean = sum(ImageStat.Stat(actual, mask=panel_mask).mean) / 3
            # Even white underlying footage cannot exceed 255-alpha after a
            # black alpha-composite; allow twelve levels for encoding/conversion.
            panel_upper = 255 - ImageStat.Stat(alpha, mask=panel_mask).mean[0] + 12
            result["checks"][f"encoded_overlay_{name}"] = {
                "frame": frame, "glyph_mae": glyph_mae,
                "white_glyph_fraction": white_fraction,
                "panel_mean": panel_mean, "panel_upper_bound": panel_upper,
            }
            if glyph_mae > 25 or white_fraction < 0.8 or panel_mean > panel_upper:
                result["errors"].append(
                    f"Encoded overlay {name} is absent/incorrect at frame {frame}: "
                    f"glyph MAE {glyph_mae:.2f}; white glyph fraction {white_fraction:.3f}; "
                    f"panel {panel_mean:.2f} (limit {panel_upper:.2f})"
                )


def validate(path: Path, root: Path, report_path: Path) -> dict:
    result = {"video": str(path), "passed": False, "errors": [], "checks": {}, "probe": None}
    errors = result["errors"]
    if not path.is_file() or path.stat().st_size == 0:
        errors.append("Finished MP4 does not exist or is empty")
    else:
        try:
            info = probe_media(path)
            result["probe"] = info
            errors.extend(metadata_errors(info))
            result["checks"]["metadata"] = not metadata_errors(info)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            errors.append(f"FFprobe failed: {exc}")
        # Decode every packet, so a truncated file with a plausible header cannot pass.
        decoded = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(path),
             "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        result["checks"]["full_decode"] = decoded.returncode == 0
        if decoded.returncode:
            errors.append("Full audio/video decode failed: " + decoded.stderr[-2000:])
        audio = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", "volumedetect",
             "-f", "null", "-"], capture_output=True, text=True,
        )
        volumes = re.findall(r"max_volume: ([\-\w.]+) dB", audio.stderr)
        audible = bool(volumes) and volumes[-1] != "-inf" and float(volumes[-1]) > -80
        result["checks"]["non_silent_audio"] = audible
        if not audible:
            errors.append("The audio track is silent, missing, or could not be decoded")
        try:
            check_encoded_overlays(path, root, result)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
            errors.append(f"Encoded historical-caption verification failed: {exc}")
        expected_card = root / "output/cards/final.png"
        if not expected_card.is_file():
            errors.append("Missing expected Arabic raster: output/cards/final.png")
        else:
            try:
                expected = Image.open(expected_card).convert("RGB")
                if expected.size != (1920, 1080):
                    errors.append("Expected Arabic raster is not 1920 × 1080")
                gold_pixels = sum(
                    1 for (red, green, blue) in expected.getdata()
                    if red > 140 and green > 80 and red > green + 10 and green > blue + 15
                )
                result["checks"]["final_card_gold_pixels"] = gold_pixels
                if gold_pixels < 1000:
                    errors.append("Arabic end-card raster has no substantial visible gold lettering")
                with tempfile.TemporaryDirectory() as tmp:
                    tmp = Path(tmp)
                    # Sample both ends of the eight-second hold, not the fade.
                    for frame_no in (4590, 4740):
                        image_path = tmp / f"frame-{frame_no}.png"
                        extract_frame(path, frame_no, image_path)
                        mae = image_mae(expected, Image.open(image_path))
                        result["checks"][f"arabic_card_frame_{frame_no}_mae"] = mae
                        if mae > 8:
                            errors.append(f"Arabic end-card frame {frame_no} differs from approved raster (MAE {mae:.2f})")
                    for frame_no in (0, 4799):
                        image_path = tmp / f"frame-{frame_no}.png"
                        extract_frame(path, frame_no, image_path)
                        means = ImageStat.Stat(Image.open(image_path).convert("RGB")).mean
                        dark = max(means) <= 2
                        result["checks"][f"black_frame_{frame_no}"] = dark
                        if not dark:
                            errors.append(f"Frame {frame_no} must be pure black within encoding tolerance")
            except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                errors.append(f"End-card/frame verification failed: {exc}")
    # Re-run clearance at validation time; a cached report is not sufficient.
    preflight = root / "scripts/preflight.py"
    if not preflight.is_file():
        errors.append("Missing publication preflight script")
    else:
        clearance = subprocess.run(
            [sys.executable, str(preflight), "--report", str(root / "output/preflight.json")],
            cwd=root, capture_output=True, text=True,
        )
        result["checks"]["publication_clearance"] = clearance.returncode == 0
        if clearance.returncode:
            errors.append("Publication preflight failed: " + (clearance.stdout + clearance.stderr)[-4000:])
    result["passed"] = not errors
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=ROOT / "output/validation.json")
    args = parser.parse_args()
    result = validate(args.video.resolve(), args.root.resolve(), args.report.resolve())
    if result["passed"]:
        print(f"PASS: 4800 frames / 160 s, 1920×1080, 30 FPS, H.264 + AAC: {args.video}")
    else:
        for error in result["errors"]:
            print(f"FAIL: {error}", file=sys.stderr)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
