"""Original, royalty-free cartoon stings for speech-synchronized comic beats.

All sounds are generated mathematically, without sampled copyrighted media,
YouTube downloads, prerecorded laughter, or paid model inference. They sit
beside (never replace or truncate) the original WhatsApp vocal and its effect.
Placement follows observed speech-pause FX boundaries, not guessed timestamps.
"""
import math
import numpy as np

def create_sting(style,sr=32000,bpm=145,variant=0):
    if not 8000<=sr<=48000 or not 100<=bpm<=180:
        raise ValueError("invalid sample rate / tempo")
    valid=("monster","comic_roll","rewind","helium","yo_yo","tape")
    if style not in valid:
        return np.zeros(0,dtype=np.float32)
    seconds=min(.76,max(.29,60./bpm*(1.12 if style in ("monster","rewind") else .80)))
    n=max(2,int(round(seconds*sr)))
    t=np.arange(n,dtype=np.float64)/sr
    phase=t/max(.001,seconds)
    rng=np.random.default_rng(100+variant%100000)
    # Repeated synth stings keep timbral character but not identical phase.
    detune=1.+((variant%7)-3)*.012
    if style=="monster":
        freq=(410*(1.-phase)**2+78)*detune
        carrier=np.sin(2*np.pi*np.cumsum(freq)/sr)
        wobble=np.sin(2*np.pi*12*t)
        signal=(.80*carrier*(1+.19*wobble)+.18*np.sin(2*np.pi*np.cumsum(freq*.49)/sr))
    elif style=="comic_roll":
        # Double jazz rimshot with a natural room-decay tail.
        signal=np.zeros(n,dtype=np.float64)
        for at,gain in ((.015,.84),(.16,.60)):
            tail=np.maximum(0.,t-at)
            impulse=(t>=at)
            wood=np.sin(2*np.pi*(208*tail+420*tail*tail))
            sand=rng.standard_normal(n)
            signal+=gain*impulse*(.78*wood+.18*sand)*np.exp(-tail*36)
    elif style=="rewind":
        freq=(690*(1.-phase)**1.8+62)*detune
        signal=np.sin(2*np.pi*np.cumsum(freq)/sr)
        signal+=.10*rng.standard_normal(n)*(1.-phase)
    elif style=="helium":
        freq=(560+930*phase**2)*detune
        signal=np.sin(2*np.pi*np.cumsum(freq)/sr)+.13*np.sin(4*np.pi*np.cumsum(freq)/sr)
    elif style=="yo_yo":
        freq=(260+590*np.sin(2*np.pi*phase)**2)*detune
        signal=np.sin(2*np.pi*np.cumsum(freq)/sr)
    else:  # tape-stop miniature: pitch decays nonlinearly.
        freq=(360*(1.-phase)**3+42)*detune
        signal=np.sin(2*np.pi*np.cumsum(freq)/sr)
        signal+=.06*rng.standard_normal(n)
    rise=np.minimum(1.,t/.009)
    decay=np.clip((seconds-t)/.12,0,1)**1.2
    env=rise*decay*np.exp(-t*(2.2 if style=="monster" else 1.55))
    signal*=env
    signal=np.asarray(np.tanh(signal*1.1),dtype=np.float32)
    peak=float(np.max(np.abs(signal)))
    if peak>.001:signal*=.30/peak
    return signal

def add_comic_stings(mix,mask,sr,bpm,cue_for_fraction,max_stings=3):
    """Add select Foley only in existing voice-FX inserts, not over words."""
    a=np.asarray(mix,dtype=np.float32)
    m=np.asarray(mask,dtype=np.float32)
    if a.ndim!=2 or a.shape[1]!=2 or len(a)!=len(m):
        raise ValueError("invalid stereo and FX mask dimensions")
    if max_stings<=0 or len(m)<sr*.5:
        return a
    # Rising edges indicate the start of a separate, already beat-fit vocal
    # effect. We do not force timing from an unreliable Hebrew ASR estimate.
    starts=np.flatnonzero((m[1:]>.5)&(m[:-1]<=.5))+1
    if m[0]>.5:starts=np.concatenate(([0],starts))
    if not len(starts):return a
    out=a.copy()
    used=0
    previous=-sr*10
    for start in starts:
        if used>=max_stings:break
        if start-previous<sr*1.5:continue
        cue=cue_for_fraction(float(start)/max(1,len(m)))
        if not cue:continue
        sound=create_sting(cue,sr,bpm,used)
        if not len(sound):continue
        # Accent sits just after the beginning of a spoken-word FX, to
        # underline the punchline without erasing the original speech.
        offset=int(.06*sr)
        at=min(len(out)-1,int(start+offset))
        end=min(len(out),at+len(sound))
        if end<=at:continue
        mid=sound[:end-at]
        out[at:end,0]+=mid*.72
        out[at:end,1]+=mid*.81
        used+=1
        previous=start
    return out
