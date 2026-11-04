"""Comedy performed ON the user's actual spoken voice, not only in gaps.

Previously the remix inserted occasional sampled stingers but left all
ordinary recorded words dry. This module adds a recognizably different vocal
performance to selected voiced syllables within each original sample span.
It is deterministic for a recorded source, uses no GPU or paid API, retains
the dry voice at every moment, never changes duration or drops a word, and
exports the EXACT effected intervals to the live-video cutter.
"""
from __future__ import annotations

import math
import numpy as np

# A recurring comic 'character' is more coherent than unrelated random
# effects every eighth note. Each source alternates setup, surprise, payoff.
AUTO_MODES=("helium","monster","yo_yo","robot","comic_roll","pitch")
MAX_EVENTS=18


def _rms(audio):
    if not len(audio):return 0.
    x=np.asarray(audio,dtype=np.float32)
    return float(np.sqrt(np.mean(x*x)))


def _original_windows(spans, start, sr):
    windows=[]
    for source_begin,source_end,arranged_begin,arranged_end in spans:
        size=min(source_end-source_begin,arranged_end-arranged_begin)
        if size<int(sr*.32):continue
        absolute=int(start+arranged_begin)
        windows.append((absolute,absolute+int(size),int(source_begin)))
    return windows


def _word_mode(mode,word_times,source_seconds,semantic_cue):
    if mode!="auto" or not word_times or semantic_cue is None:
        return None
    # Prefer words that the original Hebrew recognizer actually placed near
    # this source time; never invent timing or decode someone else's file.
    nearby=[word for word in word_times
            if isinstance(word,dict)
            and isinstance(word.get("start"),(int,float))
            and isinstance(word.get("end"),(int,float))
            and float(word["start"])<=source_seconds+.28
            and float(word["end"])>=source_seconds-.45]
    if not nearby:return None
    phrase=" ".join(str(word.get("text",""))[:70] for word in nearby)
    return semantic_cue(phrase,.5) or None


def perform_comic_voice(vocal, start_frame, spans, sr, bpm, humor,
                        intensity, fx_gain, rng, effect_fn,
                        word_times=None, semantic_cue=None):
    """Replace ONLY some speech samples with a wet/dry comic interpretation.

    vocal: entire existing mono output stem, updated in-place.
    start_frame: exact mix position of this input file's arranged voice.
    spans: (source start/end, arranged start/end) from non-destructive DJ.
    events: sample-derived original-source positions for visual FX.
    """
    if humor=="off" or not len(spans) or not 1<=intensity<=3:
        return []
    windows=_original_windows(spans,start_frame,sr)
    if not windows:return []
    total=sum(end-begin for begin,end,_ in windows)
    if total<.45*sr:return []
    duration=total/sr
    # Short WhatsApp: 2 strong transformations; narration: spaced
    # character turns over the WHOLE recording, including the final words.
    count=max(1,min(MAX_EVENTS,int(math.ceil(duration/4.5))))
    if duration>=3.2:count=max(2,count)
    # A >5 minute voice message must not produce >70 separately encoded
    # live-action video shots on Render Free.
    targets=[(i+.55)/count*total for i in range(count)]
    mode_order=(AUTO_MODES if humor in ("auto","chaos") else (humor,))
    desired_width={1:.58,2:.78,3:1.02}[intensity]
    dry_ratio={1:.46,2:.30,3:.20}[intensity]
    events=[]
    for i,target in enumerate(targets):
        accumulated=0
        chosen=None
        for begin,end,source_begin in windows:
            length=end-begin
            if target<accumulated+length:
                chosen=(begin,end,source_begin,int(target-accumulated))
                break
            accumulated+=length
        if chosen is None:continue
        begin,end,source_begin,relative=chosen
        width=min(int(desired_width*sr),end-begin)
        if width<int(sr*.28):continue
        anchor=begin+relative
        # Look for a voiced syllable near the planned joke while preserving
        # source chronology and never shifting an effect into another word.
        candidates=[]
        for delta in (-.32,-.16,0,.16,.32):
            left=int(max(begin,min(end-width,anchor+delta*sr-width*.5)))
            sample=vocal[left:left+width]
            level=_rms(sample)
            if level>=.016:
                # Prefer strong vowels, but avoid moving across a phrase.
                score=level*(1.-min(.30,abs(left+width*.5-anchor)/sr*.28))
                candidates.append((score,left))
        if not candidates:continue
        left=max(candidates)[1]
        if events and left<events[-1]["end_frame"]+int(.10*sr):
            continue
        original=vocal[left:left+width].copy()
        src_time=(source_begin+left-begin)/sr
        mode=_word_mode(humor,word_times,src_time,semantic_cue)
        if mode is None:mode=mode_order[i%len(mode_order)]
        # The existing vintage DSP operates ONLY on a bounded spoken chunk.
        # No high-memory full-track time stretching, speech erasure or API.
        wet=np.asarray(effect_fn(original,mode,sr,bpm,rng),dtype=np.float32)
        if not len(wet) or not np.isfinite(wet).all():continue
        usable=min(len(original),len(wet))
        if usable<int(.16*sr):continue
        original=original[:usable]
        wet=wet[:usable].copy()
        source_level=_rms(original)
        effect_level=_rms(wet)
        if effect_level<.003:continue
        # Gain-match a genuine modified performance to its own source,
        # not to the loudness of the backing track. Never hard-clip.
        wet*=np.float32(min(2.4,max(.55,
                   source_level/max(.001,effect_level)*fx_gain)))
        wet=np.tanh(wet*1.28).astype(np.float32)
        blend=np.float32(1.-dry_ratio)
        edge=min(int(sr*.022),usable//5)
        amount=np.full(usable,blend,dtype=np.float32)
        if edge:
            ramp=np.linspace(0,blend,edge,endpoint=False,dtype=np.float32)
            amount[:edge]=ramp
            amount[-edge:]=ramp[::-1]
        changed=original*(1.-amount)+wet*amount
        difference=_rms(changed-original)/max(.015,source_level)
        if difference<.10:continue
        vocal[left:left+usable]=changed
        events.append({
            "start_frame":int(left),"end_frame":int(left+usable),
            "source_seek":float(src_time),"effect":mode,
            "strength":round(float(difference),3),
        })
    return events
