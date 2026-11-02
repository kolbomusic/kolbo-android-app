"""Original sampled-voice mini-show for a 1–3-word WhatsApp clip.

Never synthesizes a fake transcript and never replaces the original utterance.
Builds a tight DJ performance with a reverse tease, clear dry phrase,
bass/pitch response, rapid word chop, tape stop and final comic hit.
All parts derive from real recorded speech and are musically quantized.
"""
from __future__ import annotations
import math
import numpy as np


def arrange_micro_phrase(source,sr,bpm,humor,intensity,gain,rng,
                         *,vintage_effect,quality,semantic_cue=None):
    x=np.asarray(source,dtype=np.float32)
    if len(x)<int(sr*.10) or len(x)>int(sr*4.5) or humor=="off":
        raise ValueError("Not a short comic phrase")
    beat=60./bpm
    # Short voice notes need a *compact punchline*, not 30s of repetitive bed.
    # Entire original first, subsequent treatments are independent sampled copies.
    original_duration=len(x)/sr
    target_seconds=max(7.9,math.ceil((original_duration+6.0)/beat)*beat)
    target_seconds=min(15.5,target_seconds)
    n=int(math.ceil(target_seconds*sr))
    track=np.zeros(n,dtype=np.float32)
    mask=np.zeros(n,dtype=np.float32)
    original_start=int(.76*sr)
    original_end=original_start+len(x)
    if original_end>n:
        raise ValueError("Short phrase too long")
    track[original_start:original_end]+=x
    spans=[(0,len(x),original_start,original_end)]
    # Pick a vowel-like, voiced segment. The highest *sample peak* would
    # preferentially select consonant plosives and sound irritating.
    window=min(len(x),max(int(sr*.13),min(int(sr*.36),len(x)//2)))
    offsets=range(0,max(1,len(x)-window+1),max(1,int(sr*.024)))
    chosen=max(offsets,key=lambda p:quality(x[p:p+window],sr))
    hook=x[chosen:chosen+window]
    # For a spoken word, a one-shot joke is not enough. Build a four-stage
    # recognizable routine; preserve the dry original at its original start.
    mode=semantic_cue or ('comic_roll' if humor=="auto" else humor)
    if humor=="chaos":mode="scratch"
    family=[
        ("rewind",max(.12,original_start/sr-.34),.32),
        (mode,original_end/sr+.28,.77),
        ("pitch" if mode!="pitch" else "scratch",
         original_end/sr+2*beat,.67),
        ("glitch" if mode!="glitch" else "tape",
         original_end/sr+4.25*beat,.82),
    ]
    if intensity>=2:
        family.append(("tape" if mode!="tape" else "rewind",
                       original_end/sr+6.3*beat,.61))
    if intensity>=3:
        family.append(("monster" if mode!="monster" else "helium",
                       original_end/sr+8.1*beat,.64))
    for i,(effect,second,wet_gain) in enumerate(family):
        if second<0 or second>=target_seconds-.06:continue
        if i==0:
            # Teaser before the unmodified phrase, intentionally quiet.
            treated=vintage_effect(hook[::-1],effect,sr,bpm,rng)
        else:
            treated=vintage_effect(hook,effect,sr,bpm,rng)
        if not len(treated):continue
        at=int(second*sr)
        remaining=n-at
        clip=np.asarray(treated[:min(remaining,len(treated),int(sr*.90))],dtype=np.float32).copy()
        if len(clip)<int(sr*.04):continue
        energy=float(np.sqrt(np.mean(clip*clip)))
        original_energy=float(np.sqrt(np.mean(hook*hook)))
        if energy<.0001:continue
        amp=min(2.3,max(.35,original_energy/energy))
        amp*=wet_gain*gain*{1:.76,2:1.0,3:1.15}[intensity]
        clip=np.tanh(clip*amp).astype(np.float32)
        ramp=min(int(sr*.012),len(clip)//8)
        if ramp:
            fade=np.linspace(0.,1.,ramp,endpoint=False,dtype=np.float32)
            clip[:ramp]*=fade
            clip[-ramp:]*=fade[::-1]
        track[at:at+len(clip)]+=clip
        mask[at:at+len(clip)]=np.maximum(mask[at:at+len(clip)],.92)
    return np.tanh(track*.93).astype(np.float32),mask,spans
