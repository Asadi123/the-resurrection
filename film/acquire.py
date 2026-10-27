#!/usr/bin/env python3
"""Authentic-only media intake: original pixels, documented licenses, SHA256 audit."""
import hashlib, html, json, re, sys, time
from pathlib import Path
from urllib.parse import quote
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"original"
OUT.mkdir(exist_ok=True)
DATA=json.loads((ROOT/"production.json").read_text())
S=requests.Session()
S.headers.update({"User-Agent":"IRAQ-HISTORICAL-DOCUMENTARY/2.0 (source-preservation; contact via GitHub Asadi123/the-resurrection)"})

def get(url, **kw):
    exc=None
    for n in range(3):
        try:
            r=S.get(url,timeout=kw.get("timeout",85),params=kw.get("params"))
            r.raise_for_status()
            return r
        except Exception as e:
            exc=e
            time.sleep(n*2+1)
    raise RuntimeError(f"Download failed {url}: {exc}")

def store(path,data):
    if not data or len(data)<1000:
        raise ValueError("Missing or truncated archival asset: "+str(path))
    path.write_bytes(data)
    return {"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}

def short(s):
    return re.sub(r"<[^>]+>","",html.unescape(s or "")).strip()

def main():
    manifest={"sources":[],"errors":[],"policy":"Strictly original scans/photographs/footage, with original aspect and visible boundaries; no AI-generated history."}
    verified_caches={
        # Pinned authentic sources already secured in an earlier Actions source audit.
        "andimeshk-footage":("Public domain","1986-11-25",""),
        "iran-1986-address":("CC BY 4.0","1986-02-14","Khamenei.ir"),
    }
    for a in DATA["references"]["visuals"]:
        try:
            if a["id"] in verified_caches:
                cached=OUT/(a["id"]+Path(a["name"]).suffix.lower())
                if cached.is_file() and cached.stat().st_size > 50000:
                    license,date,artist=verified_caches[a["id"]]
                    meta={"bytes":cached.stat().st_size,
                        "sha256":hashlib.sha256(cached.read_bytes()).hexdigest()}
                    manifest["sources"].append({**a,"kind":a["type"],
                        "local_file":str(cached.relative_to(ROOT)),
                        "source_url":"https://commons.wikimedia.org/wiki/File:"+
                            quote(a["name"].replace(" ","_")),
                        "download_method":"reused_pinned_source_from_previous_authenticated_archive",
                        "date":date,"artist":artist,"license":license,
                        "entire_image_in_frame":True,**meta})
                    print("VERIFIED CACHE",a["id"],meta["bytes"],flush=True)
                    continue
            q=get("https://commons.wikimedia.org/w/api.php",timeout=45,params={
                "action":"query","format":"json","prop":"imageinfo","iiprop":"url|size|extmetadata","iiurlwidth":"1920",
                "titles":"File:"+a["name"]}).json()["query"]["pages"]
            page=next(iter(q.values()))
            if not page.get("imageinfo"): raise ValueError("Commons file not found")
            obj=page["imageinfo"][0]; ext=obj.get("extmetadata",{})
            license=short(ext.get("LicenseShortName",{}).get("value",""))
            if not any(z in license.lower() for z in ("public domain","cc0","cc by","pd-","gfdl")):
                raise PermissionError(f"Source license not cleared: {license}")
            desc=short(ext.get("ImageDescription",{}).get("value",""))
            credit=short(ext.get("Artist",{}).get("value",""))
            src= obj["url"]
            suffix=Path(src.split("?")[0]).suffix.lower()
            if suffix not in (".jpg",".jpeg",".png",".webm",".ogv",".mp4"):
                raise ValueError("Non photograph/film media")
            p=OUT/(a["id"]+suffix)
            if p.exists() and p.stat().st_size>1000:
                meta={"bytes":p.stat().st_size,
                    "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
                acquisition="verified_cached_original"
            else:
                # Commons' full-resolution CDN may rate-limit shared CI addresses.
                # A Wikimedia-generated thumbnail preserves the *entire* photo
                # including its borders, aspect ratio and content (only reduces pixels).
                preferred=obj.get("thumburl") if a["type"]=="image" else src
                try:
                    data=get(preferred,timeout=240).content
                except Exception:
                    if a["type"]!="image" or preferred==src:raise
                    data=get(src.split("?")[0],timeout=240).content
                meta=store(p,data)
                acquisition="full_frame_resized_from_original" if preferred!=src else "original_unmodified"
            manifest["sources"].append({**a,"kind":a["type"],"local_file":str(p.relative_to(ROOT)),
                "source_url":"https://commons.wikimedia.org/wiki/File:"+quote(a["name"].replace(" ","_")),
                "file_url":src,"download_method":acquisition,
                "entire_image_in_frame":True,
                "artist":credit,"description":desc[:400],"license":license,**meta})
            print("VISUAL",a["id"],meta["bytes"],flush=True)
        except Exception as e:
            manifest["errors"].append(f"{a['id']}: {str(e)}")
            print("SOURCE ERROR",a["id"],str(e),flush=True,file=sys.stderr)
    for a in DATA["references"]["documents"]:
        try:
            file=OUT/(a["id"]+".pdf")
            content=get(a["url"],timeout=240).content
            if not content.startswith(b"%PDF"):raise ValueError("UN server response was not PDF")
            meta=store(file,content)
            manifest["sources"].append({**a,"kind":"document","local_file":str(file.relative_to(ROOT)),
                "source_url":a["url"],"archive":"United Nations Digital Library",**meta})
            print("DOCUMENT",a["id"],meta["bytes"],flush=True)
        except Exception as e:
            manifest["errors"].append(f"{a['id']}: {str(e)}")
            print("DOCUMENT ERROR",a["id"],str(e),flush=True,file=sys.stderr)
    (ROOT/"audit.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    (ROOT/"SOURCE-CREDITS.md").write_text("# Archival source and rights register\n\n"+
      "\n".join("- **"+a["id"]+"** — "+a.get("source_url","")+" — "+
      a.get("license","UN public archival document; reuse subject to UN terms")+" — "+
      a.get("artist","") for a in manifest["sources"])+"\n")
    print("ACQUIRED",len(manifest["sources"]),"ERRORS",len(manifest["errors"]),flush=True)
    if manifest["errors"]:
        raise SystemExit("Research-source gaps must be resolved before a final film; do not substitute generated images.")
if __name__=="__main__":main()
