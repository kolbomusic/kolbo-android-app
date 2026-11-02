"""Actual Android emulator screenshot acceptance: fail on black/blank UI."""
import sys
from collections import Counter
from pathlib import Path

from PIL import Image


def inspect(image_path):
    path = Path(image_path)
    if not path.is_file() or path.stat().st_size < 1000:
        raise AssertionError("No real Android screenshot was produced")
    image = Image.open(path).convert("RGB")
    width, height = image.size
    if min(width, height) < 320:
        raise AssertionError("Emulator screenshot is unexpectedly small")
    area = image.crop((width // 12, height // 8, 11 * width // 12,
                       7 * height // 8)).resize((96, 96))
    colors = Counter(area.getdata())
    visual = sum(n for (r, g, b), n in colors.items()
                 if max(r, g, b) > 70)
    if visual < 120:
        raise AssertionError(f"Black/empty app screen: visible pixels={visual}")
    if len(colors) < 18:
        raise AssertionError(f"Blank solid-color app: colors={len(colors)}")
    print("REAL_ANDROID_EMULATOR_VISIBLE_STARTUP_PASS",
          image.size, visual, len(colors))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: inspect_android_launch.py screenshot.png")
    inspect(sys.argv[1])
