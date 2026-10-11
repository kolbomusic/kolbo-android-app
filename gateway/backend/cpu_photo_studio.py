"""Truly local/CPU-only photo-motion video, no AI vendor and no ad network.

Honest output category: animated PHOTO COMPOSITE (Ken Burns), not generated
acting, singing, identity-preserving AI motion or text-to-video. Render CPU
time/egress is finite even when no payment is made.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import hashlib
import json
import os
import subprocess
import tempfile
import wave
import procedural_sfx

class FreeStudioError(ValueError):
    pass

WIDTH, HEIGHT, FPS = 640, 360, 24
MAX_SECONDS = 12
MAX_IMAGES = 2
MAX_PIXELS = 15_000_000

@dataclass(frozen=True)
class StudioReceipt:
    mode: str
    bytes: int
    sha256: str
    requested_seconds: int
    actual_seconds: float
    photos: int
    audio_from_user: bool
    has_audio_track: bool = False
    generated_sfx: str = "none"
    ai_video_generated: bool = False
    performed_actions_verified: bool = False
    identity_motion_verified: bool = False
    provider_spend_usd: int = 0

    def as_dict(self):
        return asdict(self)


def _check_wav(path: Path, seconds: int) -> None:
    # No download of remote tracks. User must own or be authorized to use the audio.
    if path.suffix.lower() != ".wav" or not path.is_file():
        raise FreeStudioError("Only user-supplied WAV audio is supported")
    if path.stat().st_size > 7_000_000:
        raise FreeStudioError("Audio too large")
    try:
        with wave.open(str(path),"rb") as stream:
            channels=stream.getnchannels()
            depth=stream.getsampwidth()
            rate=stream.getframerate()
            duration=stream.getnframes() / rate if rate else 0
            if stream.getcomptype()!="NONE" or channels not in (1,2) \
                or depth not in (1,2) or not 8000 <= rate <= 48000:
                raise FreeStudioError("WAV must be 8/16-bit PCM mono/stereo")
            if duration < seconds-0.06 or duration > 40:
                raise FreeStudioError("User soundtrack duration must cover all requested seconds")
    except (OSError,EOFError,ZeroDivisionError,wave.Error) as exc:
        raise FreeStudioError("Invalid WAV audio") from exc


def _poster(paths:list[Path], save_to:Path) -> None:
    if not 1 <= len(paths) <= MAX_IMAGES:
        raise FreeStudioError("Only one or two personal photos are supported")
    canvas=Image.new("RGB",(1280,720),(22,26,36))
    paint=ImageDraw.Draw(canvas)
    for x in range(0,1280,8):
        tint=int(29 + 13*x/1280)
        paint.rectangle((x,0,x+8,719),fill=(22,tint,39))
    gutter=20
    cell_width=(1280-(len(paths)+1)*gutter)//len(paths)
    for index,source in enumerate(paths):
        with Image.open(source) as original:
            if original.width*original.height > MAX_PIXELS:
                raise FreeStudioError("Photo resolution exceeds CPU limit")
            rotated=ImageOps.exif_transpose(original)
            image=ImageOps.contain(rotated.convert("RGB"),
                (cell_width,720-2*gutter),Image.Resampling.LANCZOS)
            col=gutter+index*(cell_width+gutter)
            pos=(col+(cell_width-image.width)//2,
                 (720-image.height)//2)
            canvas.paste(image,pos)
    canvas.save(save_to,format="PNG")


def _probe(path:Path)->tuple[float,bool,bool]:
    try:
        output=subprocess.run(
            ["ffprobe","-v","error","-show_entries",
             "format=duration:stream=codec_type","-of","json",str(path)],
            capture_output=True,text=True,check=True,timeout=20)
        obj=json.loads(output.stdout)
        streams=obj.get("streams",[])
        return (float(obj["format"]["duration"]),
                any(s.get("codec_type")=="video" for s in streams),
                any(s.get("codec_type")=="audio" for s in streams))
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        raise FreeStudioError("Output video failed verification") from exc


def render(*,photos:list[Path],seconds:int,out:Path,
           user_wav:Path|None=None,generated_sfx:str="none",
           timeout_seconds:int=150) ->StudioReceipt:
    if type(seconds) is not int or not 2<=seconds<=MAX_SECONDS:
        raise FreeStudioError("Photo-motion supports 2–12 full seconds")
    if not 1<=len(photos)<=2:
        raise FreeStudioError("One or two photos required")
    if out.exists():
        raise FreeStudioError("Refusing to overwrite existing video")
    if generated_sfx not in procedural_sfx.SFX_KIND:
        raise FreeStudioError("Unknown or unsupported sound effect")
    if user_wav is not None and generated_sfx!="none":
        raise FreeStudioError("Cannot replace user sound with synthesized sound")
    if user_wav is not None:
        _check_wav(Path(user_wav), seconds)
    with tempfile.TemporaryDirectory(prefix="kolbo-cpu-studio-") as directory:
        poster=Path(directory)/"poster.png"
        _poster([Path(p) for p in photos],poster)
        out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        working=Path(directory)/"output.mp4"
        # Composite moves AS A CAMERA, not as separately animated characters.
        n=seconds*FPS
        command=["ffmpeg","-nostdin","-v","error","-y",
                 "-loop","1","-framerate",str(FPS),"-i",str(poster)]
        sound=Path(user_wav) if user_wav is not None else None
        if generated_sfx!="none":
            sound=Path(directory)/"original_synthetic_sound.wav"
            procedural_sfx.synthesize(sound,seconds=seconds,kind=generated_sfx)
        if sound is not None:
            command.extend(["-i",str(sound)])
        command.extend([
            "-filter_complex",
            "[0:v]zoompan=z='min(zoom+0.00055,1.08)':d=1:s=640x360:fps=24,"
            "format=yuv420p[v]",
            "-map","[v]","-frames:v",str(n),
            "-c:v","libx264","-preset","ultrafast","-crf","26",
            "-pix_fmt","yuv420p"])
        if sound is None:
            command.extend(["-an"])
        else:
            command.extend(["-map","1:a:0","-c:a","aac","-b:a","128k","-t",str(seconds)])
        command.extend(["-movflags","+faststart",str(working)])
        try:
            subprocess.run(command,capture_output=True,check=True,
                           timeout=timeout_seconds)
        except (OSError,subprocess.SubprocessError) as exc:
            raise FreeStudioError("CPU render failed or exceeded quota") from exc
        duration, video, audio = _probe(working)
        if not video or abs(duration-seconds)>0.15 or audio != (sound is not None):
            raise FreeStudioError("Output failed measured video/audio contract")
        if not 3000<=working.stat().st_size<=30_000_000:
            raise FreeStudioError("Video size outside safety limits")
        # No partial/failed publication, no overwrite.
        with working.open("rb") as input_file, out.open("xb") as output_file:
            while block:=input_file.read(1_048_576):
                output_file.write(block)
        with out.open("rb") as stream:
            digest=hashlib.file_digest(stream,"sha256").hexdigest()
        return StudioReceipt("cpu_photo_motion",out.stat().st_size,digest,
            seconds,duration,len(photos),user_wav is not None,
            audio,generated_sfx)
