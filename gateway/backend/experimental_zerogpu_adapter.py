"""Experimental single-image ZeroGPU worker for Kolbo Video.

One public Gradio job per *explicit* invocation. No automatic retries, billing,
anonymous quota bypass, multi-person identity claims, or automatic publication.
This is not the live Android production dispatcher. External media can be sent
only with explicit consent and the worker's privacy gate enabled.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Callable

SPACE_ID = "zerogpu-aoti/wan2-2-fp8da-aoti-faster"
API_NAME = "/generate_video"
MAX_MP4_BYTES = 300 * 1024 * 1024
MAX_SOURCE_BYTES = 10 * 1024 * 1024

class ProviderUnavailable(RuntimeError): pass
class UnsupportedRequest(ValueError): pass
class UnknownAcceptance(RuntimeError): pass

@dataclass(frozen=True)
class Proof:
    sha256: str
    duration: float
    audio: bool
    bytes: int
    origin: str
    status: str = "requires_manual_semantic_review"

    def public_record(self):
        return {"sha256":self.sha256, "duration_seconds":self.duration,
                "has_audio":self.audio, "bytes":self.bytes,
                "provider":self.origin, "status":self.status,
                "two_subject_identity_verified":False,
                "lip_sync_verified":False, "commercial_rights_verified":False}


def validate(*, references: int, seconds: float, wants_audio: bool,
             wants_lipsync: bool, commercial: bool, consent: bool) -> None:
    if type(references) is not int or references != 1:
        raise UnsupportedRequest("ZeroGPU experimental engine accepts ONE reference only")
    if type(seconds) not in (int,float) or not (1 <= seconds <= 5):
        raise UnsupportedRequest("Provider cannot generate this requested duration")
    if wants_audio or wants_lipsync:
        raise UnsupportedRequest("This engine does not provide synchronized speech or audio")
    if commercial:
        raise UnsupportedRequest("Commercial usage of this public hosted Space not verified")
    if not consent:
        raise UnsupportedRequest("Explicit consent to transfer reference to external provider required")
    if os.getenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA") != "EXPLICITLY_ENABLED":
        raise ProviderUnavailable("Third-party media transfer is disabled by server policy")


def probe(file: Path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type", "-of", "json", str(file)],
        check=True, capture_output=True, timeout=30)
    obj = json.loads(p.stdout)
    tracks = obj.get("streams", [])
    return (float(obj["format"]["duration"]),
            any(x.get("codec_type")=="video" for x in tracks),
            any(x.get("codec_type")=="audio" for x in tracks))


def submit_one(*, reference: Path, prompt: str, seconds: float,
               destination: Path, consent: bool,
               commercial: bool = False, wants_audio: bool = False,
               wants_lipsync: bool = False, deadline_seconds: int = 260,
               client_factory: Callable|None = None,
               handle_file_fn: Callable|None = None) -> Proof:
    validate(references=1, seconds=seconds, wants_audio=wants_audio,
             wants_lipsync=wants_lipsync, commercial=commercial, consent=consent)
    if not isinstance(prompt,str) or not 5<=len(prompt.strip())<=3000:
        raise UnsupportedRequest("Invalid video scene prompt")
    src=Path(reference)
    if not src.is_file() or not 0<src.stat().st_size<=MAX_SOURCE_BYTES:
        raise UnsupportedRequest("Reference image missing or exceeds size limit")
    if not src.name.lower().endswith((".jpg",".jpeg",".png",".webp")):
        raise UnsupportedRequest("Only supported reference image formats may be sent")
    dst=Path(destination)
    if dst.exists():
        raise UnsupportedRequest("Cannot replace an existing output")
    if client_factory is None or handle_file_fn is None:
        from gradio_client import Client, handle_file
        client_factory = client_factory or Client
        handle_file_fn = handle_file_fn or handle_file
    # Never include input media or prompts in diagnostics. Gradio demo providers
    # are not private. Account-specific pricing and quotas are NOT controlled here.
    try:
        client=client_factory(SPACE_ID,verbose=False)
        task=client.submit(handle_file_fn(str(src)),prompt,8,"",
                           float(seconds),1.0,1.0,42,False,
                           api_name=API_NAME)
    except Exception as exc:
        # A transport error may occur AFTER a provider accepted the job.
        raise UnknownAcceptance("Provider request status is uncertain; no retry") from exc
    stop=time.monotonic()+deadline_seconds
    while not task.done() and time.monotonic()<stop:
        time.sleep(2)
    if not task.done():
        task.cancel()
        raise UnknownAcceptance("Provider job exceeded timeout; do not submit again")
    try:
        payload=task.result()
        returned=payload[0]
        if isinstance(returned,dict):
            returned=returned.get("path") or returned.get("name")
        candidate=Path(returned) if isinstance(returned,str) else None
        if candidate is None or not candidate.is_file() or candidate.is_symlink():
            raise ProviderUnavailable("Provider returned no accessible MP4")
        if candidate.suffix.lower() != ".mp4":
            raise ProviderUnavailable("Provider did not return MP4")
        size=candidate.stat().st_size
        if size<2000 or size>MAX_MP4_BYTES:
            raise ProviderUnavailable("Provider output exceeds accepted size range")
        duration,has_video,has_audio=probe(candidate)
        if not has_video or abs(duration-seconds)>0.5:
            raise ProviderUnavailable("Invalid output video duration or stream")
        dst.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation: a second request cannot overwrite the first.
        with candidate.open("rb") as inp, dst.open("xb") as out:
            shutil.copyfileobj(inp,out,1024*1024)
        with dst.open("rb") as inp:
            checksum=hashlib.file_digest(inp,"sha256").hexdigest()
        return Proof(checksum,duration,has_audio,size,SPACE_ID)
    except (UnsupportedRequest,ProviderUnavailable):
        raise
    except Exception as exc:
        raise ProviderUnavailable("Invalid/unavailable supplier result") from exc
