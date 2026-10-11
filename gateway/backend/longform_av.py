"""Kolbo Video 4.3.0: verifiable 1–15s *real moving clip* stitching with audio.

This module DOES NOT itself create an actor, lipsync, singing, or a GPU.
It needs genuinely moving, provenance-verified image-to-video segments from a
licensed model. It rejects static input and silent output and never silently
converts still photos into 'AI video'. Compatible with a future quota-backed,
authorized multi-shot provider. No paid computing or external calls here.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import subprocess
from tempfile import TemporaryDirectory
from typing import Literal
import wave

import visual_quality
import audio_evidence
import procedural_sfx

MAX_SECONDS=15
SECONDS_PER_SHOT=5
RATE=16
WIDTH,HEIGHT=640,360
MAX_PARTS=3
MAX_VIDEO_BYTES=80_000_000

class LongformError(ValueError):
    pass

@dataclass(frozen=True)
class LongformPlan:
    status:str
    seconds:int
    shots:tuple[int,...]
    required_external_video_submissions:int
    audio_source:str
    blockers:tuple[str,...]
    external_model_quota_verified:bool=False
    character_continuity_verified:bool=False
    singing_supported:bool=False
    lipsync_supported:bool=False
    unlimited_free_rendering:bool=False

    def as_dict(self):
        x=asdict(self)
        x["shots"]=list(self.shots)
        x["blockers"]=list(self.blockers)
        return x


def split_shots(seconds:int)->tuple[int,...]:
    if type(seconds) is not int or not 1<=seconds<=MAX_SECONDS:
        raise LongformError("Requested seconds must be an integer from 1 to 15")
    steps=[]
    while seconds:
        amount=min(SECONDS_PER_SHOT,seconds)
        steps.append(amount)
        seconds-=amount
    return tuple(steps)


def plan(*,seconds:int,image_count:int,voice_requested:bool=False,
         singing_requested:bool=False,lipsync_requested:bool=False,
         two_independent_people:bool=False,audio_source:str="none",
         quota_remaining:int=0,licensed_provider:bool=False,
         consent_to_external_transfer:bool=False)->LongformPlan:
    shots=split_shots(seconds)
    if type(image_count) is not int or not 0<=image_count<=2:
        raise LongformError("Invalid reference count")
    if audio_source not in ("none","owned_wav","synthetic_sfx"):
        raise LongformError("Unrecognized soundtrack source")
    reasons=[]
    if image_count!=1:reasons.append("one_image_per_scene_only")
    if voice_requested:reasons.append("speech_generation_and_sync_not_available")
    if singing_requested:reasons.append("singing_generation_and_sync_not_available")
    if lipsync_requested:reasons.append("lipsync_not_available")
    if two_independent_people:reasons.append("two_identity_preservation_not_available")
    if audio_source=="none":reasons.append("audible_track_required")
    if not licensed_provider:reasons.append("source_video_provider_license_unverified")
    if not consent_to_external_transfer:reasons.append("external_image_transfer_consent_missing")
    if type(quota_remaining) is not int or quota_remaining <len(shots):
        reasons.append("insufficient_real_video_model_quota")
    return LongformPlan(
        "eligible_for_attempt" if not reasons else "blocked",seconds,shots,
        len(shots),audio_source,tuple(reasons),
        external_model_quota_verified=quota_remaining>=len(shots) and licensed_provider,
    )


def _run(args:list[str],timeout:int=90)->bytes:
    try:
        return subprocess.run(args,check=True,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=timeout).stdout
    except (OSError,subprocess.SubprocessError) as exc:
        raise LongformError("Video processing failed or exceeded bounded compute budget") from exc


def _probe(file:Path)->tuple[float,bool,bool]:
    try:
        details=json.loads(_run(["ffprobe","-v","error","-show_entries",
            "format=duration:stream=codec_type","-of","json",str(file)],
            timeout=20))
        tracks=details.get("streams",[])
        return (float(details["format"]["duration"]),
            any(x.get("codec_type")=="video" for x in tracks),
            any(x.get("codec_type")=="audio" for x in tracks))
    except (ValueError,KeyError,TypeError) as exc:
        raise LongformError("Media probing failed") from exc


def _inspect_wav(sound:Path,seconds:int)->None:
    if sound.is_symlink() or not sound.is_file() or sound.suffix.lower()!=".wav":
        raise LongformError("A real, authorized WAV soundtrack is required")
    if not 100<=sound.stat().st_size<=10_000_000:
        raise LongformError("Soundtrack exceeds supported bytes")
    try:
        with wave.open(str(sound),"rb") as wav:
            rate=wav.getframerate()
            duration=wav.getnframes()/rate if rate else 0
            if (wav.getcomptype()!="NONE" or wav.getnchannels() not in (1,2)
                or wav.getsampwidth() not in (1,2) or not 8000<=rate<=48000
                or duration<seconds-.03):
                raise LongformError("Authorized PCM WAV must span the full video")
    except (wave.Error,EOFError,ZeroDivisionError,OSError) as exc:
        raise LongformError("Invalid authorized soundtrack WAV") from exc


def _verified_video(segment:Path,expected_seconds:int)->dict:
    if segment.is_symlink() or not segment.is_file():
        raise LongformError("Real video segment missing")
    if not 2500<=segment.stat().st_size<=MAX_VIDEO_BYTES:
        raise LongformError("Video segment size invalid")
    duration,has_video,_=_probe(segment)
    if not has_video or duration < expected_seconds-.10 or duration>expected_seconds+.65:
        raise LongformError("Provider output has invalid duration or video track")
    measured=visual_quality.inspect_mp4(segment,audio_required=False)
    # Weak global pixel change alone can never guarantee actor movement;
    # this is a lower bound, not semantic/identity proof.
    if measured.pixel_change_fraction<0.012:
        raise LongformError("Frozen or nearly identical video frames rejected")
    return measured.as_dict()


def last_frame(source:Path,output:Path)->Path:
    seconds,video,_=_probe(source)
    if not video or output.exists():raise LongformError("Invalid continuity frame request")
    _run(["ffmpeg","-nostdin","-v","error","-y",
          "-ss",str(max(0,seconds-0.16)),"-i",str(source),
          "-frames:v","1",str(output)],timeout=30)
    if not output.is_file() or output.stat().st_size<300:
        raise LongformError("Cannot prepare continuity reference")
    return output


def assemble(*,segments:list[Path],seconds:int,output:Path,
             user_soundtrack:Path|None=None,
             synthetic_effect:str="none")->dict:
    shots=split_shots(seconds)
    if len(segments)!=len(shots):
        raise LongformError("Real video segments missing: no silent padding allowed")
    if user_soundtrack is not None and synthetic_effect!="none":
        raise LongformError("Cannot replace a user soundtrack with an automatic effect")
    if user_soundtrack is None and synthetic_effect=="none":
        raise LongformError("An audible soundtrack is mandatory for this output mode")
    if output.exists():
        raise LongformError("Will not overwrite an existing output")
    before=[_verified_video(Path(source),shot)
            for source,shot in zip(segments,shots)]
    output.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix="kolbo-15s-motion-") as scratch:
        root=Path(scratch)
        converted=[]
        for i,(path,shot) in enumerate(zip(segments,shots)):
            normalized=root/f"part{i}.mp4"
            # Sequential transcoding prevents 3 decoders from running at once
            # in the Render Free 512MB container.
            _run(["ffmpeg","-nostdin","-v","error","-y",
                "-i",str(path),"-an",
                "-vf",f"fps={RATE},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                      f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                "-frames:v",str(shot*RATE),"-c:v","libx264","-preset",
                "ultrafast","-crf","28","-video_track_timescale","16384",
                str(normalized)],timeout=90)
            elapsed,video,audio=_probe(normalized)
            if not video or audio or abs(elapsed-shot)>.08:
                raise LongformError("Normalized real-model shot did not meet exact length")
            converted.append(normalized)
        manifest=root/"parts.ffconcat"
        manifest.write_text("ffconcat version 1.0\n"+"".join(
            f"file 'part{i}.mp4'\n" for i in range(len(converted))),encoding="utf8")
        raw=root/"concat.mp4"
        _run(["ffmpeg","-nostdin","-v","error","-y","-safe","0",
             "-f","concat","-i",str(manifest),"-c:v","copy",
             "-an",str(raw)],timeout=60)
        if user_soundtrack is None:
            if synthetic_effect not in procedural_sfx.SFX_KIND or synthetic_effect=="none":
                raise LongformError("Unsupported procedurally generated sound")
            sound=root/"generated-fx.wav"
            procedural_sfx.synthesize(sound,seconds=seconds,kind=synthetic_effect)
        else:
            sound=Path(user_soundtrack)
            _inspect_wav(sound,seconds)
        finished=root/"output.mp4"
        _run(["ffmpeg","-nostdin","-v","error","-y","-i",str(raw),
              "-i",str(sound),"-map","0:v:0","-map","1:a:0","-c:v","copy",
              "-c:a","aac","-b:a","128k","-t",str(seconds),
              "-movflags","+faststart",str(finished)],timeout=80)
        duration,video,audio=_probe(finished)
        if not video or not audio or abs(duration-seconds)>.085:
            raise LongformError("Final duration or audible audio stream absent")
        sound_report=audio_evidence.inspect_mp4(finished,audio_required=True)
        if sound_report.verdict=="reject":
            raise LongformError("Audio exists but is silent or inaudible")
        visual_report=visual_quality.inspect_mp4(finished,audio_required=True)
        if visual_report.pixel_change_fraction<.012:
            raise LongformError("Final video lacks measured movement")
        if finished.stat().st_size>MAX_VIDEO_BYTES:
            raise LongformError("Final output exceeds safe transfer size")
        # Exclusive copy after every gate, no partial publication.
        with finished.open("rb") as inp,output.open("xb") as out:
            while piece:=inp.read(1024*1024):
                out.write(piece)
    with output.open("rb") as src:
        digest=hashlib.file_digest(src,"sha256").hexdigest()
    return {
        "mode":"assembled_real_motion_with_audio",
        "duration_seconds":duration,
        "requested_seconds":seconds,
        "video_segments":len(segments),
        "shots_seconds":list(shots),
        "has_audio":True,
        "audio_source":"user_supplied_wav" if user_soundtrack is not None
                       else "original_synthetic_sfx",
        "sha256":digest,
        "bytes":output.stat().st_size,
        "motion_evidence":{"segments":before,"final":visual_report.as_dict()},
        "audio_evidence":sound_report.as_dict(),
        "singing_verified":False,
        "spoken_language_verified":False,
        "lip_sync_verified":False,
        "actor_identity_continuity_verified":False,
        "user_prompt_semantics_verified":False,
        "gpu_provider_licensing_verified":False,
    }


def generate_shots_then_assemble(*,reference_image:Path,seconds:int,
            prompt:str,output:Path,generator,
            authorized_wav:Path|None=None,synthetic_effect:str="none",
            quota_remaining:int=0,provider_license_verified:bool=False,
            external_transfer_consent:bool=False)->dict:
    """Orchestrate genuine motion segments and last-frame continuity.

    Generator is a trusted, injected provider callback. There is NO default
    GPU, quota bypass, retry, or paid provider. Caller must establish actual
    free credits and rights on server before running; caller-supplied booleans
    from an Android request must never be trusted as verification.
    """
    import re
    if not isinstance(prompt,str) or not 5<=len(prompt.strip())<=3000:
        raise LongformError("Invalid scene instructions")
    if reference_image.is_symlink() or not reference_image.is_file():
        raise LongformError("Missing or untrusted initial scene image")
    if not callable(generator):
        raise LongformError("Verified video model provider is required")
    if authorized_wav is None and synthetic_effect=="none":
        raise LongformError("Audio is required for 15-second mode")
    if authorized_wav is not None and synthetic_effect!="none":
        raise LongformError("Choose exactly one audible soundtrack")
    soundtrack_type="owned_wav" if authorized_wav is not None else "synthetic_sfx"
    # The parser is deliberately conservative; it is NOT a replacement for
    # structured prompt understanding or scene semantics QA.
    singing=bool(re.search(r"\b(?:sing|singing|sings|lyrics)\b|"
        r"(?:לשיר|שרה|שרות|תשיר|שיר(?:ה|ים)?)",prompt,re.I))
    speech=bool(re.search(r"\b(?:speaks?|dialogue|talks?|says?)\b|"
        r"(?:תדבר|מדבר|אומר|דיבור|קריינות)",prompt,re.I))
    lipsync=bool(re.search(r"\b(?:lipsync|lip.sync)\b|סנכרון\s*שפתיים",prompt,re.I))
    independent=bool(re.search(r"\b(?:two\s+people|two\s+characters)\b|"
        r"(?:שני\s+אנשים|שתי\s+דמויות|שניהם)",prompt,re.I))
    task=plan(seconds=seconds,image_count=1,voice_requested=speech,
              singing_requested=singing,lipsync_requested=lipsync,
              two_independent_people=independent,audio_source=soundtrack_type,
              quota_remaining=quota_remaining,
              licensed_provider=provider_license_verified,
              consent_to_external_transfer=external_transfer_consent)
    if task.status!="eligible_for_attempt":
        raise LongformError("Long-form generation blocked: "+",".join(task.blockers))
    with TemporaryDirectory(prefix="kolbo-verified-gpu-shots-") as folder:
        root=Path(folder)
        shots=[]
        current_reference=Path(reference_image)
        for index,amount in enumerate(task.shots):
            generated=root/f"ai-part-{index}.mp4"
            # If this remote request succeeds but transport fails, STOP.
            # Never auto resend an ambiguous provider submission.
            generator(reference=current_reference,prompt=prompt,seconds=amount,
                      destination=generated,consent=True,commercial=False,
                      wants_audio=False,wants_lipsync=False)
            _verified_video(generated,amount)
            shots.append(generated)
            if index<len(task.shots)-1:
                current_reference=last_frame(
                    generated,root/f"reference-for-{index+1}.png")
        receipt=assemble(segments=shots,seconds=seconds,
                    output=output,user_soundtrack=authorized_wav,
                    synthetic_effect=synthetic_effect)
        receipt["provider_calls"] = len(shots)
        receipt["continuation_method"]="previous_shot_final_frame_reference"
        receipt["identity_continuity_verified"]=False
        receipt["semantic_prompt_adherence_verified"]=False
        return receipt
