"""Offline source-boundary regressions; mocks are never connectivity evidence."""
from __future__ import annotations

import copy
import hashlib
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image
import pytest
import requests

from two_thread import acquire


ROOT = Path(__file__).resolve().parents[1]
FIRST = "1668916665550094339"
SECOND = "1986782578565579207"
PAGE = acquire.source_url(FIRST)
IMAGE = "https://pbs.twimg.com/media/verified.jpg"
VIDEO = "https://video.twimg.com/ext_tw_video/123/pu/vid/640x360/clip.mp4?tag=12"


def snapshot(thread=FIRST):
    return (ROOT / "two_thread" / "evidence" / f"{thread}.html").read_text(encoding="utf-8")


def node(tweet=FIRST, body="Source assertion", author="xumas_iq"):
    return f'<div class="content-tweet" data-tweet="{tweet}" data-screenname="{author}">{body}</div>'


def image_entity(url=IMAGE):
    return f'<div class="entity-image"><a href="{url}"><img src="{url}"></a></div>'


def verified_collection():
    threads = []
    for thread in acquire.THREADS:
        posts = acquire.parse_thread(snapshot(thread), thread)
        for post in posts:
            for asset in post["attachments"]:
                asset["download_status"] = "downloaded"
        threads.append({"id": thread, "url": acquire.source_url(thread), "posts": posts})
    return {"threads": threads}


@pytest.mark.parametrize("thread,posts,images,videos,last", [
    (FIRST, 28, 22, 15, "1719330977808355797"),
    (SECOND, 44, 51, 10, "1987633532567470256"),
])
def test_retained_sources_account_for_every_primary_attachment(thread, posts, images, videos, last):
    html = snapshot(thread)
    soup = BeautifulSoup(html, "html.parser")
    parsed = acquire.parse_thread(html, thread)
    # Both retained source pages include 18 recommendation cards. They are not
    # commissioned posts and must never leak into the production manifest.
    assert len(soup.select(".content-tweet")) == posts + 18
    assert len(parsed) == posts
    assert parsed[0]["id"] == thread
    assert parsed[-1]["id"] == last
    attachments = [a for p in parsed for a in p["attachments"]]
    assert sum(a["kind"] == "image" for a in attachments) == images
    assert sum(a["kind"] == "video" for a in attachments) == videos
    assert len({a["id"] for a in attachments}) == images + videos
    assert all(a["local_path"].startswith(f"two_thread/assets/{thread}/") for a in attachments)
    assert all(p["ordinal"] == i for i, p in enumerate(parsed, 1))


def test_recommendations_and_unrelated_links_do_not_become_attachments():
    html = node(body='Exact claim <a href="https://example.org/book">citation</a>' + image_entity())
    html += '<div class="content-tweet">Recommendation' + image_entity("https://evil.example/replacement.jpg") + '</div>'
    post, = acquire.parse_thread(html, FIRST)
    assert post["text"] == "Exact claim citation"
    assert len(post["attachments"]) == 1
    assert "https://example.org/book" in post["links"]
    assert post["attachments"][0]["source_url"] == IMAGE


@pytest.mark.parametrize("html", [
    "<html><title>Just a moment</title><p>Checking your browser</p></html>",
    node(tweet=SECOND),
    node() + node(),
    node(tweet="not-a-tweet"),
    node(author=""),
    node(author="bad/author"),
])
def test_bot_wrong_root_duplicate_or_malformed_html_is_not_a_collection(html):
    with pytest.raises(ValueError):
        acquire.parse_thread(html, FIRST)


def test_unknown_thread_cannot_be_requested_or_parsed():
    with pytest.raises(ValueError):
        acquire.source_url("123")
    with pytest.raises(ValueError):
        acquire.parse_thread(node(tweet="123"), "123")


def test_video_uses_highest_explicit_mp4_and_retains_nested_source_variants():
    low = "https://video.twimg.com/ext_tw_video/123/pu/vid/320x180/low.mp4"
    high = "https://video.twimg.com/ext_tw_video/123/pu/vid/1280x720/high.mp4"
    mid = "https://video.twimg.com/ext_tw_video/123/pu/vid/640x360/middle.mp4"
    body = '<div class="entity-video"><video poster="https://pbs.twimg.com/ext_tw_video_thumb/123/pu/img/poster.jpg">'
    body += f'<source type="video/mp4" src="{low}"><source type="video/mp4" src="{high}"><source type="video/mp4" src="{mid}">'
    body += f'<source type="video/mp4" src="{high}"></video>'
    # Nested preview markup is not a second historical image.
    body += '<div class="entity-image"><img src="https://pbs.twimg.com/ext_tw_video_thumb/123/pu/img/poster.jpg"></div></div>'
    post, = acquire.parse_thread(node(body=body), FIRST)
    asset, = post["attachments"]
    assert asset["kind"] == "video"
    assert asset["source_url"] == high
    assert asset["variants"] == [low, high, mid]
    assert asset["poster_url"].endswith("poster.jpg")


def test_video_poster_alone_is_not_a_recording():
    body = '<div class="entity-video"><video poster="https://pbs.twimg.com/ext_tw_video_thumb/123/pu/img/poster.jpg"></video></div>'
    with pytest.raises(ValueError, match="no explicit MP4"):
        acquire.parse_thread(node(body=body), FIRST)


def test_malicious_unselected_video_variant_is_also_rejected():
    body = '<div class="entity-video"><video>'
    body += f'<source type="video/mp4" src="{VIDEO}">'
    body += '<source type="video/mp4" src="https://evil.example/1x1/fake.mp4"></video></div>'
    with pytest.raises(ValueError):
        acquire.parse_thread(node(body=body), FIRST)


@pytest.mark.parametrize("url,media", [
    ("http://threadreaderapp.com/thread/1668916665550094339.html", False),
    ("https://threadreaderapp.com.evil.example/thread/1668916665550094339.html", False),
    ("https://user:password@threadreaderapp.com/thread/1668916665550094339.html", False),
    ("https://threadreaderapp.com:444/thread/1668916665550094339.html", False),
    ("https://threadreaderapp.com/thread/123.html", False),
    ("https://threadreaderapp.com/login", False),
    ("https://threadreaderapp.com/thread/../login", False),
    ("https://threadreaderapp.com/thread/%2e%2e/login", False),
    ("https://pbs.twimg.com/profile_images/123/avatar.jpg", True),
    ("https://pbs.twimg.com/not-a-media-attachment.jpg", True),
    ("https://video.twimg.com/not-a-recording.mp4", True),
    ("https://video.twimg.com/ext_tw_video/123/pu/vid/640x360/clip.html", True),
    ("https://video.twimg.com/ext_tw_video/123/../../private/clip.mp4", True),
    ("file:///tmp/legacy.jpg", True),
    ("https://pbs.twimg.com.evil.example/media/forged.jpg", True),
    ("https://user:password@pbs.twimg.com/media/forged.jpg", True),
])
def test_allowlist_rejects_uncommissioned_pages_and_non_attachment_media_paths(url, media):
    with pytest.raises(ValueError):
        acquire.allowed_url(url, media=media)


@pytest.mark.parametrize("url,media", [(PAGE, False), (acquire.source_url(SECOND), False), (IMAGE, True), (VIDEO, True)])
def test_allowlist_accepts_commissioned_sources_and_explicit_cdn_attachments(url, media):
    assert acquire.allowed_url(url, media=media) == url


class Response:
    def __init__(self, data=b"source", *, status=200, location=None, content_type="text/html"):
        self.data = data
        self.status_code = status
        self.is_redirect = location is not None
        self.headers = {"Content-Type": content_type}
        if location is not None:
            self.headers["Location"] = location

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, size):
        for i in range(0, len(self.data), 3):
            yield self.data[i:i + 3]


class Session:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_bounded_fetch_records_actual_bytes_hash_and_uses_get_without_automatic_redirects(tmp_path):
    target = tmp_path / "evidence.html"
    session = Session(Response(b"exact original bytes"))
    receipt = acquire.fetch(PAGE, target, session=session)
    assert target.read_bytes() == b"exact original bytes"
    assert receipt["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert receipt["bytes"] == target.stat().st_size
    assert receipt["requested_url"] == PAGE == receipt["final_url"]
    assert session.calls[0][1]["allow_redirects"] is False
    assert not target.with_suffix(".html.part").exists()


@pytest.mark.parametrize("location", ["https://evil.example/replacement", "http://threadreaderapp.com/thread/1668916665550094339.html", "/login", "/thread/123.html"])
def test_redirects_are_rejected_before_contacting_unapproved_destination(tmp_path, location):
    session = Session(Response(location=location))
    with pytest.raises(ValueError):
        acquire.fetch(PAGE, tmp_path / "evidence.html", session=session)
    assert len(session.calls) == 1
    assert not (tmp_path / "evidence.html").exists()


def test_media_redirect_cannot_change_to_unrelated_host(tmp_path):
    session = Session(Response(location="https://commons.wikimedia.org/old-film.jpg"))
    with pytest.raises(ValueError):
        acquire.fetch(IMAGE, tmp_path / "photo.jpg", media=True, session=session)
    assert len(session.calls) == 1


def test_byte_limit_preserves_prior_evidence_and_removes_partial_download(tmp_path):
    target = tmp_path / "evidence.html"
    target.write_bytes(b"previous evidence")
    with pytest.raises(ValueError, match="byte limit"):
        acquire.fetch(PAGE, target, session=Session(Response(b"long replacement")), max_bytes=5)
    assert target.read_bytes() == b"previous evidence"
    assert not target.with_suffix(".html.part").exists()


def test_http_failure_never_overwrites_retained_evidence(tmp_path):
    target = tmp_path / "evidence.html"
    target.write_bytes(b"previous evidence")
    with pytest.raises(requests.HTTPError):
        acquire.fetch(PAGE, target, session=Session(Response(status=403)))
    assert target.read_bytes() == b"previous evidence"


def test_redirect_loop_has_finite_bound(tmp_path):
    session = Session(*(Response(location=PAGE) for _ in range(4)))
    with pytest.raises(ValueError, match="too many"):
        acquire.fetch(PAGE, tmp_path / "evidence.html", session=session)
    assert len(session.calls) == 4


@pytest.mark.parametrize("value", ["../outside.jpg", "/tmp/uncommissioned.jpg", "two_thread/../../outside.jpg"])
def test_production_paths_cannot_escape_root(tmp_path, value):
    with pytest.raises(ValueError, match="outside production root"):
        acquire.safe_path(tmp_path, value)


def test_symlink_cannot_escape_production_root(tmp_path):
    outside = tmp_path.parent / "outside-media"
    outside.mkdir(exist_ok=True)
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        acquire.safe_path(tmp_path, "escape/photo.jpg")


def test_failed_asset_is_a_collection_blocker_with_exact_post_and_url():
    collection = verified_collection()
    assert acquire.missing_items(collection) == []
    asset = collection["threads"][0]["posts"][0]["attachments"][0]
    asset.update(download_status="failed", error="HTTPError: 403")
    missing = acquire.missing_items(collection)
    assert len(missing) == 1
    assert asset["id"] in missing[0]
    assert asset["source_url"] in missing[0]
    assert "post 1" in missing[0]
    assert "403" in missing[0]


def test_missing_entire_thread_does_not_invent_asset_count():
    missing = acquire.missing_items({"threads": [{"id": FIRST, "error": "HTTPError: 403", "posts": []}]})
    assert len(missing) == 2
    assert all("attachment URLs and count unknown" in line for line in missing)
    assert "403" in missing[0]


def test_missing_post_is_not_silently_accepted_as_complete():
    collection = verified_collection()
    collection["threads"][0]["posts"].pop()
    assert any("parsed 27 posts" in m for m in acquire.missing_items(collection))


def test_missing_attachment_with_unchanged_post_count_is_not_complete():
    collection = verified_collection()
    collection["threads"][0]["posts"][0]["attachments"].pop()
    missing = acquire.missing_items(collection)
    assert any(FIRST in m and "attachment" in m.lower() for m in missing)


def test_corrupt_download_is_failed_instead_of_claiming_source_complete(tmp_path, monkeypatch):
    asset = acquire.parse_thread(node(body=image_entity()), FIRST)[0]["attachments"][0]

    def corrupt_fetch(url, target, **kwargs):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(b"<html>Access denied</html>")
        return {"status": 200}

    monkeypatch.setattr(acquire, "fetch", corrupt_fetch)
    result = acquire.acquire_asset(asset, tmp_path)
    assert result["download_status"] == "failed"
    assert "sha256" not in result


def png_bytes(color="red"):
    output = BytesIO()
    Image.new("RGB", (20, 30), color).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("previous_kind", ["missing", "wrong-url", "wrong-hash", "failed-status", "unproven-retrieval"])
def test_cache_requires_matching_source_receipt_and_bytes(tmp_path, monkeypatch, previous_kind):
    asset = acquire.parse_thread(node(body=image_entity()), FIRST)[0]["attachments"][0]
    target = tmp_path / asset["local_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(png_bytes("red"))
    previous = {**asset, "sha256": acquire.digest(target), "download_status": "downloaded",
                "retrieval": {"status": 200, "requested_url": acquire.download_url(asset)}}
    if previous_kind == "missing":
        previous = None
    elif previous_kind == "wrong-url":
        previous["source_url"] = "https://pbs.twimg.com/media/unrelated.jpg"
    elif previous_kind == "wrong-hash":
        previous["sha256"] = "0" * 64
    elif previous_kind == "failed-status":
        previous["download_status"] = "failed"
    elif previous_kind == "unproven-retrieval":
        previous["retrieval"]["status"] = "cached-byte-verification"
    calls = []

    def sourced_fetch(url, destination, **kwargs):
        calls.append((url, kwargs))
        Path(destination).write_bytes(png_bytes("blue"))
        return {"status": 200, "requested_url": url, "final_url": url}

    monkeypatch.setattr(acquire, "fetch", sourced_fetch)
    result = acquire.acquire_asset(asset, tmp_path, previous=previous)
    assert result["download_status"] == "downloaded"
    assert len(calls) == 1
    assert calls[0][0] == IMAGE + "?name=orig"
    assert calls[0][1]["media"] is True
    assert target.read_bytes() == png_bytes("blue")


def test_proven_unchanged_cache_retains_original_receipt_and_avoids_network(tmp_path, monkeypatch):
    asset = acquire.parse_thread(node(body=image_entity()), FIRST)[0]["attachments"][0]
    target = tmp_path / asset["local_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(png_bytes())
    original = acquire.download_url(asset)
    receipt = {"status": 200, "requested_url": original, "final_url": original, "retrieved_at": "2026-10-27T12:00:00Z"}
    previous = {**asset, "sha256": acquire.digest(target), "download_status": "downloaded", "retrieval": receipt}

    def no_fetch(*args, **kwargs):
        pytest.fail("Unchanged source receipt should permit verified cached bytes")

    monkeypatch.setattr(acquire, "fetch", no_fetch)
    result = acquire.acquire_asset(asset, tmp_path, previous=previous)
    assert result["retrieval"] == receipt
    assert result["download_status"] == "downloaded"
    assert result["width"] == 20 and result["height"] == 30
    assert result["cache_verified_at"]


def test_corrupt_refresh_preserves_previously_retained_source_bytes(tmp_path, monkeypatch):
    asset = acquire.parse_thread(node(body=image_entity()), FIRST)[0]["attachments"][0]
    target = tmp_path / asset["local_path"]
    target.parent.mkdir(parents=True)
    retained = png_bytes()
    target.write_bytes(retained)
    previous = {**asset, "sha256": acquire.digest(target), "download_status": "downloaded", "retrieval": {"status": 200}}

    def unavailable_source(url, destination, **kwargs):
        Path(destination).write_bytes(b"<html>browser challenge</html>")
        return {"status": 200}

    monkeypatch.setattr(acquire, "fetch", unavailable_source)
    result = acquire.acquire_asset(asset, tmp_path, previous=previous, refresh=True)
    assert result["download_status"] == "failed"
    assert target.read_bytes() == retained
    assert not target.with_suffix(target.suffix + ".download").exists()


def test_lower_resolution_receipt_forces_original_image_refetch(tmp_path, monkeypatch):
    asset = acquire.parse_thread(node(body=image_entity()), FIRST)[0]["attachments"][0]
    target = tmp_path / asset["local_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(png_bytes("red"))
    previous = {**asset, "sha256": acquire.digest(target), "download_status": "downloaded",
                "retrieval": {"status": 200, "requested_url": IMAGE, "final_url": IMAGE}}
    requests_made = []

    def original_fetch(url, destination, **kwargs):
        requests_made.append(url)
        output = BytesIO()
        Image.new("RGB", (40, 60), "blue").save(output, format="PNG")
        Path(destination).write_bytes(output.getvalue())
        return {"status": 200, "requested_url": url, "final_url": url}

    monkeypatch.setattr(acquire, "fetch", original_fetch)
    result = acquire.acquire_asset(asset, tmp_path, previous=previous)
    assert requests_made == [IMAGE + "?name=orig"]
    assert result["source_url"] == IMAGE  # Exact attachment membership is unchanged.
    assert result["retrieval"]["requested_url"] == IMAGE + "?name=orig"
    assert result["download_status"] == "downloaded"
    assert (result["width"], result["height"]) == (40, 60)
    assert "cache_verified_at" not in result


@pytest.mark.parametrize("source,expected", [
    (IMAGE, IMAGE + "?name=orig"),
    (IMAGE + "?name=small", IMAGE + "?name=orig"),
    (IMAGE + "?format=jpg&name=large", IMAGE + "?format=jpg&name=orig"),
])
def test_original_image_variant_preserves_exact_media_path_and_other_query_fields(source, expected):
    asset = {"kind": "image", "source_url": source}
    assert acquire.download_url(asset) == expected
    assert asset["source_url"] == source
    assert acquire.allowed_url(expected, media=True) == expected


def test_recording_url_is_never_replaced_by_image_variant_or_poster():
    assert acquire.download_url({"kind": "video", "source_url": VIDEO}) == VIDEO


def source_bound_collection(tmp_path):
    collection = verified_collection()
    collection.update(complete=True, missing=[])
    for thread in collection["threads"]:
        thread["html_path"] = f"two_thread/evidence/{thread['id']}.html"
        raw = tmp_path / thread["html_path"]
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(snapshot(thread["id"]), encoding="utf-8")
        thread["html_sha256"] = acquire.digest(raw)
    return collection


def test_render_manifest_is_bound_to_retained_root_posts_and_exact_attachments(tmp_path):
    collection = source_bound_collection(tmp_path)
    assert acquire.verify_collection_sources(tmp_path, collection) is True


@pytest.mark.parametrize("field,value", [
    ("id", "9999999999999999999"),
    ("ordinal", 4),
    ("text", "Fabricated replacement assertion"),
    ("tweet_url", "https://x.com/unrelated/status/123"),
])
def test_render_manifest_cannot_rewrite_original_post_evidence(tmp_path, field, value):
    collection = source_bound_collection(tmp_path)
    collection["threads"][0]["posts"][0][field] = value
    with pytest.raises(ValueError, match="differs from actual source"):
        acquire.verify_collection_sources(tmp_path, collection)


@pytest.mark.parametrize("field,value", [
    ("id", "substitute"),
    ("kind", "video"),
    ("source_url", "https://pbs.twimg.com/media/unrelated.jpg"),
    ("variants", ["https://pbs.twimg.com/media/unrelated.jpg"]),
    ("local_path", "assets/visuals/old-film.jpg"),
])
def test_allowed_cdn_host_does_not_permit_substituting_unrelated_content(tmp_path, field, value):
    collection = source_bound_collection(tmp_path)
    collection["threads"][0]["posts"][0]["attachments"][0][field] = value
    with pytest.raises(ValueError, match="differs from actual source"):
        acquire.verify_collection_sources(tmp_path, collection)


def test_retained_html_mutation_is_rejected_before_render(tmp_path):
    collection = source_bound_collection(tmp_path)
    raw = tmp_path / collection["threads"][0]["html_path"]
    raw.write_text(raw.read_text() + "<!-- changed -->", encoding="utf-8")
    with pytest.raises(ValueError, match="HTML source hash mismatch"):
        acquire.verify_collection_sources(tmp_path, collection)


@pytest.mark.parametrize("tamper", ["third-thread", "duplicate-thread", "different-html-path", "different-thread-url", "incomplete"])
def test_source_binding_requires_exactly_the_commissioned_complete_collections(tmp_path, tamper):
    collection = source_bound_collection(tmp_path)
    if tamper == "third-thread":
        extra = copy.deepcopy(collection["threads"][0])
        extra["id"] = "123"
        collection["threads"].append(extra)
    elif tamper == "duplicate-thread":
        collection["threads"].append(copy.deepcopy(collection["threads"][0]))
    elif tamper == "different-html-path":
        collection["threads"][0]["html_path"] = "old-project/research.html"
    elif tamper == "different-thread-url":
        collection["threads"][0]["url"] = "https://threadreaderapp.com/thread/123.html"
    else:
        collection["complete"] = False
    with pytest.raises(ValueError):
        acquire.verify_collection_sources(tmp_path, collection)


def test_inventory_preserves_verbatim_claims_and_marks_missing_recording(tmp_path):
    collection = verified_collection()
    post = next(p for p in collection["threads"][0]["posts"] if any(a["kind"] == "video" for a in p["attachments"]))
    asset = next(a for a in post["attachments"] if a["kind"] == "video")
    asset.update(download_status="failed", error="HTTPError: unavailable recording")
    out = tmp_path / "inventory.md"
    acquire.write_inventory(collection, out)
    text = out.read_text()
    assert post["text"] in text
    assert asset["id"] in text
    assert asset["source_url"] in text
    assert "unavailable recording" in text
    assert "not independent authentication" in text
    assert "No missing primary attachments" not in text


def test_main_cannot_report_success_when_source_pages_fail(tmp_path, monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise requests.HTTPError("403 source unavailable")

    monkeypatch.setattr(acquire, "fetch", denied)
    assert acquire.main(["--root", str(tmp_path)]) == 2
    import json
    collection = json.loads((tmp_path / "two_thread/collection.json").read_text())
    assert collection["complete"] is False
    assert len(collection["missing"]) == 2
    assert "complete\": false" in capsys.readouterr().out
    assert (tmp_path / "two_thread/MISSING-ASSETS.md").is_file()


def test_http_200_challenge_preserves_retained_html_and_reports_blocked_collection(tmp_path, monkeypatch):
    retained = {}
    for thread in acquire.THREADS:
        raw = tmp_path / "two_thread/evidence" / f"{thread}.html"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(snapshot(thread), encoding="utf-8")
        retained[raw] = raw.read_bytes()
    seen = []

    def challenge(url, destination, **kwargs):
        seen.append(url)
        Path(destination).write_text("<html><title>Just a moment</title>Browser challenge</html>", encoding="utf-8")
        return {"status": 200, "requested_url": url, "final_url": url}

    def no_assets(*args, **kwargs):
        pytest.fail("Challenge HTML must block acquisition before any attachment request")

    monkeypatch.setattr(acquire, "fetch", challenge)
    monkeypatch.setattr(acquire, "acquire_asset", no_assets)
    assert acquire.main(["--root", str(tmp_path)]) == 2
    assert seen == [acquire.source_url(t) for t in acquire.THREADS]
    assert all(raw.read_bytes() == original for raw, original in retained.items())
    import json
    collection = json.loads((tmp_path / "two_thread/collection.json").read_text())
    assert collection["complete"] is False
    assert len(collection["missing"]) == 2
    assert all("incorrect thread root" in t["error"] for t in collection["threads"])
