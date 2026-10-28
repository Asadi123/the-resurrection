# Existing documentary branch inspection

Reviewed read-only on 2026-10-27. All three requested branches exist in `Asadi123/the-resurrection` and contain working-project source files. No branch was checked out, changed, reset, deleted or overwritten during this review. Counts below are tracked paths at the named commit, including inherited files.

| Preserved branch | Exact inspected commit | Tracked paths |
| --- | --- | ---: |
| `feature/iran-iraq-war-archival-v2` | `540c2a9e63777637a6791771d6a2c2d54c9e851b` | 113 |
| `documentary/iran-iraq-war-rebuild` | `bb6eb09e94de4e86553291312766f1e0025da475` | 116 |
| `documentary/iraq-iran-war-new-film` | `4af186819ea94f460c92a766542fea7d62ae2dd0` | 118 |

## Archival V2

Distinct implementation: `iran_iraq_v2/build.py`; workflow `.github/workflows/iran-iraq-war-v2.yml`.

The builder downloads seven document-image URLs from `pbs.twimg.com/media` (`FykVBoMWcAMSzso`, `FykeHQhWAAEHzyz`, `Fykg9YPWwAI7coV`, `Fykh8B5WcAYJw45`, `FykiJ1XWYAIUvVi`, `FykkTtZXwAE1kxt`, `Fykk4HkWcAUYjQr`) and a video-thumbnail URL associated with tweet `1668890627482820609`. These are useful recovery leads only: each must be matched to an actual post in one of the two authorized threads before new-film use. A thumbnail is not the attached recording.

Its `SOURCE` dictionary also includes two Wikimedia maps. Its scripted beats introduce United Nations resolutions and broader claims, while its closing source text includes UN URLs. These materials do not meet the new two-thread-only restriction unless the exact item is independently shown in the authorized collections. The renderer crops source pages for close-ups and some title compositions, outputs 1280×720, uses Edge neural TTS and generates an atmospheric score. Do not run it unchanged for the new commission.

Reusable technical ideas: checked subprocess execution, duration probing, per-shot FFmpeg assembly, concatenation, and MP4 `+faststart`. It does not provide a complete attachment-by-attachment inventory or immutable download-byte audit.

## Iran–Iraq rebuild

Distinct files: `iran-iraq-war/prepare_sources.py`, `render.py`, `narration.txt`, `research/source-register.json`; workflow `.github/workflows/iran-iraq-war.yml`.

Acquisition explicitly selects Commons archival videos/images and five UN PDFs. They are authentic-source candidates for that older production, but authenticity alone does not establish membership in the two newly authorized threads. Its source register treats the threads as leads and includes outside sources. The narration and selected historical assets must not flow into the new edit by default.

Reusable implementation patterns: SHA-256/byte-count records, source-audit fail-closed gate, 1920×1080 at 30fps, Pillow `ImageOps.contain`, FFmpeg proportional `scale` plus centered `pad`, `setsar=1`, source-duration checks, H264/AAC fast-start output, duration QA and Actions diagnostic artifacts. It deliberately fails for missing human-sounding narration rather than silently reusing old synthetic narration. Its UN-specific document-page lookup and historical text are content, not reusable general evidence.

## New-film branch

Distinct files: `film/acquire.py`, `edit.py`, `narrate.py`, `production.json`; workflows `.github/workflows/eight-year-front.yml` and `publish-eight-year-front.yml`.

`production.json` selects twelve Commons photographs/videos and five UN PDFs. The two X threads are described as internal research inputs; their individual attachments are not its exclusive historical archive. `acquire.py` can reuse prior artifacts and query Commons; the render workflow also copies historical cached media from fixed prior run IDs. This path must stay isolated from the new acquisition pipeline. Its narrator uses Pocket TTS (`peter_yearsley`), whose naturalness is not established by code or technical MP4 validation; the old narration is also excluded by the present source restriction. The user prohibits a robotic narrator, not necessarily every synthetic voice.

Reusable technical patterns: retries, original-byte hashing, explicit errors, contain/pad composition, intact image boundaries, 1080p H264/AAC verification, caption-track generation with human synchronization caveat, source-duration bounds, MP4 decode validation, QA contact-sheet frames, and authenticated artifact upload. The publisher demonstrates a direct GitHub Release MP4 download, but pins an old run and uses release `--clobber`; new publication must use a new tag/file and must not replace the old films.

## Isolation requirements for the separate branch

Keep all old assets, configurations, workflows, caches, prior films and branches intact. The new pipeline should have its own directory, source manifests and outputs. Its only historical discovery roots are the two specified Thread Reader pages; legitimate mirrors may recover the same posts and attachments, not add historical subjects. Every renderable media item needs a thread/post/attachment identity, exact URL, original-byte hash, retrieval status and visible attribution. Do not treat author assertions or OCR as independently established facts. Require complete collection acquisition before calling a render the finished film. Missing source pages, videos or post mappings must remain explicit blockers, not generic-slide or unrelated-footage replacements.
