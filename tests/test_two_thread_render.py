"""Source isolation, edit bounds, and an actual 1080p encode regression."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SPEC = importlib.util.spec_from_file_location("thread_render", Path(__file__).resolve().parents[1] / "two_thread/render.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class SourceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        path = self.root / "two_thread/assets/1668916665550094339/1668916665550094339-p01-a01.jpg"
        path.parent.mkdir(parents=True)
        Image.new("RGB", (200, 300), "white").save(path)
        self.asset = {"id": "1668916665550094339-p01-a01", "kind": "image", "source_url": "https://pbs.twimg.com/media/test.jpg", "local_path": str(path.relative_to(self.root)), "sha256": renderer.sha256(path), "width": 200, "height": 300, "has_audio": False, "download_status": "downloaded", "variants": ["https://pbs.twimg.com/media/test.jpg"], "poster_url": None}
        self.manifest = {"complete": True, "missing": [], "threads": []}
        from two_thread.acquire import parse_thread
        for tid, count in renderer.THREADS.items():
            snippets = []
            for i in range(count):
                attached = '<div class="entity-image"><a href="https://pbs.twimg.com/media/test.jpg"><img src="https://pbs.twimg.com/media/test.jpg"></a></div>' * (37 if tid == "1668916665550094339" else 61) if i == 0 else ""
                snippets.append(f'<div class="content-tweet" data-tweet="{int(tid)+i}" data-screenname="example">Source assertion, not an independently verified fact.{attached}</div>')
            html = "".join(snippets)
            html_path = self.root / f"two_thread/evidence/{tid}.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html)
            posts = parse_thread(html, tid)
            for post in posts:
                for asset in post["attachments"]:
                    target = self.root / asset["local_path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target != path:
                        shutil.copyfile(path, target)
                    asset.update(sha256=renderer.sha256(target), width=200, height=300, has_audio=False, download_status="downloaded")
            self.manifest["threads"].append({"id": tid, "url": f"https://threadreaderapp.com/thread/{tid}.html", "posts": posts, "html_path": str(html_path.relative_to(self.root)), "html_sha256": renderer.sha256(html_path)})
        self.asset = self.manifest["threads"][0]["posts"][0]["attachments"][0]
        self.edit = {"title": "Test", "perspective": "Attributed editorial perspective", "segments": [{"asset_id": "1668916665550094339-p01-a01", "duration": 1, "caption": "This is a reproduction, not independently authenticated.", "kicker": "Evidence"}]}

    def tearDown(self):
        self.temp.cleanup()

    def loaded(self):
        return renderer.load_assets(self.manifest, self.root)

    def test_full_edit_digest_binds_caption_kicker_and_metadata(self):
        original = renderer.object_digest(self.edit)
        for changes in [{"caption": "Changed caption"}, {"kicker": "Changed heading"}]:
            edit = copy.deepcopy(self.edit)
            edit["segments"][0].update(changes)
            self.assertNotEqual(renderer.object_digest(edit), original)
        for field in ("source_limits", "unused_editorial_metadata"):
            edit = copy.deepcopy(self.edit)
            edit[field] = "Must remain bound even if not rendered"
            self.assertNotEqual(renderer.object_digest(edit), original)

    def test_object_digest_is_canonical_and_binds_full_collection(self):
        self.assertEqual(renderer.object_digest({"b": "عراق", "a": 1}), renderer.object_digest({"a": 1, "b": "عراق"}))
        changed = copy.deepcopy(self.manifest)
        changed["acquisition_note"] = "Changed provenance metadata"
        self.assertNotEqual(renderer.object_digest(changed), renderer.object_digest(self.manifest))

    def test_complete_sources_load(self):
        self.assertEqual(len(self.loaded()), 98)
        self.assertIn("1668916665550094339-p01-a01", self.loaded())

    def test_missing_second_collection_blocks(self):
        self.manifest["threads"].pop()
        with self.assertRaisesRegex(renderer.SourceError, "Both authorized"):
            self.loaded()

    def test_missing_post_blocks(self):
        self.manifest["threads"][1]["posts"].pop()
        with self.assertRaises(renderer.SourceError):
            self.loaded()

    def test_wrong_thread_provenance_blocks(self):
        self.manifest["threads"][0]["url"] = "https://un.org/unrelated-document"
        with self.assertRaises(renderer.SourceError):
            self.loaded()

    def test_legacy_asset_is_rejected_even_if_hash_matches(self):
        target = self.root / "assets/visuals/old.png"
        target.parent.mkdir(parents=True)
        shutil.copyfile(self.root / self.asset["local_path"], target)
        self.asset["local_path"] = "assets/visuals/old.png"
        with self.assertRaises(renderer.SourceError):
            self.loaded()

    def test_escape_is_rejected(self):
        self.asset["local_path"] = "../../elsewhere.png"
        with self.assertRaises(renderer.SourceError):
            self.loaded()

    def test_changed_bytes_block_render(self):
        (self.root / self.asset["local_path"]).write_bytes(b"replacement footage")
        with self.assertRaisesRegex(renderer.SourceError, "Missing or changed"):
            self.loaded()

    def test_unrelated_attachment_url_blocks(self):
        self.asset["source_url"] = "https://commons.wikimedia.org/image.png"
        with self.assertRaises(renderer.SourceError):
            self.loaded()

    def test_http_or_credential_url_blocks(self):
        for url in ["http://pbs.twimg.com/media/a.png", "https://secret@pbs.twimg.com/media/a.png"]:
            self.asset["source_url"] = url
            with self.assertRaises(renderer.SourceError):
                self.loaded()

    def test_duplicate_attachment_identity_blocks(self):
        self.manifest["threads"][1]["posts"][0]["attachments"] = [copy.deepcopy(self.asset)]
        with self.assertRaises(renderer.SourceError):
            self.loaded()

    def test_tampered_dimensions_or_audio_metadata_is_rejected(self):
        for changes in [{"width": 999}, {"height": 999}, {"has_audio": True}]:
            original = {k: self.asset[k] for k in changes}
            self.asset.update(changes)
            with self.assertRaisesRegex(renderer.SourceError, "metadata"):
                self.loaded()
            self.asset.update(original)

    def test_incomplete_flag_rejects_even_available_files(self):
        self.manifest["complete"] = False
        with self.assertRaisesRegex(renderer.SourceError, "Incomplete source"):
            self.loaded()

    def test_no_generic_slide_or_unknown_asset(self):
        self.edit["segments"][0]["asset_id"] = "generic-slide"
        with self.assertRaisesRegex(renderer.SourceError, "Unknown source"):
            renderer.validate_edit(self.edit, self.loaded())

    def test_crop_zoom_or_unrelated_audio_is_forbidden(self):
        for key in ["crop", "zoom", "narration", "audio_path", "generated_image", "background_image"]:
            segment = dict(self.edit["segments"][0], **{key: True})
            with self.assertRaisesRegex(renderer.SourceError, "prohibited"):
                renderer.validate_edit({"segments": [segment]}, self.loaded())

    def test_nan_infinite_zero_negative_duration_blocks(self):
        for value in [float("nan"), float("inf"), 0, -1, True, "bad", None, 0.001]:
            self.edit["segments"][0]["duration"] = value
            with self.assertRaises(renderer.SourceError):
                renderer.validate_edit(self.edit, self.loaded())

    def test_video_excerpt_cannot_overrun(self):
        assets = self.loaded()
        assets["1668916665550094339-p01-a01"].update(kind="video", duration=5)
        self.edit["segments"][0].update(duration=4, clip_start=2)
        with self.assertRaisesRegex(renderer.SourceError, "extends beyond"):
            renderer.validate_edit(self.edit, assets)

    def test_image_cannot_have_inpoint(self):
        self.edit["segments"][0]["clip_start"] = 1
        with self.assertRaisesRegex(renderer.SourceError, "document"):
            renderer.validate_edit(self.edit, self.loaded())

    def highlight(self):
        return {"rect": [10, 20, 160, 40], "quote": "Verbatim words", "image_sha256": self.asset["sha256"], "verified_by": "Visual review against original image"}

    def test_reviewed_highlight_accepts_exact_image(self):
        self.edit["segments"][0]["highlight"] = self.highlight()
        self.assertEqual(len(renderer.validate_edit(self.edit, self.loaded())), 1)

    def test_ocr_without_visual_review_does_not_authorize_highlight(self):
        highlight = self.highlight()
        highlight.pop("verified_by")
        self.edit["segments"][0]["highlight"] = highlight
        with self.assertRaisesRegex(renderer.SourceError, "Unreviewed OCR"):
            renderer.validate_edit(self.edit, self.loaded())

    def test_highlight_outside_complete_page_blocks(self):
        highlight = self.highlight()
        highlight["rect"] = [190, 20, 20, 40]
        self.edit["segments"][0]["highlight"] = highlight
        with self.assertRaisesRegex(renderer.SourceError, "outside"):
            renderer.validate_edit(self.edit, self.loaded())

    def test_highlight_rejects_changed_image_or_empty_quote(self):
        for changes in [{"image_sha256": "0" * 64}, {"quote": ""}]:
            self.edit["segments"][0]["highlight"] = dict(self.highlight(), **changes)
            with self.assertRaises(renderer.SourceError):
                renderer.validate_edit(self.edit, self.loaded())

    def test_filter_contains_whole_portrait_or_landscape(self):
        for w, h in [(100, 800), (3000, 200), (200, 300)]:
            x, y, rw, rh = renderer.placement(w, h)
            self.assertGreaterEqual(x, renderer.AREA[0])
            self.assertGreaterEqual(y, renderer.AREA[1])
            self.assertLessEqual(x + rw, renderer.AREA[0] + renderer.AREA[2])
            self.assertLessEqual(y + rh, renderer.AREA[1] + renderer.AREA[3])
            filters = renderer.video_filter({"width": w, "height": h})
            self.assertIn("pad=1920:1080", filters)
            self.assertNotIn("crop", filters)
            self.assertIn("setsar=1", filters)

    def test_limited_preview_cannot_be_named_final(self):
        with self.assertRaisesRegex(renderer.SourceError, "preview"):
            renderer.render(self.manifest, self.edit, self.root / "final.mp4", self.root / "work", root=self.root, limit=1)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg not installed")
    def test_actual_encode_decode_and_contact_sheet(self):
        output = self.root / "film-preview.mp4"
        self.edit["segments"][0]["duration"] = 0.2
        report = renderer.render(self.manifest, self.edit, output, self.root / "work", root=self.root, crf=30, limit=1)
        self.assertEqual(report["status"], "PREVIEW_NOT_FINAL")
        self.assertEqual(report["edit_sha256"], renderer.object_digest(self.edit))
        self.assertEqual(report["collection_sha256"], renderer.object_digest(self.manifest))
        self.assertEqual(report["decode_validation"], "PASS")
        self.assertEqual(report["resolution"], [1920, 1080])
        self.assertFalse(report["segments"][0]["original_audio"])
        self.assertEqual(report["sha256"], renderer.sha256(output))
        self.assertTrue(output.with_suffix(".contact-sheet.jpg").is_file())
        self.assertTrue(output.with_suffix(".render-report.json").is_file())


if __name__ == "__main__":
    unittest.main()
