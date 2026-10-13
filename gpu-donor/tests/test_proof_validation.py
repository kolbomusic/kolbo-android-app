"""Offline decoder regression tests; no AI claims, network or private media."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from proof_validation import inspect_local_receipt
from admission_gate import inspect_receipt,inspect_donor

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
class MediaProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make(self, static=False, silent=False, no_audio=False):
        source = "color=c=blue:size=160x90:rate=12" if static else "testsrc2=size=160x90:rate=12"
        args = ["ffmpeg","-y","-v","error","-f","lavfi","-i",source]
        if not no_audio:
            args += ["-f","lavfi","-i","sine=frequency=660:sample_rate=16000"]
            if silent:
                args += ["-af","volume=0"]
        args += ["-t","2.5","-c:v","mpeg4","-q:v","4"]
        if not no_audio:
            args += ["-c:a","aac","-b:a","64k","-shortest"]
        args += [str(self.root/"synthetic-proof.mp4")]
        subprocess.run(args,check=True,timeout=20)
        media=self.root/"synthetic-proof.mp4"
        receipt=self.root/"receipt.json"
        receipt.write_text(json.dumps({"schema_version":2,"media_file":"synthetic-proof.mp4",
                                       "sha256":hashlib.sha256(media.read_bytes()).hexdigest()}))
        return receipt

    def test_moving_nonsilent_video_detected_but_gpu_never_claimed(self):
        proof=inspect_local_receipt(self.make())
        self.assertTrue(proof["verified"],proof)
        self.assertTrue(proof["audio_signal_detected"])
        self.assertGreaterEqual(proof["moving_intervals"],2)
        self.assertFalse(proof["gpu_origin_attested"])
        self.assertFalse(proof["ai_origin_attested"])

    def test_static_frames_rejected(self):
        self.assertFalse(inspect_receipt(self.make(static=True)))

    def test_missing_audio_rejected(self):
        self.assertFalse(inspect_receipt(self.make(no_audio=True)))

    def test_silent_audio_rejected(self):
        self.assertFalse(inspect_receipt(self.make(silent=True)))

    def test_tampered_hash_rejected(self):
        r=self.make()
        o=json.loads(r.read_text())
        o["sha256"]="0"*64
        r.write_text(json.dumps(o))
        self.assertFalse(inspect_receipt(r))

    def test_directory_traversal_rejected(self):
        r=self.make()
        o=json.loads(r.read_text())
        o["media_file"]="../../private.mp4"
        r.write_text(json.dumps(o))
        self.assertFalse(inspect_receipt(r))

    def test_local_media_never_registers_worker(self):
        r=self.make()
        for k in (0,1):
            nodes={"1":{"class_type":"CLIPTextEncode","inputs":{"text":"__KOLBO_PROMPT__"}},
                   "2":{"class_type":"Frames","inputs":{"count":"__KOLBO_FRAMES__"}}}
            if k==1:
                nodes["3"]={"class_type":"LoadImage","inputs":{"image":"__KOLBO_IMAGE1__"}}
            (self.root/f"workflow_{k}_images.json").write_text(json.dumps(nodes))
        report=inspect_donor(hardware_report={"eligible_for_operator_review":True},workflows=self.root,receipt=r)
        self.assertTrue(report["synthetic_local_proof"])
        self.assertTrue(report["eligible_for_independent_review"])
        self.assertFalse(report["owner_approved"])
        self.assertFalse(report["registered_worker"])
        self.assertFalse(report["gpu_inference_verified"])
        self.assertFalse(report["allowed_to_receive_private_media"])

if __name__=="__main__":
    unittest.main()
