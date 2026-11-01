"""Original deterministic trance composition with original-audio sampling."""
import math
import re
import hashlib
import subprocess
import numpy as np
from scipy.signal import butter, sosfilt, lfilter, stft, istft

def load_audio(path, sample_rate=32000):
    command=['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),'-t','120.02','-ac','1','-ar',str(sample_rate),'-f','f32le','-']
    result=subprocess.run(command,check=True,capture_output=True,timeout=45)
    x=np.frombuffer(result.stdout,dtype='<f4').copy()
    if len(x)>sample_rate*120:raise ValueError('הקלטה ארוכה מ־120 שניות')
    return x

def prepare_voice(x,sr):
    x=np.asarray(x,dtype=np.float32)
    if not len(x) or len(x)>sr*120 or not np.isfinite(x).all():raise ValueError('הקלטה ריקה או לא תקינה')
    peak=float(np.max(np.abs(x)))
    if peak<.001:raise ValueError('לא נמצא קול בהקלטה')
    frame=max(1,int(sr*.01));rms=np.array([np.sqrt(np.mean(x[i:i+frame]**2)) for i in range(0,len(x),frame)])
    active=np.flatnonzero(rms>max(.003,peak*.035))
    if not len(active):raise ValueError('לא נמצא קול בהקלטה')
    # Preserve the complete timeline, including very quiet speech at either end.
    # RMS gating here is only a sanity check: trimming can erase whispered words.
    x=x.copy()
    # WhatsApp codecs already compress speech. Use gentle cleanup and gain,
    # not the previous hard saturation, which made consonants crunchy.
    x=sosfilt(butter(2,[85,min(7100,sr*.43)],btype='bandpass',
                        fs=sr,output='sos'),x).astype(np.float32)
    rms=float(np.sqrt(np.mean(x*x)))
    gain=min(3.0,.145/max(.001,rms))
    x*=gain
    # Soft-knee peak limiting affects only unusually loud samples.
    amplitude=np.abs(x)
    above=amplitude>.84
    if np.any(above):
        x[above]=np.sign(x[above])*(.84+.13*np.tanh((amplitude[above]-.84)*5))
    t=np.arange(len(x),dtype=np.float32)/sr
    x*=np.minimum(1.,t/.006)*np.minimum(1.,(len(x)/sr-t)/.012)
    return x.astype(np.float32)


STYLES = ('melodic', 'psy', 'progressive', 'goa', 'acid', 'uplifting',
          'eurodance', 'hard', 'rave', 'mixed', 'auto', 'israeli')
HUMOR = ('auto', 'classic', 'cartoon', 'scratch', 'robot', 'chaos',
         'stretch', 'tape', 'pitch', 'glitch', 'vinyl', 'dj',
         'helium','monster','yo_yo','comic_roll','rewind','off')
MOTIFS = (
    (74,77,81,77,72,77,79,77,70,74,77,74,69,73,76,73),
    (69,72,76,79,76,72,74,71,67,71,74,78,74,71,69,71),
    (76,79,83,79,78,74,71,74,72,76,79,84,79,76,74,72),
    (73,76,80,83,80,76,73,71,69,73,76,81,76,73,71,68),
    (62,65,69,72,69,65,67,64,60,64,67,71,67,64,62,60),
    (81,79,76,74,76,79,84,81,79,76,74,71,74,76,79,76),
)
ROOTS = ((38,34,41,33),(33,36,38,31),(41,38,34,36),
         (36,31,33,38),(38,41,36,33),(34,41,38,33))

def speech_boundaries(x, sr):
    """Locate natural pauses; never use this to drop original speech."""
    frame=max(1,int(sr*.02))
    level=np.array([np.sqrt(np.mean(x[i:i+frame]**2)) for i in range(0,len(x),frame)])
    if not len(level):return [(0,len(x))]
    active=level>max(.004,float(np.quantile(level,.93))*.16)
    idx=np.flatnonzero(active)
    if not len(idx):return [(0,len(x))]
    units=[];start=int(idx[0]);end=start
    for point in idx[1:]:
        point=int(point)
        if point-end>8:  # silence longer than ~180 ms is a usable phrase break
            a=max(0,(start-3)*frame);b=min(len(x),(end+4)*frame)
            if b-a>=sr*.22:units.append((a,b))
            start=point
        end=point
    a=max(0,(start-3)*frame);b=min(len(x),(end+4)*frame)
    if b-a>=sr*.22:units.append((a,b))
    return units if units else [(0,len(x))]

def comic_variant(clip, mode, sr, rng):
    """Original, royalty-free voice manipulations, never replacing the narration."""
    if len(clip)<sr*.1:return clip
    if mode=='auto':
        mode=('classic','cartoon','scratch','robot')[int(rng.integers(0,4))]
    if mode=='chaos':
        mode=('cartoon','scratch','robot')[int(rng.integers(0,3))]
    x=clip.copy()
    if mode=='cartoon':
        speed=float(rng.choice([.76,1.28,1.47]))
        out_len=max(1,int(len(x)/speed))
        x=np.interp(np.arange(out_len)*speed,np.arange(len(x)),x,
                    left=0,right=0).astype(np.float32)
    elif mode=='scratch':
        short=x[:min(len(x),int(sr*.21))]
        x=np.concatenate([short,short[::-1],short,short[::-1],short])
    elif mode=='robot':
        t=np.arange(len(x))/sr
        x=x*(.55+.45*np.sign(np.sin(2*np.pi*21*t)))
        x=np.round(x*28)/28
    else:  # old-school beat-synced stutter with original source
        short=x[:min(len(x),int(sr*.16))]
        x=np.concatenate([short,short,short,x])
    k=min(int(sr*.009),len(x)//4)
    if k:
        fade=np.linspace(0,1,k,endpoint=False,dtype=np.float32)
        x[:k]*=fade;x[-k:]*=fade[::-1]
    return np.asarray(x,dtype=np.float32)


def zero_crossing_cut(x, target, sr):
    """Select a low-click cut near an intentional mid-syllable target."""
    x=np.asarray(x)
    if len(x)<4:return max(0,min(int(target),len(x)))
    t=max(1,min(len(x)-2,int(target)))
    radius=max(1,int(.012*sr))
    lo=max(1,t-radius);hi=min(len(x)-1,t+radius)
    crossings=np.flatnonzero(np.signbit(x[lo-1:hi-1])!=np.signbit(x[lo:hi]))+lo
    if crossings.size:
        return int(crossings[np.argmin(np.abs(crossings-t))])
    return int(lo+np.argmin(np.abs(x[lo:hi])))


def stretch_voice(clip, factor, sr):
    """Pitch-preserving WSOLA stretch for *short copied* vocal samples.

    Unlike slowing the playback rate, the output retains the original vocal
    pitch. Local waveform matching avoids the phase-vocoder's metallic edge,
    particularly on consonants. The clean narration is never modified.
    """
    x=np.asarray(clip,dtype=np.float32)
    if not .55<=factor<=2.8:
        raise ValueError("unsupported stretch factor")
    if len(x)<max(256,int(.08*sr)) or abs(factor-1.)<.015:
        return x.copy()
    target=max(1,int(round(len(x)*factor)))
    window=max(128,int(.032*sr)//2*2)
    hop=max(16,window//4)
    overlap=window-hop
    search=max(6,int(sr*.006))
    output=np.zeros(target+window,dtype=np.float64)
    weights=np.zeros_like(output)
    win=np.hanning(window+2)[1:-1].astype(np.float64)
    padded=np.pad(x.astype(np.float64),(window,window*2))
    original_size=len(x)
    previous=0
    for out_pos in range(0,target,hop):
        expected=int(round(out_pos/factor))
        if out_pos==0:
            best=0
        else:
            reference=output[out_pos:out_pos+overlap]/np.maximum(
                weights[out_pos:out_pos+overlap],.0001)
            reference=reference-reference.mean()
            ref_energy=float(np.dot(reference,reference))
            best=max(0,min(original_size-1,expected))
            high=-1e30
            if ref_energy>1e-9:
                step=max(1,sr//8000)
                low=max(0,expected-search)
                upper=min(original_size-1,expected+search)
                for candidate in range(low,upper+1,step):
                    fragment=padded[window+candidate:window+candidate+overlap]
                    centered=fragment-fragment.mean()
                    energy=float(np.dot(centered,centered))
                    if energy<1e-10:
                        continue
                    score=float(np.dot(reference,centered))/math.sqrt(
                        ref_energy*energy)
                    # Favour the expected phoneme location on near-ties.
                    score-=.0003*abs(candidate-expected)/max(1,search)
                    if score>high:
                        high=score
                        best=candidate
        fragment=padded[window+best:window+best+window]
        usable=min(window,len(output)-out_pos)
        output[out_pos:out_pos+usable]+=fragment[:usable]*win[:usable]
        weights[out_pos:out_pos+usable]+=win[:usable]
        previous=best
    y=(output[:target]/np.maximum(weights[:target],.001)).astype(np.float32)
    if not np.isfinite(y).all():
        raise ValueError("invalid stretched vocal")
    return np.clip(y,-1.,1.)



def pitch_speed(clip, semitones, sr):
    """Old-school tape-pitch: rising/falling pitch also changes duration."""
    x=np.asarray(clip,dtype=np.float32)
    rate=2**(float(semitones)/12)
    target=max(1,int(round(len(x)/rate)))
    return np.interp(np.arange(target)*rate,np.arange(len(x)),x,
                     left=0,right=0).astype(np.float32)


def tape_stop(clip, sr, duration=.70):
    """Decelerating tape-deck playback that drops in pitch and slows to a stop."""
    x=np.asarray(clip,dtype=np.float32)
    length=max(1,int(min(duration,1.4)*sr))
    t=np.linspace(0,1,length,dtype=np.float32)
    speed=1.55*(1-t)**2+.07
    index=np.cumsum(speed).astype(np.float64)
    index-=index[0]
    if len(x)>1:index*=min(1.,(len(x)-1)/max(1.,index[-1]))
    y=np.interp(index,np.arange(len(x)),x,left=0,right=0)
    y*=np.maximum(0,1-t**2)**.7
    return y.astype(np.float32)


def pitch_bend(clip, sr):
    """Record-player pitch sweep; deliberate voice distortion."""
    x=np.asarray(clip,dtype=np.float32)
    if len(x)<5:return x.copy()
    n=max(1,int(len(x)*1.15))
    t=np.linspace(0,1,n,dtype=np.float32)
    rates=.56+1.25*t**1.5
    idx=np.cumsum(rates,dtype=np.float64)
    idx-=idx[0]
    idx*=min(1.,(len(x)-1)/max(1.,idx[-1]))
    return np.interp(idx,np.arange(len(x)),x).astype(np.float32)


def broken_roll(clip, sr, bpm, rng):
    """Slice WITHIN a word, roll in triplets, interrupt, then resume with
    scratch/granular chops. Copies only; the clean narration remains uncut."""
    x=np.asarray(clip,dtype=np.float32)
    if len(x)<int(.14*sr):return x.copy()
    middle=zero_crossing_cut(x,len(x)//2,sr)
    width=max(1,min(int(sr*60/bpm/3),int(sr*.20)))
    middle=max(width,min(len(x)-width,middle))
    grain=x[max(0,middle-width):middle]
    if len(grain)<int(.03*sr):grain=x[:width]
    chunks=[]
    for j in range(6):
        piece=grain.copy()
        if j in (2,4):piece=piece[::-1].copy()
        if j>=3:piece=pitch_speed(piece,3 if j%2 else -3,sr)
        chunks.append(piece)
        if j==3:chunks.append(np.zeros(int(.12*sr),np.float32)) # the intentional break
    out=np.concatenate(chunks+[x[middle:min(len(x),middle+width*2)]])
    return out.astype(np.float32)


def vintage_voice_fx(clip, mode, sr, bpm, rng):
    """A library of early-90s/2000s DJ tricks, synthesized from the user audio."""
    x=np.asarray(clip,dtype=np.float32)
    if len(x)<int(sr*.10):return x.copy()
    if mode=='auto':
        mode=('dj','stretch','pitch','tape','glitch','scratch','cartoon','vinyl','robot')[
            int(rng.integers(0,9))]
    if mode=='chaos':
        mode=('dj','glitch','stretch','tape','pitch')[int(rng.integers(0,5))]
    if mode=='stretch':
        # Stretch one clean copied sample moderately. The previous 2.3x
        # mid-phoneme duplicate produced unnatural joins and drawn-out vowels.
        y=stretch_voice(x,1.32,sr)
    elif mode=='tape':
        y=np.concatenate([x[:len(x)//2],tape_stop(x[len(x)//2:],sr,.65)])
    elif mode=='pitch':
        cut=zero_crossing_cut(x,len(x)//2,sr)
        y=np.concatenate([pitch_speed(x[:cut],-6,sr),pitch_bend(x[cut:],sr)])
    elif mode=='glitch':
        y=broken_roll(x,sr,bpm,rng)
    elif mode=='vinyl':
        lo=sosfilt(butter(2,[230,min(4300,sr*.43)],btype='bandpass',
                            fs=sr,output='sos'),x).astype(np.float32)
        y=np.round(np.tanh(lo*2.1)*30)/30
        y=y.astype(np.float32)
    elif mode=='dj':
        cut=zero_crossing_cut(x,len(x)//2,sr)
        first=x[:cut]
        roll=broken_roll(x[max(0,cut-int(sr*.38)):],sr,bpm,rng)
        slowed=tape_stop(x[cut:],sr,.42)
        y=np.concatenate([first,roll,np.zeros(int(sr*.11),np.float32),slowed])
    elif mode in ('helium','monster','yo_yo','comic_roll','rewind'):
        y=comedy_voice_transform(x,mode,sr,bpm,rng)
    else:
        y=comic_variant(x,mode,sr,rng)
    limit=int(sr*3.15)
    y=np.clip(np.asarray(y[:limit],dtype=np.float32),-1,1)
    k=min(int(sr*.009),len(y)//4)
    if k>0:
        ramp=np.linspace(0,1,k,endpoint=False,dtype=np.float32)
        y[:k]*=ramp;y[-k:]*=ramp[::-1]
    return y


def comedy_voice_transform(clip, mode, sr, bpm, rng):
    """Pronounced vocal-only turntable/comedy stingers.

    These are placed BETWEEN original spoken phrases, never over the
    next words. Distinct pitch, rhythmic rolls and exaggerated delivery
    preserve the entire clean source recording elsewhere.
    """
    x=np.asarray(clip,dtype=np.float32)
    if len(x)<int(sr*.12):return x.copy()
    if mode=='helium':
        # Chipmunk: exaggerated tape-pitch rise with a little syllable roll.
        high=pitch_speed(x,9,sr)
        return np.concatenate((high[:min(len(high),int(.15*sr))],
                               high[:min(len(high),int(.15*sr))],high))
    if mode=='monster':
        deep=pitch_speed(x,-10,sr)
        wobble=np.sin(2*np.pi*13*np.arange(len(deep))/sr).astype(np.float32)
        return np.tanh(deep*(1.16+.24*wobble)).astype(np.float32)
    if mode=='yo_yo':
        mid=max(1,zero_crossing_cut(x,len(x)//2,sr))
        return np.concatenate((pitch_speed(x[:mid],8,sr),
                               pitch_speed(x[mid:],-9,sr),
                               pitch_speed(x[:mid],5,sr)))
    if mode=='comic_roll':
        grain=x[max(0,len(x)//3-int(sr*.12)):max(1,len(x)//3)]
        if len(grain)<int(sr*.035):grain=x[:max(1,int(sr*.10))]
        bits=[pitch_speed(grain,p,sr) for p in (0,4,8,12,-7,0)]
        return np.concatenate(bits+[x])
    if mode=='rewind':
        left=x[:max(1,len(x)//2)]
        return np.concatenate((left,left[::-1],pitch_speed(x,-5,sr),x[-int(sr*.12):]))
    return x.copy()


def vocal_fx_timeline(voice, sr, bpm, humor, intensity, rng):
    """Non-destructive 1990s-style vocal sampling.

    All original WhatsApp samples remain in the dry stem. Scratch, pitch
    bends, stutters and stretch FX are copied only from those samples, with
    musical crossfades; instrumental music NEVER enters this processor.
    """
    x=np.asarray(voice,dtype=np.float32)
    if humor=='off' or len(x)<int(.35*sr):
        return x.copy()
    if intensity not in (1,2,3):
        raise ValueError('FX intensity must be 1, 2 or 3')
    wet=np.zeros_like(x)
    # Distinct punctuation, not a distortion every fraction of a second.
    # Short dense files get fewer tricks; longer spoken messages get more.
    spacing={1:3.8,2:2.7,3:2.05}[intensity]
    beat=60./bpm
    window=int(min(.76,beat*1.6)*sr)
    order=('stretch','pitch','glitch','tape','cartoon','dj','vinyl','scratch','robot')
    count=0
    for target_seconds in np.arange(.7,len(x)/sr-.3,spacing):
        # Find an actual strong syllable near the proposed beat-synced point.
        anchor=int(round(target_seconds/beat)*beat*sr)
        lo=max(0,anchor-int(.55*sr))
        hi=min(len(x)-window,anchor+int(.42*sr))
        if hi<=lo:continue
        stride=max(1,int(.05*sr))
        positions=range(lo,hi+1,stride)
        # Prefer a sustained vowel/deliberate syllable, not silence.
        start=max(positions,key=lambda p:float(np.mean(x[p:p+window:12]**2)))
        src=x[start:start+window].copy()
        if len(src)<int(.22*sr) or float(np.sqrt(np.mean(src*src)))<.012:
            continue
        mode=order[count%len(order)] if humor in ('auto','chaos') else humor
        count+=1
        # Large effects only on one copy of the ORIGINAL spoken voice.
        effect=vintage_voice_fx(src,mode,sr,bpm,rng)
        if len(effect)<int(.04*sr):continue
        effect=effect[:min(len(effect),int(.93*sr),len(x)-start)]
        length=len(effect)
        fade=min(int(.018*sr),length//5)
        envelope=np.ones(length,dtype=np.float32)
        if fade:
            ramp=np.linspace(0,1,fade,endpoint=False,dtype=np.float32)
            envelope[:fade]=ramp
            envelope[-fade:]=ramp[::-1]
        wet[start:start+length]+=effect*envelope
    # Keep untouched words fully audible at ALL times, even inside chops.
    # No destructive replacement, no arbitrary silence, and no word loss.
    amount={1:.34,2:.47,3:.60}[intensity]
    if humor=='chaos':amount=min(.67,amount*1.12)
    peak=max(.15,float(np.max(np.abs(wet))))
    wet=wet*min(1.0,.82/peak)
    return (x*.84+wet*amount).astype(np.float32)



def _vocal_hook_quality(sample, sr):
    """Rate a sampled word fragment for clear, musical comedy inserts.

    Louder is not automatically better: breath noise, fricatives and clicks
    often have high RMS but are unpleasant when pitch-shifted or repeated.
    Prefer short, voiced/harmonic material without clipping. This is a
    lightweight spectral heuristic, not a substitute for word alignment.
    """
    x=np.asarray(sample,dtype=np.float32)
    if len(x)<int(.09*sr) or not np.isfinite(x).all():
        return 0.
    rms=float(np.sqrt(np.mean(x*x)))
    if rms<.009:return 0.
    # Calculate a small downsampled Hann-windowed spectrum. Harmonic vowels
    # have concentrated energy; hiss/breath has near-flat spectral energy.
    stride=max(1,sr//8000)
    short=x[::stride]
    size=min(len(short),2048)
    if size<128:return 0.
    frame=short[(len(short)-size)//2:(len(short)+size)//2]
    spectrum=np.abs(np.fft.rfft(frame*np.hanning(len(frame))))**2
    spectrum=spectrum[2:]
    mean=float(np.mean(spectrum))
    if mean<1e-10:return 0.
    flatness=float(np.exp(np.mean(np.log(spectrum+1e-10)))/(mean+1e-10))
    saturation=float(np.mean(np.abs(x)>.94))
    # Use a modest loudness weighting to avoid picking consonant transients.
    return min(.35,rms)*(.04+.96*(1.-min(1.,flatness))**2)*(1.-min(1.,saturation*8))


def _semantic_comedy_cue(transcript, fraction):
    """Conservative speech-dependent comic preset for approximate phrase timing.

    The original Hebrew is used locally on the production server only.
    Word-count interpolation is explicitly NOT forced word alignment, so the
    source audio and syllable boundaries remain untouched.
    """
    phrases=[part.strip() for part in re.split(r"[.!?;,]+",str(transcript or "")[:4000])
             if part.strip()]
    if not phrases:return None
    counts=[max(1,len(re.findall(r"[א-ת]+",part))) for part in phrases]
    target=max(0.,min(.999,float(fraction)))*sum(counts)
    elapsed=0
    part=phrases[-1]
    for item,count in zip(phrases,counts):
        elapsed+=count
        if target<elapsed:
            part=item
            break
    terms=set(re.findall(r"[א-ת]+",part))
    if terms.intersection(("לא","בלי","אינו","אינה","אינם")):
        return None
    cues=(
        (("חמור","החמור","חמורה","נוער","נעירה","צורח","צועק","צעק"),"monster"),
        (("צחוק","מצחיק","צוחק","צוחקת","צוחקים","צחקתי","צחקו"),"comic_roll"),
        (("נפילה","נפל","נופל","נופלת","בום","פיצוץ","התפוצץ","נשבר"),"rewind"),
        (("בוכה","בכיתי","בכי","בכייה","תינוק"),"helium"),
        (("רוקד","רוקדת","רוקדים","ריקוד","מסיבה"),"yo_yo"),
        (("שרתי","שרים","שירה","לשיר","שיר"),"tape"),
    )
    for words,mode in cues:
        if terms.intersection(words):
            return mode
    return None


def arranged_vocal_track(voice, sr, bpm, humor, density, fx_gain, rng, transcript_hint=''):
    """Pause-aware, beat-length vocal solos without slicing spoken words.

    This is an automatic editing heuristic, not phoneme/word-level ASR
    alignment. It inserts FX ONLY in real measured gaps between utterances
    and at the recording's end; a continuous phrase is never cut merely to
    meet an arbitrary 1.85-second FX interval. Originals are bit-identical
    in original_spans and every FX sample is a separate solo, never an
    overlay over the next spoken word.
    """
    x=np.asarray(voice,dtype=np.float32)
    if humor=='off' or len(x)<int(sr*.5):
        return x.copy(),np.zeros(len(x),dtype=np.float32),[(0,len(x),0,len(x))]
    if density not in (1,2,3) or not .55<=fx_gain<=1.7:
        raise ValueError('invalid vocal effect controls')
    beat=60./bpm
    # Find only actual silences, with enough breathing room either side.
    units=speech_boundaries(x,sr)
    possible=[]
    for left,right in zip(units,units[1:]):
        gap=right[0]-left[1]
        if gap>=int(sr*.025):
            cut=(left[1]+right[0])//2
            if int(.7*sr)<cut<len(x)-int(.25*sr):
                possible.append(cut)
    # The old fixed five-second gap left most short WhatsApp speech
    # untouched and piled the only comic effect onto the final word.
    # Keep conservative gaps for longer narration, but adapt to 5–10s
    # voice notes: two or three spaced punchlines are more intelligible
    # than either no humor or a single exaggerated ending.
    duration=len(x)/sr
    min_spacing={1:6.5,2:3.8,3:2.5}[density]
    if duration<10.:
        min_spacing=min(min_spacing,max(1.75,duration/3.0))
    chosen=[]
    previous=0
    for cut in possible:
        if (cut-previous)/sr>=min_spacing:
            chosen.append(cut)
            previous=cut
    # One final flourish is allowed; do not repeat a word during every beat.
    final=len(x)
    if not chosen or (final-chosen[-1])/sr>=1.4:
        chosen.append(final)
    # Keep the whole narration intact; reserve up to 19% additional time
    # (capped to 10s) for a few genuinely paced comic punchlines.
    max_extensions=min(10.0,max(.85,len(x)/sr*.19))
    total_fx_seconds=0.
    pieces=[];masks=[];original_spans=[]
    position=0;offset=0
    # A recording needs one consistent comic language, not an unrelated
    # random effect family at every pause. These neutral hooks always use
    # copies of the actual spoken syllable; contextual effects require
    # an explicit, non-negated Hebrew story cue.
    neutral_hooks=('comic_roll','stretch')
    last_story_cue=None
    last_story_cue_cut=-int(sr*20)
    for index,cut in enumerate(chosen):
        raw=x[position:cut].copy()
        if len(raw):
            pieces.append(raw)
            masks.append(np.zeros(len(raw),dtype=np.float32))
            original_spans.append((position,cut,offset,offset+len(raw)))
            offset+=len(raw)
        position=cut
        remaining=max_extensions-total_fx_seconds
        if remaining<.20 or len(raw)<int(.35*sr):
            continue
        # Collect a short sample from the last clearly voiced phoneme in
        # this phrase. The source phrase itself is NEVER truncated.
        width=min(int(sr*.43),len(raw))
        start=max(0,len(raw)-int(sr*.94))
        if len(raw)-start<width:
            start=max(0,len(raw)-width)
        step=max(1,int(sr*.03))
        candidates=range(start,len(raw)-width+1,step)
        if not candidates:
            continue
        # Locate an actual voiced/harmonic syllable, not merely the
        # loudest plosive or breath. Bias slightly toward the end of a
        # phrase, where a repeated hook reads as a punchline.
        last=max(start+1,len(raw)-width)
        pick=max(candidates,key=lambda p:
                 _vocal_hook_quality(raw[p:p+width],sr)*
                 (.88+.12*(p-start)/max(1,last-start)))
        sample=raw[pick:pick+width]
        source_rms=float(np.sqrt(np.mean(sample*sample)))
        if source_rms<.008:
            continue
        if humor=='auto':
            # Never invent an animal, explosion or baby from generic speech.
            # Avoid replaying the same specific gag in adjacent pauses;
            # between events use rhythmic samples of the speaker instead.
            cue=_semantic_comedy_cue(transcript_hint,cut/max(1,len(x)))
            if cue and cue==last_story_cue and cut-last_story_cue_cut<int(sr*7):
                cue=None
            if cue:
                last_story_cue=cue
                last_story_cue_cut=cut
            mode=cue or neutral_hooks[index%len(neutral_hooks)]
        else:
            mode=(('helium','comic_roll','monster','yo_yo','rewind')[index%5]
                  if humor=='chaos' else humor)
        effect=vintage_voice_fx(sample,mode,sr,bpm,rng)
        if not len(effect):
            continue
        # Phrase breaks use an intentionally short half/whole-beat fill.
        # The total effect overhead is bounded: a 30-second voice will not
        # be dragged out into minutes by repeated stretches and rewinds.
        # Musical length is planned BEFORE trimming: half, one, two or
        # three beats according to the joke, source phrase and intensity.
        # A two-beat monster/rewind punchline must not be shaved down to a
        # generic 0.6-second insert just because BPM is high.
        dramatic=mode in ('monster','rewind','tape','stretch','dj')
        desired_beats=(
            (1.0 if density==1 else 2.0) if dramatic
            else (1.0 if density<=2 else 1.5))
        if cut==final:
            # One last longer cadence only at the END of the recording.
            desired_beats=min(desired_beats,2.0)
        max_fx=min(remaining-.04,beat*desired_beats)
        if max_fx<.18:
            continue
        planned_samples=max(1,int(max_fx*sr))
        # Speed-normalise an actual effect to a chosen beat duration
        # without changing its final perceived pitch again.
        # WSOLA avoids the crude "stretch then amputate" behaviour.
        ratio=planned_samples/max(1,len(effect))
        if .55<=ratio<=2.8:
            effect=stretch_voice(effect,ratio,sr)
        elif ratio>2.8:
            effect=stretch_voice(effect,2.8,sr)
            # Remaining room is NOT padded with silence or fake laughter.
        else:
            effect=effect[:planned_samples]
        effect=np.asarray(effect[:planned_samples],dtype=np.float32)
        effect_rms=float(np.sqrt(np.mean(effect*effect)))
        if effect_rms<.0001:
            continue
        gain=min(3.0,max(.4,(source_rms/effect_rms)*fx_gain*
                         {1:.85,2:1.,3:1.12}[density]))
        # Smooth dynamics, never hard clip a loud source or the insert itself.
        effect=np.tanh(effect*gain*.9).astype(np.float32)
        # Longer micro-fades soften the end of a forcibly bounded fill
        # and avoid high-frequency clicks at the next spoken phrase.
        fade=min(int(sr*.055),len(effect)//4)
        if fade:
            ramp=np.linspace(0.,1.,fade,endpoint=False,dtype=np.float32)
            effect[:fade]*=ramp
            effect[-fade:]*=ramp[::-1]
        # Snap the insertion towards the *next* eighth-note only if it needs
        # <=60ms of padding; never delay a speaker by a large quantization gap.
        beat_grid=beat/2.
        timeline=offset/sr+beat*4.
        delay=(beat_grid-timeline%beat_grid)%beat_grid
        pad=min(.06,delay) if delay<=.06 else 0.
        if pad:
            pause=np.zeros(int(sr*pad),dtype=np.float32)
            pieces.append(pause);masks.append(np.zeros(len(pause),np.float32))
            offset+=len(pause)
        pieces.append(effect)
        masks.append(np.ones(len(effect),dtype=np.float32))
        offset+=len(effect)
        total_fx_seconds+=len(effect)/sr+pad
    if position<len(x):
        rest=x[position:].copy()
        pieces.append(rest)
        masks.append(np.zeros(len(rest),dtype=np.float32))
        original_spans.append((position,len(x),offset,offset+len(rest)))
    if not pieces:
        return x.copy(),np.zeros(len(x),dtype=np.float32),[(0,len(x),0,len(x))]
    return np.concatenate(pieces),np.concatenate(masks),original_spans




def speech_aware_music_map(arranged, sr, bpm, seconds, frame_seconds=.10):
    """Locate REAL voiced spans for musical call-and-response arrangement.

    Uses the original-sample mapping returned by arranged_vocal_track;
    inserted jokes and silence do not masquerade as spoken sentences.
    Energy is only used to schedule music, never to delete speech.
    No unreliable word timestamps or external transcription dependency.
    """
    frames=max(1,int(math.ceil(seconds/frame_seconds)))
    voiced=np.zeros(frames,dtype=np.float32)
    fill_locations=[]
    cursor=4*(60./bpm)
    for track,mask,spans in arranged:
        for _,_,start,end in spans:
            for at in range(start,end,max(1,int(frame_seconds*sr))):
                excerpt=track[at:min(end,at+int(frame_seconds*sr))]
                if len(excerpt)<int(.02*sr):
                    continue
                rms=float(np.sqrt(np.mean(excerpt*excerpt)))
                if rms>=.024:
                    index=int((cursor+at/sr)/frame_seconds)
                    if index<frames:
                        voiced[index]=max(voiced[index],min(1.,rms/.095))
        marks=np.flatnonzero((mask[1:]>.5)&(mask[:-1]<=.5))+1
        for index in marks:
            fill_locations.append(cursor+index/sr)
        cursor+=len(track)/sr+3*(60./bpm)
    # 300ms 'look both ways' smoothing keeps single loud consonants from
    # producing jarring note-by-note volume oscillations.
    smoothed=np.convolve(voiced,np.array([.12,.20,.36,.20,.12],np.float32),mode='same')
    return smoothed.astype(np.float32),fill_locations

def render_mix(clips,sample_rate=32000,seconds=60,bpm=145,style='mixed',voice_level=1,melody='auto',humor='auto',fx_intensity=2,fx_gain=1.15,mix_variation=0,return_voice=False,progress=lambda *args:None,transcript_hint=''):
    if not 120<=bpm<=165 or seconds not in (0,30,60,90,120,180) or style not in STYLES or humor not in HUMOR or not (melody=='auto' or str(melody) in ('1','2','3','4','5','6')) or fx_intensity not in (1,2,3) or not .55<=fx_gain<=1.7 or type(mix_variation) is not int or not 0<=mix_variation<=100000 or not .5<=voice_level<=1.5 or not 8000<=sample_rate<=48000:raise ValueError('הגדרות המיקס אינן תקינות')
    if not 1<=len(clips)<=4:raise ValueError('יש לבחור בין הקלטה אחת לארבע הקלטות')
    sr=sample_rate;beat=60/bpm
    voices=[prepare_voice(c,sr) for c in clips]
    signature=hashlib.blake2b(digest_size=8)
    for v in voices:
        signature.update(len(v).to_bytes(8,'little'))
        signature.update(v[::max(1,len(v)//512)].tobytes())
    signature.update(mix_variation.to_bytes(4,'little'))
    seed=int.from_bytes(signature.digest(),'little')
    rng=np.random.default_rng(seed)
    voice_rng=np.random.default_rng(seed^0x9E3779B97F4A7C15)
    # Voice is arranged FIRST. Its actual duration determines the score length.
    # This guarantees the last words and the final vocal trick cannot be cut.
    arranged=[arranged_vocal_track(v,sr,bpm,humor,fx_intensity,fx_gain,voice_rng,
                                   transcript_hint=transcript_hint)
              for v in voices]
    total_vocal_duration=sum(len(track)/sr for track,_,_ in arranged)
    needed=beat*10+total_vocal_duration+max(0,len(voices)-1)*beat*3
    seconds=max(30.,float(seconds),math.ceil(needed))
    if seconds>360:raise ValueError('משך ההקלטות הכולל גדול מדי לעיבוד חינמי')
    n=int(round(seconds*sr))
    activity,fx_fill_times=speech_aware_music_map(arranged,sr,bpm,seconds)
    def talking(t):
        if t<0:return 0.
        frame=int(t/.10)
        if frame>=len(activity):return 0.
        return float(np.max(activity[max(0,frame-1):min(len(activity),frame+4)]))
    music=np.zeros((n,2),dtype=np.float32)
    def add(x,time,gain=1,pan=0):
        start=int(round(time*sr));count=min(len(x),n-start)
        if start<0 or count<=0:return
        music[start:start+count,0]+=x[:count]*gain*(1-pan*.5)
        music[start:start+count,1]+=x[:count]*gain*(1+pan*.5)
    def sample(duration,fn):return fn(np.arange(int(duration*sr))/sr).astype(np.float32)
    kick=sample(.32,lambda t:.78*np.sin(2*np.pi*(48*t+115*.021*(1-np.exp(-t/.021))))*np.exp(-t*13)+rng.uniform(-1,1,len(t))*.035*np.exp(-t*250))
    hat=sample(.12,lambda t:rng.uniform(-1,1,len(t))*np.exp(-t*65)*.065)
    snare=sample(.22,lambda t:(rng.uniform(-1,1,len(t))*.14*np.exp(-t*24)+.11*np.sin(2*np.pi*185*t)*np.exp(-t*32))*(1-np.exp(-t*400)))
    # Synthetic hand-drum, not a sampled melody or recorded performance.
    darbuka=sample(.17,lambda t:(
        .27*np.sin(2*np.pi*(174*t-45*t*t))*np.exp(-t*29)+
        .075*rng.uniform(-1,1,len(t))*np.exp(-t*65)))
    # Music production: stable D-minor scale and i–VI–III–VII chord cycle.
    # Timbres, rhythms and melodic phrases change while harmony remains coherent.
    cache={}
    # Distinctive original Israeli-folk / trance flavor uses D Freygish
    # (Phrygian dominant), not a copyrighted popular Hebrew song.
    if style=='israeli':
        allowed_pc=(0,2,3,6,7,9,10)  # C D Eb F# G A Bb
        chords=((38,(2,6,9)),(39,(3,7,10)),(43,(7,10,2)),(36,(0,3,7)))
    else:
        allowed_pc=(0,2,4,5,7,9,10)  # D natural minor
        chords=((38,(2,5,9)),(34,(10,2,5)),(41,(5,9,0)),(36,(0,4,7)))
    contours=(
        (0,2,4,7,4,2,0,2),(0,4,3,2,0,2,5,4),(4,3,2,0,2,3,5,7),
        (7,5,4,2,4,2,0,2),(0,0,4,5,7,5,4,2),(2,5,7,5,4,2,0,4))
    sound_colors=('pluck','lead','bell','saw','organ','acid')
    # Harmonize every phrase to the active chord: downbeats land on chord notes.
    def quantized_pitch(target,chord_pcs,strong=False):
        pcs=chord_pcs if strong else allowed_pc
        return min((p for p in range(62,87) if p%12 in pcs),
                   key=lambda p:abs(p-target))
    def synth(m,dur,kind):
        key=(m,round(dur,3),kind)
        if key in cache:return cache[key]
        f=440.*2**((m-69.)/12.)
        t=np.arange(max(1,int(sr*dur)),dtype=np.float32)/sr
        fundamental=np.sin(2*np.pi*f*t)
        second=np.sin(2*np.pi*f*2*t)
        third=np.sin(2*np.pi*f*3*t)
        if kind=='bass':
            raw=.85*fundamental+.24*second
            env=np.exp(-t*8.5)*np.minimum(1.,t/.006)
            level=.27
        elif kind=='pad':
            # Smooth dual-oscillator pad: avoids the repetitive naked sine tune.
            detuned=np.sin(2*np.pi*f*1.006*t+.12*np.sin(2*np.pi*.65*t))
            raw=.42*fundamental+.23*second+.10*third+.24*detuned
            env=np.minimum(1.,t/.12)*np.clip((dur-t)/.24,0,1)
            level=.10
        elif kind=='acid':
            raw=(2*((t*f)%1)-1)+.19*second
            env=np.exp(-t*7.6)*np.minimum(1.,t/.008)
            level=.15
        elif kind=='bell':
            raw=fundamental+.25*np.sin(2*np.pi*f*2.012*t)+.2*third
            env=np.exp(-t*5.8)
            level=.145
        elif kind=='organ':
            raw=.65*fundamental+.37*second+.18*third
            env=np.clip((dur-t)/.055,0,1)*np.minimum(1.,t/.009)
            level=.095
        elif kind=='saw':
            # Band-limited harmonic stack rather than brittle full-scale saw.
            raw=(fundamental+.42*second+.22*third+
                 .10*np.sin(2*np.pi*f*4*t)+
                 .06*np.sin(2*np.pi*f*5*t)+
                 .16*np.sin(2*np.pi*f*1.008*t))
            env=np.exp(-t*5.6)*np.minimum(1.,t/.006)
            level=.12
        elif kind=='pluck':
            raw=fundamental+.27*second+.08*third
            env=np.exp(-t*13.)
            level=.165
        elif kind=='oud':
            # Original plucked timbre: woody attack and natural harmonic
            # decay, not a sample of a recorded artist.
            raw=.84*fundamental+.32*second+.24*third
            env=np.minimum(1.,t/.004)*np.exp(-t*9.8)
            level=.19
        elif kind=='reed':
            vibrato=np.sin(2*np.pi*5.3*t)*.012
            raw=(.68*np.sin(2*np.pi*f*t*(1.+vibrato))+
                 .34*second+.20*third)
            env=np.minimum(1.,t/.012)*np.clip((dur-t)/.055,0,1)
            level=.135
        else:
            raw=fundamental+.18*second+.11*np.sin(2*np.pi*f*1.009*t)
            env=np.exp(-t*6.5)
            level=.15
        out=np.tanh(raw*1.20)*env*level
        out*=np.minimum(1.,t/.005)*np.clip((dur-t)/.015,0,1)
        cache[key]=out.astype(np.float32)
        return cache[key]
    # Sections remain coherent: intro -> groove -> build -> drop ->
    # breakdown -> final drop -> outro.
    total=math.ceil(seconds/beat)
    bars=max(1,math.ceil(total/4))
    intro_end=max(2,min(4,bars//10))
    outro_start=max(intro_end+2,bars-3)
    music_seed=int(rng.integers(0,6)) if melody=='auto' else int(melody)-1
    progress(10,'יוצר מבנה טראנס והרמוניה אחידה')
    for b in range(total):
        time=b*beat
        bar=b//4;quarter=b%4
        if bar<intro_end:
            section='intro'
        elif bar>=outro_start:
            section='outro'
        else:
            pct=(bar-intro_end)/max(1,outro_start-intro_end)
            section='groove' if pct<.22 else 'build' if pct<.35 else 'drop' if pct<.57 else 'breakdown' if pct<.70 else 'final'
        chord_root,chord_pcs=chords[bar%4]
        phrase=(bar//4)
        motif_index=(music_seed+bar//4)%len(contours) if melody=='auto' else music_seed
        motif=contours[motif_index]
        # Change instrumental color every two bars, keeping the rhythmic
        # hook for four bars. Variation is arranged, never randomly pasted.
        theme=sound_colors[(bar//2+music_seed)%len(sound_colors)]
        if style=='acid':theme='acid'
        if style=='eurodance':theme='organ'
        if style=='progressive':theme='pluck'
        if style in ('psy','goa'):theme='saw'
        if style=='uplifting':theme='bell'
        if style=='israeli':theme='oud' if phrase%2==0 else 'reed'
        # Percussion patterns, musical bass and volume-driven section changes.
        strength={'intro':.22,'groove':.55,'build':.63,'drop':.9,
                  'breakdown':.19,'final':.98,'outro':.33}[section]
        if section!='breakdown' or quarter==0:
            add(kick,time,strength)
        if section in ('groove','build','drop','final'):
            add(hat,time+beat*.5,1.0 if section!='final' else 1.35,-.40)
            if section in ('drop','final'):
                add(hat,time+beat*.75,.52,.40)
        if quarter in (1,3) and section in ('groove','build','drop','final'):
            add(snare,time,.48 if section=='groove' else .70)
        if style=='israeli' and section in ('groove','build','drop','final'):
            if quarter in (0,2):
                add(darbuka,time+beat*.5,.56 if quarter==0 else .42,
                    -.12 if quarter==0 else .13)
            if quarter==3:
                add(darbuka,time+beat*.75,.30,.18)
        if section=='build' and quarter==3:
            for j in range(4):
                add(snare,time+j*beat/4,.20+j*.12)
        if section not in ('intro','breakdown','outro'):
            for j in (0,2,3):
                bass_offset=0 if j!=3 else 12
                add(synth(chord_root+bass_offset,beat*.22,'bass'),
                    time+j*beat/4,.88 if section in ('drop','final') else .57)
        # One pad chord per BAR, not a random note every beat.
        if quarter==0 and section!='outro':
            for k,pc in enumerate(chord_pcs):
                pitch=min((p for p in range(50,68) if p%12==pc),
                          key=lambda p:abs(p-(chord_root+19)))
                add(synth(pitch,beat*3.65,'pad'),time,.53 if section=='breakdown' else .46,
                    (k-1)*.30)
        # DJ-style call and response: voice gets first priority. The motif
        # answers in REAL measured gaps, instead of a constant annoying loop
        # under every spoken syllable. Original key and chord remain stable.
        if section in ('intro','drop','final','breakdown') or (section=='groove' and bar%2==0):
            density=2 if section in ('drop','final') else 1
            for j in range(density):
                note_time=time+j*beat/2
                speech_level=talking(note_time)
                if speech_level>.31:
                    # Leave speech clear: no competing high synth during
                    # active conversation, but drums/bass keep the groove.
                    continue
                # Musical rests stop the incessant eight-note machine loop.
                if j==1 and (quarter+bar)%3==0:
                    continue
                if section=='breakdown' and quarter==1:
                    continue
                step=(quarter*2+j+(bar%4==3))%8
                scale_steps=(0,1,4,5,7,8,10,12) if style=='israeli' else (0,2,3,5,7,8,10,12)
                target=74+scale_steps[motif[step]%8]-5
                pitch=quantized_pitch(target,chord_pcs,strong=(quarter==0 and j==0))
                wave=synth(pitch,beat*(.62 if j==0 else .30),theme)
                gain=(.53 if section=='intro' else .58 if section=='breakdown' else .73)
                gain*=1.03-.60*speech_level
                add(wave,note_time,gain,-.18 if j==0 else .18)
                if section=='final' and j==0 and speech_level<.14 and quarter==3:
                    add(wave,time+beat*.75,.10,.38)
        # Small original rhythmic turnaround in each four-bar phrase.
        if section in ('drop','final') and bar%4==3 and quarter==3:
            add(snare,time+beat*.5,.30,-.12)
            add(hat,time+beat*.75,.45,.28)
        # A build is actual snare acceleration; the breakdown removes drums.
        if b%16==0:
            progress(10+int(45*b/max(1,total)),'מפיק ליווי עשיר עם הרמוניה ומעברים')
    progress(62,'משמיע רולים ועיוותי קול בעוצמה מלאה ללא חפיפות')
    vocal=np.zeros(n,dtype=np.float32)
    fx_highlight=np.zeros(n,dtype=np.float32)
    cursor=beat*4
    for track,mask,_ in arranged:
        start=int(round(cursor*sr))
        end=min(n,start+len(track))
        if end>start:
            vocal[start:end]+=track[:end-start]*voice_level
            fx_highlight[start:end]=np.maximum(fx_highlight[start:end],mask[:end-start])
        cursor+=len(track)/sr+beat*3
    progress(80,'מבצע מיקס כשהקול המעובד בחזית')
    # The synth is independent. Duck only its volume during speech so the
    # user's *treated* words remain in front, not drowned by the melody.
    from scipy.ndimage import maximum_filter1d
    env=maximum_filter1d(np.abs(vocal),size=max(1,int(sr*.025)))
    env=lfilter([.003],[1,-.997],env).astype(np.float32)
    # Keep a quiet rhythmic bed through the punchline instead of dropping
    # the instrumental almost to silence and then suddenly bringing it back.
    # Short voice samples and their story punctuation must remain a single
    # cohesive arrangement, especially on small phone loudspeakers.
    music*= ((1-.67*np.clip(env/.18,0,1))*(1-.20*fx_highlight))[:,None]
    # At a copied-voice comic punchline, create a short, intentional backing
    # break before its entrance. This leaves the spoken original untouched.
    # No arbitrary swooshes or cartoon noises are inserted here.
    for cue_time in fx_fill_times:
        at=int(cue_time*sr)
        left=max(0,at-int(.11*sr))
        right=min(n,at+int(.15*sr))
        if right<=left:continue
        down=np.ones(right-left,dtype=np.float32)
        until=at-left
        if until:
            down[:until]=np.linspace(.88,.28,until,endpoint=False,dtype=np.float32)
        if right>at:
            down[until:]=np.linspace(.28,.87,right-at,endpoint=True,dtype=np.float32)
        music[left:right]*=down[:,None]
    # Original cartoon punctuation is added to the INSTRUMENTAL stem ONLY.
    # It must never attenuate, distort or re-limit the spoken original.
    # Without a recognized contextual cue the treated voice itself is the
    # joke; no unrelated stock-like cartoon noise is invented.
    if humor=='auto' and transcript_hint:
        # Explicit Hebrew story cues override generic musical accents.
        from comic_stingers import add_comic_stings
        # The score contains intro/outro padding. Locate the actual
        # performed voice span before approximately mapping spoken Hebrew
        # clauses to comic events. Never pretend this is word alignment.
        active_voice=np.flatnonzero(np.abs(vocal)>.009)
        first=int(active_voice[0]) if len(active_voice) else 0
        last=int(active_voice[-1]) if len(active_voice) else len(vocal)-1
        span=max(1,last-first)
        music=add_comic_stings(
            music,fx_highlight,sr,bpm,
            lambda fraction:_semantic_comedy_cue(
                transcript_hint,max(0.,min(.999,
                    ((fraction*len(vocal))-first)/span))))
    music+=vocal[:,None]*1.13
    # Keep the voice solo clean, including in the reserved FX slots.
    # Echo and other delayed copies previously collided with the next line.
    # Conservative master gain / limiter: no global overdrive or loudness pumping.
    fade=np.clip(np.arange(n)/(sr*.025),0,1)*np.clip((n-1-np.arange(n))/(sr*.65),0,1)
    music*=fade[:,None]
    np.nan_to_num(music,copy=False)
    music*=.91/max(.91,float(np.max(np.abs(music))))
    progress(92,'מכין קובץ להורדה')
    return (music,vocal) if return_voice else music

def export_mp3(audio,path,sr=32000):
    audio=np.asarray(audio,dtype=np.float32)
    if audio.ndim==1:channels=1
    elif audio.ndim==2 and audio.shape[1]==2:channels=2
    else:raise ValueError('expected mono or stereo audio')
    subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(sr),
                    '-ac',str(channels),'-i','pipe:0',
                    '-af','alimiter=limit=0.92:level=false',
                    '-codec:a','libmp3lame','-b:a','192k',str(path)],
                   input=audio.astype('<f4').tobytes(),check=True,
                   capture_output=True,timeout=65)
