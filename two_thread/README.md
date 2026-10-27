# Iraq's Case — The War They Would Not End

A separate documentary production in **Asadi123/the-resurrection**, on
`documentary/two-thread-evidence-film`. This is an explicitly Iraqi Ba'athist
editorial argument. It attributes claims to the source authors and separates
their conclusions from the limited evidence that the supplied reproductions
actually establish. It does not present agreement between two threads as
independent historical corroboration.

The previous films and their branches are preserved. Their historical footage,
Commons material, UN downloads, narration, music and cached assembly are not
inputs to this production. The new code reuses the repository's proven FFmpeg
contain/pad, square-pixel, fast-start, audit and validation approach.

## Exclusive source collections

1. <https://threadreaderapp.com/thread/1668916665550094339.html>
   — @xumas_iq, 28 posts, 22 images, 15 recordings.
2. <https://threadreaderapp.com/thread/1986782578565579207.html>
   — @3rab_vision, 44 posts, 51 images, 10 recordings. The thread credits
   @ARLTruthSeeker.

Both supplied pages were directly accessible during acquisition on October 27,
2026. **72 posts and all 98 primary attachment associations were acquired.**
Recommendation cards (18 per page) are excluded. Video posters are previews;
the actual highest-resolution explicitly listed MP4 variant is acquired. Public
original-size image variants preserve taller pages than the CDN's default
1200-pixel version. Every acquisition is a TLS-verified, bounded public GET.
No login workaround, private API, unrelated historical source or invented
missing content is used.

The UN letter reproduced in thread 1, post 20 is eligible solely because that
exact image is attached to the commissioned thread. No outside UN PDF or text
from the previous films is added. Unaltered HTML evidence includes the site's
recommendation cards, which are excluded from the parsed inventory and film.

See [the attachment-by-attachment inventory](INVENTORY.md),
[the machine-readable collection](collection.json),
[source acquisition status](MISSING-ASSETS.md), and
[the earlier-branch inspection](evidence/previous-branches.md).

"Complete" means complete against the explicit attachments in the two retrieved
Thread Reader pages. It cannot establish whether X omitted or deleted other
posts before these pages were captured. Some document attachments are already
cropped excerpts. The film displays each entire supplied image with its edges
intact; unseen original pages cannot be recreated. Fine print remains limited
by source resolution and 1080p display; the download bundle retains original
files for inspection.

## Actual film and editorial choices

The edit uses 97 unique attachments in 98 segments, approximately **14 minutes
36 seconds**. All 73 image attachments appear. Twenty-four attached recordings
appear as explicitly identified excerpts, with their genuine sound and embedded
captions unchanged. The complete original recordings are available in the source
bundle. One prisoner-humiliation recording from thread 2, post 33 is inventoried
but deliberately omitted from the edit. Personal abuse and sexual or ethnic
taunts in the source text are not the film's editorial argument.

The picture is the original material throughout, with restrained source labels
and editorial captions. There are no generic slide backgrounds, synthetic
battlefield images, generated narrator, added score or replacement archival
footage. Original source languages are retained; this version does not invent
new translations. Sound pauses while documents are displayed.

[The exact edit decision list](edit.json) specifies each source, in-point,
duration, caption and evidence highlight. Three highlighted passages were
visually compared with the actual source image. [Review records](highlights.json)
contain their original-pixel rectangles, exact image hashes, quotations and
interpretation limits. Existing source highlights remain visible. A reproduced
committee print proposing sanctions is labeled as a proposal, not proof of
enactment. A reproduced historical author's interpretation of war aims is
labeled as an interpretation, not independent proof of those aims.

## Run and test

Install Python 3.12, FFmpeg/FFprobe and DejaVu Sans. From the repository root:

```sh
python -m pip install -r two_thread/requirements.txt pytest
python -m pytest -q
python -m two_thread.acquire
python -m two_thread.render --output two_thread/output/iraqs-case-1080p.mp4 --workdir two_thread/output/render
python -m two_thread.publish --check-only --film two_thread/output/iraqs-case-1080p.mp4 --bundle two_thread/output/source-bundle.zip
```

`acquire --snapshots` parses the committed HTML instead of requesting new thread
pages; it still downloads missing attachments and checks cached receipts and
hashes. `--refresh-media` requests all media again. Acquisition failures write
precise missing-asset diagnostics and return nonzero. They cannot silently fall
back to earlier films. A failed HTML refresh preserves retained source bytes.

The renderer verifies both collections against the retained HTML, validates
every file's SHA256, actual media dimensions and duration, and rejects unrelated
media, missing attachments, cropping, synthetic assets and unreviewed highlights.
Final export is 1920×1080, 30 fps, H.264, square pixels, limited-range BT.709,
AAC 48 kHz stereo, with fast-start metadata. Original audio is assembled through
PCM intermediates and encoded to AAC once. The entire final MP4 is decoded with
FFmpeg errors treated as failures. Validation also produces a per-segment source
report and contact sheet.

A limited render requires `--limit N` and a filename containing `preview`.
It is labeled **PREVIEW_NOT_FINAL** and cannot pass publication validation.
Publication rechecks the actual film, source bytes and complete approved edit;
the renderer's success message alone is insufficient.

## GitHub Actions and iPhone access

The separate **Two-thread documentary — acquire, test and render** workflow
runs on this production branch and pull requests touching it. The earlier film
workflows remain unchanged. This workflow installs only the new production's
small dependency set, runs the complete test suite, requests the real public
sources, renders the full edit, revalidates it, and uploads source diagnostics
even when an upstream server fails. A missing source or mismatched hash blocks
publication.

On an iPhone, open this repository in Safari, select this production branch,
then **Actions → Two-thread documentary — acquire, test and render → latest
run**. Its Summary distinguishes a validated film from a blocked production.
The validated artifact includes the MP4, source bundle, report and contact sheet.
The **Releases** page provides a direct MP4 download that does not require
unpacking an Actions artifact. Tap the MP4 to play it, or use Safari's download
menu to save it to Files.

Once this workflow is present on the default branch, **Run workflow** can select
this branch. Leave `publish` false for verification only. Set it true to publish
a new, separately tagged GitHub Release after both jobs revalidate the full
film and all sources. No branch is merged automatically. Original media is
distributed in the source bundle rather than added as large Git objects.

## Limits and attribution

The source threads supply their own identifications, dates, quotations,
translations and political claims. Retaining their media does not independently
authenticate an archival origin, speaker, translation or historical conclusion.
No broader historical fact-check is claimed because additional historical
sources are excluded by the commission. The new production's editorial
perspective is explicit; it is not an official statement by a party or state.

The repository's software license does not grant rights to third-party thread
attachments. Attribution and byte provenance are recorded; public availability
does not establish a blanket redistribution license. Source-specific rights
remain with their respective holders. No old film's footage or narration is
relicensed or adopted into this production.
