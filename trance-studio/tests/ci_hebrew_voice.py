"""Public synthetic Hebrew voice smoke for real original-file OPUS ASR.

This test synthesizes its own words; it never contains or uploads a customer's
private WhatsApp recordings. A simple load/zero-tone test is not sufficient.
"""
import os
import pathlib
import subprocess
import json
import tempfile
from source_asr import transcribe_original_files
from live_video import visual_plan

path=pathlib.Path('/tmp/kolbo-hebrew-voice.opus')
assert path.exists() and path.stat().st_size>1000
words, complete=transcribe_original_files([path],progress=lambda step:print('ASR_STAGE',step,flush=True))
print('RECOGNIZED_HEBREW_WORDS',repr(words), 'complete=',complete,flush=True)
tokens=('כלב','נובח','משאית','נוסעת','כביש','רחוב')
hits=sum(1 for token in tokens if token in words)
assert hits>=2, ('Incorrect or ungrounded Hebrew ASR on real voiced OPUS',repr(words),hits)
plan=visual_plan(words,40)
assert plan['scenes'], ('No grounded video scenes from actual ASR',words)
print('HEBREW_SPOKEN_OPUS_TO_SCENES_PASS',hits,len(plan['scenes']),flush=True)

# End-to-end REAL moving-video acceptance from Hebrew-speech recognition.
# The original TTS voice is a legitimate recorded-audio test fixture; the
# real-world video is retrieved from Wikimedia with verified reuse metadata.
audio_path=pathlib.Path('/tmp/kolbo-hebrew-synthetic.mp3')
assert audio_path.exists()
audio_seconds=float(subprocess.check_output([
    'ffprobe','-v','quiet','-show_entries','format=duration',
    '-of','default=noprint_wrappers=1:nokey=1',str(audio_path)
]).decode().strip())
with tempfile.TemporaryDirectory(prefix='kolbo-real-voice-film-') as temp:
    from live_video import export_live_story
    root=pathlib.Path(temp)
    movie=root/'story.mp4'
    footage=visual_plan(words,audio_seconds)
    source_credits=export_live_story(audio_path,movie,footage,root/'footage')
    assert movie.is_file() and movie.stat().st_size>25000
    details=json.loads(subprocess.check_output([
        'ffprobe','-v','error','-show_streams','-show_format','-of','json',str(movie)
    ]))
    streams={s['codec_type'] for s in details['streams']}
    assert streams=={'video','audio'}, streams
    assert 'subtitle' not in streams
    assert source_credits
    print('HEBREW_VOICE_TO_AUTHENTIC_LICENSED_MP4_PASS',
          json.dumps({'mp4_bytes':movie.stat().st_size,
                      'duration':float(details['format']['duration']),
                      'scenes':len(source_credits),
                      'coverage':footage.get('visual_coverage'),
                      'sources':[s['page'] for s in source_credits]},
                     ensure_ascii=False),flush=True)
