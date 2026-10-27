#!/usr/bin/env python3
"""Build licensed soundtrack + timed modern narration without time stretching.

Default: free, local Piper Norman male model. An uploaded WAV/MP3 narration
may replace TTS; supply its timing JSON to identify the main/closing boundary.
No upload is silently treated as verified exact speech: --narration-transcript
must match the requested text, and a human must verify the actual recording.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SR = 48000
DURATION = 160


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch_verified(asset):
    path = ROOT / asset['filename']
    if not asset.get('rights_confirmed'):
        raise ValueError(f"Uncleared audio: {asset['id']}")
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(asset['download_url'], headers={
            'User-Agent': 'ResurrectionArchivalProduction/1.0 (rights-verified acquisition)'})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        temporary = path.with_suffix(path.suffix + '.part')
        temporary.write_bytes(data)
        if digest(temporary) != asset['sha256']:
            temporary.unlink()
            raise ValueError(f"Downloaded audio hash mismatch: {asset['id']}")
        temporary.replace(path)
    if digest(path) != asset['sha256']:
        raise ValueError(f"Audio hash mismatch: {asset['id']}")
    return path


def decode(path, start=None, duration=None):
    args = ['ffmpeg', '-v', 'error']
    if start is not None:
        args += ['-ss', str(start)]
    args += ['-i', str(path)]
    if duration is not None:
        args += ['-t', str(duration)]
    args += ['-ar', str(SR), '-ac', '2', '-f', 'f32le', '-']
    raw = subprocess.check_output(args)
    return np.frombuffer(raw, dtype='<f4').reshape(-1, 2).copy()


def wav_write(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SR)
        output.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())


def trim_silence(samples, threshold=0.008, margin=0.06):
    # Only remove external silence, preserving all internal pauses and words.
    mask = np.max(np.abs(samples), axis=1) > threshold
    indices = np.flatnonzero(mask)
    if not len(indices):
        raise ValueError('A narration segment contains no audible speech')
    pad = int(margin * SR)
    return samples[max(0, indices[0] - pad):min(len(samples), indices[-1] + pad)]


def schedule(segments, config):
    timeline = np.zeros((DURATION * SR, 2), dtype=np.float32)
    measured = []
    for section in ('main', 'closing'):
        chosen = [s for s in segments if s['section'] == section]
        section_start = config['timeline'][section + '_start']
        section_end = config['timeline'][section + '_end']
        blocks = [trim_silence(decode(ROOT / s['file'])) for s in chosen]
        speech_duration = sum(len(b) for b in blocks) / SR
        available_pause = section_end - section_start - speech_duration
        if available_pause < 0:
            raise ValueError(f'{section} speech {speech_duration:.3f}s exceeds '
                             f'{section_end - section_start}s. Re-record or change '
                             'synthesis settings; audio will never be sped up.')
        # Leave readable factual qualification cards beside the relevant words.
        minimum_gaps = [max(0, s.get('minimum_screen_seconds', 0) - len(b) / SR)
                        for s, b in zip(chosen[:-1], blocks[:-1])]
        if sum(minimum_gaps) > available_pause:
            raise ValueError(f'{section} has insufficient room for readable contextual cards')
        remaining_pause = available_pause - sum(minimum_gaps)
        # Rhetorical questions receive a slightly longer reflective pause.
        weights = [1.35 if s['text'].endswith('?') else 1.0 for s in chosen[:-1]]
        total_weight = sum(weights)
        cursor = round(section_start * SR)
        for index, (segment, block) in enumerate(zip(chosen, blocks)):
            gain = segment.get('volume', 1)
            timeline[cursor:cursor + len(block)] += block * gain
            actual = {**segment, 'start': cursor / SR,
                      'duration': len(block) / SR,
                      'end': (cursor + len(block)) / SR,
                      'timing_status': 'measured_from_rendered_audio',
                      'audio_sha256': digest(ROOT / segment['file'])}
            measured.append(actual)
            cursor += len(block)
            if index < len(weights):
                cursor += round((minimum_gaps[index] + remaining_pause * weights[index]
                                 / total_weight) * SR)
        if cursor > round(section_end * SR) + len(chosen):
            raise ValueError(f'Rounding overflow in {section} timing')
    return timeline, measured


def synthesize(config):
    from piper import PiperVoice, SynthesisConfig
    voice = PiperVoice.load(str(ROOT / config['voice']['model_file']))
    original_phonemize = voice.phonemize
    overrides = config['voice'].get('pronunciation_overrides', {})
    phoneme_patterns = [(original_phonemize(word)[0], list(ipa))
                        for word, ipa in overrides.items()]

    def corrected_phonemize(text):
        sentences = original_phonemize(text)
        for sentence in sentences:
            for pattern, replacement in phoneme_patterns:
                index = 0
                while index <= len(sentence) - len(pattern):
                    if sentence[index:index + len(pattern)] == pattern:
                        sentence[index:index + len(pattern)] = replacement
                        index += len(replacement)
                    else:
                        index += 1
        return sentences

    voice.phonemize = corrected_phonemize
    for segment in config['segments']:
        path = ROOT / segment['file']
        stamp = path.with_suffix('.synthesis.json')
        settings = {'text': segment['text'],
                    'synthesis_text': segment.get('synthesis_text', segment['text']),
                    'length_scale': segment['synthesis_length_scale'],
                    'model_sha256': digest(ROOT / config['voice']['model_file']),
                    'engine': config['voice']['engine'],
                    'pronunciation_overrides': {word: ipa for word, ipa in overrides.items()
                                                if word in segment['text']}}
        if not path.exists() or not stamp.exists() or json.loads(stamp.read_text()) != settings:
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as output:
                voice.synthesize_wav(settings['synthesis_text'], output,
                    syn_config=SynthesisConfig(length_scale=settings['length_scale']))
            stamp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
    return schedule(config['segments'], config)


def read_uploaded(args, config):
    rights_path = ROOT / 'config/uploaded-audio-rights.json'
    if not rights_path.is_file():
        raise ValueError('Uploaded narration requires config/uploaded-audio-rights.json '
                         '(creator, source_url, license, license_url, rights_confirmed:true, sha256)')
    rights = json.loads(rights_path.read_text())
    required = ('creator', 'source_url', 'license', 'license_url', 'sha256')
    if (rights.get('rights_confirmed') is not True or
            any(not isinstance(rights.get(key), str) or not rights[key].strip() for key in required)):
        raise ValueError('Uploaded narration rights declaration is incomplete or uncleared')
    if not re.fullmatch(r'[0-9a-f]{64}', rights['sha256']):
        raise ValueError('Uploaded narration rights SHA-256 must be 64 lowercase hex characters')
    path = Path(args.narration) if args.narration else ROOT / 'assets/audio/uploaded-narration'
    if args.narration_url:
        if not args.narration_url.startswith('https://'):
            raise ValueError('Narration URL must use HTTPS')
        with urllib.request.urlopen(args.narration_url, timeout=120) as response:
            path.write_bytes(response.read())
    if digest(path) != rights['sha256']:
        raise ValueError('Uploaded narration SHA-256 differs from its rights declaration')
    if not args.narration_transcript:
        raise ValueError('Uploaded narration requires --narration-transcript text file '
                         'and --narration-timing JSON; no unverifiable replacement is published.')
    expected = config['exact_text'] + ' ' + config['exact_closing_text']
    normalize = lambda s: ' '.join(s.split()).strip('“”')
    if normalize(Path(args.narration_transcript).read_text()) != normalize(expected):
        raise ValueError('Uploaded narration transcript differs from requested exact narration')
    if not args.narration_timing:
        raise ValueError('Uploaded narration requires --narration-timing, a JSON list '
                         'of {id, source_start, source_end}, one for each config segment. '
                         'Use the downloadable example in config/upload-timing-example.json.')
    timing = json.loads(Path(args.narration_timing).read_text())
    cues = {cue['id']: cue for cue in timing}
    uploaded_segments = []
    for segment in config['segments']:
        if segment['id'] not in cues:
            raise ValueError(f"Missing uploaded narration cue {segment['id']}")
        cue = cues[segment['id']]
        start, end = float(cue['source_start']), float(cue['source_end'])
        if start < 0 or end <= start:
            raise ValueError(f"Invalid uploaded narration cue {segment['id']}")
        block = decode(path, start, end - start)
        target = ROOT / 'assets/audio/uploaded-segments' / f"{segment['id']}.wav"
        wav_write(target, block)
        uploaded_segments.append({**segment, 'file': str(target.relative_to(ROOT)),
                                  'origin': 'user-uploaded narration; transcript supplied by uploader'})
    timeline, measured = schedule(uploaded_segments, config)
    return timeline, measured, rights


def make_music(config, assets):
    mix = np.zeros((DURATION * SR, 2), dtype=np.float32)
    for cue in config['music_cues']:
        asset = assets[cue['asset_id']]
        block = decode(ROOT / asset['filename'], cue['source_start'], cue['source_duration'])
        needed = round(cue['source_duration'] * SR)
        if len(block) < needed - 100:
            raise ValueError(f"Music cue {cue['id']} exceeds source duration")
        block = block[:needed]
        n_in = min(round(cue['fade_in'] * SR), len(block))
        n_out = min(round(cue['fade_out'] * SR), len(block))
        block[:n_in] *= np.linspace(0, 1, n_in)[:, None]
        block[-n_out:] *= np.linspace(1, 0, n_out)[:, None]
        offset = round(cue['timeline_start'] * SR)
        if offset + len(block) > len(mix):
            raise ValueError(f"Music cue {cue['id']} exceeds video duration")
        mix[offset:offset + len(block)] += block * cue['gain']
    return mix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--narration')
    parser.add_argument('--narration-url', default=os.environ.get('NARRATION_URL') or None)
    parser.add_argument('--narration-transcript')
    parser.add_argument('--narration-timing')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    # iPhone/GitHub web users can add companion files through Add file → Upload.
    # A distinct input name prevents the generated narration.wav being reused
    # accidentally as an upload on the next run.
    if not args.narration and not args.narration_url:
        uploaded = ROOT / 'assets/audio/uploaded-narration.wav'
        if uploaded.exists():
            args.narration = str(uploaded)
    if args.narration or args.narration_url:
        if not args.narration_transcript:
            transcript = ROOT / 'config/uploaded-transcript.txt'
            if transcript.exists():
                args.narration_transcript = str(transcript)
        if not args.narration_timing:
            timing = ROOT / 'config/uploaded-timing.json'
            if timing.exists():
                args.narration_timing = str(timing)
    config = json.loads((ROOT / 'config/narration.json').read_text())
    music_config = json.loads((ROOT / 'config/audio.json').read_text())
    manifest = json.loads((ROOT / 'research/audio-assets.json').read_text())
    assets = {a['id']: a for a in manifest['assets']}
    for asset in assets.values():
        fetch_verified(asset)
    if args.check_only:
        print('All licensed audio source hashes verified.')
        return
    if args.narration or args.narration_url:
        voice, measured, uploaded_source = read_uploaded(args, config)
        origin = 'Uploaded narration; supplied transcript and cue timings'
    else:
        voice, measured = synthesize(config)
        uploaded_source = None
        origin = 'Local free Piper Norman; modern synthesized narration'
    # A short fade follows the last words; no speech is truncated.
    voice *= music_config.get('narration_gain', 0.82)
    wav_write(ROOT / 'assets/audio/narration.wav', voice)
    wav_write(ROOT / 'output/music_bed.wav', make_music(music_config, assets))
    output = ROOT / music_config['output']
    output.parent.mkdir(parents=True, exist_ok=True)
    duck = music_config['ducking']
    graph = (
        '[0:a]highpass=f=65,asplit=2[voice][sidechain];'
        '[1:a][sidechain]sidechaincompress='
        f"threshold={duck['threshold']}:ratio={duck['ratio']}:"
        f"attack={duck['attack_ms']}:release={duck['release_ms']}[music];"
        '[voice][music]amix=inputs=2:normalize=0,'
        'alimiter=limit=0.93:level=false,atrim=duration=160,asetpts=PTS-STARTPTS[out]')
    command = ['ffmpeg', '-y', '-v', 'warning', '-i', ROOT / 'assets/audio/narration.wav',
               '-i', ROOT / 'output/music_bed.wav', '-filter_complex', graph,
               '-map', '[out]', '-ar', SR, '-ac', 2, '-c:a', 'pcm_s16le', output]
    run(command)
    report = {'schema_version': 1, 'duration': DURATION, 'sample_rate': SR,
              'origin': origin, 'audio_processing': 'No tempo or pitch modification; '
              'external silence trimmed, deliberate sentence pauses, closing gain 0.78, '
              '65 Hz high-pass, narration-driven music ducking, peak limiter.',
              'narration_sha256': digest(ROOT / 'assets/audio/narration.wav'),
              'mix_sha256': digest(output), 'segments': measured,
              'music_cues': music_config['music_cues'], 'ffmpeg_command': [str(a) for a in command]}
    if uploaded_source is not None:
        report['uploaded_audio_source'] = uploaded_source
    (ROOT / 'output/audio-timing.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'Audio mix ready: {output}; {len(measured)} measured narration cues; 160.000 s')
    print(f"Main ends {max(s['end'] for s in measured if s['section']=='main'):.3f}; "
          f"closing ends {max(s['end'] for s in measured if s['section']=='closing'):.3f}")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'AUDIO BLOCKER: {exc}', file=sys.stderr)
        sys.exit(1)
