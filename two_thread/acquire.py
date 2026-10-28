"""Acquire only the two commissioned threads and their explicit attachments.

No guessed tweets, recommendation cards, historical replacements, login bypass,
scraping of private APIs, or traversal of unrelated links. Retain original HTML,
each explicit video variant, source attribution and byte-level evidence.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from PIL import Image
import requests

ROOT = Path(__file__).resolve().parents[1]
THREADS = {"1668916665550094339": 28, "1986782578565579207": 44}
ATTACHMENT_COUNTS = {"1668916665550094339": 37, "1986782578565579207": 61}
MEDIA_HOSTS = {"pbs.twimg.com", "video.twimg.com"}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_path(root, value):
    p = (Path(root) / value).resolve()
    if not p.is_relative_to(Path(root).resolve()):
        raise ValueError("path outside production root")
    return p


def source_url(thread):
    if thread not in THREADS:
        raise ValueError("uncommissioned thread")
    return f"https://threadreaderapp.com/thread/{thread}.html"


def allowed_url(url, *, media=False):
    u = urlsplit(url)
    hosts = MEDIA_HOSTS if media else {"threadreaderapp.com"}
    if u.scheme != "https" or u.hostname not in hosts or u.username or u.password or u.port not in (None, 443):
        raise ValueError("URL outside explicit public-source allowlist")
    if u.fragment:
        raise ValueError("source URL must not contain a fragment")
    if not media:
        if u.query or u.path not in {f"/thread/{t}.html" for t in THREADS}:
            raise ValueError("uncommissioned Thread Reader page")
    elif u.hostname == "pbs.twimg.com":
        if not re.fullmatch(r"/media/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)", u.path):
            raise ValueError("not an explicit thread image")
    elif not re.fullmatch(r"/(?:ext_tw_video|amplify_video)/[0-9]+/(?:pu/)?vid/(?:avc1/)?[0-9]+x[0-9]+/[A-Za-z0-9_-]+\.mp4", u.path):
        raise ValueError("not an explicit attached MP4")
    return url


def fetch(url, target, *, media=False, session=None, max_bytes=256 * 1024 * 1024):
    """Bounded TLS GET. Validate every redirect before following it."""
    client = session or requests.Session()
    current = allowed_url(url, media=media)
    for _ in range(4):
        with client.get(current, timeout=(15, 90), stream=True, allow_redirects=False,
                        headers={"User-Agent": "TheResurrection-SourceInventory/1.0"}) as r:
            if r.is_redirect:
                from urllib.parse import urljoin
                current = allowed_url(urljoin(current, r.headers["Location"]), media=media)
                continue
            r.raise_for_status()
            target = Path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(target.suffix + ".part")
            count = 0
            try:
                with temp.open("wb") as f:
                    for block in r.iter_content(128 * 1024):
                        count += len(block)
                        if count > max_bytes:
                            raise ValueError("source exceeds configured byte limit")
                        f.write(block)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
            return {"requested_url": url, "final_url": current, "status": r.status_code,
                    "content_type": r.headers.get("Content-Type", ""), "bytes": count,
                    "retrieved_at": now(), "sha256": digest(target)}
    raise ValueError("too many source redirects")


def video_area(url):
    matches = re.findall(r"/(\d+)x(\d+)/", urlsplit(url).path)
    return int(matches[-1][0]) * int(matches[-1][1]) if matches else 0


def download_url(asset):
    # Public original-size CDN variant of the exact image explicitly linked by
    # the thread. The default URL can downsample tall pages to 1200 pixels.
    if asset["kind"] == "image":
        from urllib.parse import parse_qsl, urlencode, urlunsplit
        u = urlsplit(asset["source_url"])
        query = dict(parse_qsl(u.query))
        query["name"] = "orig"
        return urlunsplit((u.scheme, u.netloc, u.path, urlencode(query), ""))
    return asset["source_url"]


def parse_thread(html, thread):
    """Select root tweet nodes only: recommendations lack data-tweet."""
    source_url(thread)
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select(".content-tweet[data-tweet]")
    if not nodes or nodes[0].get("data-tweet") != thread:
        raise ValueError("missing or incorrect thread root; not a source collection")
    posts, seen = [], set()
    for ordinal, node in enumerate(nodes, 1):
        tweet = node.get("data-tweet", "")
        if not tweet.isdigit() or tweet in seen:
            raise ValueError("invalid or duplicate post ID")
        seen.add(tweet)
        screen = node.get("data-screenname", "")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,30}", screen):
            raise ValueError("missing source author")
        clone = BeautifulSoup(str(node), "html.parser")
        for x in clone.select(".tw-permalink, .entity-image, .entity-video, video"):
            x.decompose()
        text = clone.get_text(" ", strip=True)
        assets = []
        # DOM order matters for attachment-by-attachment accounting.
        for entity in node.select(".entity-image, .entity-video"):
            if entity.find_parent(class_="entity-video"):
                continue
            index = len(assets) + 1
            asset_id = f"{thread}-p{ordinal:02d}-a{index:02d}"
            if "entity-video" in entity.get("class", []):
                variants = list(dict.fromkeys(x.get("src") for x in entity.select('source[type="video/mp4"][src]')))
                if not variants:
                    raise ValueError(f"video has no explicit MP4 source: {asset_id}")
                for v in variants:
                    allowed_url(v, media=True)
                selected = max(variants, key=video_area)
                kind, suffix = "video", ".mp4"
                video = entity.find("video")
                poster = video.get("poster") if video else None
            else:
                a, img = entity.find("a"), entity.find("img")
                selected = a.get("href") if a else None
                selected = selected or (img.get("data-src") or img.get("src") if img else None)
                if not selected:
                    raise ValueError(f"image has no source URL: {asset_id}")
                allowed_url(selected, media=True)
                variants, kind, poster = [selected], "image", None
                suffix = Path(urlsplit(selected).path).suffix.lower()
                if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
                    suffix = ".jpg"
            assets.append({"id": asset_id, "kind": kind, "source_url": selected,
                           "variants": variants, "poster_url": poster,
                           "local_path": f"two_thread/assets/{thread}/{asset_id}{suffix}",
                           "download_status": "pending"})
        posts.append({"id": tweet, "ordinal": ordinal, "text": text,
                      "tweet_url": f"https://x.com/{screen}/status/{tweet}",
                      "links": list(dict.fromkeys(a["href"] for a in node.select('a[href]'))),
                      "attachments": assets})
    return posts


def inspect_media(path, kind):
    if kind == "image":
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return {"width": im.width, "height": im.height, "duration": None, "has_audio": False}
    p = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams",
                      "-show_format", "-of", "json", str(path)], text=True))
    video = next(s for s in p["streams"] if s["codec_type"] == "video")
    duration = float(p["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid video duration")
    return {"width": video["width"], "height": video["height"], "duration": duration,
            "has_audio": any(s["codec_type"] == "audio" for s in p["streams"])}


def acquire_asset(asset, root, *, refresh=False, previous=None):
    asset = dict(asset)
    target = safe_path(root, asset["local_path"])
    try:
        cached = (target.exists() and previous and previous.get("source_url") == asset["source_url"]
                  and previous.get("sha256") == digest(target)
                  and previous.get("download_status") == "downloaded"
                  and previous.get("retrieval", {}).get("status") == 200
                  and previous.get("retrieval", {}).get("requested_url") == download_url(asset))
        if not cached or refresh:
            downloaded = target.with_suffix(target.suffix + ".download")
            try:
                asset["retrieval"] = fetch(download_url(asset), downloaded, media=True)
                metadata = inspect_media(downloaded, asset["kind"])
                downloaded.replace(target)
            finally:
                downloaded.unlink(missing_ok=True)
        else:
            asset["retrieval"] = dict(previous["retrieval"])
            asset["cache_verified_at"] = now()
            metadata = inspect_media(target, asset["kind"])
        asset.update(metadata)
        asset.update(sha256=digest(target), bytes=target.stat().st_size, download_status="downloaded")
    except (requests.RequestException, ValueError, OSError, subprocess.SubprocessError, StopIteration, KeyError) as e:
        asset.update(download_status="failed", error=f"{type(e).__name__}: {e}")
    return asset


def missing_items(collection):
    missing = []
    by_id = {t["id"]: t for t in collection.get("threads", [])}
    for thread, expected in THREADS.items():
        t = by_id.get(thread)
        if not t or t.get("error"):
            missing.append(f"{thread}: entire thread body, post ordering/text, attachment URLs and count unknown; {t.get('error') if t else 'not acquired'}")
            continue
        count = len(t.get("posts", []))
        if count != expected:
            missing.append(f"{thread}: parsed {count} posts; prior verified collection contains {expected}; investigate source drift")
        attachment_count = sum(len(p["attachments"]) for p in t["posts"])
        if attachment_count != ATTACHMENT_COUNTS[thread]:
            missing.append(f"{thread}: parsed {attachment_count} attachments; verified source snapshot contains {ATTACHMENT_COUNTS[thread]}; investigate missing or changed entities")
        for post in t["posts"]:
            for asset in post["attachments"]:
                if asset.get("download_status") != "downloaded":
                    missing.append(f"{thread} post {post['ordinal']} {asset['id']}: {asset['kind']} {asset['source_url']} — {asset.get('error', 'not downloaded')}")
    return missing


def verify_collection_sources(root, collection):
    """Bind the renderer's manifest to exact retained public thread HTML.

    CDN-host membership alone cannot distinguish allowed from unrelated media.
    Require the original post ordering, text and each explicit media association.
    """
    if collection.get("complete") is not True or collection.get("missing") or missing_items(collection):
        raise ValueError("both source collections must be complete before rendering")
    if {t["id"] for t in collection.get("threads", [])} != set(THREADS) or len(collection["threads"]) != 2:
        raise ValueError("exactly two commissioned source collections required")
    for thread in collection["threads"]:
        if thread.get("url") != source_url(thread["id"]):
            raise ValueError("incorrect thread source URL")
        expected_path = f"two_thread/evidence/{thread['id']}.html"
        if thread.get("html_path") != expected_path:
            raise ValueError("incorrect raw source evidence path")
        raw = safe_path(root, expected_path)
        if digest(raw) != thread.get("html_sha256"):
            raise ValueError("raw HTML source hash mismatch")
        actual = parse_thread(raw.read_text(encoding="utf-8"), thread["id"])
        def membership(posts):
            return [(p['id'], p['ordinal'], p['text'], p['tweet_url'],
                     [(a['id'], a['kind'], a['source_url'], a['variants'], a['local_path']) for a in p['attachments']]) for p in posts]
        if membership(actual) != membership(thread['posts']):
            raise ValueError("manifest differs from actual source posts or attachment associations")
    return True


def write_inventory(collection, path):
    lines = ["# Exclusive-source attachment inventory", "",
             "Source reproductions are evidence of what the threads display, not independent authentication of the underlying historical assertions.", "",
             "All supplied image pixels are retained. Some source attachments are already excerpts; missing original full pages cannot be reconstructed.", ""]
    for t in collection["threads"]:
        lines += [f"## Thread {t['id']}", "", t["url"], "", f"HTML SHA256: `{t.get('html_sha256', 'not acquired')}`", ""]
        for p in t.get("posts", []):
            lines += [f"### Post {p['ordinal']} — {p['id']}", "", p["tweet_url"], "", p["text"] or "[No accompanying post text; no invented translation]", ""]
            for a in p["attachments"]:
                lines += [f"- `{a['id']}` — {a['kind']}, {a.get('width','?')}×{a.get('height','?')}, {a.get('duration') or 0}s, {a['download_status']}",
                          f"  Source: {a['source_url']}", f"  File: `{a['local_path']}`; SHA256: `{a.get('sha256','MISSING')}`; {a.get('bytes',0)} bytes."]
            lines += [""]
    missing = missing_items(collection)
    lines += ["## Missing material", ""] + ([f"- {m}" for m in missing] if missing else ["No missing primary attachments in the two retrieved Thread Reader collections (72 posts, 98 attachment associations)."])
    lines += ["", "Public Thread Reader HTML does not establish that deleted or omitted original X posts never existed. Video posters are previews; the actual attached MP4 recordings are inventoried instead. External URLs in post text remain citations, not permission to add their content.", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--snapshots", action="store_true", help="Parse retained HTML rather than fetching it again; still acquire/validate attachment bytes")
    parser.add_argument("--refresh-media", action="store_true")
    args = parser.parse_args(argv)
    base = args.root / "two_thread"
    (base / "evidence").mkdir(parents=True, exist_ok=True)
    collection = {"schema": 1, "acquired_at": now(), "historical_source_policy": "ONLY the two commissioned threads; no legacy historical content", "threads": []}
    previous = {}
    old_manifest = base / "collection.json"
    if old_manifest.exists():
        old = json.loads(old_manifest.read_text(encoding="utf-8"))
        previous = {a['id']: a for t in old.get('threads', []) for p in t.get('posts', []) for a in p.get('attachments', [])}
    for thread in THREADS:
        t = {"id": thread, "url": source_url(thread), "posts": []}
        raw = base / "evidence" / f"{thread}.html"
        try:
            if not args.snapshots:
                incoming = raw.with_suffix(".incoming.html")
                t["retrieval"] = fetch(t["url"], incoming, max_bytes=8 * 1024 * 1024)
                # A 200 challenge/login page is not a recovered thread. Keep the
                # last known source bytes intact when acquisition is blocked.
                parse_thread(incoming.read_text(encoding="utf-8"), thread)
                incoming.replace(raw)
            t["html_sha256"] = digest(raw)
            t["html_path"] = str(raw.relative_to(args.root))
            t["posts"] = parse_thread(raw.read_text(encoding="utf-8"), thread)
            refs = [(p, a) for p in t["posts"] for a in p["attachments"]]
            with ThreadPoolExecutor(max_workers=4) as pool:
                acquired = list(pool.map(lambda pair: acquire_asset(pair[1], args.root, refresh=args.refresh_media, previous=previous.get(pair[1]['id'])), refs))
            for (post, old), new in zip(refs, acquired):
                post["attachments"][post["attachments"].index(old)] = new
        except (requests.RequestException, ValueError, OSError) as e:
            t["error"] = f"{type(e).__name__}: {e}"
        collection["threads"].append(t)
    missing = missing_items(collection)
    collection.update(complete=not missing, missing=missing)
    (base / "collection.json").write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_inventory(collection, base / "INVENTORY.md")
    (base / "MISSING-ASSETS.md").write_text("# Source acquisition status\n\n" + ("\n".join(f"- {m}" for m in missing) if missing else "Both retrieved thread collections and all 98 primary attachment associations acquired. Some original pages are available only as the excerpts supplied by the threads; no unseen page content is claimed.") + "\n", encoding="utf-8")
    print(json.dumps({"complete": not missing, "posts": sum(len(t['posts']) for t in collection['threads']), "attachments": sum(len(p['attachments']) for t in collection['threads'] for p in t['posts']), "missing": missing}, ensure_ascii=False))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
