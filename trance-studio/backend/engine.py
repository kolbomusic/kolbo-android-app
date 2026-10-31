"""Original deterministic trance composition with original-audio sampling."""
import math
import subprocess
import numpy as np
from scipy.signal import butter, sosfilt, lfilter

def load_audio(path, sample_rate=32000):
    command=['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),'-t','60.01','-ac','1','-ar',str(sample_rate),'-f','f32le','-']
    result=subprocess.run(command,check=True,capture_output=True,timeout=25)
    x=np.frombuffer(result.stdout,dtype='<f4').copy()
    if len(x)>sample_rate*60:raise ValueError('הקלטה ארוכה מ־60 שניות')
    return x

def prepare_voice(x,sr):
    x=np.asarray(x,dtype=np.float32)
    if not len(x) or len(x)>sr*60 or not np.isfinite(x).all():raise ValueError('הקלטה ריקה או לא תקינה')
    peak=float(np.max(np.abs(x)))
    if peak<.001:raise ValueError('לא נמצא קול בהקלטה')
    frame=max(1,int(sr*.01));rms=np.array([np.sqrt(np.mean(x[i:i+frame]**2)) for i in range(0,len(x),frame)])
    active=np.flatnonzero(rms>max(.003,peak*.035))
    if not len(active):raise ValueError('לא נמצא קול בהקלטה')
    start=max(0,int(active[0]*frame-.06*sr));end=min(len(x),int((active[-1]+1)*frame+.16*sr),start+8*sr)
    x=x[start:end].copy()
    x=sosfilt(butter(2,[90,min(7000,sr*.43)],btype='bandpass',fs=sr,output='sos'),x).astype(np.float32)
    gain=min(4,.20/max(.001,float(np.sqrt(np.mean(x*x)))))
    x=np.tanh(x*gain*1.1)
    t=np.arange(len(x))/sr
    x*=np.minimum(1,t/.008)*np.minimum(1,(len(x)/sr-t)/.015)
    return x.astype(np.float32)

def render_mix(clips,sample_rate=32000,seconds=60,bpm=145,style='melodic',voice_level=1,progress=lambda *args:None):
    if not 130<=bpm<=150 or seconds not in (30,60,90) or style not in ('melodic','psy') or not .5<=voice_level<=1.5 or not 8000<=sample_rate<=48000:raise ValueError('הגדרות המיקס אינן תקינות')
    if not 1<=len(clips)<=4:raise ValueError('יש לבחור בין הקלטה אחת לארבע הקלטות')
    sr=sample_rate;n=int(seconds*sr);beat=60/bpm;rng=np.random.default_rng(712825)
    voices=[prepare_voice(c,sr) for c in clips]
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
    motif=[74,77,81,77,72,77,79,77,70,74,77,74,69,73,76,73];roots=[38,34,41,33]
    total=math.ceil(seconds/beat)
    progress(10,'בונה קצב טראנס')
    for b in range(total):
        time=b*beat;p=time/seconds;bar=b//4;drop=.26<=p<.50 or .72<=p<.94;build=.16<=p<.26 or .62<=p<.72;groove=.08<=p<.98 and not .50<=p<.62
        if groove:add(kick,time,1 if drop else .82 if build else .72)
        if .08<p<.98:
            add(hat,time+beat*.5,1.6 if drop else .9,-.35)
            if drop:add(hat,time+beat*.75,.7,.4)
        if b%4 in (1,3) and (drop or build):add(snare,time,.65)
        if build:
            density=2 if p<.23 or .62<p<.69 else 4
            for j in range(density):add(snare,time+j*beat/density,.3+(p%.1)*2)
        if groove:
            for s in (1,2,3):add(note(roots[(bar//4)%4],beat*.24,'bass'),time+s*beat/4,1 if drop else .75)
        if drop or .50<=p<.62 or p<.08:
            for s in range(2):
                m=motif[(b*2+s)%16] if style=='melodic' else motif[(b*3+s)%16]+12;g=.9 if drop else .45;pan=(-1 if s==0 else 1)*.35;a=note(m,beat*.82,'lead')
                add(a,time+s*beat/2,g,pan);add(a,time+s*beat/2+beat*.75,g*.25,-pan)
        if b%16==0:progress(10+int(45*b/total),'בונה בס ומלודיה')
    progress(62,'משלב את הקולות המקוריים')
    positions={1:[.025],2:[.025,.515],3:[.025,.36,.515],4:[.025,.19,.515,.73]}[len(voices)]
    def add_voice(x,time,gain=1):
        start=int(round(time*sr));count=min(len(x),n-start)
        if count>0:vox[start:start+count]+=x[:count]*gain*voice_level
    for k,v in enumerate(voices):
        add_voice(v,positions[k]*seconds)
        length=min(len(v),int(beat*.9*sr));starts=range(0,max(1,len(v)-length+1),max(1,int(sr*.08)));best=max(starts,key=lambda j:float(np.sum(v[j:j+length:8]**2)))
        hook=v[best:best+length];grain=hook[:int(beat*.24*sr)]
        for pos in (.26,.43,.72,.87):
            start=round(pos*seconds/beat)*beat+k*beat*2;add_voice(hook,start,.8);add_voice(hook,start+beat*2,.55)
        for pos in (.247,.707):
            for j in range(4):add_voice(grain,math.floor(pos*seconds/beat)*beat+j*beat/4+k*beat,.6+j*.08)
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
