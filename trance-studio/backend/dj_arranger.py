"""Speech-grounded, audible DJ overdubs without cutting the original voice.

An overdub is a copy of a real recorded syllable. Every source sample remains
in the dry stem, so no original word is deleted when effects are aggressive.
"""
from __future__ import annotations
import numpy as np


def event_mode(timed_phrases, at_seconds, cue_from_text):
    """Use real ASR ranges; an event away from this moment never triggers."""
    for item in timed_phrases or ():
        try:
            start=float(item["start"]); end=float(item["end"])
            if start-.12<=at_seconds<=end+.65:
                return cue_from_text(item.get("text",""))
        except (KeyError,ValueError,TypeError):
            continue
    return None


def accent_overdub(voice,sr,bpm,humor,intensity,gain,rng,
                   *,vintage_effect,quality,timed_phrases=None,cue_from_text=None):
    """Audible vocal chops, slap punctuations and pitch turns every few seconds.

    Unlike silence-only inserts, this works on continuous WhatsApp messages.
    Different manual choices always use their requested processor. The dry
    original is not changed; the caller mixes the wet track alongside it.
    """
    x=np.asarray(voice,dtype=np.float32)
    wet=np.zeros_like(x)
    if humor=="off" or len(x)<int(sr*.9):
        return wet
    duration=len(x)/sr
    spacing={1:5.5,2:3.0,3:1.8}[intensity]
    starts=np.arange(min(.85,duration*.3),duration-.15,spacing)
    if not len(starts):
        starts=[duration*.55]
    hook_cycle=("dj","comic_roll","scratch","pitch","stretch","glitch","tape")
    for n,second in enumerate(starts):
        target=int(second*sr)
        width=min(int(sr*.28),len(x)//5)
        lo=max(0,target-int(sr*.36))
        hi=min(len(x)-width,target+int(sr*.35))
        if hi<=lo or width<int(sr*.08):
            continue
        candidates=range(lo,hi+1,max(1,int(.04*sr)))
        picked=max(candidates,key=lambda p:quality(x[p:p+width],sr))
        sample=x[picked:picked+width]
        if quality(sample,sr)<.00015:
            continue
        mode=humor
        if humor=="auto":
            mode=(event_mode(timed_phrases,(picked+width/2)/sr,
                             cue_from_text or (lambda text:None))
                  or hook_cycle[n%len(hook_cycle)])
        if humor=="chaos":
            mode=hook_cycle[(n*3+1)%len(hook_cycle)]
        produced=vintage_effect(sample,mode,sr,bpm,rng)
        if not len(produced):
            continue
        # A short tempo-related echo after a real spoken syllable.
        delay=.08 if n%2==0 else .155
        begin=picked+int(sr*delay)
        remain=len(x)-begin
        if remain<int(sr*.075):
            continue
        piece=np.asarray(produced[:min(len(produced),int(.76*sr),remain)],
                         dtype=np.float32).copy()
        if len(piece)<int(sr*.07):
            continue
        src_rms=float(np.sqrt(np.mean(sample*sample)))
        wet_rms=float(np.sqrt(np.mean(piece*piece)))
        volume={1:.39,2:.62,3:.85}[intensity]
        scaling=min(2.5,max(.35,src_rms/max(.0001,wet_rms)))
        piece=np.tanh(piece*scaling*volume*gain).astype(np.float32)
        fade=min(len(piece)//5,int(.022*sr))
        if fade>0:
            ramp=np.linspace(0,1,fade,endpoint=False,dtype=np.float32)
            piece[:fade]*=ramp
            piece[-fade:]*=ramp[::-1]
        wet[begin:begin+len(piece)]+=piece
    return np.tanh(wet*.94).astype(np.float32)
