"""The optional public AI video mode must be truthful, opt-in, and safe."""
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from ai_video import (
    AIVideoUnavailable, _video_result_url, cinematic_prompt,
    _request_video_generation, _request_ltx25_generation, generate_ai_story, _narrative_shots,
)


class AIVideoTests(unittest.TestCase):
    def test_prompt_uses_actual_hebrew_narration_not_predefined_donkey_story(self):
        s='הכלב נובח. המשאית נוסעת בכביש.'
        prompt=cinematic_prompt(s)
        self.assertIn(s,prompt)
        self.assertIn('dog barking',prompt)
        self.assertIn('truck driving',prompt)
        self.assertIn('No written words',prompt)
        with self.assertRaises(AIVideoUnavailable):
            cinematic_prompt('Hello world')

    def test_gradio_public_failure_classifies_quota_and_hides_input(self):
        from ai_video import _public_provider_error, _public_http_error
        import urllib.error
        secret='user-private-phrase-123'
        for raw in (
            json.dumps({'error':'You have exceeded your GPU quota. '+secret}),
            json.dumps({'message':'GPU time limit reached '+secret}),
            json.dumps({'detail':'ZeroGPU quota exceeded '+secret}),
        ):
            issue=_public_provider_error(raw)
            self.assertIsInstance(issue,AIVideoUnavailable)
            self.assertIn('GPU',str(issue))
            self.assertNotIn(secret,str(issue))
        self.assertIn('עמוס',str(_public_provider_error(
            json.dumps({'error':'GPU capacity busy '+secret}))))
        self.assertNotIn(secret,str(_public_provider_error(
            json.dumps({'message':'unhandled exception '+secret}))))
        self.assertIn('429',str(_public_http_error(
            urllib.error.HTTPError('https://x',429,'',{},None))))
        self.assertIn('הרשאה',str(_public_http_error(
            urllib.error.HTTPError('https://x',403,'',{},None))))

    def test_gradio_video_url_requires_exact_public_https_host(self):
        u='https://lightricks-ltx-video-distilled.hf.space/gradio_api/file=/tmp/gradio/a/clip.mp4'
        data=[{'video':{'path':'/tmp/gradio/a/clip.mp4','url':u}},42]
        self.assertEqual(_video_result_url(data),u)
        for bad in ('http://lightricks-ltx-video-distilled.hf.space/gradio_api/file=x',
                    'https://localhost/gradio_api/file=x',
                    'https://lightricks-ltx-video-distilled.hf.space.evil.org/gradio_api/file=x',
                    'https://lightricks-ltx-video-distilled.hf.space/evil/clip.mp4'):
            with self.subTest(url=bad):
                with self.assertRaises(AIVideoUnavailable):
                    _video_result_url([{'video':{'url':bad}}])

    def test_queue_protocol_calls_true_text_to_video_and_parses_completion(self):
        class MockResponse:
            def __init__(self, payload, stream=False):
                self.payload=payload
                self.stream=stream
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,maxbytes=None):return self.payload
            def __iter__(self):return iter(self.payload.splitlines(keepends=True))
        calls=[]
        video='https://lightricks-ltx-video-distilled.hf.space/gradio_api/file=/tmp/gradio/a/movie.mp4'
        def opener(req,timeout):
            calls.append(req)
            if len(calls)==1:
                body=json.loads(req.data)
                self.assertIn('Narration',body['data'][0])
                self.assertEqual(body['data'][6],'text-to-video')
                return MockResponse(b'{"event_id":"0123456789abcdef0123456789abcdef"}')
            payload='event: pending\n\nevent: complete\ndata: '+json.dumps([
                {'video':{'url':video}},42
            ])+'\n\n'
            return MockResponse(payload.encode(),True)
        out=_request_video_generation('Narration',opener=opener,duration=2)
        self.assertEqual(out,video)
        self.assertEqual(len(calls),2)

    def test_film_plan_splits_new_unknown_hebrew_story_into_two_shots(self):
        spoken='האדם מרים את הכוס. אחר כך היא נופלת על הרצפה ונשברת.'
        scenes=_narrative_shots(spoken)
        self.assertEqual(len(scenes),2)
        self.assertIn('הכוס',scenes[0])
        self.assertIn('נשברת',scenes[1])
        self.assertIn('הכוס',cinematic_prompt(scenes[0]))

    def test_two_original_ai_shots_are_distinct_and_audio_is_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            audio=root/'mix.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','sine=frequency=385:duration=6',
                '-c:a','libmp3lame',str(audio)],check=True)
            count={'n':0}
            prompts=[]
            def generate(prompt):
                prompts.append(prompt)
                return 'https://lightricks-ltx-video-distilled.hf.space/gradio_api/file=/tmp/gradio/a.mp4'
            def download(url,dest):
                count['n']+=1
                v='testsrc' if count['n']==1 else 'smptebars'
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                    '-f','lavfi','-i',f'{v}=size=512x704:rate=12:duration=4',
                    '-c:v','libvpx-vp9','-b:v','180k',str(dest)],check=True)
                return 4.0
            out=root/'story.mp4'
            plan=generate_ai_story(
                'האיש צוחק בקול. אחר כך הכוס נשברת על הרצפה.',
                audio,out,root/'generated',generator=generate,download=download)
            self.assertEqual(count['n'],2)
            self.assertEqual(len(prompts),2)
            self.assertEqual(plan['ai_clips_generated'],2)
            self.assertEqual(len(plan['scenes']),2)
            probe=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(out)]))
            self.assertGreater(float(probe['format']['duration']),5.4)
            codec=next(s for s in probe['streams'] if s['codec_type']=='video')
            self.assertEqual((codec['codec_name'],codec['width'],codec['height']),
                             ('h264',360,640))
            subprocess.run(['ffmpeg','-v','error','-ss','4.3','-i',str(out),
                '-frames:v','1','-f','null','-'],check=True)

    def test_ltx25_public_generator_uses_actual_named_schema_and_safe_url(self):
        class Response:
            def __init__(self, body):self.body=body
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,count=None):return self.body
            def __iter__(self):return iter(self.body.splitlines(keepends=True))
        calls=[]
        good='https://lightricks-ltx-2-5.hf.space/gradio_api/file=/tmp/gradio/clip.mp4'
        def opener(req,timeout):
            calls.append(req)
            if len(calls)==1:
                body=json.loads(req.data)
                self.assertEqual(body['height'],512)
                self.assertEqual(body['width'],768)
                self.assertEqual(body['decoder'],'conv')
                self.assertEqual(body['duration_s'],2.0)
                self.assertIsNone(body['image_path'])
                self.assertEqual(body['prompt'],'A happy donkey')
                return Response(b'{"event_id":"0123456789abcdef0123456789abcdef"}')
            event="event: complete"+chr(10)+"data: "+json.dumps([
                {'url':good,'path':'/tmp/gradio/clip.mp4'},'narration',42
            ])+chr(10)*2
            return Response(event.encode())
        result=_request_ltx25_generation('A happy donkey',opener=opener)
        self.assertEqual(result,good)
        self.assertEqual(len(calls),2)
        with self.assertRaises(AIVideoUnavailable):
            _video_result_url([{'url':'https://evil.com/gradio_api/file=x'}],
                              expected_host='lightricks-ltx-2-5.hf.space')

    def test_long_uneven_narration_is_planned_before_spending_public_gpu(self):
        # One original clause is repeated as genuinely new camera angles.
        # Server must use the DIVIDED per-shot weight, like the phone,
        # not count the full original clause again for every angle.
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); audio=root/'mix.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','sine=frequency=440:duration=39',
                '-c:a','libmp3lame',str(audio)],check=True,timeout=30)
            called=[]
            def quota_mock(prompt):
                called.append(prompt)
                raise AIVideoUnavailable('fake external quota')
            with self.assertRaisesRegex(AIVideoUnavailable,
                                        'fake external quota'):
                generate_ai_story(
                    'האיש נופל. אחר כך המשאית נוסעת בכביש '
                    'ועוצרת ברמזור ואנשים צוחקים בקול רם.',
                    audio,root/'story.mp4',root/'generated',
                    generator=quota_mock)
            self.assertEqual(len(called),1,
                'A valid duration plan must reach the provider, not fail preflight')
            self.assertFalse((root/'story.mp4').exists())

    def test_short_public_clip_stops_before_wasting_followup_gpu_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);audio=root/'mix.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','sine=frequency=420:duration=15',
                '-c:a','libmp3lame',str(audio)],check=True)
            calls=[]
            def generator(prompt):
                calls.append(prompt)
                return 'https://lightricks-ltx-2-5.hf.space/gradio_api/file=/a.mp4'
            def download(url,destination):
                return 1.5
            output=root/'story.mp4'
            with self.assertRaisesRegex(AIVideoUnavailable,'לא נמחזר קליפ קצר'):
                generate_ai_story(
                    'הכלב נובח בחצר. אחר כך האיש רץ ברחוב. הכוס נשברת בבית.',
                    audio,output,root/'generated',generator=generator,download=download)
            self.assertEqual(len(calls),1)
            self.assertFalse(output.exists())

    def test_gen_video_is_original_motion_and_full_sound_no_subtitles(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            audio=root/'mix.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','sine=frequency=390:duration=4',
                '-c:a','libmp3lame',str(audio)],check=True)
            seen=[]
            def generate(prompt):
                seen.append(prompt)
                return 'https://lightricks-ltx-video-distilled.hf.space/gradio_api/file=/tmp/gradio/fake.mp4'
            def download(url,dest):
                # This is an actual moving WebM video, not a still or waveform.
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                    '-i','testsrc=size=512x704:rate=12:duration=4',
                    '-c:v','libvpx-vp9','-b:v','140k',str(dest)],check=True,timeout=30)
                return 4.0
            out=root/'story.mp4'
            plan=generate_ai_story('האיש צוחק בקול.',audio,out,root/'ai',
                                   generator=generate,download=download)
            self.assertEqual(plan['source'],'generated_from_original_hebrew_transcript')
            self.assertEqual(plan['visual_coverage'],'approximate')
            self.assertFalse(plan['repeated_ai_shot'])
            self.assertTrue(seen and 'האיש צוחק' in seen[0])
            report=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(out)]))
            video=next(s for s in report['streams'] if s['codec_type']=='video')
            self.assertEqual((video['codec_name'],video['width'],video['height']),
                             ('h264',360,640))
            self.assertEqual({s['codec_type'] for s in report['streams']},
                             {'audio','video'})
            self.assertGreater(float(report['format']['duration']),3.4)

if __name__=='__main__':
    unittest.main()
