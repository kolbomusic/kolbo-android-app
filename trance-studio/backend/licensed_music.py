"""Mix a legitimately supplied music file with the original voice/FX stem.

Never downloads or records a YouTube stream. The user must supply a local
licensed audio file. Apply voice-led ducking, RMS normalization and a soft
true-ish peak limiter, without confusing a preview with granted rights.
"""
from pathlib import Path
import subprocess
import numpy as np
from scipy.ndimage import maximum_filter1d
from scipy.signal import lfilter

SUPPORTED={".mp3",".wav",".ogg",".m4a"}

class BackingTrackError(ValueError):pass

def mix_licensed_backing(path,vocal,sr=32000):
    src=Path(path)
    if src.suffix.lower() not in SUPPORTED or not src.is_file():
        raise BackingTrackError("סוג קובץ המוזיקה אינו נתמך")
    mono=np.asarray(vocal,dtype=np.float32)
    if mono.ndim!=1 or not len(mono) or not np.isfinite(mono).all():
        raise BackingTrackError("קול ההקלטה אינו תקין")
    duration=len(mono)/sr
    if duration>360.:
        raise BackingTrackError("המיקס ארוך מדי")
    try:
        proc=subprocess.run([
            'ffmpeg','-nostdin','-v','error','-stream_loop','-1',
            '-i',str(src),'-t',str(duration),
            '-vn','-ac','2','-ar',str(sr),
            '-f','f32le','-acodec','pcm_f32le','pipe:1'],
            check=True,capture_output=True,timeout=120)
    except (OSError,subprocess.SubprocessError) as exc:
        raise BackingTrackError("לא ניתן לפענח את קובץ המוזיקה המורשה") from exc
    raw=np.frombuffer(proc.stdout,dtype='<f4')
    if len(raw)<sr//2*2 or len(raw)%2:
        raise BackingTrackError("קובץ המוזיקה ריק או קצר מדי")
    bed=raw.reshape(-1,2).astype(np.float32,copy=True)
    if len(bed)<len(mono):
        bed=np.pad(bed,((0,len(mono)-len(bed)),(0,0)))
    bed=bed[:len(mono)]
    power=float(np.sqrt(np.mean(bed*bed)))
    if power<.00001:
        raise BackingTrackError("לא נשמעת מוזיקה בקובץ המורשה")
    bed*=min(3.,.16/max(.001,power))
    # Accurate envelope based on the already arranged original voice and
    # actual comic FX inserts (no crude 1 second music mute per speech beat).
    env=maximum_filter1d(np.abs(mono),size=max(1,int(.03*sr)))
    env=lfilter([.003],[1.,-.997],env).astype(np.float32)
    gain=1.-.73*np.clip(env/.17,0,1)
    bed*=gain[:,None]
    mixed=bed+mono[:,None]*1.15
    fade=np.clip(np.arange(len(mono),dtype=np.float32)/(sr*.03),0,1)
    fade*=np.clip((len(mono)-1-np.arange(len(mono),dtype=np.float32))/(sr*.5),0,1)
    mixed*=fade[:,None]
    np.nan_to_num(mixed,copy=False)
    mixed=np.tanh(mixed*1.05)*.93
    return mixed.astype(np.float32)
