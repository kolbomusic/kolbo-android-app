"""Lightweight, honest, voice-driven MP4 fallback.

The voice recording generates every waveform pixel; background trance audio
is only the soundtrack. No unrelated people, captions, fabricated events or
external GPU service. A fallback is clearly marked as such in the API.
"""
from pathlib import Path
import subprocess

def export_voice_visualizer(voice_mp3, mix_mp3, output_mp4):
    voice=Path(voice_mp3); mix=Path(mix_mp3); output=Path(output_mp4)
    if not voice.is_file() or not mix.is_file():
        raise ValueError('Missing source voice or mixed soundtrack')
    output.parent.mkdir(parents=True,exist_ok=True)
    cmd=[
        "ffmpeg","-nostdin","-hide_banner","-v","error","-y",
        "-i",str(voice),"-i",str(mix),
        "-filter_complex",
        "[0:a]showwaves=s=360x640:mode=cline:rate=12:colors=0xD18AFF,"
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
