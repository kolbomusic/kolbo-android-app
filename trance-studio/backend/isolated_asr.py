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


class IsolatedAsrUnavailable(RuntimeError):
    pass


def transcribe_in_child(paths, *, timeout=240):
    """Return (original Hebrew words, complete, per-file timestamp lists).

    A failure never causes a second upload, and the caller may still produce
    the user's MP3 with reduced semantic cue accuracy.
    """
    if not 1 <= len(paths) <= 4:
        raise IsolatedAsrUnavailable("invalid original media count")
    safe_paths = [str(Path(p).resolve()) for p in paths]
    try:
        response = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *safe_paths],
            capture_output=True, text=True, check=True, timeout=timeout,
        )
        # Cap unexpected output from a compromised or broken child; no
        # transcript is ever logged by this wrapper.
        if len(response.stdout) > 320_000:
            raise IsolatedAsrUnavailable("ASR response too large")
        result = json.loads(response.stdout)
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
