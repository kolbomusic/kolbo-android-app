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
    _matches_metadata, _valid_license, _candidate_urls
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

    def test_two_actions_in_same_original_sentence_are_separate(self):
        plan=visual_plan('החמור נוער והחקלאי מגיש לו קש.',12)
        self.assertEqual([scene['action'] for scene in plan['scenes']],
                         ['donkey_bray','farmer_feed'])
        self.assertEqual(plan['total_clauses'],2)
        self.assertEqual(plan['visual_coverage'],'matched')

    def test_ambiguous_multi_action_without_clear_boundary_is_not_fabricated(self):
        with self.assertRaises(UnavailableVideo):
            visual_plan('החמור נוער החקלאי מגיש לו קש',12)

    def test_negated_action_not_shown_as_happening(self):
        self.assertIsNone(action_for_clause('לא נסעתי באוטו'))
        self.assertIsNone(action_for_clause('בלי לראות את הים'))

    def test_grounded_plan_has_no_subtitles(self):
        plan=visual_plan('אני נוסע באוטו. אחר כך הלכתי לים.',8)
        self.assertEqual([x['action'] for x in plan['scenes']],['car_drive','beach_walk'])
        self.assertTrue(all(x['caption']=='' for x in plan['scenes']))
        self.assertEqual(plan['scenes'][-1]['end'],8.)

    def test_unknown_transcript_never_invents_waveform_or_story(self):
        with self.assertRaises(UnavailableVideo) as error:
            visual_plan('אני לא יודע איך להסביר מה קרה.',20)
        self.assertIn('וידאו מצולם',str(error.exception))

    def test_unknown_clauses_do_not_abort_known_action_video(self):
        plan=visual_plan('אני נוסע באוטו. אחר כך משהו מסתורי קרה.',20)
        self.assertEqual(len(plan['scenes']),1)
        self.assertEqual(plan['scenes'][0]['action'],'car_drive')
        self.assertEqual(plan['scenes'][0]['end'],20)
        self.assertEqual(plan['unmatched_clauses'],1)
        self.assertEqual(plan['visual_coverage'],'partial')
        self.assertIn('משהו מסתורי',plan['scenes'][0]['spoken'])

    def test_long_recording_more_than_five_events_is_supported(self):
        transcript='.'.join([
            'החמור נוער','אני נוסע באוטו','הלכתי לים',
            'אכלתי פיצה','גשם יורד','כולם רוקדים במסיבה',
            'החמור נוער','אני נוסע באוטו'])+'.'
        plan=visual_plan(transcript,49)
        self.assertEqual(plan['total_clauses'],8)
        self.assertEqual(plan['recognized_action_beats'],8)
        self.assertEqual(len(plan['scenes']),8)
        self.assertEqual(plan['scenes'][0]['action'],'donkey_bray')
        self.assertEqual(plan['scenes'][-1]['action'],'car_drive')
        self.assertAlmostEqual(plan['scenes'][-1]['end'],49)
        self.assertEqual(plan['transcript'],transcript)
        self.assertTrue(all(s['end']>s['start'] for s in plan['scenes']))

    def test_many_events_are_bounded_without_rejecting_entire_story(self):
        transcript='.'.join(['החמור נוער' if i%2==0 else 'אני נוסע באוטו'
                              for i in range(36)])
        plan=visual_plan(transcript,120)
        self.assertEqual(plan['total_clauses'],36)
        self.assertEqual(plan['recognized_action_beats'],36)
        self.assertEqual(plan['visual_beats'],18)
        self.assertEqual(plan['visual_coverage'],'partial')
        self.assertEqual(plan['transcript'],transcript)
        self.assertAlmostEqual(plan['scenes'][-1]['end'],120)
        self.assertTrue(all(s['end']>s['start'] for s in plan['scenes']))

    def test_repeated_media_query_downloaded_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            audio=root/'mix.mp3'
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                            '-i','sine=frequency=240:duration=3.6',
                            '-c:a','libmp3lame',str(audio)],check=True)
            plan=visual_plan('החמור נוער. אני נוסע באוטו. החמור נוער.',3.6)
            counts={'search':0,'download':0}
            def find(query):
                counts['search']+=1
                return [{'url':'https://upload.wikimedia.org/example.webm',
                         'title':'File:Example.webm','bytes':100000,'license':'CC0',
                         'page':'https://commons.wikimedia.org/wiki/File:Example.webm'}]
            def download(item,dest):
                counts['download']+=1
                subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                                '-i','testsrc=size=320x180:rate=15:duration=4',
                                '-c:v','libvpx-vp9','-b:v','100k',str(dest)],
                               check=True,timeout=25)
            out=root/'story.mp4'
            sources=export_live_story(audio,out,plan,root/'assets',search=find,download=download)
            self.assertEqual(len(sources),3)
            self.assertEqual(counts['search'],2)
            self.assertEqual(counts['download'],2)
            self.assertGreater(out.stat().st_size,10000)

    def test_strict_license_and_descriptive_title(self):
        self.assertFalse(_matches_metadata('File:Car driving.webm','donkey braying'))
        self.assertTrue(_matches_metadata('File:Donkey braying.webm','donkey braying'))
        self.assertTrue(_matches_metadata('File:Braying donkey (Equus africanus asinus).webm','donkey braying'))
        self.assertFalse(_matches_metadata('File:Donkey walking.webm','donkey braying'))
        self.assertFalse(_valid_license({'LicenseShortName':{'value':'CC BY-NC'}}))
        self.assertTrue(_valid_license({'LicenseShortName':{'value':'CC0'}}))
        self.assertTrue(_valid_license({'LicenseShortName':{'value':'CC BY-SA 2.0'}}))

    def test_preferred_small_official_video_source(self):
        item={'url':'https://upload.wikimedia.org/wikipedia/commons/b/b9/Maasai_people_singing_and_dancing.webm'}
        urls=list(_candidate_urls(item))
        self.assertEqual(len(urls),2)
        self.assertTrue(urls[0].endswith('Maasai_people_singing_and_dancing.webm.360p.vp9.webm'))
        self.assertEqual(urls[-1],item['url'])

    def test_prepare_every_scene_and_export_partial_video_with_full_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            song=root/'mix.mp3'
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                            '-i','sine=frequency=290:duration=8',
                            '-c:a','libmp3lame',str(song)],check=True)
            plan=visual_plan('החמור נוער. אחר כך אני נוסע באוטו.',8)
            queries=[]
            def find(query):
                queries.append(query)
                if query=='donkey braying':return []
                return [{'url':'https://upload.wikimedia.org/test.webm',
                         'page':'https://commons.wikimedia.org/wiki/File:Car_driving.webm',
                         'license':'CC0'}]
            def download(item,dest):
                subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                                '-i','testsrc=size=320x180:rate=12:duration=2',
                                '-c:v','libvpx-vp9',str(dest)],
                               check=True,timeout=30)
            video=root/'film.mp4'
            sources=export_live_story(song,video,plan,root/'work',
                                      search=find,download=download)
            self.assertEqual(queries,['donkey braying','car driving'])
            self.assertEqual(len(sources),1)
            self.assertEqual(plan['visual_coverage'],'partial')
            self.assertEqual(len(plan['missing_footage']),1)
            data=json.loads(subprocess.check_output(['ffprobe','-v','error',
                 '-show_format','-show_streams','-of','json',str(video)]))
            self.assertGreater(float(data['format']['duration']),7.2)
            self.assertEqual({x['codec_type'] for x in data['streams']},
                             {'audio','video'})

    def test_eight_speech_events_export_49_seconds_of_actual_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            sound=root/'voice.mp3'
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                            '-i','sine=frequency=235:duration=49',
                            '-c:a','libmp3lame','-q:a','8',str(sound)],check=True)
            clauses=['החמור נוער' if i%2==0 else 'אני נוסע באוטו'
                     for i in range(8)]
            plan=visual_plan('. '.join(clauses),49.)
            calls=[]
            def search(query):
                calls.append(query)
                return [{'url':'https://upload.wikimedia.org/example.webm',
                         'title':'File:Verified action.webm','license':'CC0',
                         'page':'https://commons.wikimedia.org/wiki/File:Verified_action.webm'}]
            def download(item,dest):
                subprocess.run(['ffmpeg','-loglevel','error','-y',
                                '-f','lavfi','-i','testsrc=size=320x180:rate=15:duration=3',
                                '-c:v','libvpx-vp9','-b:v','180k',str(dest)],
                               check=True,timeout=30)
            out=root/'eight-scenes.mp4'
            sources=export_live_story(sound,out,plan,root/'media',search=search,download=download)
            self.assertEqual(len(sources),8)
            self.assertEqual(len(calls),2)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet',
                                '-show_format','-show_streams','-of','json',str(out)]))
            self.assertGreater(float(probe['format']['duration']),45.)
            self.assertLess(float(probe['format']['duration']),51.)
            self.assertEqual({x['codec_type'] for x in probe['streams']},
                             {'audio','video'})

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
                               '-c:v','libvpx-vp9','-b:v','170k',str(dest)],check=True,
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
            self.assertEqual(codec['width'],640)
            self.assertEqual(codec['height'],360)
            # No subtitle stream or text filter in produced video.
            self.assertNotIn('subtitle',types)

if __name__=='__main__':unittest.main()
