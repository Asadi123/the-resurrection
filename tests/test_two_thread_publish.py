"""Offline publication-gate tests; fake MP4 bytes are never render evidence."""
import json
from pathlib import Path
import zipfile

from PIL import Image
import pytest

from two_thread import acquire, publish, render


def write_json(path, value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def production(tmp_path, monkeypatch):
    """98 valid local images plus synthetic HTML, with only decoding mocked."""
    base = tmp_path / "two_thread"
    base.mkdir()
    manifest = {"complete": True, "missing": [], "threads": []}
    for tid, count in acquire.THREADS.items():
        html = []
        for i in range(count):
            images = acquire.ATTACHMENT_COUNTS[tid] if i == 0 else 0
            entities = '<div class="entity-image"><a href="https://pbs.twimg.com/media/test.jpg"><img src="https://pbs.twimg.com/media/test.jpg"></a></div>' * images
            html.append(f'<div class="content-tweet" data-tweet="{int(tid)+i}" data-screenname="test_source">Attributed test assertion {i}{entities}</div>')
        raw = base / "evidence" / f"{tid}.html"
        raw.parent.mkdir(exist_ok=True)
        raw.write_text("".join(html))
        posts = acquire.parse_thread(raw.read_text(), tid)
        for post in posts:
            for asset in post["attachments"]:
                path = tmp_path / asset["local_path"]
                path.parent.mkdir(exist_ok=True, parents=True)
                Image.new("RGB", (20, 30), "white").save(path)
                asset.update(sha256=render.sha256(path), width=20, height=30,
                             has_audio=False, download_status="downloaded", duration=None)
        manifest["threads"].append({"id": tid, "url": acquire.source_url(tid), "posts": posts,
                                    "html_path": str(raw.relative_to(tmp_path)), "html_sha256": render.sha256(raw)})
    assets = render.load_assets(manifest, tmp_path)
    ids = list(assets)
    segments = [{"asset_id": aid, "duration": 1.0, "caption": "Attributed source reproduction.", "kicker": "Test evidence"} for aid in ids[:-1]]
    edit = {"title": "Test source-bound documentary", "perspective": "Attributed editorial test perspective",
            "unused_attachments": [{"asset_id": ids[-1], "reason": "Explicit editorial omission"}], "segments": segments}
    film = base / "output/test-film.mp4"
    film.parent.mkdir()
    film.write_bytes(b"FAKE MP4 UNIT TEST FIXTURE - not actual video")
    receipts = [{"segment": i, "asset_id": aid, "source_url": assets[aid]["source_url"],
                 "tweet_url": assets[aid]["tweet_url"], "asset_sha256": assets[aid]["sha256"],
                 "start_in_master": i - 1, "duration": 1.0, "clip_start": 0,
                 "original_audio": False, "caption": "Attributed source reproduction.",
                 "highlight": None, "entire_source_contained": True} for i, aid in enumerate(ids[:-1], 1)]
    report = {"status": "RENDERED_VALIDATED", "sha256": render.sha256(film), "output": str(film),
              "edit_sha256": publish.object_digest(edit), "collection_sha256": publish.object_digest(manifest),
              "title": edit["title"], "perspective": edit["perspective"], "exclusive_source_threads": list(acquire.THREADS),
              "all_source_assets_verified": 98, "segment_count": 97, "segments": receipts,
              "expected_duration_seconds": 97.0, "duration_seconds": 97.0,
              "resolution": [1920, 1080], "fps": 30, "decode_validation": "PASS",
              "synthetic_narration": False, "synthetic_historical_images": False, "unrelated_music": False}
    write_json(base / "collection.json", manifest)
    write_json(base / "edit.json", edit)
    write_json(base / "highlights.json", [])
    write_json(film.with_suffix(".render-report.json"), report)
    for name in ("INVENTORY.md", "MISSING-ASSETS.md", "README.md", "__init__.py", "acquire.py", "render.py", "publish.py", "requirements.txt"):
        (base / name).write_text("TEST FIXTURE ONLY\n")
    decoded = []

    def mocked_decode(path, expected):
        decoded.append((path, expected))
        return {"format": {"duration": "97.0"}}

    monkeypatch.setattr(render, "validate_output", mocked_decode)
    return {"root": tmp_path, "film": film, "manifest": manifest, "edit": edit,
            "report": report, "assets": assets, "decoded": decoded}


def run(production, **kwargs):
    return publish.check_publication(production["film"], root=production["root"], **kwargs)


def save_report(production):
    write_json(production["film"].with_suffix(".render-report.json"), production["report"])


def test_gate_reopens_sources_and_independently_decodes_before_marking_publishable(production):
    result = run(production)
    assert result["status"] == "PUBLISHABLE"
    assert result["source_assets_verified"] == 98
    assert result["source_assets_used"] == 97
    assert result["full_decode_validation"] == "PASS"
    assert result["publication_performed"] is False
    assert production["decoded"] == [(production["film"], 97.0)]
    assert production["film"].with_suffix(".publication.json").exists()


@pytest.mark.parametrize("field,value", [
    ("status", "PREVIEW_NOT_FINAL"), ("status", "RENDERING"), ("sha256", "0" * 64),
    ("edit_sha256", "0" * 64), ("collection_sha256", "0" * 64),
    ("title", "Unrelated film"), ("perspective", "Changed argument"),
    ("all_source_assets_verified", 97), ("segment_count", 1),
    ("exclusive_source_threads", ["123"]), ("expected_duration_seconds", 96.0),
    ("resolution", [1280, 720]), ("fps", 24), ("decode_validation", "PENDING"),
    ("synthetic_narration", True), ("synthetic_historical_images", True), ("unrelated_music", True),
])
def test_partial_preview_stale_or_unapproved_report_is_rejected(production, field, value):
    production["report"][field] = value
    save_report(production)
    with pytest.raises((publish.PublicationError, render.SourceError)):
        run(production)
    assert production["decoded"] == []
    assert not production["film"].with_suffix(".publication.json").exists()


@pytest.mark.parametrize("field,value", [
    ("asset_id", "unrelated"), ("source_url", "https://pbs.twimg.com/media/unrelated.jpg"),
    ("asset_sha256", "0" * 64), ("clip_start", 1), ("duration", 2),
    ("caption", "Rewritten unsupported claim"), ("highlight", {"rect": [0, 0, 1, 1]}),
    ("start_in_master", 4), ("original_audio", True), ("entire_source_contained", False),
])
def test_each_reported_segment_must_match_current_edit_and_source(production, field, value):
    production["report"]["segments"][0][field] = value
    save_report(production)
    with pytest.raises(publish.PublicationError, match="receipt differs"):
        run(production)


def test_reordered_or_missing_segments_are_not_complete_film_proof(production):
    production["report"]["segments"].reverse()
    save_report(production)
    with pytest.raises(publish.PublicationError):
        run(production)


def test_kicker_change_is_caught_by_complete_edl_digest(production):
    edit = production["edit"]
    edit["segments"][0]["kicker"] = "Different burned-in text"
    write_json(production["root"] / "two_thread/edit.json", edit)
    with pytest.raises(publish.PublicationError, match="not bound"):
        run(production)


def test_receipt_duration_uses_the_renderers_frame_rounding(production):
    production["edit"]["segments"][0]["duration"] = 1.004
    write_json(production["root"] / "two_thread/edit.json", production["edit"])
    production["report"]["edit_sha256"] = publish.object_digest(production["edit"])
    save_report(production)
    assert run(production)["expected_duration_seconds"] == 97.0


def test_missing_actual_asset_blocks_even_when_report_claims_all_sources_verified(production):
    asset = next(iter(production["assets"].values()))
    asset["path"].unlink()
    with pytest.raises(render.SourceError, match="Missing or changed attachment"):
        run(production)
    assert production["decoded"] == []


def test_changed_film_bytes_block_before_decode(production):
    production["film"].write_bytes(b"substituted film")
    with pytest.raises(publish.PublicationError, match="film hash"):
        run(production)


def test_decode_failure_cannot_write_publishable_receipt(production, monkeypatch):
    def failed(*args):
        raise render.SourceError("MP4 decoding failed")

    monkeypatch.setattr(render, "validate_output", failed)
    with pytest.raises(render.SourceError, match="decoding failed"):
        run(production)
    assert not production["film"].with_suffix(".publication.json").exists()


def test_actual_duration_is_compared_to_report_not_just_header_pass(production):
    production["report"]["duration_seconds"] = 96.9
    save_report(production)
    with pytest.raises(publish.PublicationError, match="duration differs"):
        run(production)


def test_undeclared_source_omission_blocks_even_with_updated_edl_hash(production):
    production["edit"]["unused_attachments"] = []
    write_json(production["root"] / "two_thread/edit.json", production["edit"])
    production["report"]["edit_sha256"] = publish.object_digest(production["edit"])
    save_report(production)
    with pytest.raises(publish.PublicationError, match="editorial omission"):
        run(production)


def test_bundle_contains_all_98_originals_and_no_legacy_or_output_tree(production):
    root = production["root"]
    (root / "assets/visuals").mkdir(parents=True)
    (root / "assets/visuals/forbidden.jpg").write_bytes(b"OLD FILM")
    (root / "two_thread/output/render").mkdir()
    (root / "two_thread/output/render/intermediate.mov").write_bytes(b"OUTPUT")
    (root / "two_thread/__pycache__").mkdir()
    (root / "two_thread/__pycache__/cache.pyc").write_bytes(b"CACHE")
    bundle = root / "two_thread/output/source-bundle.zip"
    result = run(production, bundle=bundle)
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        assert len([name for name in names if name.startswith("two_thread/assets/")]) == 98
        assert "two_thread/collection.json" in names
        assert "two_thread/edit.json" in names
        assert "two_thread/README.md" in names
        assert "two_thread/publish.py" in names
        assert "two_thread/PUBLICATION-VALIDATION.json" in names
        assert not any("output/" in name or "__pycache__" in name or "forbidden.jpg" in name for name in names)
        assert all(name.startswith("two_thread/") and ".." not in Path(name).parts for name in names)
        assert archive.testzip() is None
    assert result["bundle"]["sha256"] == render.sha256(bundle)


@pytest.mark.parametrize("destination", ["two_thread/edit.json", "two_thread/assets/substitute.zip", "../outside.zip", "two_thread/output/test-film.mp4"])
def test_bundle_cannot_overwrite_sources_master_or_escape_repository(production, destination):
    with pytest.raises(publish.PublicationError):
        run(production, bundle=destination)


def test_unknown_evidence_file_does_not_enter_bundle(production):
    (production["root"] / "two_thread/evidence/old-un-document.pdf").write_bytes(b"UNRELATED")
    with pytest.raises(publish.PublicationError, match="Unknown evidence file"):
        run(production, bundle="two_thread/output/source-bundle.zip")


def test_symlink_outside_cannot_enter_evidence_or_output(production, tmp_path):
    outside = production["root"].parent / "foreign.txt"
    outside.write_text("UNRELATED")
    (production["root"] / "two_thread/evidence/previous-branches.md").symlink_to(outside)
    with pytest.raises(publish.PublicationError, match="Symlinks"):
        run(production)


def test_bundle_temporary_file_cannot_follow_an_external_symlink(production):
    outside = production["root"].parent / "outside-source.zip"
    outside.write_bytes(b"PRESERVE")
    destination = production["root"] / "two_thread/output/source-bundle.zip"
    destination.with_suffix(".zip.part").symlink_to(outside)
    with pytest.raises(publish.PublicationError):
        run(production, bundle=destination)
    assert outside.read_bytes() == b"PRESERVE"


def test_source_file_cannot_be_treated_as_publication_output(production):
    asset = next(iter(production["assets"].values()))
    with pytest.raises(publish.PublicationError, match="must not overwrite"):
        publish.check_publication(asset["path"], root=production["root"])


def test_cli_check_only_creates_receipt_but_never_calls_a_publish_service(production, capsys):
    assert publish.main(["--check-only", "--film", str(production["film"]), "--root", str(production["root"])]) == 0
    assert json.loads(capsys.readouterr().out)["publication_performed"] is False


def test_cli_requires_explicit_check_only(production):
    with pytest.raises(SystemExit) as error:
        publish.main(["--film", str(production["film"]), "--root", str(production["root"])])
    assert error.value.code == 2
