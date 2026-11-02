"""Prevent stale displayed Android installer labels in Kolbo Trance builds."""
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android" / "app"

class AndroidReleaseIdentityTests(unittest.TestCase):
    def test_app_label_matches_android_version_name(self):
        gradle = (ANDROID / "build.gradle").read_text(encoding="utf-8")
        match = re.search(r"\bversionName\s+'([^']+)'", gradle)
        self.assertIsNotNone(match, "Missing versionName in Android Gradle config")
        version = re.match(r"\d+\.\d+\.\d+", match.group(1))
        self.assertIsNotNone(version, "Unsupported Android versionName")
        resources = ElementTree.parse(ANDROID / "src/main/res/values/strings.xml")
        labels = [node.text or "" for node in resources.iter("string")
                  if node.attrib.get("name") == "app_name"]
        self.assertEqual(len(labels), 1, "Android must have one app_name resource")
        self.assertTrue(labels[0].rstrip().endswith(version.group(0)),
                        f"Android installer label {labels[0]!r} is not version {version.group(0)}")

if __name__ == "__main__":
    unittest.main()
