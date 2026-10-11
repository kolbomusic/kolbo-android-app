"""Scene-level QA of real AI video; specifically reject static split-screen collages.

Audio streams, correct duration and global pixel motion cannot tell whether
two independent photographs were transformed into ONE staged performance.
This module checks persistent center dividers and overall motion. It can
identify suspicious split-screen imagery but NEVER certifies location, crowd
size, actor identity, lyrics, singing, or synchrony.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import json,statistics,subprocess
from PIL import Image

SIZE=384
MOTION_THRESHOLD=2.0
STRONG_SEAM_VALUE=37.0
SEAM_RATIO=4.8
MIN_SEAM_GAP=11
MAX_SEAM_GAP=52

class SceneAnalysisError(ValueError):
    pass

@dataclass(frozen=True)
class SceneAudit:
    output_is_split_layout:bool
    near_static_frames:bool
    video_duration_seconds:float
    left_change_mean:float
    right_change_mean:float
    persistent_dividers:list[int]
    divider_strengths:list[float]
    scene_context_verified:bool=False
    two_distinct_actor_identities_verified:bool=False
    stage_verified:bool=False
    crowd_size_verified:bool=False
    singing_language_verified:bool=False
    lip_sync_verified:bool=False
    def as_dict(self)->dict:
        return asdict(self)

def analyze_frames(images:list[Image.Image],duration:float=3.0)->SceneAudit:
    if len(images)!=3 or not .9<=duration<=16:
        raise SceneAnalysisError("Scene QA expects three frames and valid duration")
    buf=[]
    for image in images:
        if min(image.size)<96:raise SceneAnalysisError("Source frames too small")
        buf.append(image.convert("L").resize((SIZE,SIZE)).tobytes())
    # Detect panels by 2 STRONG STATIONARY VERTICAL BORDERS in center 32–68%.
    # Actual changing-stage scenes can have one central pole or a microphone,
    # but two persistent boundaries enclosing a collage divider are rarer.
    # Use min edge strength across 3 timestamps so camera-panning edges fail.
    xstart,xend=int(SIZE*.34),int(SIZE*.66)
    ys=range(int(SIZE*.16),int(SIZE*.85),4)
    columns=[]
    for pixels in buf:
        profile=[0.0]*SIZE
        for x in range(xstart,xend):
            total=0
            for y in ys:
                row=y*SIZE
                total+=abs(pixels[row+x]-pixels[row+x+1])
            profile[x]=total/len(ys)
        columns.append(profile)
    persistent=[min(c[x] for c in columns) for x in range(SIZE)]
    background=statistics.median(
        persistent[x] for x in range(xstart,xend)) or 1.0
    candidates=sorted([
        x for x in range(xstart,xend)
        if persistent[x]>STRONG_SEAM_VALUE and
           persistent[x]>SEAM_RATIO*background
    ],key=lambda x:persistent[x],reverse=True)
    peaks=[]
    for x in candidates:
        if all(abs(x-v)>=4 for v in peaks):
            peaks.append(x)
        if len(peaks)==12:break
    peaks=sorted(peaks)
    split=any(
        MIN_SEAM_GAP<=b-a<=MAX_SEAM_GAP
        for i,a in enumerate(peaks) for b in peaks[i+1:])
    left_diffs=[]
    right_diffs=[]
    for previous,current in ((buf[0],buf[1]),(buf[1],buf[2])):
        for low,high,target in ((0,SIZE//2,left_diffs),
                                (SIZE//2,SIZE,right_diffs)):
            delta=0
            count=0
            for y in range(12,SIZE-12,4):
                offset=y*SIZE
                for x in range(low,high,4):
                    delta+=abs(previous[offset+x]-current[offset+x])
                    count+=1
            target.append(delta/count if count else 0)
    left=statistics.mean(left_diffs)
    right=statistics.mean(right_diffs)
    return SceneAudit(split,left<MOTION_THRESHOLD and right<MOTION_THRESHOLD,
        float(duration),round(left,4),round(right,4),
        peaks,[round(persistent[x],2) for x in peaks])

def _run(args:list[str],timeout:int=30)->bytes:
    try:
        return subprocess.run(args,capture_output=True,check=True,
                             timeout=timeout).stdout
    except (OSError,subprocess.SubprocessError) as exc:
        raise SceneAnalysisError("FFmpeg scene frames unavailable") from exc

def inspect_video(path:Path)->SceneAudit:
    file=Path(path)
    if file.is_symlink() or not file.is_file():
        raise SceneAnalysisError("Invalid scene video")
    try:
        info=json.loads(_run(["ffprobe","-v","error",
           "-show_entries","format=duration","-of","json",str(file)]))
        duration=float(info["format"]["duration"])
    except (KeyError,ValueError,TypeError) as exc:
        raise SceneAnalysisError("Invalid scene duration") from exc
    if not .9<=duration<=16:
        raise SceneAnalysisError("Scene duration out of supported range")
    times=[max(.05,duration*x) for x in (.13,.51,.87)]
    frames=[]
    with TemporaryDirectory(prefix="kolbo-scene-qa-") as scratch:
        for i,t in enumerate(times):
            outfile=Path(scratch)/f"frame_{i}.png"
            _run(["ffmpeg","-nostdin","-v","error","-y",
                  "-ss",str(t),"-i",str(file),
                  "-frames:v","1",str(outfile)],timeout=30)
            if not outfile.is_file():raise SceneAnalysisError("Scene frame decode failed")
            with Image.open(outfile) as frame:frames.append(frame.copy())
    return analyze_frames(frames,duration)
