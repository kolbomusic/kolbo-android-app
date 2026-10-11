"""Advisory image QA: deterministic tests, no GPU or external provider requests."""
from PIL import Image, ImageDraw, ImageFilter
import pytest
from visual_quality import assess_frames


def rocket(x: int = 0):
    img = Image.new("RGB", (640, 640), (125, 185, 230))
    draw = ImageDraw.Draw(img)
    draw.polygon([(315+x, 140), (390+x, 400), (315+x, 365),
                  (230+x, 400)], fill=(244, 176, 27))
    draw.ellipse((292+x, 243, 339+x, 291), fill="white")
    return img


def test_blurred_provider_output_cannot_be_marked_approved():
    reference = rocket()
    blurry = rocket(5).filter(ImageFilter.GaussianBlur(9))
    report = assess_frames(reference, rocket(2), blurry,
        duration_seconds=1.31, audio_present=False)
    assert report.verdict == "needs_review"
    assert "detail_loss_detected" in report.warnings
    assert "scene_semantics_not_verified" in report.warnings
    assert report.detail_retention_ratio < 0.75


def test_static_video_does_not_count_as_verified_motion():
    image = rocket()
    report = assess_frames(image, image, image,
        duration_seconds=1, audio_present=False)
    assert "weak_visual_motion_evidence" in report.warnings
    assert report.pixel_change_fraction == 0


def test_audio_required_missing_must_reject():
    image = rocket()
    report = assess_frames(image, image, image,
        duration_seconds=1, audio_present=False, audio_required=True)
    assert report.verdict == "reject"
    assert "missing_required_audio" in report.warnings


def test_strong_motion_is_still_not_automatic_semantic_approval():
    report = assess_frames(rocket(-60), rocket(0), rocket(60),
        duration_seconds=1, audio_present=True, audio_required=True)
    assert report.verdict == "needs_review"
    assert "scene_semantics_not_verified" in report.warnings


def test_invalid_sample_sizes_are_rejected():
    with pytest.raises(ValueError, match="dimensions"):
        assess_frames(rocket(), rocket(), Image.new("RGB", (32, 32)),
            duration_seconds=1, audio_present=False)
