"""Original deterministic trance composition with original-audio sampling."""
import math
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
          'eurodance', 'hard', 'rave', 'mixed', 'auto')
HUMOR = ('auto', 'classic', 'cartoon', 'scratch', 'robot', 'chaos',
         'stretch', 'tape', 'pitch', 'glitch', 'vinyl', 'dj', 'off')
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
        if point-end>14:  # pause of at least 280 ms
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
    """Small phase-vocoder time stretch: elongates a syllable without
    simple sample-rate slowdown; intentionally retains a vintage granular edge.
    Only use on short FX copies, never on the full source narration."""
    x=np.asarray(clip,dtype=np.float32)
    if len(x)<512:return x.copy()
    if not .55<=factor<=2.8:raise ValueError("unsupported stretch factor")
    fft_size=512;hop=128
    _,_,z=stft(x,fs=sr,nperseg=fft_size,noverlap=fft_size-hop,
               boundary='zeros',padded=True)
    if z.shape[1]<3:return x.copy()
    rate=1.0/factor
    steps=np.arange(0,z.shape[1]-1,rate)
    advance=2*np.pi*hop*np.arange(z.shape[0])/fft_size
    phase=np.angle(z[:,0])
    output=np.empty((z.shape[0],len(steps)),dtype=np.complex64)
    for column,step in enumerate(steps):
        n=int(step);part=step-n
        amp=(1-part)*np.abs(z[:,n])+part*np.abs(z[:,n+1])
        output[:,column]=amp*np.exp(1j*phase)
        delta=np.angle(z[:,n+1])-np.angle(z[:,n])-advance
        phase+=advance+((delta+np.pi)%(2*np.pi)-np.pi)
    _,y=istft(output,fs=sr,nperseg=fft_size,noverlap=fft_size-hop,
              input_onesided=True,boundary=True)
    needed=max(1,int(round(len(x)*factor)))
    if len(y)<needed:y=np.pad(y,(0,needed-len(y)))
    return np.clip(y[:needed],-1,1).astype(np.float32)


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
        cut=zero_crossing_cut(x,len(x)//2,sr)
        grain=x[max(0,cut-int(.24*sr)):min(len(x),cut+int(.24*sr))]
        y=np.concatenate([x[:cut],stretch_voice(grain,2.3,sr),x[cut:]])
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
    else:
        y=comic_variant(x,mode,sr,rng)
    limit=int(sr*3.15)
    y=np.clip(np.asarray(y[:limit],dtype=np.float32),-1,1)
    k=min(int(sr*.009),len(y)//4)
    if k>0:
        ramp=np.linspace(0,1,k,endpoint=False,dtype=np.float32)
        y[:k]*=ramp;y[-k:]*=ramp[::-1]
    return y


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


def render_mix(clips,sample_rate=32000,seconds=60,bpm=145,style='mixed',voice_level=1,melody='auto',humor='auto',fx_intensity=2,return_voice=False,progress=lambda *args:None):
    if not 120<=bpm<=165 or seconds not in (0,30,60,90,120,180) or style not in STYLES or humor not in HUMOR or not (melody=='auto' or str(melody) in ('1','2','3','4','5','6')) or fx_intensity not in (1,2,3) or not .5<=voice_level<=1.5 or not 8000<=sample_rate<=48000:raise ValueError('הגדרות המיקס אינן תקינות')
    if not 1<=len(clips)<=4:raise ValueError('יש לבחור בין הקלטה אחת לארבע הקלטות')
    sr=sample_rate;beat=60/bpm
    voices=[prepare_voice(c,sr) for c in clips]
    total_speech=sum(len(v)/sr for v in voices)
    # Intro + complete narration + dedicated DJ turnaround slots + outro.
    # Never shorten a recording in order to satisfy a chosen output duration.
    needed=beat*7+total_speech+len(voices)*beat*16
    seconds=max(30.,float(seconds),math.ceil(needed))
    if seconds>360:raise ValueError('משך ההקלטות הכולל גדול מדי לעיבוד חינמי')
    n=int(round(seconds*sr))
    signature=hashlib.blake2b(digest_size=8)
    for v in voices:
        signature.update(len(v).to_bytes(8,'little'))
        signature.update(v[::max(1,len(v)//512)].tobytes())
    rng=np.random.default_rng(int.from_bytes(signature.digest(),'little'))
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
    # Music production: stable D-minor scale and i–VI–III–VII chord cycle.
    # Timbres, rhythms and melodic phrases change while harmony remains coherent.
    cache={}
    allowed_pc=(0,2,4,5,7,9,10)  # D natural minor pitch classes: C D E F G A Bb
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
            raw=.52*fundamental+.27*second+.14*third
            env=np.minimum(1.,t/.075)*np.clip((dur-t)/.16,0,1)
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
            raw=fundamental+.35*second+.20*third+.10*np.sin(2*np.pi*f*4*t)
            env=np.exp(-t*4.5)
            level=.14
        elif kind=='pluck':
            raw=fundamental+.27*second+.08*third
            env=np.exp(-t*13.)
            level=.165
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
        motif_index=(music_seed+phrase//2)%len(contours) if melody=='auto' else music_seed
        motif=contours[motif_index]
        theme=sound_colors[(phrase//2+music_seed)%len(sound_colors)]
        if style=='acid':theme='acid'
        if style=='eurodance':theme='organ'
        if style=='progressive':theme='pluck'
        if style in ('psy','goa'):theme='saw'
        if style=='uplifting':theme='bell'
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
        # Melodic variation every two phrases: same key, changed contour/timbre.
        if section in ('intro','drop','final','breakdown') or (section=='groove' and bar%2==0):
            density=2 if section in ('drop','final') else 1
            for j in range(density):
                step=(quarter*2+j)%8
                scale_steps=(0,2,3,5,7,8,10,12)
                target=74+scale_steps[motif[step]%8]-5
                pitch=quantized_pitch(target,chord_pcs,strong=(quarter==0 and j==0))
                wave=synth(pitch,beat*(.70 if j==0 else .35),theme)
                gain=(.62 if section=='intro' else .72 if section=='breakdown' else .93)
                add(wave,time+j*beat/2,gain,-.18 if j==0 else .18)
                if section=='final' and j==0:
                    add(wave,time+beat*.75,.12,.38)
        # A build is actual snare acceleration; the breakdown removes drums.
        if b%16==0:
            progress(10+int(45*b/max(1,total)),'מפיק ליווי עשיר עם הרמוניה ומעברים')
    progress(62,'מפעיל אפקטים על הקול שהגיע מ־WhatsApp')
    # The vocal waveform is the ONLY input to the processing chain; music
    # never receives pitch, tape, stutter or distortion effects.
    vocal=np.zeros(n,dtype=np.float32)
    cursor=beat*4
    for i,v in enumerate(voices):
        transformed=vocal_fx_timeline(v,sr,bpm,humor,fx_intensity,rng)
        start=int(round(cursor*sr))
        end=min(n,start+len(v))
        if end>start:
            vocal[start:end]+=transformed[:end-start]*voice_level
        cursor+=len(v)/sr+beat*16
    progress(80,'מבצע מיקס כשהקול המעובד בחזית')
    # The synth is independent. Duck only its volume during speech so the
    # user's *treated* words remain in front, not drowned by the melody.
    from scipy.ndimage import maximum_filter1d
    env=maximum_filter1d(np.abs(vocal),size=max(1,int(sr*.025)))
    env=lfilter([.003],[1,-.997],env).astype(np.float32)
    music*= (1-.78*np.clip(env/.18,0,1))[:,None]
    music+=vocal[:,None]*1.13
    # Subtle vocal-only echo. No echo or pitch FX applied to instruments.
    delay=int(beat*.75*sr)
    if 0<delay<n:
        music[delay:,0]+=vocal[:-delay]*.065
        music[delay:,1]+=vocal[:-delay]*.085
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
