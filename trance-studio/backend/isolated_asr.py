"""Low-memory Hebrew speech recognition isolated from audio/video mixing.

The Render Free worker has only 512 MiB RAM. CTranslate2 model weights
loaded directly in gunicorn may remain resident after garbage collection,
overlapping full-length NumPy DJ tracks and FFmpeg's H264 frame buffers.
Use a short-lived child process to release native inference memory at exit.
No network provider receives private audio; all files remain on this host.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import time


class IsolatedAsrUnavailable(RuntimeError):
    pass



def _safe_memory_for_asr():
    """Avoid starting Whisper if another process leaves too little cgroup RAM.

    This guards the *512 MiB* Render Free worker only. Unknown/non-cgroup
    environments keep the old behavior. Never send audio off-box to cope
    with insufficient resources.
    """
    mib=1024*1024
    for limit_file, usage_file in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
         "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        try:
            raw=Path(limit_file).read_text().strip()
            if raw == "max":
                return True
            limit=int(raw)
            usage=int(Path(usage_file).read_text().strip())
            if 0<limit<=768*mib:
                # Tiny multilingual ASR + decoder + OS/FFmpeg reserve.
                return limit-usage>=230*mib
            return True
        except (OSError,ValueError):
            continue
    return True



def _cgroup_remaining_bytes():
    """Report actual shared container headroom, not child-only RSS."""
    for limit_file, usage_file in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
         "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        try:
            maximum=Path(limit_file).read_text().strip()
            if maximum=="max":
                return None
            limit=int(maximum)
            if not 0<limit<=768*1024*1024:
                return None
            usage=int(Path(usage_file).read_text().strip())
            return max(0,limit-usage)
        except (OSError,ValueError):
            continue
    return None


def transcribe_in_child(paths, *, timeout=240):
    """Return (original Hebrew words, complete, per-file timestamp lists).

    A failure never causes a second upload, and the caller may still produce
    the user's MP3 with reduced semantic cue accuracy.
    """
    if not 1 <= len(paths) <= 4:
        raise IsolatedAsrUnavailable("invalid original media count")
    if not _safe_memory_for_asr():
        raise IsolatedAsrUnavailable("Insufficient local ASR memory budget")
    safe_paths = [str(Path(p).resolve()) for p in paths]
    try:
        # An ASR child can exceed the 512 MiB Render container even when it
        # had enough free memory at launch. Inspect the shared cgroup during
        # inference; cancel only the child before the kernel kills Gunicorn.
        command=[sys.executable, str(Path(__file__).resolve()), *safe_paths]
        child=subprocess.Popen(command,stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,text=True)
        started=time.monotonic()
        try:
            while True:
                remaining=timeout-(time.monotonic()-started)
                if remaining<=0:
                    raise subprocess.TimeoutExpired(command,timeout)
                headroom=_cgroup_remaining_bytes()
                if headroom is not None and headroom<96*1024*1024:
                    raise IsolatedAsrUnavailable("Local ASR memory safety guard")
                try:
                    stdout,_=child.communicate(timeout=min(.25,remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if child.returncode!=0:
                raise IsolatedAsrUnavailable("Local ASR worker exited")
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate()
        # Cap unexpected output from a compromised or broken child; no
        # transcript is ever logged by this wrapper.
        if len(stdout)>320_000:
            raise IsolatedAsrUnavailable("ASR response too large")
        result=json.loads(stdout)
        words = result["text"]
        complete = result["complete"]
        timeline = result["timeline"]
        if not isinstance(words, str) or len(words) > 4000 or not isinstance(complete, bool):
            raise ValueError("ASR fields invalid")
        if (not isinstance(timeline, list) or len(timeline) != len(safe_paths)
                or any(not isinstance(group, list) or len(group) > 1200
                       for group in timeline)):
            raise ValueError("ASR timeline invalid")
        return words, complete, timeline
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        raise IsolatedAsrUnavailable("Local isolated Hebrew recognition unavailable") from exc


def _child_main():
    from source_asr import transcribe_original_files
    # The child is a private local CPU process; it does not contact external
    # API providers or save a permanent copy of the incoming recording.
    words, complete, timeline = transcribe_original_files(
        [Path(p) for p in sys.argv[1:]], return_timeline=True
    )
    sys.stdout.write(json.dumps({
        "text": words, "complete": complete, "timeline": timeline
    }, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        _child_main()
    except Exception:
        # Do not dump private speech, source paths or model internals to logs.
        sys.exit(2)
