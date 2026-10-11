"""One-shot public ZeroGPU proof with a synthetic test image. NO production use.

No user imagery, no payment token, no retries, no live Kolbo systems.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw
from gradio_client import Client, handle_file

SPACE = "zerogpu-aoti/wan2-2-fp8da-aoti-faster"
OUTPUT = Path("proof-out")
PROMPT = (
    "A small golden origami rocket gently moves upward against a plain blue sky, "
    "real visible movement, locked camera, no text or subtitles"
)

def ffprobe(path: Path) -> dict:
    process = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,format_name:stream=codec_type,codec_name,width,height,nb_frames",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=20)
    return json.loads(process.stdout)

def make_synthetic_image(path: Path) -> None:
    pic = Image.new("RGB", (640, 640), (125, 187, 233))
    paint = ImageDraw.Draw(pic)
    paint.polygon([(315, 140), (390, 400), (315, 364), (230, 400)],
                  fill=(240, 184, 31))
    paint.ellipse((292, 243, 339, 291), fill=(249, 249, 252))
    pic.save(path)

def media_path(value):
    if isinstance(value, str):
        return Path(value)
    if isinstance(value, dict):
        for key in ("video", "path", "name"):
            if value.get(key) is not None:
                found = media_path(value[key])
                if found is not None:
                    return found
    return None

def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    reference = OUTPUT / "synthetic-reference.png"
    make_synthetic_image(reference)
    print("Provider:", SPACE, "| input: synthetic only", flush=True)
    print("Anonymous public quota; no payment token; one job only.", flush=True)
    client = Client(SPACE, verbose=False)
    api_spec = client.view_api(return_format="dict")
    available = api_spec.keys() if isinstance(api_spec, dict) else []
    print("API groups:", list(available), flush=True)

    start = time.monotonic()
    task = client.submit(
        handle_file(str(reference)), PROMPT, 1, "", 1.2,
        1.0, 1.0, 42, False, api_name="/generate_video")
    deadline = start + 215
    while not task.done() and time.monotonic() < deadline:
        time.sleep(4)
    if not task.done():
        task.cancel()
        raise TimeoutError("One anonymous ZeroGPU job did not complete in time")
    raw = task.result()
    if not isinstance(raw, (list, tuple)) or not raw:
        raise AssertionError("Unexpected Gradio response, no proof")
    src = media_path(raw[0])
    if src is None or not src.is_file():
        raise AssertionError("No accessible real provider MP4 returned")
    clip = OUTPUT / "zerogpu-original.mp4"
    shutil.copyfile(src, clip)
    details = ffprobe(clip)
    duration = float(details.get("format", {}).get("duration", 0))
    has_video = any(s.get("codec_type") == "video"
                    for s in details.get("streams", []))
    if not has_video or not (0.6 <= duration <= 2.0) or clip.stat().st_size < 2000:
        raise AssertionError(f"Invalid video duration/codec: {duration}, {has_video}")
    with clip.open("rb") as fp:
        clip_digest = hashlib.file_digest(fp, "sha256").hexdigest()
    receipt = {
        "provider": SPACE,
        "model": "Wan2.2 I2V A14B public ZeroGPU demo",
        "external_ai_generated": True,
        "input": "synthetic origami rocket only",
        "duration_seconds": duration,
        "has_audio": any(s.get("codec_type") == "audio" for s in details["streams"]),
        "bytes": clip.stat().st_size,
        "sha256": clip_digest,
        "source": "Gradio Space one-shot API",
        "production_ready": False,
        "commercial_usage_authorized": False,
        "two_independent_references": False,
        "identity_and_lipsync_verified": False
    }
    (OUTPUT / "receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8")
    print("REAL EXTERNAL AI VIDEO PROOF:", json.dumps(receipt), flush=True)

if __name__ == "__main__":
    main()
