"""Audio-sync and visible-edit regression tests for user's REAL WhatsApp video."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from beat_video_editor import edit_decisions, compose_edited_original_video


class BeatVideoEditTests(unittest.TestCase):
    def test_timeline_has_real_musical_cuts_and_multiple_shot_styles(self):
        bpm=145
        decisions=edit_decisions(30,bpm,9.0,'כולם צוחקים ואז האיש נפל')
        self.assertGreaterEqual(len(decisions),4)
        self.assertLessEqual(len(decisions),8)
        self.assertAlmostEqual(sum(x['duration'] for x in decisions),30,delta=.05)
        self.assertGreater(len(set(x['zoom'] for x in decisions)),2)
        self.assertGreater(len(set(x['speed'] for x in decisions)),2)
        self.assertTrue(all(x['duration']>.1 for x in decisions))
        self.assertTrue(all(.8<=x['speed']<=1.2 for x in decisions))
        # Cuts before the final one should align to bar boundaries.
        bar=240./bpm
        for x in decisions[:-1]:
            end=x['start']+x['duration']
            self.assertLess(abs(end/bar-round(end/bar)),.02)

    def test_real_mp4_contains_multiple_edited_shots_and_original_mix(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            source=root/'whatsapp-original.mp4'
            music=root/'trance.mp3'
            out=root/'edited-story.mp4'
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','testsrc2=size=360x640:rate=12:duration=4',
                '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
                str(source)],check=True,timeout=25)
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','sine=frequency=250:duration=9',
                '-c:a','libmp3lame',str(music)],check=True,timeout=25)
            meta=compose_edited_original_video(source,music,out,root/'work',
                                                 bpm=145,transcript_hint='החמור נוער ובום')
            self.assertEqual(meta['video_edit_style'],
                             'beat_cut_punch_in_speed_ramp')
            self.assertGreaterEqual(meta['video_edit_shots'],3)
            self.assertGreater(out.stat().st_size,20000)
            probe=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(out)],timeout=20))
            tracks={x['codec_type']:x for x in probe['streams']}
            self.assertEqual(set(tracks),{'audio','video'})
            self.assertEqual((tracks['video']['codec_name'],
                              tracks['video']['width'],tracks['video']['height']),
                             ('h264',360,640))
            self.assertGreater(float(probe['format']['duration']),8.5)
            self.assertLess(float(probe['format']['duration']),10.)
            # Decode two shots and show that the generated output was
            # actually spatially reframed, rather than just audio dubbed.
            def frame(movie,seconds):
                return subprocess.check_output([
                    'ffmpeg','-nostdin','-v','error','-ss',str(seconds),
                    '-i',str(movie),'-frames:v','1',
                    '-vf','scale=40:64,format=gray','-f','rawvideo','-'],
                    timeout=15)
            first=frame(out,.6)
            second=frame(out,3.)
            self.assertEqual(len(first),40*64)
            self.assertEqual(len(second),40*64)
            change=sum(abs(x-y) for x,y in zip(first,second))/len(first)
            self.assertGreater(change,1.6)


if __name__=='__main__':unittest.main()
