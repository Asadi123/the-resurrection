#!/usr/bin/env python3
"""Synthesize coherent Kokoro passages, then split only at verified word gaps.

The public entry point returns narration segment records for prepare_audio.schedule.
Model inference changes natural speaking rate; no audio time stretching is used.
"""
from __future__ import annotations

import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import time
import unicodedata

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/audio/kokoro-segments'
QA_PATH = ROOT / 'research/kokoro-asr-qa.json'
VERSION = 2
GROUP_IDS = (
    tuple(f'main-{i:02}' for i in range(1, 8)),
    tuple(f'main-{i:02}' for i in range(8, 12)),
    tuple(f'main-{i:02}' for i in range(12, 18)),
    tuple(f'main-{i:02}' for i in range(18, 24)),
    tuple(f'closing-{i:02}' for i in range(1, 6)),
)


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def _tokens(text):
    """Canonical speech tokens, retaining an index back to each original word.

    Dates use the configured spoken expansion. ASR's numeric date spellings,
    healthcare spacing, and Ba'athism spelling variants are equivalent here.
    """
    text = unicodedata.normalize('NFKC', text).lower()
    text = text.replace('’', "'").replace('‘', "'")
    text = re.sub(r'\bjune\s+1\b', 'june first', text)
    raw = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)
    expansions = {
        '1972': ['nineteen', 'seventy', 'two'], '1st': ['first'], '1': ['first'],
        '50': ['fifty'], 'healthcare': ['health', 'care'],
        "ba'athism": ['baathism'], 'bathism': ['baathism'],
    }
    return [token for word in raw for token in expansions.get(word, [word])]


def _phonemes(kokoro, text, lang, overrides):
    phonemes = kokoro.tokenizer.phonemize(text, lang=lang)
    applied = []
    for word, replacement in overrides.items():
        count = text.count(word)
        if not count:
            continue
        # eSpeak preserves final punctuation in a standalone query. Match just
        # the word phonemes inside the full passage so context stays coherent.
        pattern = kokoro.tokenizer.phonemize(word, lang=lang).strip()
        pattern = pattern.strip(' .,;:!?—–\n\t')
        if not pattern or phonemes.count(pattern) != count:
            raise ValueError(f'Cannot safely locate pronunciation override {word!r}')
        phonemes = phonemes.replace(pattern, replacement)
        applied.append({'word': word, 'original_phonemes': pattern,
                        'replacement': replacement, 'count': count})
    return phonemes, applied


def _recognize(model, audio, sr, vocabulary_prompt=None):
    # Supplying an array avoids the decoder changing timestamp coordinates.
    if sr != 24000:
        raise ValueError(f'Unexpected Kokoro sample rate {sr}; expected 24000')
    import subprocess
    raw = subprocess.check_output([
        'ffmpeg', '-v', 'error', '-f', 'f32le', '-ar', str(sr), '-ac', '1',
        '-i', 'pipe:0', '-ar', '16000', '-f', 'f32le', 'pipe:1',
    ], input=np.asarray(audio, dtype='<f4').tobytes())
    prompt = {'initial_prompt': vocabulary_prompt} if vocabulary_prompt else {}
    speech, info = model.transcribe(
        np.frombuffer(raw, dtype='<f4').copy(), language='en', beam_size=5,
        word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
        temperature=0.0, **prompt,
    )
    words = []
    recognized = []
    for chunk in speech:
        recognized.append(chunk.text.strip())
        for word in chunk.words or []:
            words.append({'word': word.word.strip(), 'start': float(word.start),
                          'end': float(word.end), 'probability': float(word.probability)})
    return {'transcript': ' '.join(recognized), 'words': words,
            'vocabulary_prompt': vocabulary_prompt,
            'language': info.language, 'duration': len(audio) / sr}


def _load_recognizer():
    from faster_whisper import WhisperModel
    settings = {'device': 'cpu', 'compute_type': 'int8',
                'cpu_threads': 2, 'num_workers': 1}
    try:
        return WhisperModel('small.en', local_files_only=True, **settings)
    except (OSError, ValueError):
        # Fresh public CI runners may download this freely published model.
        return WhisperModel('small.en', local_files_only=False, **settings)


def _quiet_boundary(audio, sr, left, right):
    """Choose a quiet point within 150 ms of adjacent ASR words' midpoint."""
    if right['start'] < left['start'] or right['end'] <= left['end']:
        raise ValueError('ASR word timestamps are not monotonic at a sentence boundary')
    midpoint = (left['end'] + right['start']) / 2
    # Word timestamps are quantized; allow up to 40 ms of edge uncertainty,
    # while requiring a real quiet run rather than cutting an audible phoneme.
    lo = max(0, midpoint - .15, left['end'] - .04)
    hi = min(len(audio) / sr, midpoint + .15, right['start'] + .04)
    if hi <= lo:
        raise ValueError('Adjacent sentence words have no safe separation')
    hop, window = max(1, round(.004 * sr)), max(1, round(.020 * sr))
    candidates = []
    for point in range(round(lo * sr), round(hi * sr) + 1, hop):
        frame = audio[max(0, point-window//2):min(len(audio), point+window//2)]
        rms = float(np.sqrt(np.mean(frame * frame)))
        if rms <= .004:
            candidates.append((abs(point / sr - midpoint), rms, point))
    if not candidates:
        raise ValueError(f'No quiet phoneme-safe sentence boundary near {midpoint:.3f}s')
    _, rms, point = min(candidates)
    return point, {'time': point / sr, 'asr_midpoint': midpoint,
                   'left_word_end': left['end'], 'right_word_start': right['start'],
                   'rms_20ms': rms, 'method': 'quiet_20ms_window_within_150ms_of_asr_gap'}


def _align_and_split(audio, sr, segments, recognition):
    # Whisper sometimes represents one apostrophized word as two timestamped
    # pieces ("Ba" + "'athism"). Join that orthographic split, retaining the
    # full time span and the untouched raw records for inspection.
    joined_words = []
    for original in recognition['words']:
        word = dict(original)
        if (joined_words and word['word'].startswith(("'", '’'))
                and word['start'] <= joined_words[-1]['end'] + .04):
            previous = joined_words[-1]
            pieces = previous.get('merged_from', [previous['word']])
            previous.update({'word': previous['word'] + word['word'],
                             'end': word['end'],
                             'probability': min(previous['probability'], word['probability']),
                             'merged_from': pieces + [word['word']]})
        else:
            joined_words.append(word)
    if len(joined_words) != len(recognition['words']):
        recognition = {**recognition, 'raw_words': recognition['words'], 'words': joined_words}
    expected = []
    ranges = []
    for segment in segments:
        start = len(expected)
        expected.extend(_tokens(segment.get('synthesis_text', segment['text'])))
        ranges.append((start, len(expected)))
    observed = []
    observed_word = []
    for index, word in enumerate(recognition['words']):
        tokens = _tokens(word['word'])
        observed.extend(tokens)
        observed_word.extend([index] * len(tokens))
    matcher = difflib.SequenceMatcher(None, expected, observed, autojunk=False)
    matches = {}
    for a, b, count in matcher.get_matching_blocks():
        for offset in range(count):
            matches[a + offset] = observed_word[b + offset]
    ratio = len(matches) / max(1, len(expected))
    observed_ratio = len(matches) / max(1, len(observed))
    qa = {**recognition, 'expected_tokens': expected, 'observed_tokens': observed,
          'alignment_fraction': ratio, 'matched_tokens': len(matches),
          'recognized_alignment_fraction': observed_ratio,
          'expected_token_count': len(expected), 'alignment_opcodes': matcher.get_opcodes(),
          'boundaries': [], 'segments': []}
    if min(ratio, observed_ratio) < .85:
        raise ValueError(f'Only {ratio:.1%} of expected speech aligned; refusing sentence cuts')
    # Each split requires exact alignment of the words on both sides, including
    # their neighboring context when available. Interior mismatches stay visible.
    points = [0]
    for index in range(len(segments)-1):
        left_start, left_end = ranges[index]
        right_start, right_end = ranges[index + 1]
        needed = set(range(max(left_start, left_end-2), left_end))
        needed.update(range(right_start, min(right_end, right_start+2)))
        missing = sorted(needed.difference(matches))
        if missing:
            bad = [expected[token] for token in missing]
            raise ValueError(f'Uncertain boundary {segments[index]["id"]} / '
                             f'{segments[index+1]["id"]}: unaligned {bad}')
        left_word = recognition['words'][matches[left_end-1]]
        right_word = recognition['words'][matches[right_start]]
        if matches[left_end-1] >= matches[right_start]:
            raise ValueError('A recognized word spans two configured sentences')
        point, boundary = _quiet_boundary(audio, sr, left_word, right_word)
        if point <= points[-1]:
            raise ValueError('Sentence split points are not strictly increasing')
        points.append(point)
        qa['boundaries'].append({**boundary, 'after': segments[index]['id'],
                                 'before': segments[index+1]['id']})
    points.append(len(audio))
    blocks = []
    for index, (segment, (a, b)) in enumerate(zip(segments, ranges)):
        aligned = [matches[token] for token in range(a, b) if token in matches]
        if not aligned or (b-a > 1 and len(aligned) / (b-a) < .85):
            raise ValueError(f'Insufficient individual sentence alignment: {segment["id"]}')
        block = audio[points[index]:points[index+1]]
        blocks.append(block)
        qa['segments'].append({'id': segment['id'], 'source_start': points[index]/sr,
                               'source_end': points[index+1]/sr,
                               'duration': len(block)/sr,
                               'alignment_fraction': len(aligned)/(b-a),
                               'asr_first_word': recognition['words'][min(aligned)]['word'],
                               'asr_last_word': recognition['words'][max(aligned)]['word']})
    if sum(map(len, blocks)) != len(audio):
        raise AssertionError('Splitting unexpectedly lost audio samples')
    return blocks, qa


def synthesize_segments(config):
    """Return config segments pointing at locally generated, ASR-checked WAVs."""
    from kokoro_onnx import Kokoro
    import onnxruntime as ort

    voice = config['voice']
    voice_name = voice.get('voice_name', 'am_michael')
    lang = voice.get('lang', 'en-us')
    model_file = ROOT / voice.get('model_file', 'assets/audio/models/kokoro-v1.0.onnx')
    voices_file = ROOT / voice.get('voices_file', 'assets/audio/models/voices-v1.0.bin')
    model_hash, voices_hash = _digest(model_file), _digest(voices_file)
    lookup = {segment['id']: segment for segment in config['segments']}
    expected_ids = [identity for group in GROUP_IDS for identity in group]
    if list(lookup) != expected_ids:
        raise ValueError('Narration segments differ from the reviewed Kokoro passage groups')
    OUT.mkdir(parents=True, exist_ok=True)
    group_dir = OUT / '_groups'
    group_dir.mkdir(exist_ok=True)
    kokoro = None
    recognizer = None
    report = {'schema_version': VERSION, 'voice_name': voice_name, 'lang': lang,
              'model_sha256': model_hash, 'voices_sha256': voices_hash,
              'asr_model': 'Systran/faster-whisper-small.en',
              'asr_prompt': None,
              'asr_notice': 'Unprompted ASR with vocabulary-only retry for a known pronunciation; not human listening approval.',
              'groups': []}
    returned = []
    for group in GROUP_IDS:
        chosen = [lookup[identity] for identity in group]
        identity = f'{group[0]}_{group[-1]}'
        speed = voice.get('closing_speed', .90) if chosen[0]['section'] == 'closing' else voice.get('speed', 1.0)
        overrides = voice.get('pronunciation_overrides', {'Ba’athism': 'bˈɑːθɪzəm'})
        settings = {'algorithm_version': VERSION, 'engine': 'kokoro-onnx',
                    'engine_version': importlib.metadata.version('kokoro-onnx'),
                    'voice_name': voice_name, 'lang': lang, 'speed': speed,
                    'model_sha256': model_hash, 'voices_sha256': voices_hash,
                    'asr_model': 'Systran/faster-whisper-small.en', 'asr_prompt': None,
                    'pronunciation_overrides': overrides,
                    'segments': [{'id': s['id'], 'text': s['text'],
                                  'synthesis_text': s.get('synthesis_text', s['text'])} for s in chosen]}
        stamp_file = group_dir / f'{identity}.json'
        group_file = group_dir / f'{identity}.wav'
        cached = json.loads(stamp_file.read_text()) if stamp_file.is_file() else {}
        paths = [OUT / f'{s["id"]}.wav' for s in chosen]
        valid = (cached.get('settings') == settings and group_file.is_file()
                 and all(path.is_file() for path in paths)
                 and cached.get('group_sha256') == _digest(group_file)
                 and cached.get('segment_sha256') == {path.name: _digest(path) for path in paths})
        if valid:
            print(f'Kokoro {identity}: using verified cached passage', flush=True)
            qa = cached['qa']
        else:
            print(f'Kokoro {identity}: synthesizing {voice_name} at {speed:g}x', flush=True)
            if kokoro is None:
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(str(model_file), sess_options=options,
                                               providers=['CPUExecutionProvider'])
                kokoro = Kokoro.from_session(session, str(voices_file))
            text = ' '.join(s.get('synthesis_text', s['text']) for s in chosen)
            phonemes, applied = _phonemes(kokoro, text, lang, overrides)
            started = time.monotonic()
            audio, sr = kokoro.create(phonemes, voice=voice_name, speed=float(speed),
                                       lang=lang, is_phonemes=True, trim=False)
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            sf.write(group_file, audio, sr, subtype='FLOAT')
            if recognizer is None:
                recognizer = _load_recognizer()
            recognition = _recognize(recognizer, audio, sr)
            try:
                try:
                    blocks, qa = _align_and_split(audio, sr, chosen, recognition)
                except ValueError as baseline_error:
                    # The model can spell the explicitly phonemized Ba'athism
                    # as Balthism. Retry with names only, never the passage text.
                    if ('unaligned' not in str(baseline_error)
                            or not any(word in text for word in overrides)):
                        raise
                    vocabulary = ', '.join(dict.fromkeys([*overrides, 'Iraq', 'UNESCO'])) + '.'
                    retried = _recognize(recognizer, audio, sr, vocabulary_prompt=vocabulary)
                    blocks, qa = _align_and_split(audio, sr, chosen, retried)
                    qa['unprompted_recognition'] = {
                        **recognition, 'alignment_error': str(baseline_error)}
            except ValueError as error:
                report['groups'].append({'id': identity, 'status': 'alignment_failed',
                                         'error': str(error), **recognition})
                _json_write(QA_PATH, report)
                raise ValueError(f'{identity}: {error}; inspect {QA_PATH}') from error
            for path, block in zip(paths, blocks):
                # Preserve every source sample. Existing decode() resamples this
                # 24 kHz mono WAV to the project's 48 kHz stereo mix format.
                sf.write(path, block, sr, subtype='FLOAT')
            qa.update({'id': identity, 'status': 'passed', 'phonemes': phonemes,
                       'pronunciation_overrides_applied': applied,
                       'elapsed_seconds': time.monotonic()-started})
            _json_write(stamp_file, {'settings': settings, 'qa': qa,
                                    'group_sha256': _digest(group_file),
                                    'segment_sha256': {path.name: _digest(path) for path in paths}})
            print(f'Kokoro {identity}: {len(audio)/sr:.2f}s, '
                  f'{qa["alignment_fraction"]:.1%} words aligned', flush=True)
        report['groups'].append(qa)
        _json_write(QA_PATH, report)
        for segment, path in zip(chosen, paths):
            returned.append({**segment, 'file': str(path.relative_to(ROOT)),
                             'start': None, 'duration': None})
    report['status'] = 'passed'
    report['total_source_duration'] = sum(group['duration'] for group in report['groups'])
    _json_write(QA_PATH, report)
    return returned


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/narration.json')
    parser.add_argument('--voice', default=None)
    arguments = parser.parse_args()
    configuration = json.loads(arguments.config.read_text())
    # A standalone audition may run before the integration updates voice config.
    configuration['voice'].update({
        'model_file': 'assets/audio/models/kokoro-v1.0.onnx',
        'voices_file': 'assets/audio/models/voices-v1.0.bin',
    })
    if arguments.voice:
        configuration['voice']['voice_name'] = arguments.voice
        configuration['voice']['lang'] = 'en-gb' if arguments.voice.startswith('b') else 'en-us'
    result = synthesize_segments(configuration)
    print(json.dumps({'segments': len(result), 'qa': str(QA_PATH)}, indent=2))
