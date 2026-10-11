"""Advisory visual evidence for Kolbo Video staging, never an automatic approval.

Checks motion/detail of decoded frames, not semantic prompt adherence, identity
or lip-sync. Weak motion and loss of detail require review; they must not be
silently reported as a successful AI generation. No upload or provider calls.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, ImageChops, ImageStat


@dataclass(frozen=True)
class VisualEvidence:
    verdict: str
    warnings: tuple[str, ...]
    pixel_change_fraction: float
    detail_retention_ratio: float
    duration_seconds: float
    audio_present: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _analysis_crop(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    w, h = gray.size
    if w < 96 or h < 96:
        raise ValueError("Image too small for reliable visual analysis")
    return gray.crop((w // 4, h // 8, (3 * w) // 4, (7 * h) // 8))


def _detail(image: Image.Image) -> float:
    gray = _analysis_crop(image)
    # Spatial gradients are a *proxy* for sharpness; natural scenes can be
    # intentionally soft. Do not infer video quality from this number alone.
    horizontal = ImageChops.difference(gray, ImageChops.offset(gray, 1, 0))
    vertical = ImageChops.difference(gray, ImageChops.offset(gray, 0, 1))
    # Gradient *energy* (squared differences), unlike mean gradient
    # magnitude, detects when sharp edges spread into blur.
    return (ImageStat.Stat(horizontal).rms[0] ** 2
            + ImageStat.Stat(vertical).rms[0] ** 2)


def assess_frames(
    first: Image.Image, middle: Image.Image, last: Image.Image,
    *, duration_seconds: float, audio_present: bool,
    audio_required: bool = False
) -> VisualEvidence:
    if not 0.1 <= duration_seconds <= 360:
        raise ValueError("Invalid measured duration")
    if first.size != middle.size or first.size != last.size:
        raise ValueError("Frame dimensions differ")
    warnings = []
    first_gray = _analysis_crop(first)
    last_gray = _analysis_crop(last)
    delta = ImageStat.Stat(ImageChops.difference(
        first_gray, last_gray)).mean[0] / 255
    first_detail, last_detail = _detail(first), _detail(last)
    ratio = last_detail / first_detail if first_detail > 0.05 else 0.0
    if first_detail < 0.05:
        warnings.append("insufficient_initial_detail")
    if ratio < 0.75:
        warnings.append("detail_loss_detected")
    if delta < 0.025:
        warnings.append("weak_visual_motion_evidence")
    # This gate cannot verify visual meaning, multiple identities, real speech,
    # singing, or consistent locations. Always require semantic/manual QA.
    warnings.append("scene_semantics_not_verified")
    if audio_required and not audio_present:
        warnings.append("missing_required_audio")
        verdict = "reject"
    else:
        verdict = "needs_review"
    return VisualEvidence(
        verdict=verdict, warnings=tuple(warnings),
        pixel_change_fraction=round(delta, 5),
        detail_retention_ratio=round(ratio, 5),
        duration_seconds=round(duration_seconds, 4),
        audio_present=audio_present,
    )


def _run(command: list[str], timeout: int = 30) -> bytes:
    return subprocess.run(
        command, check=True, capture_output=True,
        timeout=timeout).stdout


def inspect_mp4(file: Path, *, audio_required: bool = False) -> VisualEvidence:
    video = Path(file)
    if not video.is_file() or video.stat().st_size < 2000:
        raise ValueError("MP4 missing or implausibly small")
    raw = _run(["ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of", "json", str(video)])
    spec = json.loads(raw.decode("utf-8"))
    duration = float(spec["format"]["duration"])
    streams = spec.get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams):
        raise ValueError("File has no video stream")
    with TemporaryDirectory(prefix="kolbo-visual-qa-") as tmp:
        samples = []
        for i, sec in enumerate((0, duration * 0.5, duration * 0.85)):
            frame = Path(tmp) / f"{i}.png"
            _run(["ffmpeg", "-nostdin", "-v", "error", "-y",
                  "-ss", str(sec), "-i", str(video),
                  "-frames:v", "1", str(frame)])
            if not frame.is_file():
                raise ValueError("Unable to decode sampled video frame")
            with Image.open(frame) as img:
                samples.append(img.convert("RGB"))
        return assess_frames(*samples, duration_seconds=duration,
            audio_present=any(s.get("codec_type") == "audio" for s in streams),
            audio_required=audio_required)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--require-audio", action="store_true")
    args = parser.parse_args()
    print(json.dumps(inspect_mp4(args.video,
        audio_required=args.require_audio).as_dict(), indent=2))
