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
    x=sosfilt(butter(2,[90,min(7000,sr*.43)],btype='bandpass',fs=sr,output='sos'),x).astype(np.float32)
    gain=min(4,.20/max(.001,float(np.sqrt(np.mean(x*x)))))
    x=np.tanh(x*gain*1.1)
    t=np.arange(len(x))/sr
    x*=np.minimum(1,t/.008)*np.minimum(1,(len(x)/sr-t)/.015)
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
    """Vocal-only inserts ON the original WhatsApp audio timeline.

    The original utterance never disappears: a quieter dry lane stays present
    throughout the treated regions; transformed voice is the prominent lane.
    No music waveforms enter this processor.
    """
    x=np.asarray(voice,dtype=np.float32)
    foreground=x.copy()
    assert intensity in (1,2,3)
    if humor=='off':return foreground
    window=int(sr*(2.5 if intensity==1 else 1.65 if intensity==2 else 1.10))
    duration=max(int(.35*sr),min(int(.76*sr),int(sr*60/bpm*1.55)))
    # Auto cycles through clearly different voice effects across the WHOLE file.
    order=('pitch','stretch','glitch','cartoon','dj','tape','robot','vinyl','scratch')
    passcount=0
    # Skip the first quarter-second, select across all successive windows.
    for wstart in range(int(.26*sr),max(0,len(x)-int(.25*sr)),window):
        region=x[wstart:min(len(x),wstart+window)]
        if len(region)<duration:return foreground
        # Work only on an energetic part of the uploaded VOICE.
        hop=max(1,int(sr*.06));width=min(duration,len(region))
        candidates=range(0,len(region)-width+1,hop)
        best=max(candidates,key=lambda i:float(np.mean(region[i:i+width:16]**2)))
        start=wstart+best;end=min(len(x),start+width)
        src=x[start:end]
        if len(src)<int(sr*.16) or float(np.sqrt(np.mean(src*src)))<.009:
            continue
        mode=order[passcount%len(order)] if humor in ('auto','chaos') else humor
        passcount+=1
        effected=vintage_voice_fx(src,mode,sr,bpm,rng)
        if len(effected)<32:continue
        # No pitch-compensating resize: doing so would undo the selected
        # vocal pitch/slowdown. Place the earliest full-length portion at the
        # *same* point in the source; insert effects into that voice span.
        effect=effected[:len(src)]
        if len(effect)<len(src):
            effect=np.pad(effect,(0,len(src)-len(effect)))
        # Two fast fades prevent clip-edge clicks and keep consonants audible.
        ramp_n=min(int(sr*.020),len(src)//5)
        envelope=np.ones(len(src),dtype=np.float32)
        if ramp_n:
            edge=np.linspace(0,1,ramp_n,endpoint=False,dtype=np.float32)
            envelope[:ramp_n]=edge
            envelope[-ramp_n:]=edge[::-1]
        # Wet voice is intentionally dominant; dry voice is retained as a
        # safety net so changing pitch never drops the original words.
        wet=.71 if intensity==1 else .90 if intensity==2 else 1.03
        dry=.28 if intensity==1 else .18 if intensity==2 else .14
        mix=(src*(1-envelope)+envelope*(dry*src+wet*effect))
        foreground[start:end]=np.tanh(mix*1.17).astype(np.float32)
    return foreground

def render_mix(clips,sample_rate=32000,seconds=60,bpm=145,style='mixed',voice_level=1,melody='auto',humor='auto',fx_intensity=2,progress=lambda *args:None):
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
    music=np.zeros((n,2),dtype=np.float32);vox=np.zeros(n,dtype=np.float32)
    def add(x,time,gain=1,pan=0):
        start=int(round(time*sr));count=min(len(x),n-start)
        if start<0 or count<=0:return
        music[start:start+count,0]+=x[:count]*gain*(1-pan*.5)
        music[start:start+count,1]+=x[:count]*gain*(1+pan*.5)
    def sample(duration,fn):return fn(np.arange(int(duration*sr))/sr).astype(np.float32)
    kick=sample(.32,lambda t:.78*np.sin(2*np.pi*(48*t+115*.021*(1-np.exp(-t/.021))))*np.exp(-t*13)+rng.uniform(-1,1,len(t))*.035*np.exp(-t*250))
    hat=sample(.12,lambda t:rng.uniform(-1,1,len(t))*np.exp(-t*65)*.065)
    snare=sample(.22,lambda t:(rng.uniform(-1,1,len(t))*.14*np.exp(-t*24)+.11*np.sin(2*np.pi*185*t)*np.exp(-t*32))*(1-np.exp(-t*400)))
    cache={}
    def note(m,dur,kind):
        key=(m,round(dur,4),kind)
        if key in cache:return cache[key]
        f=440*2**((m-69)/12)
        t=np.arange(max(1,int(sr*dur)),dtype=np.float64)/sr
        if kind=='bass':
            wave=np.sin(2*np.pi*f*t)+.38*np.sin(4*np.pi*f*t)
            out=.26*np.tanh(wave*1.7)*np.exp(-t*19)
        elif kind=='pad':
            wave=.65*np.sin(2*np.pi*f*t)+.3*np.sin(4*np.pi*f*t)+.14*np.sin(6*np.pi*f*t)
            out=.072*wave*np.minimum(1,t/.08)*np.clip((dur-t)/.16,0,1)
        elif kind=='bell':
            wave=np.sin(2*np.pi*f*t)+.42*np.sin(2*np.pi*2.01*f*t)+.28*np.sin(2*np.pi*3.98*f*t)
            out=.18*wave*np.exp(-t*6)
        elif kind=='acid':
            phase=2*np.pi*f*t
            saw=2*(f*t%1)-1
            out=.19*np.tanh((saw+.3*np.sin(phase*2))*3)*np.exp(-t*13)
        elif kind=='pluck':
            wave=np.sin(2*np.pi*f*t)+.5*np.sin(4*np.pi*f*t)+.16*np.sin(6*np.pi*f*t)
            out=.18*wave*np.exp(-t*12)
        elif kind=='organ':
            wave=np.sin(2*np.pi*f*t)+.46*np.sin(4*np.pi*f*t)+.35*np.sin(6*np.pi*f*t)
            out=.115*wave*np.clip((dur-t)/.11,0,1)
        elif kind=='saw':
            wave=np.zeros(len(t),np.float64)
            for h in range(1,8):wave+=np.sin(2*np.pi*f*h*t)/h
            out=.13*np.tanh(wave*1.7)*np.exp(-t*4)
        else: # airy trance lead
            wave=np.sin(2*np.pi*f*t)+.25*np.sin(2*np.pi*2.015*f*t)
            out=.17*wave*np.exp(-t*7)
        out*=np.minimum(1,t/.006)*np.clip((dur-t)/.012,0,1)
        cache[key]=np.asarray(out,dtype=np.float32)
        return cache[key]
    genre_order=('melodic','psy','goa','acid','progressive','eurodance',
                 'uplifting','rave','hard')
    colors=('lead','acid','pluck','bell','organ','saw')
    seed_motif=int(rng.integers(0,len(MOTIFS))) if melody=='auto' else int(melody)-1
    # Four-bar changes are intentionally audible (about every 6-8 s).
    total=math.ceil(seconds/beat)
    progress(10,'מלחין מנגינות שונות לאורך המיקס')
    for b in range(total):
        time=b*beat;p=time/seconds;bar=b//4
        section=bar//4
        current=(seed_motif+section)%len(MOTIFS) if melody=='auto' else seed_motif
        motif=MOTIFS[current]
        roots=ROOTS[current]
        synth=colors[section%len(colors)]
        genre=genre_order[section%len(genre_order)] if style in ('auto','mixed') else style
        drop=.26<=p<.50 or .72<=p<.94
        build=.16<=p<.26 or .62<=p<.72
        groove=.06<=p<.985 and not .50<=p<.58
        if groove:add(kick,time,1.0 if drop else .84)
        if .08<p<.98:
            add(hat,time+beat*.5,1.6 if drop else 1.05,-.35)
            if drop or genre in ('psy','acid','rave'):
                add(hat,time+beat*.75,.60,.4)
        if b%4 in (1,3) and (drop or build):add(snare,time,.60)
        if build:
            for j in range(2 if p<.22 else 4):
                add(snare,time+j*beat/4,.29+j*.10)
        if groove:
            root=roots[(bar//4)%4]
            for k in (1,2,3):
                bass_shift=12 if genre in ('hard','acid') else 0
                add(note(root+bass_shift,beat*.26,'bass'),
                    time+k*beat/4,1.05 if drop else .75)
        # Chord/pad reveals the harmonic change, not just a different drum loop.
        if b%4==0 and .09<p<.93:
            root=roots[(bar//4)%4]+24
            for interval in (0,3,7):
                add(note(root+interval,beat*3.15,'pad'),time,.8,(interval-3)*.05)
        if p<.97 and (drop or .50<=p<.62 or p<.13 or b%2==0):
            local_beat=b%16
            density=3 if genre in ('goa','psy','rave') else 2
            for j in range(density):
                idx=(local_beat*density+j+section*3)%len(motif)
                m=motif[idx]+(12 if genre in ('psy','acid','rave','hard') else 0)
                if genre=='progressive':m-=12
                note_kind='acid' if genre=='acid' else synth
                duration=beat*.72 if j==0 else beat*.34
                gain=(.95 if drop else .70)*(0.80 if j>0 else 1)
                pan=(-.36 if j%2==0 else .36)
                a=note(m,duration,note_kind)
                add(a,time+j*beat/density,gain,pan)
                if drop:add(a,time+j*beat/density+beat*.65,gain*.18,-pan)
        if b%16==0:
            progress(10+int(45*b/max(1,total)),'משלב מקצבים, כלי סינתזה ומלודיות מתחלפות')
    progress(62,'מפעיל אפקטים על הקול שהגיע מ־WhatsApp')
    # The vocal waveform is the ONLY input to the processing chain; music
    # never receives pitch, tape, stutter or distortion effects.
    vocal=np.zeros(n,dtype=np.float32)
    voice_orig=np.zeros(n,dtype=np.float32)
    cursor=beat*4
    for i,v in enumerate(voices):
        transformed=vocal_fx_timeline(v,sr,bpm,humor,fx_intensity,rng)
        start=int(round(cursor*sr))
        end=min(n,start+len(v))
        if end>start:
            vocal[start:end]+=transformed[:end-start]*voice_level
            voice_orig[start:end]+=v[:end-start]*voice_level
        cursor+=len(v)/sr+beat*16
    progress(80,'מבצע מיקס כשהקול המעובד בחזית')
    # The synth is independent. Duck only its volume during speech so the
    # user's *treated* words remain in front, not drowned by the melody.
    from scipy.ndimage import maximum_filter1d
    env=maximum_filter1d(np.abs(vocal),size=max(1,int(sr*.025)))
    env=lfilter([.003],[1,-.997],env).astype(np.float32)
    music*= (1-.78*np.clip(env/.18,0,1))[:,None]
    music+=vocal[:,None]*1.13
    # Audible echo belongs to the VOICE only, not the background melody.
    delay=int(beat*.75*sr)
    music[delay:,0]+=vocal[:-delay]*.085
    music[delay:,1]+=vocal[:-delay]*.13
    np.tanh(music*1.08,out=music)
    fade=np.clip(np.arange(n)/(sr*.04),0,1)*np.clip((n-1-np.arange(n))/(sr*1.2),0,1)
    music*=fade[:,None]
    music*=.97/max(.97,float(np.max(np.abs(music))))
    progress(92,'מכין קובץ להורדה')
    return music

def export_mp3(audio,path,sr=32000):
    subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(sr),'-ac','2','-i','pipe:0','-af','alimiter=limit=0.95:level=false','-codec:a','libmp3lame','-b:a','192k',str(path)],input=audio.astype('<f4').tobytes(),check=True,capture_output=True,timeout=45)
