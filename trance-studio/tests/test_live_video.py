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

    def test_extended_hebrew_actions_are_grounded_not_guessed(self):
        cases={
            'החמור אוכל קש': 'donkey_eat',
            'הכלב רץ בחצר': 'dog_run',
            'הציפור עפה בשמיים': 'bird_fly',
            'התינוק בוכה בקול': 'baby_cry',
            'האיש צוחק בחוזקה': 'person_laugh',
            'האישה בוכה בקול': 'person_cry',
            'אני שר שיר': 'person_sing',
            'הטבח מבשל במטבח': 'person_cook',
        }
        for spoken, action in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(action_for_clause(spoken)['action'],action)
        self.assertIsNone(action_for_clause('אני מכין סרטון וידאו'))
        self.assertIsNone(action_for_clause('התינוק לא בוכה'))
        self.assertTrue(_matches_metadata('File:Bird flying over a lake.webm','bird flying'))
        self.assertTrue(_matches_metadata('File:Person laughs.webm','person laughing'))
        self.assertFalse(_matches_metadata('File:Dog walking.webm','dog running'))

    def test_actual_whisper_base_hebrew_errors_recover_only_grounded_motion(self):
        # Captured from a synthetic Hebrew speech -> actual OPUS -> Whisper
        # base CI run. Never substitute imagined words for the transcript.
        spoken='הכל אבנובח בחצר, המסעית נוסעת בקויש, הכל אבנובח שוב.'
        plan=visual_plan(spoken,40)
        self.assertEqual(plan['transcript'],spoken)
        self.assertEqual([s['action'] for s in plan['scenes']],['truck_drive'])
        self.assertEqual(plan['scenes'][0]['basis'],'asr_spelling_approximation')
        self.assertEqual(plan['visual_coverage'],'partial')
        self.assertGreater(plan['unmatched_clauses'],0)
        self.assertIsNone(action_for_clause('המסעית לא נוסעת'))
        self.assertIsNone(action_for_clause('משהו מוזר קורה לכולם'))

    def test_new_hebrew_subjects_split_into_independent_scenes(self):
        p=visual_plan('התינוק בוכה והאיש צוחק. הציפור עפה.',12)
        self.assertEqual([s['action'] for s in p['scenes']],
                         ['baby_cry','person_laugh','bird_fly'])
        self.assertEqual(p['visual_coverage'],'matched')

    def test_two_actions_in_same_original_sentence_are_separate(self):
        plan=visual_plan('החמור נוער והחקלאי מגיש לו קש.',12)
        self.assertEqual([scene['action'] for scene in plan['scenes']],
                         ['donkey_bray','farmer_feed'])
        self.assertEqual(plan['total_clauses'],2)
        self.assertEqual(plan['visual_coverage'],'matched')

    def test_two_explicit_actors_without_conjunction_prepared_as_two_scenes(self):
        plan=visual_plan('החמור נוער החקלאי מגיש לו קש',12)
        self.assertEqual(plan['total_clauses'],2)
        self.assertEqual([x['action'] for x in plan['scenes']],
                         ['donkey_bray','farmer_feed'])

    def test_story_preparation_uses_explicit_named_subject_when_no_verb(self):
        plan=visual_plan('פתאום ראיתי חמור ליד הכביש.',12)
        self.assertEqual(plan['visual_coverage'],'partial')
        self.assertEqual(plan['scenes'][0]['query'],'donkey')
        self.assertEqual(plan['scenes'][0]['basis'],'explicit_subject_only')
        self.assertEqual(plan['scenes'][0]['caption'],'')
        self.assertNotEqual(plan['scenes'][0]['action'],'donkey_bray')

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

    def test_real_action_footage_not_talk_about_the_action(self):
        # A prior live Wikimedia search matched an interview about self-driving
        # cars. This is NOT evidence that a car is driving in the clip.
        self.assertFalse(_matches_metadata(
            'File:Travis Kalanick on why we need self-driving cars.webm',
            'car driving'))
        self.assertFalse(_matches_metadata(
            'File:Interview with farmer feeding animals.webm',
            'farmer feeding animals'))
        self.assertTrue(_matches_metadata('File:Moving car on highway.webm','car moving'))
        self.assertTrue(_matches_metadata('File:Lorry driving on road.webm','lorry driving'))

    def test_action_media_search_expands_grounded_alternates(self):
        from unittest.mock import patch
        import live_video
        queries=[]
        def fake_api(params):
            q=params['gsrsearch']
            queries.append(q)
            return {'query': {'pages':[]}}
        with patch.object(live_video,'_json_api',side_effect=fake_api):
            self.assertEqual(live_video.commons_candidates('truck driving'),[])
        self.assertIn('filetype:video driving truck',queries)
        self.assertIn('filetype:video moving truck',queries)
        self.assertNotIn('filetype:video dancing people',queries)

    def test_preferred_small_official_video_source(self):
        item={'url':'https://upload.wikimedia.org/wikipedia/commons/b/b9/Maasai_people_singing_and_dancing.webm'}
        urls=list(_candidate_urls(item))
        self.assertEqual(len(urls),2)
        self.assertTrue(urls[0].endswith('Maasai_people_singing_and_dancing.webm.360p.vp9.webm'))
        self.assertEqual(urls[-1],item['url'])

    def test_named_subject_footage_after_exact_action_search_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            song=root/'mix.mp3'
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                            '-i','sine=frequency=290:duration=5',
                            '-c:a','libmp3lame',str(song)],check=True)
            plan=visual_plan('החמור נוער.',5)
            queries=[]
            def search(query):
                queries.append(query)
                if query=='donkey braying':return []
                if query=='donkey':
                    return [{'url':'https://upload.wikimedia.org/donkey.webm',
                             'page':'https://commons.wikimedia.org/wiki/File:Donkey.webm',
                             'license':'CC0'}]
                return []
            def download(item,dest):
                subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi',
                                '-i','testsrc=size=320x180:rate=12:duration=2',
                                '-c:v','libvpx-vp9',str(dest)],check=True,timeout=30)
            video=root/'film.mp4'
            sources=export_live_story(song,video,plan,root/'assets',
                                      search=search,download=download)
            self.assertEqual(queries,['donkey braying','donkey'])
            self.assertEqual(plan['visual_coverage'],'partial')
            self.assertEqual(plan['thematic_clips'],['donkey_bray'])
            self.assertEqual(sources[0]['match_level'],'explicit_subject_only')
            self.assertGreater(video.stat().st_size,12000)

    def test_ambiguous_clause_never_blocks_later_clear_action(self):
        plan=visual_plan('חמור נוער כלב נובח. אני נוסע באוטו.',16)
        self.assertEqual(plan['visual_coverage'],'partial')
        self.assertEqual(plan['scenes'][-1]['action'],'car_drive')
        self.assertIn('חמור נוער',plan['transcript'])
        self.assertGreaterEqual(plan['unmatched_clauses'],1)

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
                if query in ('donkey braying','donkey'):return []
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
            self.assertEqual(queries,['donkey braying','donkey','car driving'])
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

    def test_exact_footage_rejects_unrelated_traumatic_clip(self):
        self.assertFalse(_matches_metadata(
            'File:Terrorists fire into moving civilian car during attacks.webm',
            'car driving'))
        self.assertTrue(_matches_metadata(
            'File:Porto Santo from a moving car.webm',
            'car driving'))

    def test_two_independent_real_motion_scenes_normalized_to_android_h264(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            song=root/'song.mp3'
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y',
                            '-f','lavfi','-i','sine=frequency=440:duration=6',
                            '-c:a','libmp3lame',str(song)],check=True)
            plan=visual_plan('הכלב נובח. החמור נוער.',6.0)
            def search(query):
                return [{
                    'url':'https://upload.wikimedia.org/example.webm',
                    'title':'File:Test authentic motion.webm',
                    'page':'https://commons.wikimedia.org/wiki/File:Test.webm',
                    'license':'CC0'}]
            def download(item,dest):
                # Deliberately different original codecs, shapes and frame
                # rates. Old concat stream-copy silently corrupted scene 2.
                freq=11 if 'source-0' in str(dest) else 19
                width,height=(640,360) if freq==11 else (320,240)
                codec='libvpx-vp9' if freq==11 else 'libx264'
                subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y',
                    '-f','lavfi','-i',f'testsrc=size={width}x{height}:rate={freq}:duration=3',
                    '-c:v',codec,'-b:v','160k',str(dest)],check=True,timeout=35)
            output=root/'movie.mp4'
            sources=export_live_story(song,output,plan,root/'assets',
                                      search=search,download=download)
            self.assertEqual(len(sources),2)
            probe=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format','-of','json',
                str(output)]))
            video=next(s for s in probe['streams'] if s['codec_type']=='video')
            self.assertEqual(video['codec_name'],'h264')
            self.assertEqual((video['width'],video['height']),(360,640))
            self.assertEqual({s['codec_type'] for s in probe['streams']},
                             {'video','audio'})
            self.assertGreater(float(probe['format']['duration']),5.5)
            # Decode frames past the second-scene boundary, not just metadata.
            decoded=subprocess.check_output([
                'ffmpeg','-v','error','-ss','4','-i',str(output),
                '-frames:v','1','-f','rawvideo','-pix_fmt','gray','pipe:1'])
            self.assertEqual(len(decoded),360*640)

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
            self.assertEqual(codec['codec_name'],'h264')
            self.assertEqual(codec['width'],360)
            self.assertEqual(codec['height'],640)
            # No subtitle stream or text filter in produced video.
            self.assertNotIn('subtitle',types)

if __name__=='__main__':unittest.main()
