"""An AI-video MP4 must contain genuine moving frames, not a static slide."""
import pathlib
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from motion_quality import motion_score,require_visible_motion,NoVisibleMotion


class MotionQualityTests(unittest.TestCase):
    def _video(self,folder,source,name):
        out=pathlib.Path(folder)/name
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                        "-f","lavfi","-i",source,
                        "-t","2","-c:v","libx264","-pix_fmt","yuv420p",
                        str(out)],check=True,timeout=30)
        return out

    def test_static_slide_mp4_is_rejected_even_if_codec_duration_are_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self._video(temp,"color=c=black:s=320x240:r=15","still.mp4")
            self.assertEqual(motion_score(p),0)
            with self.assertRaises(NoVisibleMotion):
                require_visible_motion(p)

    def test_real_moving_frames_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            p=self._video(temp,"testsrc=size=320x240:rate=15","motion.mp4")
            self.assertGreater(motion_score(p),0.3)
            self.assertGreater(require_visible_motion(p),0.3)

    def test_audio_file_does_not_masquerade_as_moving_video(self):
        with tempfile.TemporaryDirectory() as temp:
            fake=pathlib.Path(temp)/'fake.mp4'
            fake.write_bytes(b'not a real movie')
            with self.assertRaises(NoVisibleMotion):
                require_visible_motion(fake)


if __name__=='__main__':
    unittest.main()
