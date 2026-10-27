#!/usr/bin/env python3
"""Fail closed on missing media, provenance, audio, or editorial qualifications."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from PIL import Image
from common import ROOT, read_json, write_json, digest, probe, safe_path


def check():
    errors, warnings = [], []
    required = ["config/film.json", "research/asset-manifest.json", "research/audio-assets.json",
                "config/editorial-review.json", "config/qa-review.json", "output/audio-timing.json"]
    for name in required:
        if not (ROOT / name).is_file():
            errors.append(f"Missing input: {name}")
    if errors:
        return {"passed": False, "errors": errors, "warnings": warnings}
    cfg = read_json("config/film.json")
    visual = read_json("research/asset-manifest.json")
    audio = read_json("research/audio-assets.json")
    editorial = read_json("config/editorial-review.json")
    qa = read_json("config/qa-review.json")
    for document, kind in [(visual, "visual"), (audio, "audio")]:
        if not document.get("assets"):
            errors.append(f"Empty {kind} manifest")
        for a in document.get("assets", []):
            name = a.get("id", "unnamed")
            for field in ("filename", "source_url", "creator", "date", "license", "license_url", "sha256"):
                if not a.get(field):
                    errors.append(f"{kind} {name}: missing {field}")
            if not a.get("rights_confirmed"):
                errors.append(f"{kind} {name}: reuse rights not confirmed")
            if kind == "visual" and (a.get("generated") is not False or a.get("historical_authenticity") != "confirmed"):
                errors.append(f"Visual {name}: not confirmed authentic historical material")
            path = safe_path(a.get("filename", "missing"))
            if not path.is_file():
                errors.append(f"Missing {kind} file: {path.relative_to(ROOT)}")
            elif digest(path) != a.get("sha256"):
                errors.append(f"{kind} {name}: SHA-256 mismatch")
    shots = cfg.get("shots", [])
    ids = {a["id"] for a in visual.get("assets", [])}
    if len(shots) < 8:
        errors.append("Insufficient unique archival coverage: fewer than eight configured shots")
    if len({s["asset"] for s in shots}) != len(shots):
        errors.append("A visual is repeated; each archival shot must use a unique source")
    position = 13
    for s in shots:
        if s["asset"] not in ids:
            errors.append(f"Unknown archival source: {s['asset']}")
        if abs(s["start"] - position) > .001 or s["end"] <= s["start"]:
            errors.append(f"Gap/overlap/invalid interval at {s['asset']}")
        for t in (s["start"], s["end"]):
            if abs(t * 30 - round(t * 30)) > .0001:
                errors.append(f"Shot is not frame aligned: {s['asset']}")
        position = s["end"]
    if position != 150:
        errors.append("Archival sequence must end at 150 seconds")
    if not shots or not shots[0].get("title") or shots[0]["end"] != 21:
        errors.append("Opening Baghdad/title must occupy 13–21 seconds")
    if cfg.get("duration") != 160 or cfg.get("fps") != 30 or (cfg.get("width"), cfg.get("height")) != (1920, 1080):
        errors.append("Film settings differ from required 160s /1080p /30fps")
    if cfg.get("final_hold_end", 0)-cfg.get("final_hold_start", 0) != 8:
        errors.append("Final Arabic-only hold must last eight seconds")
    if qa.get("reviewed_text") != cfg.get("final_text") or not all(qa.get(k) for k in ["arabic_shaping_verified", "rtl_verified", "english_absent", "gold_on_black"]):
        errors.append("Arabic card does not have documented visual QA for the exact text")
    captions = editorial.get("timed_captions", [])
    covered = {claim for c in captions for claim in c.get("claim_ids", [])}
    mandatory = {c["id"] for c in editorial.get("claims", []) if c.get("caption") and c.get("verdict") != "political_interpretation"}
    mandatory |= {c["id"] for c in editorial.get("opening_card_claims", [])}
    missing = mandatory - covered
    if missing:
        errors.append("Missing synchronized factual corrections: " + ", ".join(sorted(missing)))
    if not editorial.get("synchronization_verified"):
        errors.append("Editorial captions have not been synchronized against measured narration")
    timing_path = ROOT / "output/audio-timing.json"
    if editorial.get("caption_sync", {}).get("timing_sha256") != digest(timing_path):
        errors.append("Editorial captions are stale: re-run scripts/sync_editorial.py after audio preparation")
    timing = read_json("output/audio-timing.json")
    if timing.get("mix_sha256") != digest(ROOT / "output/audio_mix.wav"):
        errors.append("Audio timing report does not match the current audio mix")
    if not any("context_repression" in c.get("claim_ids", []) and c["end"]-c["start"] >= 6 for c in captions):
        errors.append("Missing required dictatorship/Anfal historical-context caption")
    ordered = sorted(captions, key=lambda c: c["start"])
    previous = None
    for c in ordered:
        if c["start"] < 13 or c["end"] > 150 or c["end"] <= c["start"]:
            errors.append("Caption interval intrudes on opening/final card or is invalid")
        if previous and c["start"] < previous["end"] - .001:
            errors.append("Factual correction captions overlap; they would be illegible")
        previous = c
    mix = ROOT / "output/audio_mix.wav"
    if not mix.is_file():
        errors.append("Missing prepared narration/music mix")
    else:
        p = probe(mix)
        if abs(float(p["format"]["duration"])-160) > .001:
            errors.append("Audio mix is not exactly 160 seconds")
    warnings.extend(["Archival coverage gap: " + (g if isinstance(g, str) else str(g.get("subject", g))) for g in visual.get("gaps", [])])
    warnings.append("Some originals are low resolution. They are proportionally scaled without generated detail.")
    return {"passed": not errors, "errors": errors, "warnings": warnings,
            "visual_asset_count": len(visual["assets"]), "unique_shots": len(shots),
            "editorial_mode": cfg.get("publication_mode"), "final_card_visually_reviewed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="output/preflight.json")
    args = parser.parse_args()
    try:
        result = check()
    except Exception as exc:
        result = {"passed": False, "errors": [f"Preflight exception: {type(exc).__name__}: {exc}"], "warnings": []}
    write_json(args.report, result)
    for message in result["errors"]:
        print("BLOCKED: " + message, file=sys.stderr)
    for message in result["warnings"]:
        print("NOTE: " + message)
    if result["passed"]:
        print("PASS: sources, unique timeline, qualified narration, audio and Arabic QA")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
