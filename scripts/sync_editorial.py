#!/usr/bin/env python3
"""Synchronize factual qualifications to measured, unmodified narration.

Run after prepare_audio.py. Timings come from actual recorded/synthesized sentence
files, never from guessed word durations. Adjacent short claims share a readable
caption. The exact supplied narration and all claim/source review records remain
unchanged. A changed recording that cannot accommodate these corrections fails
explicitly instead of silently dropping them or compressing speech.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FPS = 30


def normalize(text):
    return " ".join(text.replace("’", "'").replace("—", "-").split())


def read(path):
    return json.loads(path.read_text())


def synchronize(timing_path=None, write=True):
    review_path = ROOT / "config/editorial-review.json"
    review = read(review_path)
    narration = read(ROOT / "config/narration.json")
    if timing_path is None:
        timing_path = ROOT / "output/audio-timing.json"
        if not timing_path.is_file():
            timing_path = ROOT / "config/narration.json"
    timing_path = Path(timing_path)
    measured = read(timing_path)
    segments = measured["segments"]
    for segment in segments:
        if segment.get("start") is None or segment.get("duration") is None:
            raise ValueError("Narration is not timed. Run prepare_audio.py or supply measured uploaded narration cues.")
        segment.setdefault("end", segment["start"] + segment["duration"])
        if not 0 <= segment["start"] < segment["end"] <= 160:
            raise ValueError(f"Invalid narration cue: {segment.get('id')}")
    for section, key in (("main", "exact_text"), ("closing", "exact_closing_text")):
        spoken = " ".join(s["text"] for s in segments if s["section"] == section)
        if normalize(spoken) != normalize(narration[key]):
            raise ValueError(f"Measured {section} text differs from exact supplied narration")

    def sentence(text):
        found = [s for s in segments if normalize(s["text"]) == normalize(text)]
        if len(found) != 1:
            raise ValueError(f"Expected one measured sentence: {text!r}")
        return found[0]

    def start(text):
        return sentence(text)["start"]

    # The three opening slogans are qualified together immediately afterward.
    # At least 8.2 seconds permits the 27-word card at a conservative reading rate.
    opening_start = start("June 1st 1972.")
    bp_start = max(start("The wealth extracted for fifty years by British Petroleum — came home."), opening_start + 8.2)
    income_start = start("Per capita income tripled.")
    education_start = start("Every child received free education through university.")
    health_start = start("Every citizen received free healthcare.")
    unesco_start = start("UNESCO awarded Iraq its literacy prize.")
    regional_start = start("The Arab world watched and understood — this is what sovereignty looks like.")
    ideology_start = start("Ba’athism answered the oldest question — what does the Arab nation owe itself?")
    women_start = start("Its women standing in every courtroom, every hospital, every military rank.")
    aziz_start = start("A Christian as Foreign Minister.")
    secular_start = start("One secular state.")
    context_start = start("They called Ba’athism dangerous.")
    oil_start = start("A sovereign Arab state that nationalized its oil threatened every company grown rich on Arab resources.")
    interpretation_start = start("An educated Arab population threatened every power that depended on Arab dependency.")
    stability_start = start("They called it instability.")
    closing_start = start("The oil was Arab.")
    closing_women_start = start("The women were free.")
    closing_borders_start = max(start("The borders were challenged."), closing_women_start + 5.2)

    specifications = [
        ("opening-and-nationalization", opening_start, bp_start,
         "Britain and France shaped borders; Iraq already received oil revenues.\nThe dispute predated Ba’ath rule. The 1 June 1972 decree nationalized IPC alone.",
         ["opening_borders", "opening_royalties", "opening_party", "oil_date"], ["S1", "S15", "S16"]),
        ("bp-consortium", bp_start, income_start,
         "IPC was a multinational consortium; BP held 23.75%.\nIts concession dated to 1925, not fifty years of BP extraction.", ["bp"], ["S1"]),
        ("gdp-measure", income_start, education_start,
         "GDP/person, 1972–75: nearly 3× in current US dollars.\nInflation-adjusted growth: about 23%. GDP is not personal income.", ["income"], ["S3", "S4"]),
        ("education-access", education_start, health_start,
         "Education was tuition-free through university.\nAttendance and access were not universal.", ["education"], ["S2", "S5"]),
        ("health-access", health_start, unesco_start,
         "Public healthcare was provided free of charge.\nThis did not guarantee care reached everyone.", ["health"], ["S6"]),
        ("literacy-award", unesco_start, regional_start,
         "1979 · UNESCO Krupskaya literacy prize\nRecognized Iraq’s national literacy campaign, not universal literacy.", ["unesco"], ["S2"]),
        ("regional-reaction", regional_start, ideology_start,
         "The narration voices a pan-Arab political interpretation.\nRegional governments responded differently to nationalization.", ["arab_reaction"], ["S1", "S12"]),
        ("ideology-attribution", ideology_start, women_start,
         "Ba’athist ideals: Arab unity, liberation and socialism.\nIraq also contained non-Arab peoples and languages.", ["ideology", "language"], ["S10", "S12"]),
        ("women-professions", women_start, aziz_start,
         "Women gained educational and professional roles.\nThe claim of women in “every military rank” is not substantiated.", ["women"], ["S5"]),
        ("aziz-and-land", aziz_start, secular_start,
         "Tariq Aziz, a Chaldean Christian: Foreign Minister, 1983–91.\nLand reform began in 1958 and continued under Ba’ath rule.", ["aziz", "land"], ["S7", "S8", "S9", "S11", "S14"]),
        ("secular-ideal", secular_start, context_start,
         "A secular, pan-Arab state was the party’s ideal.\nIraq’s people held diverse identities; discrimination persisted.", ["secular"], ["S5", "S10", "S12"]),
        ("repression-context", context_start, oil_start,
         "Development coexisted with dictatorship.\nThe 1988 Anfal campaign targeted Kurdish civilians.", ["dangerous"], ["S10"]),
        ("oil-dispute", oil_start, interpretation_start,
         "IPC owners contested compensation and oil sales.\nA threat to “every company” is political interpretation.", ["oil_threat"], ["S1"]),
        ("causal-interpretation", interpretation_start, stability_start,
         "These causal claims are political interpretations.\nThey do not establish the motives of every foreign power.", ["education_threat"], ["S12"]),
        ("stability-and-repression", stability_start, closing_start,
         "The narrator’s question is political rhetoric.\nDevelopment coexisted with violent repression of opposition.", ["stability"], ["S10"]),
        ("closing-services", closing_start, closing_women_start,
         "Oil revenues supported expanding state services.\nSchool enrollment and access varied; not every child attended.", ["closing_oil"], ["S1", "S2", "S5"]),
        ("closing-women", closing_women_start, closing_borders_start,
         "Women’s opportunities expanded.\nEqual rights and political freedom remained limited.", ["closing_women"], ["S5", "S10"]),
        ("closing-borders", closing_borders_start, 150,
         "Pan-Arab unity was an aspiration.\nIraq also waged devastating wars.", ["closing_borders"], ["S6", "S12"]),
    ]
    captions = []
    for identifier, begin, end, text, covers, source_ids in specifications:
        claim_ids = covers + (["context_repression"] if identifier == "repression-context" else [])
        captions.append(dict(id=identifier, start=round(round(begin * FPS) / FPS, 6),
                             end=round(round(end * FPS) / FPS, 6), text=text,
                             heading="HISTORICAL CONTEXT", covers=covers, claim_ids=claim_ids,
                             source_ids=source_ids))

    # The file is an evidence review, not permission to publish inaccurate facts.
    # Check all reviewed claims are represented, and all material claims overlap
    # their spoken sentence(s). Opening slogans are corrected on the next image.
    all_claims = review["claims"] + review.get("opening_card_claims", [])
    required_ids = {c["id"] for c in all_claims}
    covered = {c for caption in captions for c in caption["covers"]}
    if required_ids - covered:
        raise ValueError(f"Missing editorial coverage: {sorted(required_ids - covered)}")
    source_ids = {s["id"] for s in review["sources"]}
    previous_end = 13.0
    for caption in captions:
        begin, end = caption["start"], caption["end"]
        words = len(caption["text"].split())
        minimum = max(5.0, words / 3.5)
        if caption["id"] == "repression-context":
            minimum = max(minimum, 6.0)
        if begin < 13 or end > 150 or begin < previous_end - 1e-5:
            raise ValueError(f"Overlapping or out-of-range correction: {caption['id']}")
        if end - begin + 0.04 < minimum:
            raise ValueError(f"Correction {caption['id']} needs {minimum:.2f}s but has {end-begin:.2f}s. "
                             "Adjust sentence pauses without changing audio tempo, or revise narration.")
        if not set(caption["source_ids"]).issubset(source_ids):
            raise ValueError(f"Unknown evidence source in {caption['id']}")
        caption["minimum_reading_seconds"] = round(minimum, 3)
        previous_end = end

    for claim in all_claims:
        if claim["id"].startswith("opening_"):
            continue
        matching = [s for s in segments if normalize(s["text"]) in normalize(claim["match_text"])]
        if not matching:
            raise ValueError(f"Cannot match review claim to measured audio: {claim['id']}")
        begin, end = min(s["start"] for s in matching), max(s["end"] for s in matching)
        qualifying = [c for c in captions if claim["id"] in c["covers"]]
        # Combined Aziz/land and philosophy/language cards span adjacent sentences.
        # Border card follows by at most 2.3s to give the women's correction time.
        if not any(c["start"] <= end + 2.3 and c["end"] > begin for c in qualifying):
            raise ValueError(f"Correction not synchronized to claim: {claim['id']}")

    review["timed_captions"] = captions
    review["synchronization_verified"] = True
    review["caption_sync"] = dict(
        timing_source=str(timing_path.relative_to(ROOT)) if timing_path.is_relative_to(ROOT) else str(timing_path),
        timing_sha256=hashlib.sha256(timing_path.read_bytes()).hexdigest(),
        method="Measured sentence boundaries, grouped adjacent claims, 30 FPS boundaries; no speech time stretching.",
        nonoverlapping=True, all_reviewed_claims_covered=True,
        reading_rate_limit_words_per_second=3.5,
        final_english_end=150,
        remaining_publication_conditions="Renderer must include these captions legibly and preserve actual archival dates/provenance."
    )
    if write:
        review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    return captions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate schedule without rewriting review JSON")
    args = parser.parse_args()
    result = synchronize(args.timing, write=not args.check)
    print(f"Synchronized {len(result)} non-overlapping factual context captions through 150s.")
