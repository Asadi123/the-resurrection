#!/usr/bin/env python3
"""Download only manifest-cleared archive assets; never search or substitute at render time."""
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'research' / 'asset-manifest.json'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def acquire(manifest=MANIFEST):
    document = json.loads(Path(manifest).read_text())
    for asset in document['assets']:
        if asset.get('rights_confirmed') is not True or asset.get('historical_authenticity') != 'confirmed':
            raise ValueError(f"Asset {asset['id']} is not cleared; refusing to download")
        filename = ROOT / asset['filename']
        if not filename.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Asset path escapes repository')
        expected = asset['sha256']
        if len(expected) != 64:
            raise ValueError(f"Asset {asset['id']} has no pinned SHA-256")
        if filename.exists():
            if sha256(filename) != expected:
                raise ValueError(f"Existing asset hash mismatch: {filename}")
            print(f"Verified {asset['id']}")
            continue
        filename.parent.mkdir(parents=True, exist_ok=True)
        temporary = filename.with_suffix(filename.suffix + '.part')
        request = urllib.request.Request(asset['download_url'], headers={'User-Agent': 'ResurrectionDocumentaryResearch/1.0 (archival reuse verification)'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    temporary.unlink(missing_ok=True)
                    raise
                time.sleep(2 ** attempt)
        if sha256(temporary) != expected:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"Downloaded asset hash mismatch: {asset['id']}")
        temporary.replace(filename)
        print(f"Downloaded and verified {asset['id']}")
    print(f"All {len(document['assets'])} cleared visual assets verified; {len(document.get('gaps', []))} documented coverage gaps")


if __name__ == '__main__':
    acquire()
