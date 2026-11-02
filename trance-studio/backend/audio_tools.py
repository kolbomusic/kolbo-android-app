"""Professional basic audio tools backed by FFmpeg, with real effect processing.

Do not confuse this with generative music, source separation or voice cloning.
Untrusted inputs are local sanitized uploaded media files, never shell commands.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path


class AudioToolError(ValueError):
    pass


SUPPORTED={".mp3",".wav",".ogg",".opus",".m4a",".aac",".flac",".mp4",
           ".webm",".mov",".3gp",".3gpp"}


def probe_audio(path):
    path=Path(path)
    if path.suffix.lower() not in SUPPORTED:
        raise AudioToolError("סוג קובץ השמע אינו נתמך.")
    try:
        r=subprocess.run([
            "ffprobe","-v","error","-show_entries",
            "format=duration:stream=codec_type","-of","json",str(path)],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,
            check=True)
        data=json.loads(r.stdout)
        duration=float(data.get("format",{}).get("duration",0))
        streams=data.get("streams",[])
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired,
            ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        raise AudioToolError("לא ניתן לקרוא קובץ שמע תקין.") from exc
    if not any(x.get("codec_type")=="audio" for x in streams):
        raise AudioToolError("לא נמצא ערוץ שמע בקובץ.")
    if not math.isfinite(duration) or not 0.15<duration<=120.5:
        raise AudioToolError("עיבוד אולפן מוגבל להקלטות באורך עד 120 שניות.")
    return duration


def render_audio_tool(source,output,*,mode="master",voice=None,
                      sound="balanced",voice_gain=100,backing_gain=80):
    """Export a playable stereo MP3 from mastering or source+voice mixing.

    An uploaded voice is a performance, not a target timbre. This function
    does NOT clone any singer or transform a singer to sing different lyrics.
    """
    if mode not in ("master","mix"):
        raise AudioToolError("מצב עיבוד האולפן אינו נתמך.")
    if sound not in ("balanced","warm","punchy","clean"):
        raise AudioToolError("סגנון המאסטרינג אינו נתמך.")
    if not 25<=voice_gain<=180 or not 15<=backing_gain<=150:
        raise AudioToolError("העוצמות חייבות להיות בטווח התקין.")
    probe_audio(source)
    if mode=="mix":
        if voice is None:
            raise AudioToolError("לצורך מיקס יש להוסיף קובץ שירה שני.")
        probe_audio(voice)
    # Compressor settings tailored for clean listening rather than an
    # obviously fake 'AI generated' output.
    eq={
      "balanced":"highpass=f=32,acompressor=threshold=-18dB:ratio=2.3:attack=16:release=160",
      "warm":"highpass=f=35,equalizer=f=180:t=q:w=1.0:g=1.5,acompressor=threshold=-19dB:ratio=2.3:attack=18:release=170",
      "punchy":"highpass=f=36,equalizer=f=3500:t=q:w=1.1:g=1.0,acompressor=threshold=-21dB:ratio=3.0:attack=7:release=100",
      "clean":"highpass=f=25,acompressor=threshold=-16dB:ratio=1.5:attack=24:release=180"
    }[sound]
    master="loudnorm=I=-14:TP=-1.3:LRA=10,alimiter=limit=0.92"
    command=["ffmpeg","-hide_banner","-loglevel","error","-nostdin",
             "-y","-i",str(source)]
    if mode=="master":
        command+=["-vn","-map","0:a:0","-af",eq+","+master]
    else:
        command+=["-i",str(voice)]
        filters=(
          "[0:a:0]aresample=44100,highpass=f=35,"
          "volume="+str(backing_gain/100)+ "[base];"
          "[1:a:0]aresample=44100,highpass=f=70,"
          "volume="+str(voice_gain/100)+"[vox];"
          "[base][vox]amix=inputs=2:duration=longest:dropout_transition=1.5,"
          +eq+","+master+"[final]"
        )
        command+=["-filter_complex",filters,"-map","[final]","-vn"]
    command+=["-ac","2","-ar","44100","-c:a","libmp3lame","-b:a",
              "192k","-t","121",str(output)]
    try:
        subprocess.run(command,stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE,timeout=75,check=True)
    except subprocess.TimeoutExpired as exc:
        raise AudioToolError(
            "עיבוד השמע לא הסתיים במגבלת הזמן של השרת החינמי.") from exc
    except (OSError,subprocess.CalledProcessError) as exc:
        raise AudioToolError("מנוע המיקס והמאסטרינג לא הצליח לעבד את הקבצים.") from exc
    result=Path(output)
    if not result.is_file() or result.stat().st_size<2048:
        raise AudioToolError("לא הופק קובץ MP3 תקין.")
    probe_audio(result)
    return result
