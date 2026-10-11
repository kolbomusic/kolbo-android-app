"""Experimental native-A/V LTX-2.5 public Gradio adapter.

Noncommercial trial only. The public queue has unknown availability,
anonymous daily quotas and no guaranteed API SLA. Never use an access token,
pay, retry an ambiguous submission, or substitute static photos for video.
Must verify BOTH new motion and decoded audible audio before publishing.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Callable
import hashlib
import json
import os
import shutil
import subprocess
import time

import audio_evidence
import visual_quality

SPACE_ID="ChopperBlu/ltx-2-5-demo"
MAX_REFERENCE_BYTES=5_000_000
MAX_VIDEO_BYTES=80_000_000
MIN_SECONDS=1
MAX_SECONDS=15
SHOT_RESOLUTION=512

class Unavailable(RuntimeError):pass
class Unsupported(ValueError):pass
class UnknownAcceptance(RuntimeError):pass

@dataclass(frozen=True)
class NativeReceipt:
    sha256:str
    duration_seconds:float
    size_bytes:int
    source:str
    audio_evidence:dict
    visual_evidence:dict
    commercial_rights_verified:bool=False
    speech_language_verified:bool=False
    lip_sync_verified:bool=False
    character_identity_verified:bool=False
    user_prompt_semantics_verified:bool=False
    unlimited_free_compute:bool=False
    def as_dict(self):return asdict(self)

def validate(*,prompt:str,seconds:float,references:int,
             consent:bool,commercial:bool)->None:
    if not isinstance(prompt,str) or not 5<=len(prompt.strip())<=3000:
        raise Unsupported("Scene prompt must be 5–3000 characters")
    if type(seconds) not in (int,float) or not MIN_SECONDS<=seconds<=MAX_SECONDS:
        raise Unsupported("This model trial only accepts 1–15 seconds")
    if type(references)!=int or references not in (0,1):
        raise Unsupported("LTX demo accepts optional SINGLE first image")
    if commercial:
        raise Unsupported("Open-weight model and host commercial rights not verified")
    if references==1 and not consent:
        raise Unsupported("External upload of personal image requires explicit informed consent")
    if os.getenv("KOLBO_NATIVE_LTX25_TRIAL")!="EXPLICITLY_ENABLED":
        raise Unavailable("Native AI video+audio trial disabled by server policy")
    if os.getenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA")!="EXPLICITLY_ENABLED":
        raise Unavailable("Transfer to outside shared GPU is disabled")

def probe(file:Path)->tuple[float,bool,bool]:
    try:
        p=subprocess.run(["ffprobe","-v","error",
            "-show_entries","format=duration:stream=codec_type",
            "-of","json",str(file)],check=True,capture_output=True,timeout=30)
        spec=json.loads(p.stdout)
        streams=[x.get("codec_type") for x in spec.get("streams",[])]
        return float(spec["format"]["duration"]),"video" in streams,"audio" in streams
    except (OSError,subprocess.SubprocessError,KeyError,ValueError) as exc:
        raise Unavailable("Model returned unparseable video") from exc

def generate(*,prompt:str,seconds:float,destination:Path,
             reference:Path|None=None,consent:bool=False,commercial:bool=False,
             client_factory:Callable|None=None,handle_file_fn:Callable|None=None,
             deadline_seconds:int=480)->NativeReceipt:
    validate(prompt=prompt,seconds=seconds,references=int(reference is not None),
             consent=consent,commercial=commercial)
    if reference is not None:
        photo=Path(reference)
        if (photo.is_symlink() or not photo.is_file()
                or not 100<=photo.stat().st_size<=MAX_REFERENCE_BYTES
                or photo.suffix.lower() not in (".png",".jpg",".jpeg",".webp")):
            raise Unsupported("Reference image invalid")
    else:
        photo=None
    out=Path(destination)
    if out.exists():
        raise Unsupported("No overwriting existing video")
    if client_factory is None or handle_file_fn is None:
        from gradio_client import Client, handle_file
        client_factory=client_factory or Client
        handle_file_fn=handle_file_fn or handle_file
    # One public ZeroGPU request. No automatic API-level retry.
    try:
        client=client_factory(SPACE_ID,verbose=False)
        uploaded=handle_file_fn(str(photo)) if photo is not None else None
        job=client.submit(prompt,uploaded,SHOT_RESOLUTION,SHOT_RESOLUTION,
                float(seconds),False,42,False,"conv",api_name="/generate_video")
    except Exception as exc:
        raise UnknownAcceptance("Network failure after attempt to contact public GPU") from exc
    limit=time.monotonic()+deadline_seconds
    while not job.done() and time.monotonic()<limit:
        time.sleep(5)
    if not job.done():
        job.cancel()
        raise UnknownAcceptance("GPU job timed out; retry may use additional quota")
    try:
        output=job.result()
        path=output[0] if isinstance(output,(tuple,list)) and output else None
        if isinstance(path,dict):
            path=path.get("path") or path.get("name")
        candidate=Path(path) if isinstance(path,str) else None
        if (candidate is None or not candidate.is_file() or candidate.is_symlink()
                or candidate.suffix.lower()!=".mp4"
                or not 3000<=candidate.stat().st_size<=MAX_VIDEO_BYTES):
            raise Unavailable("No valid MP4 returned")
        duration,has_video,has_audio=probe(candidate)
        # The LTX frame grid rounds time to an 8k+1 frames multiple.
        # No silent padding or changing the requested length to a shorter clip.
        if not has_video or not has_audio or abs(duration-seconds)>.35:
            raise Unavailable("Requested length or required AV tracks missing")
        audio=audio_evidence.inspect_mp4(candidate,audio_required=True)
        if not audio.has_audio_stream or not audio.decoded_audio or audio.verdict=="reject":
            raise Unavailable("Native generated audio is absent or inaudible")
        motion=visual_quality.inspect_mp4(candidate,audio_required=True)
        if motion.pixel_change_fraction<0.012:
            raise Unavailable("Generated model video has nearly identical frames")
        out.parent.mkdir(parents=True,exist_ok=True)
        # Do not publish before every media validation passes.
        with candidate.open("rb") as inp,out.open("xb") as target:
            shutil.copyfileobj(inp,target,1024*1024)
        with out.open("rb") as content:
            digest=hashlib.file_digest(content,"sha256").hexdigest()
        return NativeReceipt(digest,round(duration,4),out.stat().st_size,
                             SPACE_ID,audio.as_dict(),motion.as_dict())
    except (Unavailable,Unsupported):
        raise
    except Exception as exc:
        raise Unavailable("Public model returned an invalid/unavailable result") from exc
