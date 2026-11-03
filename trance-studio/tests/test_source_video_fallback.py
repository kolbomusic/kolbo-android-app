"""Verify MP4 fallback uses only the user's genuine moving video input."""
import io, json, pathlib, subprocess, sys, tempfile, unittest
from unittest import mock
import numpy as np
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

    def test_safe_single_pass_mp4_when_multi_shot_editor_fails(self):
        # The source has real camera motion: a failed complex FFmpeg shot
        # must not silently turn a video request into MP3-only output.
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            movie=root/'original-whatsapp.mp4'
            music=root/'trance.mp3';out=root/'rescued.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i',
                'testsrc2=size=320x240:rate=12:duration=3',
                '-c:v','libx264','-preset','ultrafast',
                '-pix_fmt','yuv420p',str(movie)],
                check=True,timeout=25)
            self.make_music(music) # 5s soundtrack; the 3s source is slowed.
            with mock.patch('beat_video_editor.compose_edited_original_video',
                            side_effect=UnavailableVideo('complex filter failed')):
                meta=compose_original_video_with_mix(
                    [movie],music,out,root/'backup')
            self.assertEqual(meta['video_status'],'done')
            self.assertEqual(meta['video_edit_style'],'single_pass_source_rescue')
            self.assertFalse(meta['video_edit_audio_synced'])
            self.assertTrue(out.is_file())
            streams=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(out)],timeout=15))
            self.assertEqual({t['codec_type'] for t in streams['streams']},
                             {'audio','video'})
            self.assertAlmostEqual(float(streams['format']['duration']),5.0,
                                   delta=.8)
            self.assertEqual(next(t['codec_name'] for t in streams['streams']
                                  if t['codec_type']=='video'),'h264')

    def test_truly_audio_only_mp4_does_not_get_fake_fallback_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            movie=root/'only-audio.mp4'
            music=root/'trance.mp3';out=root/'not-a-video.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','sine=frequency=300:duration=3',
                '-c:a','aac',str(movie)],check=True,timeout=25)
            self.make_music(music)
            with self.assertRaises(UnavailableVideo) as err:
                compose_original_video_with_mix([movie],music,out,root/'work')
            self.assertIn('ערוץ תמונה',str(err.exception))
            self.assertFalse(out.exists())

    def test_backend_job_survives_asr_failure_using_original_video(self):
        import app as server
        import source_asr
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            movie=root/'uploaded.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','testsrc=size=320x240:rate=12:duration=3',
                '-c:v','libx264','-pix_fmt','yuv420p',str(movie)],
                check=True,timeout=25)
            with mock.patch.object(server,'ThreadPoolExecutor') as executor:
                app=server.create_app({'TESTING':True,'JOB_DIR':str(root/'jobs'),
                                       'API_TOKEN':'test-only'})
                client=app.test_client()
                response=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(movie.read_bytes()),'uploaded.mp4'),
                    'make_video':'on','video_requested':'on',
                    'transcript':'','transcript_origin':'auto',
                    'seconds':'30'})
                self.assertEqual(response.status_code,202,response.get_json())
                worker=executor.return_value.submit.call_args.args
                def export_fake_mp3(samples,path,sr=32000):
                    subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                        '-f','lavfi','-i','sine=frequency=260:duration=5',
                        '-c:a','libmp3lame',str(path)],check=True,timeout=25)
                with (mock.patch.object(source_asr,'transcribe_original_files',
                                        side_effect=RuntimeError('offline ASR')),
                      mock.patch.object(server,'load_audio',
                                        return_value=np.ones(160000,np.float32)*.01),
                      mock.patch.object(server,'render_mix',
                                        return_value=(np.zeros((160000,2),np.float32),
                                                      np.zeros(160000,np.float32))),
                      mock.patch.object(server,'export_mp3',side_effect=export_fake_mp3)):
                    worker[0](*worker[1:])
                status=client.get('/api/jobs/'+response.json['id']).json
                self.assertEqual(status['state'],'done',status)
                self.assertEqual(status['video_status'],'done',status)
                self.assertEqual(status['video_mode'],'original_input_video')
                self.assertEqual(status['storyboard_source'],'original_shared_video')
                self.assertIn('/video',status['video_url'])

    def test_fresh_story_mode_never_returns_original_video_on_asr_failure(self):
        import app as server
        import source_asr
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            movie=root/'uploaded.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','testsrc=size=320x240:rate=12:duration=2',
                '-c:v','libx264','-pix_fmt','yuv420p',str(movie)],
                check=True,timeout=25)
            with mock.patch.object(server,'ThreadPoolExecutor') as executor:
                app=server.create_app({'TESTING':True,'JOB_DIR':str(root/'jobs'),
                                       'API_TOKEN':'test-only'})
                client=app.test_client()
                response=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(movie.read_bytes()),'video.mp4'),
                    'make_video':'on','video_requested':'on',
                    'video_strategy':'new_story',
                    'transcript':'','transcript_origin':'auto','seconds':'30'})
                self.assertEqual(response.status_code,202,response.json)
                worker=executor.return_value.submit.call_args.args
                def export_fake_mp3(samples,path,sr=32000):
                    subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                        '-f','lavfi','-i','sine=frequency=260:duration=5',
                        '-c:a','libmp3lame',str(path)],check=True,timeout=25)
                with (mock.patch.object(source_asr,'transcribe_original_files',
                                        side_effect=RuntimeError('offline')),
                      mock.patch.object(server,'load_audio',
                                        return_value=np.ones(160000,np.float32)*.01),
                      mock.patch.object(server,'render_mix',
                                        return_value=(np.zeros((160000,2),np.float32),
                                                      np.zeros(160000,np.float32))),
                      mock.patch.object(server,'export_mp3',side_effect=export_fake_mp3),
                      mock.patch('source_video_fallback.compose_original_video_with_mix',
                                 side_effect=AssertionError('original forbidden'))):
                    worker[0](*worker[1:])
                result=client.get('/api/jobs/'+response.json['id']).json
                self.assertEqual(result['state'],'done',result)
                self.assertEqual(result['video_status'],'unavailable',result)
                self.assertNotIn('video_url',result)
                self.assertIn('download_url',result)

    def test_ai_story_does_not_call_footage_selector_even_with_valid_hebrew(self):
        import app as server
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            with mock.patch.object(server,'ThreadPoolExecutor') as executor:
                app=server.create_app({'TESTING':True,'JOB_DIR':str(root/'jobs'),
                                       'API_TOKEN':'test-only'})
                client=app.test_client()
                response=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'nonempty fake audio'),'voice.opus'),
                    'make_video':'on','video_requested':'on',
                    'video_strategy':'new_story',
                    'transcript':'החמור נוער והחקלאי צוחק בקול',
                    'transcript_origin':'manual','seconds':'30'})
                self.assertEqual(response.status_code,202,response.json)
                job=executor.return_value.submit.call_args.args
                def fake_mp3(samples,path,sr=32000):
                    pathlib.Path(path).write_bytes(b'mp3-placeholder')
                with (mock.patch.object(server,'load_audio',
                                        return_value=np.ones(160000,np.float32)*.01),
                      mock.patch.object(server,'render_mix',
                                        return_value=(np.zeros((160000,2),np.float32),
                                                      np.zeros(160000,np.float32))),
                      mock.patch.object(server,'export_mp3',side_effect=fake_mp3),
                      mock.patch.object(server,'visual_plan',
                                        side_effect=AssertionError('stock footage forbidden')),
                      mock.patch('source_video_fallback.compose_original_video_with_mix',
                                 side_effect=AssertionError('source video forbidden'))):
                    job[0](*job[1:])
                status=client.get('/api/jobs/'+response.json['id']).json
                self.assertEqual(status['state'],'done',status)
                self.assertEqual(status['video_status'],'unavailable',status)
                self.assertEqual(status['storyboard_source'],
                                 'independent_ai_not_available')
                self.assertNotIn('video_url',status)

    def test_stock_illustration_failure_must_not_return_whatsapp_source(self):
        import app as server
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            with mock.patch.object(server,'ThreadPoolExecutor') as executor:
                app=server.create_app({'TESTING':True,'JOB_DIR':str(root/'jobs'),
                                       'API_TOKEN':'test-only'})
                client=app.test_client()
                response=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'fake-video-data'),'video.mp4'),
                    'video_strategy':'illustrated_story',
                    'make_video':'on','video_requested':'on',
                    'transcript':'החמור נוער והחקלאי צוחק בקול',
                    'transcript_origin':'manual','seconds':'30'})
                self.assertEqual(response.status_code,202,response.json)
                job=executor.return_value.submit.call_args.args
                def fake_mp3(samples,path,sr=32000):
                    pathlib.Path(path).write_bytes(b'mp3-placeholder')
                with (mock.patch.object(server,'load_audio',
                                        return_value=np.ones(160000,np.float32)*.01),
                      mock.patch.object(server,'render_mix',
                                        return_value=(np.zeros((160000,2),np.float32),
                                                      np.zeros(160000,np.float32))),
                      mock.patch.object(server,'export_mp3',side_effect=fake_mp3),
                      mock.patch.object(server,'visual_plan',
                                        side_effect=UnavailableVideo('no licensed source')),
                      mock.patch('source_video_fallback.compose_original_video_with_mix',
                                 side_effect=AssertionError('video source substitution forbidden'))):
                    job[0](*job[1:])
                status=client.get('/api/jobs/'+response.json['id']).json
                self.assertEqual(status['state'],'done',status)
                self.assertEqual(status['video_status'],'unavailable',status)
                self.assertNotEqual(status.get('storyboard_source'),
                                    'original_shared_video')

    def test_audio_only_does_not_invent_a_real_world_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);music=root/'mix.mp3'
            self.make_music(music)
            with self.assertRaises(UnavailableVideo):
                compose_original_video_with_mix([music],music,root/'out.mp4',
                                                root/'work')

    def test_still_intro_does_not_hide_real_motion_later_in_video(self):
        # A news/WhatsApp clip may start with an immobile title card, then
        # move normally. The older initial-3-second-only check incorrectly
        # treated this as an audio-only/invalid video.
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);source=root/'intro-then-moving.mp4'
            music=root/'mix.mp3';result=root/'story.mp4'
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i',
                'color=c=black:size=320x240:rate=12:duration=3.6',
                '-f','lavfi','-i',
                'testsrc2=size=320x240:rate=12:duration=3.6',
                '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                '-map','[v]','-c:v','libx264','-preset','ultrafast',
                '-pix_fmt','yuv420p',str(source)
            ],check=True,timeout=30)
            from motion_quality import motion_score
            self.assertLess(motion_score(source),.30)
            self.assertGreater(motion_score(source,start_seconds=3),.30)
            self.make_music(music)
            meta=compose_original_video_with_mix(
                [source],music,result,root/'work')
            self.assertEqual(meta['video_status'],'done')
            self.assertTrue(result.exists())
            self.assertGreater(result.stat().st_size,20000)

    def test_delayed_visual_action_reaches_real_source_editor(self):
        # Movement appearing after the old 18-second scan boundary must
        # reach the original-video editor, rather than declaring no MP4.
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            movie=root/'late-moving.mp4'
            music=root/'mix.mp3'
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','color=c=black:s=256x256:r=12:d=23',
                '-f','lavfi','-i','testsrc=size=256x256:rate=12:duration=7',
                '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                '-map','[v]','-c:v','libx264','-preset','ultrafast',
                '-pix_fmt','yuv420p',str(movie)],check=True,timeout=40)
            self.make_music(music)
            expected={'video_status':'done','video_mode':'original_input_video'}
            with mock.patch('beat_video_editor.compose_edited_original_video',
                            return_value=expected) as edit:
                meta=compose_original_video_with_mix(
                    [movie],music,root/'final.mp4',root/'work')
            self.assertEqual(meta,expected)
            edit.assert_called_once()

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
