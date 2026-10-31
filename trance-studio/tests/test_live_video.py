"""No misleading captions/cartoons: verify grounded action footage and strict fallback."""
import io
import json
import math
import pathlib
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from live_video import (
    action_for_clause,visual_plan,UnavailableVideo,export_live_story,
    _matches_metadata, _valid_license
)

class GroundedVideoTests(unittest.TestCase):
    def test_no_love_from_levo(self):
        self.assertIsNone(action_for_clause('אני לא נקבו שיש לבוא'))
        self.assertIsNone(action_for_clause('יש לבוא מחר'))

    def test_recognize_action_and_hebrew_prefixes(self):
        self.assertEqual(action_for_clause('החמור נוער').get('action'),'donkey_bray')
        self.assertEqual(action_for_clause('אני נוסע באוטו').get('action'),'car_drive')
        self.assertEqual(action_for_clause('הלכתי לים').get('action'),'beach_walk')
        self.assertEqual(action_for_clause('אכלתי פיצה').get('action'),'pizza_eat')

    def test_negated_action_not_shown_as_happening(self):
        self.assertIsNone(action_for_clause('לא נסעתי באוטו'))
        self.assertIsNone(action_for_clause('בלי לראות את הים'))

    def test_grounded_plan_has_no_subtitles(self):
        plan=visual_plan('אני נוסע באוטו. אחר כך הלכתי לים.',8)
        self.assertEqual([x['action'] for x in plan['scenes']],['car_drive','beach_walk'])
        self.assertTrue(all(x['caption']=='' for x in plan['scenes']))
        self.assertEqual(plan['scenes'][-1]['end'],8.)

    def test_unsupported_scene_rejected_not_replaced_with_dancing(self):
        with self.assertRaises(UnavailableVideo):
            visual_plan('אני לא יודע איך להסביר מה קרה.',20)
        with self.assertRaises(UnavailableVideo):
            visual_plan('אני נוסע באוטו. אחר כך משהו מסתורי קרה.',20)

    def test_strict_license_and_descriptive_title(self):
        self.assertFalse(_matches_metadata('File:Car driving.webm','donkey braying'))
        self.assertTrue(_matches_metadata('File:Donkey braying.webm','donkey braying'))
        self.assertFalse(_valid_license({'LicenseShortName':{'value':'CC BY-NC'}}))
        self.assertTrue(_valid_license({'LicenseShortName':{'value':'CC0'}}))

    def test_native_motion_video_and_original_audio_without_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            sound=root/'mix.mp3'
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i',
                            'sine=frequency=240:duration=3.6','-c:a','libmp3lame',
                            str(sound)],check=True)
            plan=visual_plan('החמור נוער.',3.6)
            def find(query):
                return [{'url':'https://upload.wikimedia.org/example.webm',
                         'title':'File:Donkey braying.webm','bytes':100000,
                         'license':'CC0','page':'https://commons.wikimedia.org/wiki/File:Donkey_braying.webm'}]
            def download(item,dest):
                subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                               '-i','testsrc=size=640x360:rate=15:duration=5',
                               '-c:v','libvpx','-b:v','170k',str(dest)],check=True,
                               timeout=35)
            out=root/'story.mp4'
            sources=export_live_story(sound,out,plan,root/'scenes',search=find,download=download)
            self.assertEqual(len(sources),1)
            self.assertGreater(out.stat().st_size,16000)
            streams=json.loads(subprocess.check_output(
                ['ffprobe','-v','quiet','-show_streams','-of','json',str(out)]))
            types={x['codec_type'] for x in streams['streams']}
            self.assertEqual(types,{'audio','video'})
            codec=[x for x in streams['streams'] if x['codec_type']=='video'][0]
            self.assertEqual(codec['width'],480)
            self.assertEqual(codec['height'],854)
            # No subtitle stream or text filter in produced video.
            self.assertNotIn('subtitle',types)

if __name__=='__main__':unittest.main()
