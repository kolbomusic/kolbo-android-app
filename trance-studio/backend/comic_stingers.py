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
    # Make the accent clearly audible on smartphone speakers, while the
    # final mix is still peak-limited. The previous 0.30 peak, followed
    # by .72 gain, often disappeared under bass and vocals.
    if peak>.001:signal*=.47/peak
    return signal

def add_comic_stings(mix,mask,sr,bpm,cue_for_fraction,max_stings=4):
    """Dynamic, audible cartoon punctuation on actual beat-fit speech FX.

    Follow the *measured* FX mask and keep every accent entirely inside that
    slot. First match an explicit Hebrew story cue; if there is none, classify
    the already transformed vocal sample by energy/brightness to choose a
    subtle musical flourish. Silence and unrelated narration are not
    described as an identified joke or event.
    """
    a=np.asarray(mix,dtype=np.float32)
    m=np.asarray(mask,dtype=np.float32)
    if a.ndim!=2 or a.shape[1]!=2 or len(a)!=len(m):
        raise ValueError("invalid stereo and FX mask dimensions")
    if max_stings<=0 or len(m)<sr*.5:return a
    starts=np.flatnonzero((m[1:]>.5)&(m[:-1]<=.5))+1
    if m[0]>.5:starts=np.concatenate(([0],starts))
    if not len(starts):return a
    out=a.copy();used=0;previous=-sr*10
    for start in starts:
        if used>=max_stings:break
        if start-previous<sr*1.45:continue
        # This clip is a separate processed syllable. Never spill music or
        # Foley outside it onto the next word of original WhatsApp speech.
        end_candidates=np.flatnonzero(m[start:]<=.5)
        stop=start+int(end_candidates[0]) if len(end_candidates) else len(m)
        at=int(start+max(1,int(.035*sr)))
        if stop-at<int(.16*sr):continue
        cue=cue_for_fraction(float(start)/max(1,len(m)))
        if not cue:
            # No made-up animal/noise. Only a musically appropriate accent
            # selected by the acoustic contour of the isolated voice hook.
            window=a[start:min(stop,start+int(.22*sr))]
            energy=float(np.sqrt(np.mean(window*window))) if len(window) else 0.
            if energy<.009:continue
            l=np.abs(np.fft.rfft(window[:,0]))
            centroid=float(np.sum(np.arange(len(l))*l)/max(.00001,np.sum(l)))/max(1,len(l))
            cycle=("comic_roll","yo_yo","tape","helium")
            cue=cycle[(used+(1 if centroid>.30 else 0)+(1 if energy>.22 else 0))%len(cycle)]
        sound=create_sting(cue,sr,bpm,used)
        if not len(sound):continue
        size=min(len(sound),stop-at)
        if size<int(.14*sr):continue
        sound=sound[:size].copy()
        fade=min(int(.042*sr),size//4)
        if fade:
            sound[-fade:]*=np.linspace(1.,0.,fade,endpoint=True,dtype=np.float32)
        # Momentarily push the backing into the background, then insert the
        # punchline in both channels. This is true local ducking, *not*
        # making the complete song quieter or clipping the vocal track.
        release=np.minimum(1.,np.arange(size,dtype=np.float32)/max(1,int(.045*sr)))
        local_gain=.63+.12*release
        out[at:at+size]*=local_gain[:,None]
        out[at:at+size,0]+=sound*.96
        out[at:at+size,1]+=sound*1.03
        # Limit local accents only; leave untouched words bit-for-bit intact.
        out[at:at+size]=np.tanh(out[at:at+size]*1.12)*.95
        used+=1;previous=start
    return out
