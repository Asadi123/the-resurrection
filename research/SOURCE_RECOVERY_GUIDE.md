# IRAN–IRAQ WAR — SOURCE AND WORKSPACE RECOVERY GUIDE
Verified project path: https://github.com/Asadi123/the-resurrection
Existing production branch: documentary/iraq-iran-war-new-film
Alternate archival-edit branch: feature/iran-iraq-war-archival-v2
Last reviewed: 2026-10-28

## IMPORTANT: THE WORKSPACE IS NOT EMPTY
There is a completed film and original source-editing code in the repository. A blank Codex temporary workspace is not evidence that the upstream repo lacks assets.
In this branch examine:
- film/production.json (narrative, 14 beats, source-document links)
- film/acquire.py (preserves original images; source acquisition + rights provenance)
- film/edit.py (renderer)
- film/narrate.py (voice)
- .github/workflows/eight-year-front.yml (render workflow)
- .github/workflows/publish-eight-year-front.yml (direct 1080p MP4 release)
- research/asset-manifest.json and research/fact-check.md
- assets/visuals and assets/audio from the main branch

Existing complete 1080p release:
https://github.com/Asadi123/the-resurrection/releases/tag/the-eight-year-front-2026-10-27-v1

Earlier successful archival edit:
https://github.com/Asadi123/the-resurrection/actions/runs/40544079987
Earlier source-media URL list and motion-graphics code:
https://github.com/Asadi123/the-resurrection/blob/feature/iran-iraq-war-archival-v2/iran_iraq_v2/build.py
(Especially the SOURCE mapping at the beginning.)

## INPUT THREADS — keep as INTERNAL research leads, NOT on-screen social-media content
SOURCE 001: https://x.com/3rab_vision/status/1986782578565579207
Archive index (44-post entry, Nov 7 2025):
https://threadreaderapp.com/user/3rab_vision
The index entry is visible and includes the opening paragraph; the entire 44-post text and attached media have not been independently recovered from the archive. DO NOT invent the missing content.

SOURCE 002: https://x.com/xumas_iq/status/1668916665550094339
FULL TEXT (28 posts reported by archive): https://threadreaderapp.com/thread/1668916665550094339
IMAGE-BEARING PUBLIC MIRROR: https://en.rattibha.com/thread/1668916665550094339
The mirror presents a different count (27); inspect original post order and avoid assuming every media clip is accessible.

Specific candidate original-image URLs used in earlier V2 editing (verify individually, attribution/rights and full source pixels):
- telegram: https://pbs.twimg.com/media/FykVBoMWcAMSzso.jpg
- cited scholarship: https://pbs.twimg.com/media/FykeHQhWAAEHzyz.png
- border dispute chapter: https://pbs.twimg.com/media/Fykg9YPWwAI7coV.png
- Bani Sadr excerpt: https://pbs.twimg.com/media/Fykh8B5WcAYJw45.png
- AFP excerpt: https://pbs.twimg.com/media/FykiJ1XWYAIUvVi.png
- border excerpt: https://pbs.twimg.com/media/FykkTtZXwAE1kxt.png
- incident list: https://pbs.twimg.com/media/Fykk4HkWcAUYjQr.png

These are candidate reproduction scans, not independently authenticated primary-source originals. Locate original publications and preserve bibliographic citations. If the HTTP status of a URL fails in Codex, inspect the existing GH branch/renderer source and archived cached media; do not restart the project.

## PRIMARY DOCUMENTS ALREADY IN PRODUCTION JSON
UN S/RES/479 (1980):
https://digitallibrary.un.org/record/16029/files/S_RES_479%281980%29-EN.pdf
UN S/RES/598 (1987):
https://digitallibrary.un.org/record/137345/files/S_RES_598%281987%29-EN.pdf
Further UN documents are referenced in film/production.json and must be checked before scripting.

## CREATIVE DIRECTION, INCLUDING CORRECTIONS
- Build an edit using the actual historical document images, photos, footage and attributed historical claims; NO AI-generated fictional historical images or reenactments.
- Do not display X handles, thread interfaces, or pretend the repost is the original issuer. Track social-media provenance privately.
- Never crop original source/document images: make full image boundaries visible. Use separate magnified transcription for readability, not destructive cropping.
- Real archival footage preferred; sound documentary style, natural human-sounding narration; no cheap motion-slide repetition.
- Keep the explicitly Iraqi-centered perspective but distinguish government allegations from independent evidence, including the fact that Iraq launched its full-scale September 22, 1980 invasion.
- Copyright and licensing: check reuse permission for source screenshots/footage and maintain a complete internal manifest.
- Refuse fake completion: render MP4, validate streams, sample frames and narration, release artifact.
- If Plan Mode is enabled, tell the user to switch to Code/Agent mode for implementation rather than claim source material cannot be found.

## IMPORTANT LIMITATIONS
This recovery guide is NOT a complete audit of both threads and their attached media, because the complete first thread and some original videos were not acquired. The complete second thread text is readable via public archive, but its claims and image reproductions are not all authenticated. Prior successful render does not imply every intended source is included.
