# THE RESURRECTION — البعث

An automated archival documentary production using Python and FFmpeg. The requested master is **160 seconds, 1920 × 1080, 30 FPS, H.264 MP4 with AAC audio**. Only authentic, rights-cleared historical imagery is eligible for the film.

**Finished video — Michael American narration:** [Download the validated MP4 artifact](https://github.com/Asadi123/the-resurrection/actions/runs/40495451476/artifacts/12730895116). Unzip it and open `output/the-resurrection.mp4`. The video is **160.000 seconds**, **1920 × 1080**, **30 FPS**, and **57,847,360 bytes**. [The successful GitHub Actions run](https://github.com/Asadi123/the-resurrection/actions/runs/40495451476) verifies full decoding, 4,800 frames, all 31 factual/source overlays, the Arabic ending, and black endpoints. This revision uses the user-selected Michael voice at natural speed, with full-passage synthesis and resynchronized factual corrections. Credits, licensing, provenance, and the validation report accompany the MP4. GitHub sign-in is required; this artifact is retained until November 26, 2026.

**A repository or a successful setup step is not a completed film.** The workflow publishes the `THE-RESURRECTION-1080p-160s` artifact only after acquisition, narration, music, editorial clearance, rendering, and export validation succeed. A failed run publishes diagnostics, not a substitute video. Current source gaps and unresolved claims are recorded in `research/` and the preflight report.

## Render from an iPhone

1. Open this repository in Safari and sign in to GitHub. If the **Actions** tab is hidden, use the repository's navigation menu or Safari's **Request Desktop Website** option.
2. Review [`research/fact-check.md`](research/fact-check.md), [`research/asset-manifest.json`](research/asset-manifest.json), and [`research/audio-rights.md`](research/audio-rights.md). Resolve the explicit missing inputs and editorial issues before treating an export as publishable.
3. To supply your own narration, use **Add file → Upload files** to add `assets/audio/uploaded-narration.wav` from the iPhone Files app. A mono 48 kHz/16-bit WAV under GitHub's browser upload limit works; a permitted HTTPS download URL for a larger recording can be supplied at dispatch. Also upload `config/uploaded-transcript.txt` containing the exact words and `config/uploaded-timing.json` containing each configured sentence's `source_start`/`source_end` times in the recording. Copy the expected wording from [`config/narration-transcript.txt`](config/narration-transcript.txt); use [`config/upload-timing-example.json`](config/upload-timing-example.json) for the timing file's format, replacing its sample times with your recording's measured times. This timing metadata allows synchronization without changing playback speed. Also upload `config/uploaded-audio-rights.json` with `creator`, `source_url`, `license`, `license_url`, `rights_confirmed: true`, and `sha256` for the actual recording. Compatible licenses and the rights-check format are documented in [`research/audio-rights.md`](research/audio-rights.md). All four files are required for an uploaded recording. An upload alone does not clear its rights or certify its wording.
4. Open **Actions → Render THE RESURRECTION → Run workflow**. Select `main`. Leave `narration_url` blank to use the configured permitted local voice or uploaded narration path. Enter an HTTPS URL if supplying the recording that way. Tap **Run workflow**.
5. Open the new run. If it fails, open the failed step and download **production-diagnostics** to see the real blocker. Missing rights, unsupported factual claims, unsuitable narration timing, and absent required music cause failure.
6. After a green run, scroll to **Artifacts**, tap **THE-RESURRECTION-1080p-160s**, and save the ZIP to Files. Uncompress it and open `the-resurrection.mp4` inside `output/`. Keep `CREDITS.md`, `FILM-LICENSE.md`, and the source manifests with any shared copy. GitHub requires sign-in to download workflow artifacts. Artifacts expire after 30 days; rerun the workflow to render a new copy.

All production and rendering run on GitHub's Linux runner. No local computer is required.

## Source and editorial records

- [`research/asset-manifest.json`](research/asset-manifest.json) records each eligible visual's original page, downloadable file, creator/archive, historical date, license, local filename, and SHA-256. It also records gaps. A source's historical date and reuse license must both be established.
- [`research/audio-assets.json`](research/audio-assets.json) and [`research/audio-rights.md`](research/audio-rights.md) record narration, voice-model, recording, and score rights.
- [`research/fact-check.md`](research/fact-check.md) checks the requested narration. The exact requested words are preserved in configuration; unresolved assertions are not silently presented as verified history.
- [`config/editorial-review.json`](config/editorial-review.json) controls factual publication clearance. Review fields are evidence records, not a switch to bypass fact-checking.
- `config/qa-review.json`, when required by preflight, records visual inspection of the Arabic title/end card. Automatic pixel checks establish that the encoded video matches the raster; a reviewer must still inspect the shaped Arabic lettering.

No image-generation or synthetic reenactment tool is used. Unavailable archival coverage remains a recorded gap. New photos require their own source record; an image being on the web does not establish reuse rights.

The cleared archival photographs and soundtrack recordings are included as a licensed production cache. This avoids repeated requests to archive servers; their original source URLs, conditions, and pinned hashes remain authoritative. Acquisition verifies the bundled bytes before use and only downloads an asset if it is missing. The Apache-2.0 Kokoro narration model is fetched separately; the verified Michael passage recordings are bundled so reruns preserve the approved voice.

The completed archival assembly is also cached at `assets/cache/assembly.mp4`. The renderer reuses it only after checking its SHA-256, film configuration, source-manifest fingerprint, frame count, duration, square pixels and color range. It then applies the measured corrections and mixes the final audio. Use `--rebuild-assembly` to regenerate the scenes; a changed film configuration or source manifest automatically bypasses the cache. Every scene and the final export use consistent BT.709 limited-range video and square pixels.

## Production sequence

The opening begins on black with three separate white text cards, then archival Baghdad and the bilingual opening title. The central sequence uses unique historical imagery, proportional full-frame crops, slow pans/zooms, restrained opening sepia, natural central colors, and warm closing grading. The ending fades to black, holds **أمة عربية واحدة ذات رسالة خالدة** in gold from 151 to 159 seconds, then fades to black by 160 seconds. The final card contains no English translation.

Narration timing is measured before assembly. Pauses and scene timings may change within the fixed master; playback rate and pitch are not distorted. The score remains beneath speech, with the required oud opening, Arabic orchestral build, percussion peak, and final oud note subject to actual audio rights and source availability.

## Files and commands

The same commands used by [GitHub Actions](.github/workflows/render.yml) are available for reproducibility:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/acquire_assets.py
python scripts/prepare_audio.py
python scripts/sync_editorial.py
python scripts/preflight.py --report output/preflight.json
python scripts/render.py --output output/the-resurrection.mp4
python scripts/validate.py output/the-resurrection.mp4
```

The runner needs `ffmpeg`, `ffprobe`, `fontconfig`, and DejaVu fonts; the workflow installs them only if the tools are absent. The Arabic Noto Naskh font and its license are bundled in `assets/fonts/`. Pillow renders Arabic with shaping support and a Noto Arabic font. The renderer records its FFmpeg commands in the output diagnostics. `python scripts/render.py --cards-only` generates text-card rasters for inspection without assembling or claiming a completed documentary.

The audio step supports `--narration /path/to/recording` and `--narration-url https://…`, or the `NARRATION_URL` environment variable. Follow `config/audio.json` and `config/narration.json` for the configured upload filename and exact timing limits. Local open-source TTS is eligible only with the recorded engine/model permissions; it is not a historical recording.

`scripts/validate.py` runs FFprobe's decoded frame count and a full FFmpeg decode. It checks exactly 4,800 frames, 160-second duration, 1920 × 1080 square pixels, 30 FPS, H.264, AAC, an audible audio stream, black opening/last frames, and the encoded Arabic hold against `output/cards/final.png`. It also checks the actual encoded glyphs and panels of all 18 factual corrections and 13 archival source labels, so creating text rasters alone cannot pass. The compositor decodes archival frames once, applies the active cached text masks with Pillow, and encodes the finished frames with FFmpeg in explicit BT.709 limited range. It reruns publication preflight. The machine-readable result is `output/validation.json`.

## Downloads and licensing

The completed MP4 is downloadable from the successful workflow run's artifact, not a GitHub source-code ZIP. A diagnostics artifact is not the film. Third-party archival and audio assets retain their individual licenses and credit requirements, as recorded in the manifests. The finished film must carry required attribution with its distribution; keep the source records with any shared copy.
