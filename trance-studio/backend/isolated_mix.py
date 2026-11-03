"""Run full DJ audio DSP out of the Flask/Render Free web process.

Render Free has 512 MiB and an ephemeral filesystem. A previous in-process
NumPy/FFmpeg job killed the entire WSGI instance and lost its job registry.
A short-lived lower-priority child isolates temporary DSP allocations. If it
fails (including a cgroup OOM kill of the child), create a clearly labelled
voice-only rescue MP3 with bounded FFmpeg memory instead of losing all audio.
Neither path uploads WhatsApp recordings to a third party.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


class IsolatedMixUnavailable(RuntimeError):
    pass


def _memory_allows_heavy_mix():
    mib = 1024 * 1024
    for ceiling, used in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
         "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        try:
            limit = Path(ceiling).read_text().strip()
            if limit == "max":
                return True
            capacity = int(limit)
            current = int(Path(used).read_text().strip())
            if 0 < capacity <= 768 * mib:
                # Leave room for the web worker, FFmpeg and the OS.
                return capacity - current >= 210 * mib
            return True
        except (OSError, ValueError):
            continue
    return True


def _duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True, capture_output=True, check=True, timeout=15,
    )
    return float(result.stdout.strip())


def _voice_only_rescue(paths, output_dir):
    """Preserve every original spoken second, with low-memory audio cleanup.

    This is not represented as a full professional DJ track. It is an
    explicitly identified emergency fallback after a failed heavy mix.
    """
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    for path in paths:
        command.extend(["-i", str(path)])
    filters = []
    names = []
    for i in range(len(paths)):
        name = f"v{i}"
        filters.append(
            f"[{i}:a:0]aresample=32000,highpass=f=80,lowpass=f=7200,"
            f"acompressor=threshold=0.10:ratio=2:attack=12:release=160,"
            f"asetpts=PTS-STARTPTS[{name}]"
        )
        names.append(f"[{name}]")
    if len(paths) == 1:
        filters.append("[v0]anull[rescue]")
    else:
        filters.append("".join(names) + f"concat=n={len(paths)}:v=0:a=1[rescue]")
    voice = output_dir / "voice.mp3"
    mix = output_dir / "mix.mp3"
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[rescue]",
        "-ac", "2", "-codec:a", "libmp3lame", "-b:a", "192k",
        str(voice),
    ])
    subprocess.run(command,check=True,timeout=480,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    shutil.copyfile(voice,mix)
    if voice.stat().st_size < 512 or mix.stat().st_size < 512:
        raise IsolatedMixUnavailable("Audio rescue encoder created no media")
    duration = _duration(mix)
    if not .5 <= duration <= 420:
        raise IsolatedMixUnavailable("Unexpected rescue audio duration")
    return {"audio_seconds":duration,"video_fx_timeline":[],
            "mix_quality":"voice_rescue"}


def process_in_child(paths, options, output_dir, *, backing_music_path=None,
                     return_video_timeline=False, timeout=720):
    """Return only bounded metadata; the two MP3 files remain on local disk."""
    if not 1 <= len(paths) <= 4:
        raise IsolatedMixUnavailable("Invalid original media count")
    output_dir=Path(output_dir)
    manifest=output_dir/".private-mix-options.json"
    payload={
        "paths":[str(Path(p).resolve()) for p in paths],
        "options":options,
        "backing_music_path":(str(Path(backing_music_path).resolve())
                              if backing_music_path else None),
        "return_video_timeline":bool(return_video_timeline),
        "output_dir":str(output_dir.resolve()),
    }
    # A manifest contains source-derived speech hints and is private and
    # short-lived. It is never returned by any route.
    try:
        fd=os.open(manifest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as fp:
            json.dump(payload,fp,ensure_ascii=False,separators=(",",":"))
        if _memory_allows_heavy_mix():
            try:
                child=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),str(manifest)],
                    text=True,capture_output=True,timeout=timeout,check=True,
                )
                if len(child.stdout)>128000:
                    raise IsolatedMixUnavailable("Oversized worker report")
                report=json.loads(child.stdout)
                if (not isinstance(report,dict) or
                        report.get("mix_quality")!="full_dj" or
                        not isinstance(report.get("video_fx_timeline"),list) or
                        not .5 <= float(report["audio_seconds"]) <= 420):
                    raise IsolatedMixUnavailable("Invalid mix worker report")
                if any(not (output_dir/name).is_file() or
                       (output_dir/name).stat().st_size<512
                       for name in ("mix.mp3","voice.mp3")):
                    raise IsolatedMixUnavailable("Mix worker produced no audio")
                return report
            except (OSError,ValueError,TypeError,KeyError,
                    subprocess.SubprocessError,IsolatedMixUnavailable):
                # A crashed or OOM-killed child must not cancel the user's
                # speech. The original files are still on local disk.
                pass
        for name in ("mix.mp3","voice.mp3"):
            (output_dir/name).unlink(missing_ok=True)
        return _voice_only_rescue(paths,output_dir)
    except (OSError,subprocess.SubprocessError,ValueError) as exc:
        raise IsolatedMixUnavailable(
            "Local DJ processing and voice-only rescue failed"
        ) from exc
    finally:
        manifest.unlink(missing_ok=True)


def _child_main(manifest_path):
    # A Linux OOM kill should choose the disposable music worker over Flask,
    # allowing Flask to report the failure and run FFmpeg rescue. Setting
    # the score higher is best-effort and requires no elevated privilege.
    try:
        Path("/proc/self/oom_score_adj").write_text("500")
    except OSError:
        pass
    from engine import export_mp3,load_audio,render_mix
    from licensed_music import mix_licensed_backing
    payload=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    paths=[Path(p) for p in payload["paths"]]
    output_dir=Path(payload["output_dir"])
    options=payload["options"]
    clips=[load_audio(p) for p in paths]
    result=render_mix(
        clips,**options,return_voice=True,
        return_video_timeline=payload["return_video_timeline"],
        progress=lambda *_:None,
    )
    if len(result)==3:
        music,voice,timeline=result
    else:
        music,voice=result
        timeline=[]
    if payload["backing_music_path"]:
        music=mix_licensed_backing(
            payload["backing_music_path"],voice,32000,
            transcript_hint=options.get("transcript_hint",""),
            bpm=options.get("bpm",145),
            humor=options.get("humor","auto"),
        )
    duration=len(music)/32000
    export_mp3(music,output_dir/"mix.mp3")
    export_mp3(voice,output_dir/"voice.mp3")
    print(json.dumps({"audio_seconds":duration,
                      "video_fx_timeline":timeline,
                      "mix_quality":"full_dj"},
                     ensure_ascii=False,separators=(",",":")))


if __name__=="__main__":
    if len(sys.argv)!=2:
        sys.exit(2)
    try:
        _child_main(sys.argv[1])
    except Exception:
        # Do not log/private speech, local upload paths or raw subprocess
        # stderr to public operational logs.
        sys.exit(2)
