"""Original deterministic trance composition with original-audio sampling."""
import math
import hashlib
import subprocess
import numpy as np
from scipy.signal import butter, sosfilt, lfilter

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
HUMOR = ('auto', 'classic', 'cartoon', 'scratch', 'robot', 'chaos', 'off')
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

def render_mix(clips,sample_rate=32000,seconds=60,bpm=145,style='mixed',voice_level=1,melody='auto',humor='auto',progress=lambda *args:None):
    if not 120<=bpm<=165 or seconds not in (0,30,60,90,120,180) or style not in STYLES or humor not in HUMOR or not (melody=='auto' or str(melody) in ('1','2','3','4','5','6')) or not .5<=voice_level<=1.5 or not 8000<=sample_rate<=48000:raise ValueError('הגדרות המיקס אינן תקינות')
    if not 1<=len(clips)<=4:raise ValueError('יש לבחור בין הקלטה אחת לארבע הקלטות')
    sr=sample_rate;beat=60/bpm
    voices=[prepare_voice(c,sr) for c in clips]
    total_speech=sum(len(v)/sr for v in voices)
    needed=beat*9+total_speech+max(0,len(voices)-1)*beat*4
    seconds=max(float(seconds),math.ceil(needed))
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
        key=(m,dur,kind)
        if key in cache:return cache[key]
        f=440*2**((m-69)/12);t=np.arange(int(sr*dur))/sr;v=np.zeros(len(t))
        for h in range(1,7 if kind=='bass' else 8):v+=np.sin(2*np.pi*(f*h+(0 if kind=='bass' else .7*(-1)**h))*t)*np.exp(-h*(.34 if kind=='bass' else .23))/h
        if kind=='bass':v=np.tanh(v*1.5)*.28*np.exp(-t*22)*np.minimum(1,t/.004)
        else:v*=.11*np.exp(-t*8)*np.minimum(1,t/.012)*np.clip((dur-t)/.03,0,1)
        cache[key]=v.astype(np.float32);return cache[key]
    genre_order=('melodic','psy','goa','acid','progressive','eurodance','uplifting','rave')
    melody_index=int(rng.integers(0,len(MOTIFS))) if melody=='auto' else int(melody)-1
    motif=MOTIFS[melody_index];roots=ROOTS[melody_index]
    total=math.ceil(seconds/beat)
    progress(10,'בונה קצב טראנס')
    for b in range(total):
        time=b*beat;p=time/seconds;bar=b//4
        genre=genre_order[(bar//8)%len(genre_order)] if style in ('auto','mixed') else style
        if melody=='auto' and bar%8==0:
            melody_index=(melody_index+1)%len(MOTIFS)
            motif=MOTIFS[melody_index];roots=ROOTS[melody_index]
        drop=.26<=p<.50 or .72<=p<.94;build=.16<=p<.26 or .62<=p<.72;groove=.08<=p<.98 and not .50<=p<.62
        if groove:add(kick,time,1 if drop else .82 if build else .72)
        if .08<p<.98:
            add(hat,time+beat*.5,1.6 if drop else .9,-.35)
            if drop:add(hat,time+beat*.75,.7,.4)
        if b%4 in (1,3) and (drop or build):add(snare,time,.65)
        if build:
            density=2 if p<.23 or .62<p<.69 else 4
            for j in range(density):add(snare,time+j*beat/density,.3+(p%.1)*2)
        if groove:
            for s in (1,2,3):
                note_shift=12 if genre in ('acid','hard') else -2 if genre=='goa' else 0
                add(note(roots[(bar//4)%4]+note_shift,beat*.24,'bass'),time+s*beat/4,1 if drop else .75)
        if drop or .50<=p<.62 or p<.08:
            for s in range(2):
                m=motif[(b*(3 if genre in ('psy','goa','acid') else 2)+s)%16]
                if genre in ('psy','acid','rave','hard'):m+=12
                if genre=='progressive':m-=12
                g=(.90 if drop else .45) * (.8 if genre in ('hard','acid') else 1)
                pan=(-1 if s==0 else 1)*.35;a=note(m,beat*.82,'lead')
                add(a,time+s*beat/2,g,pan);add(a,time+s*beat/2+beat*.75,g*.25,-pan)
        if b%16==0:progress(10+int(45*b/total),'בונה בס ומלודיה')
    progress(62,'משלב את הקולות המקוריים')
    # Every original recording is included ONCE in order, in full, then creative
    # copies are used only for the jokes. No 8-second truncation or word dropping.
    def add_voice(x,time,gain=1):
        start=int(round(time*sr));count=min(len(x),n-start)
        if start<0 or count<=0:return
        vox[start:start+count]+=x[:count]*gain*voice_level
    main_positions=[];cursor=beat*4
    for v in voices:
        main_positions.append(cursor)
        add_voice(v,cursor,1)
        cursor+=len(v)/sr+beat*4
    progress(70,'מזהה הפסקות טבעיות ובונה רגעים מצחיקים')
    for index,v in enumerate(voices):
        intervals=speech_boundaries(v,sr)
        # Choose phrase endings near real pauses, not arbitrary mid-word windows.
        candidates=[(a,b) for a,b in intervals if (b-a)>=int(sr*.35)]
        if not candidates:candidates=[(0,len(v))]
        selected=[candidates[j] for j in sorted(set([0,len(candidates)//2,len(candidates)-1]))]
        for j,(a,b) in enumerate(selected):
            hook=v[max(a,b-int(sr*.88)):b].copy()
            if len(hook)<sr*.12:continue
            mode=humor
            if mode=='auto':mode=('classic','cartoon','scratch','robot')[(index+j)%4]
            effect=comic_variant(hook,mode,sr,rng)
            # A comic answer follows the *end* of the complete phrase.
            after=main_positions[index]+b/sr+max(.12,beat*.22)
            # Prefer actual pauses; if speech resumes immediately, save for
            # a break after the full recording rather than masking words.
            next_a=candidates[candidates.index((a,b))+1][0] if (a,b) in candidates and candidates.index((a,b))+1<len(candidates) else len(v)
            if next_a-b < len(effect)+int(sr*.15):
                after=main_positions[index]+len(v)/sr+beat*(1+j*1.2)
            if humor!='off':
                add_voice(effect,after,.32 if humor!='chaos' else .47)
                if j==0:
                    stutter=effect[:max(1,min(len(effect),int(sr*beat*.25)))]
                    add_voice(stutter,after+len(effect)/sr+beat*.22,.24)
    # Main narration has precedence; chorus jokes never erase or overwrite it.
    # Fast peak-envelope ducking, center voice and a stereo dotted-eighth echo.
    from scipy.ndimage import maximum_filter1d
    env=maximum_filter1d(np.abs(vox),size=max(1,int(sr*.025)))
    env=lfilter([.003],[1,-.997],env).astype(np.float32)
    music*= (1-.66*np.clip(env/.19,0,1))[:,None]
    music+=vox[:,None]*.87
    delay=int(beat*.75*sr)
    music[delay:,0]+=vox[:-delay]*.104;music[delay:,1]+=vox[:-delay]*.16
    np.tanh(music*1.08,out=music)
    fade=np.clip(np.arange(n)/(sr*.04),0,1)*np.clip((n-1-np.arange(n))/(sr*1.2),0,1)
    music*=fade[:,None]
    music*=.97/max(.97,float(np.max(np.abs(music))))
    progress(92,'מכין קובץ להורדה')
    return music

def export_mp3(audio,path,sr=32000):
    subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(sr),'-ac','2','-i','pipe:0','-af','alimiter=limit=0.95:level=false','-codec:a','libmp3lame','-b:a','192k',str(path)],input=audio.astype('<f4').tobytes(),check=True,capture_output=True,timeout=45)
