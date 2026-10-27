#!/usr/bin/env python3
"""Acquire and verify the original-source media for the distinct Iran–Iraq film.

No generated, illustrative or replacement historical media are permitted.
An unavailable or uncleared source is a hard failure, never a generic substitute.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "original"
OUT.mkdir(parents=True, exist_ok=True)
USER_AGENT = "IraqHistoricalDocumentaryStudio/1.0 (+https://github.com/Asadi123/the-resurrection; documentary source audit)"
S = requests.Session()
S.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
FILES = [
    # Publicly catalogued archival films, rather than AI reproductions.
    ("abadan-1980", "Siege of Abadan, Iran–Iraq War.webm", "video"),
    ("andimeshk-1986", "Andimeshk-25november.webm", "video"),
    ("khamenei-1986", "Ali Khamenei, Khutbah of Tehran Jumu'ah Prayer - 14 February 1986.webm", "video"),
    ("tehran-airport-1980", "Iran Iraq War Start Attack on Tehran Airport 1980-09-22.jpg", "image"),
]
PDFS = [
    ("un-479-1980", "https://digitallibrary.un.org/record/16029/files/S_RES_479%281980%29-EN.pdf"),
    ("un-sg-1980", "https://digitallibrary.un.org/record/16000/files/S_14205-EN.pdf"),
    ("un-598-1987", "https://digitallibrary.un.org/record/137345/files/S_RES_598%281987%29-EN.pdf"),
]

def fetch(url, timeout=100):
    last = None
    for attempt in range(3):
        try:
            r = S.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Source not downloadable: {url} ({last})")

def download(url, dest, prefix=None):
    if dest.is_file() and dest.stat().st_size:
        data = dest.read_bytes()
    else:
        data = fetch(url, timeout=240).content
        dest.write_bytes(data)
    if prefix and not data.startswith(prefix):
        raise ValueError(f"Source is not the expected file type: {dest.name}")
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

def main():
    entries = []
    errors = []
    for asset_id, filename, kind in FILES:
        try:
            result = fetch("https://commons.wikimedia.org/w/api.php", timeout=45) if False else None
            q = S.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "prop": "imageinfo",
                "iiprop": "url|size|extmetadata", "titles": "File:" + filename}, timeout=45)
            q.raise_for_status()
            pages = q.json()["query"]["pages"]
            page = next(iter(pages.values()))
            ii = page.get("imageinfo", [])
            if not ii:
                raise ValueError("No Commons imageinfo returned")
            info = ii[0]
            ex = info.get("extmetadata") or {}
            license_name = (ex.get("LicenseShortName") or {}).get("value", "")
            if not any(mark in license_name.lower() for mark in (
                "public domain", "cc by", "cc0", "pd-", "creative commons")):
                raise ValueError(f"Unverified reuse permission: {license_name!r}")
            url = info["url"]
            suffix = Path(filename).suffix.lower()
            target = OUT / (asset_id + suffix)
            metadata = download(url, target)
            if kind == "video" and metadata["bytes"] < 50000:
                raise ValueError("Archival video unexpectedly tiny")
            entries.append({
                "id": asset_id, "kind": kind, "title": filename,
                "source": "https://commons.wikimedia.org/wiki/File:" + quote(filename.replace(" ", "_")),
                "download_url": url, "date_context": "See original source page",
                "license_declared": license_name, "local_path": str(target.relative_to(ROOT)),
                **metadata
            })
            print("ACQUIRED", asset_id, metadata["bytes"], license_name, flush=True)
        except Exception as e:
            errors.append(f"{asset_id}: {type(e).__name__}: {e}")
            print("BLOCKED", errors[-1], file=sys.stderr, flush=True)

    for doc_id, url in PDFS:
        try:
            dest = OUT / (doc_id + ".pdf")
            metadata = download(url, dest, prefix=b"%PDF")
            entries.append({
                "id": doc_id, "kind": "original_un_document",
                "source": url, "archive": "UN Digital Library",
                "local_path": str(dest.relative_to(ROOT)), **metadata
            })
            print("ACQUIRED", doc_id, metadata["bytes"], flush=True)
        except Exception as e:
            errors.append(f"{doc_id}: {type(e).__name__}: {e}")
            print("BLOCKED", errors[-1], file=sys.stderr, flush=True)
    audit = {"status": "ready" if not errors else "blocked",
             "no_synthetic_visuals": True, "original_assets": entries, "errors": errors}
    (ROOT / "source-audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    print(json.dumps({"acquired": len(entries), "errors": errors}, indent=2), flush=True)
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
