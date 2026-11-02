"""Original AI video must never stretch a short moving clip to fake duration."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from live_video import _make_segment,UnavailableVideo
from client_ai_fallback import combine_mobile_ai_clips,MobileClipError

def media(dest,source,seconds):
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
        '-i',f'{source}=size=256x256:rate=12:duration={seconds}',
        '-c:v','libx264','-pix_fmt','yuv420p',
        '-preset','ultrafast',str(dest)],check=True,timeout=30)

class AIUniqueScenes(unittest.TestCase):
    def test_reject_one_second_motion_stretched_to_long_mixed_video(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            clip=root/'scene.mp4';media(clip,'testsrc',1.5)
            output=root/'forbidden.mp4'
            with self.assertRaises(UnavailableVideo):
                _make_segment(clip,output,12,allow_loop=False)
            self.assertFalse(output.exists())
            soundtrack=root/'mix.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','sine=frequency=400:duration=12','-c:a','libmp3lame',
                str(soundtrack)],check=True)
            with self.assertRaisesRegex(MobileClipError,'מספיק וידאו'):
                combine_mobile_ai_clips([clip],soundtrack,root/'out.mp4',
                                         root/'work')

    def test_reject_identical_generated_clips_even_when_named_differently(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=root/'a.mp4';b=root/'b.mp4'
            media(a,'testsrc2',4)
            b.write_bytes(a.read_bytes())
            audio=root/'mix.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','sine=frequency=300:duration=6','-c:a','libmp3lame',
                str(audio)],check=True)
            with self.assertRaisesRegex(MobileClipError,'אותה סצנה'):
                combine_mobile_ai_clips([a,b],audio,root/'out.mp4',root/'work')

if __name__=='__main__':unittest.main()
