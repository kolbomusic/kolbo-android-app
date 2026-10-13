"""Local synthetic-media validator. Motion/audio evidence is NOT proof of AI or GPU origin.
Run on trusted, isolated hardware for untrusted media; no network or media uploads.
"""
from __future__ import annotations
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

MAX_BYTES = 120_000_000
FRAME_SIDE = 64
FRAME_SIZE = FRAME_SIDE * FRAME_SIDE

def _run(args: list[str], timeout: int, max_stdout_bytes: int) -> bytes | None:
    try:
        completed = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        return completed.stdout if completed.returncode == 0 and len(completed.stdout) <= max_stdout_bytes else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None

def inspect_local_receipt(receipt: Path) -> dict:
    """Verify actual local MP4 hash, decoded moving frames and audible-level audio.

    Receipts cannot point to arbitrary paths. No attestation of GPU/AI provenance
    or of human identity is implied by this signal-based check.
    """
    result = {
        "verified": False, "sha256_matches": False, "video_decodes": False,
        "moving_intervals": 0, "audio_decodes": False,
        "audio_signal_detected": False, "gpu_origin_attested": False,
        "ai_origin_attested": False,
    }
    try:
        receipt = Path(receipt)
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 16_384:
            return result
        info = json.loads(receipt.read_text(encoding="utf-8"))
        if not isinstance(info, dict) or info.get("schema_version") != 2:
            return result
        if info.get("media_file") != "synthetic-proof.mp4":
            return result
        digest = info.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return result
        media = receipt.parent / "synthetic-proof.mp4"
        if media.is_symlink() or not media.is_file():
            return result
        if not 4096 < media.stat().st_size <= MAX_BYTES:
            return result
        with media.open("rb") as source:
            if source.read(12)[4:8] != b"ftyp":
                return result
            source.seek(0)
            digest_actual = hashlib.file_digest(source, "sha256").hexdigest()
        if digest_actual != digest:
            return result
        result["sha256_matches"] = True
        path = str(media.resolve(strict=True))
        raw = _run(["ffprobe", "-v", "error", "-protocol_whitelist", "file",
                    "-show_entries", "stream=codec_type,width,height:format=duration",
                    "-of", "json", path], 15, 20_000)
        if raw is None:
            return result
        meta = json.loads(raw)
        duration = float(meta.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or not 1 <= duration <= 16:
            return result
        streams = meta.get("streams", [])
        video = [s for s in streams if s.get("codec_type") == "video"]
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        if (len(video) != 1 or not audio or
                not 8 <= int(video[0].get("width", 0)) <= 4096 or
                not 8 <= int(video[0].get("height", 0)) <= 4096):
            return result
        frames = _run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist",
                       "file", "-i", path, "-map", "0:v:0", "-an", "-vf",
                       f"fps=2,scale={FRAME_SIDE}:{FRAME_SIDE}:flags=fast_bilinear,format=gray",
                       "-f", "rawvideo", "pipe:1"], 25,
                      (math.ceil(duration * 2) + 2) * FRAME_SIZE)
        if frames is None or len(frames) % FRAME_SIZE or len(frames) < 3 * FRAME_SIZE:
            return result
        result["video_decodes"] = True
        images = [frames[i:i+FRAME_SIZE] for i in range(0, len(frames), FRAME_SIZE)]
        moving = sum(sum(abs(a-b) for a,b in zip(a0,a1)) / FRAME_SIZE >= 3
                     for a0,a1 in zip(images, images[1:]))
        result["moving_intervals"] = moving
        if moving < 2:
            return result
        pcm = _run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist",
                    "file", "-i", path, "-map", "0:a:0", "-vn", "-ac", "1",
                    "-ar", "8000", "-f", "s16le", "pipe:1"], 25, 260_000)
        if pcm is None or len(pcm) < 4000 or len(pcm) % 2:
            return result
        result["audio_decodes"] = True
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        rms = math.sqrt(sum(float(s)*s for s in samples) / len(samples))
        result["audio_signal_detected"] = rms >= 260  # ~-42 dBFS RMS
        result["verified"] = bool(result["audio_signal_detected"])
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        pass
    return result
