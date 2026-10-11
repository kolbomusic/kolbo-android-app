"""Measure actual decoded sound energy; a valid AAC stream may still be silent.

This is a signal-level gate, not speech recognition or musical quality scoring.
Must never be interpreted as proof of spoken language, singing or lip sync.
"""
from __future__ import annotations
import array
from dataclasses import asdict,dataclass
import json, math, subprocess
from pathlib import Path

@dataclass(frozen=True)
class AudioEvidence:
    has_audio_stream:bool
    decoded_audio:bool
    rms_dbfs:float|None
    non_silent_fraction:float
    verdict:str
    warnings:tuple[str,...]

    def as_dict(self):return asdict(self)

def inspect_mp4(source:Path,*,audio_required:bool,sample_seconds:int=30)->AudioEvidence:
    if not 1<=sample_seconds<=60:raise ValueError("Invalid sample window")
    video=Path(source)
    if not video.is_file():raise ValueError("Video file unavailable")
    metadata=subprocess.run(
        ["ffprobe","-v","error","-show_entries","stream=codec_type",
         "-of","json",str(video)],capture_output=True,check=True,timeout=30)
    tracks=json.loads(metadata.stdout).get("streams",[])
    if not any(s.get("codec_type")=="audio" for s in tracks):
        return AudioEvidence(False,False,None,0.0,
            "reject" if audio_required else "needs_review",
            ("missing_required_audio",) if audio_required else ("no_audio_track",))
    decoded=subprocess.run(
        ["ffmpeg","-nostdin","-v","error","-t",str(sample_seconds),"-i",str(video),
         "-vn","-ac","1","-ar","16000","-f","s16le","pipe:1"],
         capture_output=True,check=True,timeout=40)
    buffer=decoded.stdout
    if not buffer:
        return AudioEvidence(True,False,None,0.0,"reject",("audio_decode_empty",))
    if len(buffer)%2:buffer=buffer[:-1]
    samples=array.array("h");samples.frombytes(buffer)
    if not samples:raise ValueError("No decoded PCM")
    # array('h') is host endian; Linux staging runner is little endian.
    squared=sum(float(v)*v for v in samples)
    rms=math.sqrt(squared/len(samples))/32768
    db=20*math.log10(max(rms,1e-12))
    window=1600
    audible=0;windows=0
    for i in range(0,len(samples),window):
        frame=samples[i:i+window]
        if not frame:continue
        power=math.sqrt(sum(float(v)*v for v in frame)/len(frame))/32768
        if power>10**(-45/20):audible+=1
        windows+=1
    fraction=audible/max(windows,1)
    warnings=[]
    if db < -58 or fraction < 0.03:
        warnings.append("silent_or_inaudible_audio")
    if max(abs(v) for v in samples)>=32760:
        warnings.append("possible_audio_clipping")
    warnings.append("speech_language_and_lipsync_unverified")
    return AudioEvidence(True,True,round(db,2),round(fraction,3),
        "reject" if audio_required and "silent_or_inaudible_audio" in warnings
        else "needs_review",tuple(warnings))
