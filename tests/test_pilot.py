from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from pilots.kolbo_grid_28_pilot import run

class PilotTest(TestCase):
    def test_no_remote_upload_without_consent(self):
        with TemporaryDirectory() as tmp:
            r=run(Path(tmp),'live',8,False)
            self.assertEqual(r['status'],'BLOCKED')
            self.assertEqual(r['reason_code'],'PUBLIC_HF_UPLOAD_OPT_IN_REQUIRED')
            self.assertFalse(r['third_party_media_uploaded'])

    def test_reject_unsupported_duration(self):
        with TemporaryDirectory() as tmp:
            r=run(Path(tmp),'fixture',7,False)
            self.assertEqual(r['status'],'BLOCKED')
            self.assertEqual(r['reason_code'],'UNSUPPORTED_DURATION')

    def test_real_motion_sync_and_audible_output(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            r=run(folder,'fixture',8,False)
            self.assertEqual(r['status'],'PASS',str(r))
            self.assertAlmostEqual(r['qa']['duration_seconds'],8,delta=.25)
            self.assertTrue(r['qa']['audio_ok'])
            self.assertTrue(r['qa']['motion_verified'])
            self.assertGreaterEqual(r['foley_events'],2)
            self.assertTrue((folder/'kolbo-pilot.mp4').is_file())
            self.assertFalse(r['ai_visual_generation_verified'])
            self.assertFalse(r['native_ai_audio_verified'])
            self.assertFalse(r['semantic_prompt_fidelity_verified'])