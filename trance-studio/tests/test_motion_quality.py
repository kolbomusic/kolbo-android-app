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

    def test_54_second_whatsapp_movie_with_real_motion_only_after_46_seconds(self):
        # User-visible regression: four old probes stopped at 18 seconds
        # and mislabelled an authentic long WhatsApp movie as static.
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/'long-still-intro-real-motion.mp4'
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i',
                'color=c=black:s=320x240:r=12:d=46',
                '-f','lavfi','-i',
                'testsrc2=size=320x240:rate=12:duration=8',
                '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                '-map','[v]','-c:v','libx264','-preset','ultrafast',
                '-pix_fmt','yuv420p',str(path),
            ],check=True,timeout=45)
            from motion_quality import require_visible_motion_somewhere
            self.assertLess(motion_score(path,start_seconds=15),.15)
            self.assertGreater(motion_score(path,start_seconds=49),.15)
            self.assertGreater(
                require_visible_motion_somewhere(path,duration=54,threshold=.15),
                .15)

    def test_54_second_entirely_static_movie_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)/'54-seconds-frozen.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','color=c=black:s=320x240:r=12:d=54',
                '-c:v','libx264','-preset','ultrafast',
                '-pix_fmt','yuv420p',str(path)],check=True,timeout=40)
            from motion_quality import require_visible_motion_somewhere
            with self.assertRaises(NoVisibleMotion):
                require_visible_motion_somewhere(path,duration=54,threshold=.15)

    def test_audio_file_does_not_masquerade_as_moving_video(self):
        with tempfile.TemporaryDirectory() as temp:
            fake=pathlib.Path(temp)/'fake.mp4'
            fake.write_bytes(b'not a real movie')
            with self.assertRaises(NoVisibleMotion):
                require_visible_motion(fake)


if __name__=='__main__':
    unittest.main()
