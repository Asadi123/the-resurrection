"""Independent publication gate; this module never contacts GitHub or publishes.

Reopen the acquired sources, compare the complete render receipt with the
current edit, and fully decode the actual master before allowing a workflow to
publish it. Source bundles contain only this production's explicit inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

from two_thread import acquire, render

ROOT = Path(__file__).resolve().parents[1]


class PublicationError(ValueError):
    """Publication cannot be independently established."""


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def object_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def checked_path(root, path, *, output=False, exists=True):
    """Keep inputs and generated outputs inside their distinct source trees."""
    root = Path(root).resolve()
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise PublicationError("Publication path escapes the production repository")
    # Reject symlinks even when their current destination is inside the root.
    # A bundle must contain source bytes, not machine-specific path redirects.
    for component in (path, *path.parents):
        if component == root.parent:
            break
        if component.is_symlink():
            raise PublicationError("Symlinks are not permitted in publication inputs")
    if output and not any(resolved.is_relative_to(root / prefix) for prefix in ("output", "two_thread/output")):
        raise PublicationError("Publication outputs must not overwrite source material")
    if exists and not resolved.is_file():
        raise PublicationError(f"Missing publication input: {resolved.name}")
    return resolved


def verify_report(report, film, edit, assets, segments, manifest):
    if report.get("status") != "RENDERED_VALIDATED" or "preview" in film.stem.lower():
        raise PublicationError("A preview or partial render cannot be published")
    if report.get("sha256") != render.sha256(film):
        raise PublicationError("Actual film hash differs from the render report")
    if report.get("edit_sha256") != object_digest(edit) or report.get("collection_sha256") != object_digest(manifest):
        raise PublicationError("Render report is not bound to the complete current edit and source manifest")
    if Path(str(report.get("output", ""))).name != film.name:
        raise PublicationError("Render report identifies a different output film")
    for key in ("title", "perspective"):
        if not isinstance(edit.get(key), str) or not edit[key] or report.get(key) != edit[key]:
            raise PublicationError(f"Render report {key} differs from the current edit")
    if report.get("exclusive_source_threads") != list(acquire.THREADS):
        raise PublicationError("Render report source collections are not exclusive")
    if len(assets) != 98 or report.get("all_source_assets_verified") != 98:
        raise PublicationError("All 98 attachment associations must be verified")
    omitted = edit.get("unused_attachments")
    if not isinstance(omitted, list) or len(omitted) != 1:
        raise PublicationError("Exactly one explicitly documented editorial omission is required")
    omission = omitted[0]
    if not isinstance(omission, dict) or omission.get("asset_id") not in assets or not isinstance(omission.get("reason"), str) or not omission["reason"].strip():
        raise PublicationError("The editorial omission must identify a known source and explain why")
    used = {segment["asset_id"] for segment in segments}
    if len(used) != 97 or set(assets) - used != {omission["asset_id"]}:
        raise PublicationError("The master must use all 97 selected sources, with only the declared omission")
    expected_receipts = []
    elapsed = 0.0
    for i, segment in enumerate(segments, 1):
        asset = assets[segment["asset_id"]]
        duration = round(float(segment["duration"]) * render.FPS) / render.FPS
        expected_receipts.append({
            "segment": i, "asset_id": asset["id"], "source_url": asset["source_url"],
            "tweet_url": asset["tweet_url"], "asset_sha256": asset["sha256"],
            "start_in_master": round(elapsed, 6), "duration": duration,
            "clip_start": segment.get("clip_start", 0),
            "original_audio": asset["kind"] == "video" and asset.get("has_audio") is True,
            "caption": segment.get("caption", ""), "highlight": segment.get("highlight"),
            "entire_source_contained": True,
        })
        elapsed += duration
    if report.get("segments") != expected_receipts or report.get("segment_count") != len(segments):
        raise PublicationError("Render receipt differs from the complete current edit or source hashes")
    if report.get("expected_duration_seconds") != round(elapsed, 6):
        raise PublicationError("Render report duration differs from the complete edit")
    if report.get("resolution") != [render.W, render.H] or report.get("fps") != render.FPS or report.get("decode_validation") != "PASS":
        raise PublicationError("Render report technical validation is incomplete")
    if any(report.get(k) is not False for k in ("synthetic_narration", "synthetic_historical_images", "unrelated_music")):
        raise PublicationError("Unapproved generated speech, history or music is prohibited")
    return elapsed


def bundle_inputs(root, manifest, highlights):
    """Use explicit source membership, never copy a repository or output tree."""
    root = Path(root).resolve()
    required = {"collection.json", "edit.json", "highlights.json", "INVENTORY.md", "MISSING-ASSETS.md", "__init__.py", "acquire.py", "render.py", "publish.py", "requirements.txt"}
    paths = {checked_path(root, root / "two_thread" / name) for name in required}
    readme = root / "two_thread/README.md"
    if readme.exists():
        paths.add(checked_path(root, readme))
    for thread in manifest["threads"]:
        for post in thread["posts"]:
            for asset in post["attachments"]:
                paths.add(checked_path(root, root / asset["local_path"]))
    allowed_evidence = {f"{tid}.html" for tid in acquire.THREADS}
    allowed_evidence |= {f"{tid}-acquisition-receipts.json" for tid in acquire.THREADS}
    allowed_evidence.add("previous-branches.md")
    # Retain OCR review attempts, including passages rejected for highlighting.
    # Names must map to a real image ordinal in a commissioned post; these are
    # diagnostics, never a route for adding images, PDFs or recording files.
    for thread in manifest["threads"]:
        for post in thread["posts"]:
            count = sum(asset["kind"] == "image" for asset in post["attachments"])
            for i in range(1, count + 1):
                allowed_evidence.update(f"ocr/p{post['ordinal']:02d}-image{i:02d}.{ext}" for ext in ("txt", "tsv"))
    if not isinstance(highlights, list):
        raise PublicationError("Highlight register must be a list")
    for record in highlights:
        ocr = record.get("ocr_tsv", "")
        prefix = "two_thread/evidence/"
        if ocr:
            if not isinstance(ocr, str) or not ocr.startswith(prefix) or not re.fullmatch(r"ocr/[A-Za-z0-9_-]+\.tsv", ocr[len(prefix):]):
                raise PublicationError("Highlight references an unapproved evidence path")
            allowed_evidence.add(ocr[len(prefix):])
            allowed_evidence.add(str(Path(ocr[len(prefix):]).with_suffix(".txt")))
    evidence = root / "two_thread/evidence"
    for entry in evidence.rglob("*"):
        if entry.is_symlink():
            raise PublicationError("Symlinks cannot enter a source bundle")
        if entry.is_file():
            relative = str(entry.relative_to(evidence))
            if relative not in allowed_evidence:
                raise PublicationError(f"Unknown evidence file cannot enter the source bundle: {relative}")
            paths.add(checked_path(root, entry))
    return sorted(paths)


def create_bundle(path, root, inputs, validation):
    path = checked_path(root, path, output=True, exists=False)
    if path.suffix.lower() != ".zip":
        raise PublicationError("The source bundle must be a ZIP archive")
    if path in inputs:
        raise PublicationError("Source bundle cannot overwrite its inputs")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = checked_path(root, path.with_suffix(".zip.part"), output=True, exists=False)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for source in inputs:
                archive.write(source, str(source.relative_to(Path(root).resolve())))
            archive.writestr("two_thread/PUBLICATION-VALIDATION.json", json.dumps(validation, indent=2, ensure_ascii=False) + "\n")
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise PublicationError("Source bundle failed its complete CRC check")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": render.sha256(path), "bytes": path.stat().st_size, "source_files": len(inputs)}


def check_publication(film, *, root=ROOT, bundle=None):
    root = Path(root).resolve()
    film = checked_path(root, film, output=True)
    if film.suffix.lower() != ".mp4":
        raise PublicationError("A publication master must be an MP4 file")
    report_path = checked_path(root, film.with_suffix(".render-report.json"), output=True)
    publication_path = checked_path(root, film.with_suffix(".publication.json"), output=True, exists=False)
    manifest_path = checked_path(root, root / "two_thread/collection.json")
    edit_path = checked_path(root, root / "two_thread/edit.json")
    highlights_path = checked_path(root, root / "two_thread/highlights.json")
    manifest, edit, report = read_json(manifest_path), read_json(edit_path), read_json(report_path)
    acquire.verify_collection_sources(root, manifest)
    assets = render.load_assets(manifest, root)
    segments = render.validate_edit(edit, assets)
    duration = verify_report(report, film, edit, assets, segments, manifest)
    inputs = bundle_inputs(root, manifest, read_json(highlights_path))
    if bundle is not None:
        destination = checked_path(root, bundle, output=True, exists=False)
        if destination in {film, report_path, publication_path}:
            raise PublicationError("Source bundle cannot overwrite the film or its validation receipts")
        if destination.suffix.lower() != ".zip":
            raise PublicationError("The source bundle must be a ZIP archive")
    # This deliberately probes and decodes the actual MP4 again, rather than
    # trusting a report's previous PASS or a container header alone.
    metadata = render.validate_output(film, duration)
    if render.number(report.get("duration_seconds"), "rendered duration", positive=True) != render.number(metadata.get("format", {}).get("duration"), "actual duration", positive=True):
        raise PublicationError("Actual master duration differs from the recorded render")
    validation = {"status": "PUBLISHABLE", "checked_at": acquire.now(), "film": str(film), "film_sha256": render.sha256(film),
                  "render_report_sha256": render.sha256(report_path), "collection_sha256": render.sha256(manifest_path),
                  "edit_sha256": render.sha256(edit_path), "source_assets_verified": len(assets), "source_assets_used": len({s['asset_id'] for s in segments}),
                  "segments_verified": len(segments), "expected_duration_seconds": round(duration, 6), "full_decode_validation": "PASS",
                  "source_files": {str(p.relative_to(root)): render.sha256(p) for p in inputs},
                  "publication_performed": False}
    if bundle is not None:
        validation["bundle"] = create_bundle(bundle, root, inputs, validation)
    publication_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return validation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", required=True, help="Validate only; this program never publishes")
    parser.add_argument("--film", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        validation = check_publication(args.film, root=args.root, bundle=args.bundle)
    except (PublicationError, render.SourceError, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"PUBLICATION BLOCKED: {exc}\n")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
