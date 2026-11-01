"""Public synthetic Hebrew voice smoke for real original-file OPUS ASR.

This test synthesizes its own words; it never contains or uploads a customer's
private WhatsApp recordings. A simple load/zero-tone test is not sufficient.
"""
import os
import pathlib
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
