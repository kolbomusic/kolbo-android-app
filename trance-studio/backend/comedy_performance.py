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
# Automatic comedy favors a coherent performance over a rapid parade of
# incompatible voices. Experimental cartoon FX remain explicit manual choices.
AUTO_MODES=("stretch",)
MAX_EVENTS=12


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
                        word_times=None, semantic_cue=None,
                        transcript_hint="", quality_fn=None):
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
    # Schedule by REAL speech activity, not wall-clock duration.
    # A 40s WhatsApp note with 30s of silence must still morph its
    # actual words at the beginning, middle and end of the recording.
    # Use short, memory-bounded RMS frames; no server ASR required.
    step=max(1,int(sr*.085))
    voiced_positions=[]
    accumulated=0
    for begin,end,_ in windows:
        for relative in range(0,end-begin,step):
            width=min(step,end-begin-relative)
            if _rms(vocal[begin+relative:begin+relative+width])>.017:
                voiced_positions.append(accumulated+relative+width*.5)
        accumulated+=end-begin
    if not voiced_positions:return []
    voiced_duration=len(voiced_positions)*step/sr
    # A single well-delivered punchline is preferable to six tiny, harsh
    # 'effects' on a short sentence. Escalation is slower and deliberate.
    count=max(1,min(MAX_EVENTS,int(math.ceil(voiced_duration/7.5))))
    if voiced_duration>=6.:count=max(2,count)
    # Preserve rare speech islands rather than applying every transformation
    # to the first energetic paragraph. Real pauses >1.2s define a new
    # utterance whose meaningful ending can carry its own comic payoff.
    groups=[]
    for position in voiced_positions:
        if not groups or position-groups[-1][-1]>sr*1.2:
            groups.append([position])
        else:
            groups[-1].append(position)
    if len(groups)>1:
        count=min(MAX_EVENTS,max(count,len(groups)))
    targets=[group[min(len(group)-1,int(.72*len(group)))]
             for group in groups] if 1<len(groups)<=count else []
    if len(targets)<count:
        targets.extend(
          voiced_positions[min(len(voiced_positions)-1,
            int((i+.65)*len(voiced_positions)/count))]
          for i in range(count))
    targets=sorted(set(targets))[:MAX_EVENTS]
    # A *single* recurring character/effect per source creates callback,
    # rather than a helium->monster->robot random palette.
    grounded_mode=(semantic_cue(transcript_hint,.5)
                   if humor=="auto" and transcript_hint.strip()
                   and semantic_cue else None)
    if grounded_mode in ("rewind","comic_roll","yo_yo"):
        # Rewind/roll repeated on every sentence sounds like a cheap glitch.
        # Keep semantic emphasis with natural elastic vowels instead.
        grounded_mode="stretch"
    if grounded_mode not in ("stretch","pitch","tape","monster","helium"):
        grounded_mode=None
    default_mode=grounded_mode or "stretch"
    mode_order=((default_mode,) if humor=="auto" else
                ("stretch",) if humor=="chaos" else (humor,))
    desired_width={1:.95,2:1.32,3:1.55}[intensity]
    dry_ratio={1:.55,2:.43,3:.34}[intensity]
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
        for delta in (-.42,-.21,0,.21,.42):
            left=int(max(begin,min(end-width,anchor+delta*sr-width*.5)))
            sample=vocal[left:left+width]
            level=_rms(sample)
            if level>=.016:
                # Reject breath/fricatives where possible: hard-pitching an
                # 's' or click is fatiguing, not funny.
                quality=(quality_fn(sample,sr) if quality_fn else level)
                if quality<.012:continue
                score=quality*(1.-min(.30,abs(left+width*.5-anchor)/sr*.28))
                candidates.append((score,left))
        if not candidates:continue
        left=max(candidates)[1]
        if events and left<events[-1]["end_frame"]+int(.10*sr):
            continue
        original=vocal[left:left+width].copy()
        src_time=(source_begin+left-begin)/sr
        mode=mode_order[0]
        # An aligned *positive* spoken word can override the global motif,
        # but never run a rotation of unrelated characters every 0.8s.
        timed_mode=_word_mode(humor,word_times,src_time,semantic_cue)
        if timed_mode in ("monster","helium","stretch","pitch","tape"):
            mode=timed_mode
        # This DSP effect can shrink the recorded syllable by 40%.
        # Truncating that output makes jerky 0.4s bursts. Instead retain
        # the FULL chosen spoken phrase with pitch-preserving WSOLA
        # time fitting and a slow musical crossfade into the clean speech.
        wet=np.asarray(effect_fn(original,mode,sr,bpm,rng),dtype=np.float32)
        if not len(wet) or not np.isfinite(wet).all():continue
        usable=len(original)
        if usable<int(.28*sr):continue
        if len(wet)!=usable:
            ratio=usable/max(1,len(wet))
            if .55<=ratio<=2.8:
                try:
                    from engine import stretch_voice
                    wet=stretch_voice(wet,ratio,sr)
                except (ValueError,RuntimeError,FloatingPointError):
                    continue
            else:
                continue
        if len(wet)<usable:continue
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
        # 80ms rounded transitions are perceived as performed vocal shifts,
        # not sudden little squeaks at the exact splice.
        edge=min(int(sr*.080),usable//4)
        amount=np.full(usable,blend,dtype=np.float32)
        if edge:
            ramp=np.linspace(0,blend,edge,endpoint=False,dtype=np.float32)
            amount[:edge]=ramp
            amount[-edge:]=ramp[::-1]
        changed=original*(1.-amount)+wet*amount
        difference=_rms(changed-original)/max(.015,source_level)
        if difference<.16:continue
        vocal[left:left+usable]=changed
        events.append({
            "start_frame":int(left),"end_frame":int(left+usable),
            "source_seek":float(src_time),"effect":mode,
            "strength":round(float(difference),3),
        })
    return events
