"""Lightweight, honest, voice-driven MP4 fallback.

The voice recording generates every waveform pixel; background trance audio
is only the soundtrack. No unrelated people, captions, fabricated events or
external GPU service. A fallback is clearly marked as such in the API.
"""
from pathlib import Path
import subprocess
import wave
import numpy as np

def write_original_source_wav(clips, path, sr=32000):
    """Write decoded ORIGINAL uploads, not pitch-shifted/remixed vocal.

    The source waves are normalized to PCM format, but their full, untouched
    sample values and original order are retained (subject only to PCM16
    quantization). Audio is never synthesized here.
    """
    if not clips:raise ValueError('No uploaded audio')
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        for clip in clips:
            data=np.asarray(clip,dtype=np.float32)
            if data.ndim!=1 or not len(data) or not np.isfinite(data).all():
                raise ValueError('Invalid original upload')
            pcm=(np.clip(data,-1.,1.)*32767).astype('<i2')
            wav.writeframes(pcm.tobytes())
    return path

def export_voice_visualizer(original_wav, mix_mp3, output_mp4):
    voice=Path(original_wav); mix=Path(mix_mp3); output=Path(output_mp4)
    if not voice.is_file() or not mix.is_file():
        raise ValueError('Missing source voice or mixed soundtrack')
    output.parent.mkdir(parents=True,exist_ok=True)
    cmd=[
        "ffmpeg","-nostdin","-hide_banner","-v","error","-y",
        "-i",str(voice),"-i",str(mix),
        "-filter_complex",
        "[0:a]apad,showwaves=s=360x640:mode=cline:rate=12:colors=0xD18AFF,"
        "format=yuv420p[v]",
        "-map","[v]","-map","1:a:0",
        "-c:v","libx264","-preset","ultrafast","-crf","29",
        "-g","24","-c:a","aac","-b:a","144k","-shortest",
        "-movflags","+faststart",str(output)
    ]
    subprocess.run(cmd,capture_output=True,check=True,timeout=70)
    if not output.exists() or output.stat().st_size<16000:
        raise RuntimeError('Empty voice-reactive MP4')
    return output
