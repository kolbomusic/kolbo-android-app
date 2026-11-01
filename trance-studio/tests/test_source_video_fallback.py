"""Verify MP4 fallback uses only the user's genuine moving video input."""
import json, pathlib, subprocess, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from source_video_fallback import compose_original_video_with_mix
from live_video import UnavailableVideo

class OriginalMovingVideoTests(unittest.TestCase):
    def make_music(self,path):
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                        '-i','sine=frequency=283:duration=5',
                        '-c:a','libmp3lame',str(path)],check=True,timeout=20)

    def test_original_video_and_remixed_audio_generate_real_mp4(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);original=root/'shared.mp4'
            music=root/'mix.mp3';result=root/'story.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                            '-f','lavfi','-i','testsrc=size=320x240:rate=12:duration=3',
                            '-c:v','libx264','-pix_fmt','yuv420p',str(original)],
                           check=True,timeout=25)
            self.make_music(music)
            meta=compose_original_video_with_mix([original],music,result,root/'work')
            self.assertEqual(meta['video_status'],'done')
            self.assertEqual(meta['visual_coverage'],'original_video_not_scene_generated')
            streams=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(result)]))
            self.assertEqual({s['codec_type'] for s in streams['streams']},
                             {'video','audio'})
            self.assertGreater(float(streams['format']['duration']),4.7)
            video=next(s for s in streams['streams'] if s['codec_type']=='video')
            self.assertEqual((video['codec_name'],video['width'],video['height']),
                             ('h264',360,640))
            self.assertGreater(result.stat().st_size,15000)

    def test_audio_only_does_not_invent_a_real_world_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);music=root/'mix.mp3'
            self.make_music(music)
            with self.assertRaises(UnavailableVideo):
                compose_original_video_with_mix([music],music,root/'out.mp4',
                                                root/'work')

    def test_static_mp4_rejected_as_not_real_moving_footage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);music=root/'mix.mp3'
            original=root/'still.mp4'
            self.make_music(music)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                            '-i','color=c=black:size=320x240:rate=12:duration=3',
                            '-c:v','libx264','-pix_fmt','yuv420p',str(original)],
                           check=True,timeout=25)
            with self.assertRaises(UnavailableVideo):
                compose_original_video_with_mix([original],music,root/'out.mp4',
                                                root/'work')

if __name__=='__main__':unittest.main()
