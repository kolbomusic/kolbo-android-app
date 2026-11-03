import io, pathlib, sys, tempfile, time, unittest, wave
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT/'backend'/'app.py').exists(), 'Remix jobs API is missing'
        from app import create_app
        cls.tmp=tempfile.TemporaryDirectory()
        cls.app=create_app({'TESTING':True,'JOB_DIR':cls.tmp.name})
        cls.client=cls.app.test_client()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_bad_input_never_creates_job(self):
        self.assertEqual(self.client.post('/api/jobs',data={}).status_code,400)
        self.assertEqual(self.client.post('/api/jobs',data={'bpm':'oops','audio':(io.BytesIO(b'bad'),'a.opus')}).status_code,400)
        self.assertEqual(self.client.get('/api/jobs/not-a-job').status_code,404)

    def test_real_upload_renders_downloadable_mp3(self):
        stream=io.BytesIO()
        with wave.open(stream,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
            w.writeframes((np.sin(np.arange(16000)*2*np.pi*337/8000)*9000).astype('<i2').tobytes())
        stream.seek(0)
        response=self.client.post('/api/jobs',data={'bpm':'145','seconds':'30','audio':(stream,'voice.wav')})
        self.assertEqual(response.status_code,202,response.get_data(as_text=True))
        job=response.json
        deadline=time.time()+45
        while time.time()<deadline:
            status=self.client.get(job['status_url']).json
            if status['state'] in ('done','error'):break
            time.sleep(.05)
        self.assertEqual(status['state'],'done',status)
        result=self.client.get(status['download_url'])
        self.assertEqual(result.status_code,200)
        self.assertIn('audio/mpeg',result.content_type)
        self.assertGreater(len(result.data),50000)
        result.close()
        self.assertIn('voice_url',status)
        vocal=self.client.get(status['voice_url'])
        self.assertEqual(vocal.status_code,200)
        self.assertIn('audio/mpeg',vocal.content_type)
        self.assertGreater(len(vocal.data),12000)
        vocal.close()

    def test_unsupported_media_fails_without_external_reads(self):
        r=self.client.post('/api/jobs',data={'audio':(io.BytesIO(b'#EXTM3U\nhttp://127.0.0.1/'),'a.m3u')})
        self.assertEqual(r.status_code,400)

    def test_production_requires_a_configured_key_and_rejects_other_origins(self):
        from app import create_app
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({'JOB_DIR':folder,'API_TOKEN':'test-access-key','ALLOWED_ORIGINS':'https://allowed.example'}).test_client()
            self.assertEqual(client.post('/api/jobs').status_code,401)
            self.assertEqual(client.post('/api/jobs',headers={'Authorization':'Bearer wrong'}).status_code,401)
            self.assertEqual(client.post('/api/jobs',headers={'Authorization':'Bearer test-access-key','Origin':'https://other.example'}).status_code,403)
            self.assertEqual(client.post('/api/jobs',headers={'Authorization':'Bearer test-access-key'}).status_code,400)

    def test_mobile_studio_serves_pwa_without_exposing_backend_token(self):
        from app import create_app
        with tempfile.TemporaryDirectory() as folder:
            app=create_app({'JOB_DIR':folder,'API_TOKEN':'private-key-123','ALLOWED_ORIGINS':'https://allowed.example'})
            client=app.test_client()
            r=client.get('/studio',base_url='https://studio.example')
            self.assertEqual(r.status_code,200)
            self.assertIn(b'Kolbo Trance',r.data)
            self.assertNotIn(b'private-key-123',r.data)
            self.assertIn('HttpOnly',r.headers.get('Set-Cookie',''))
            self.assertIn('Secure',r.headers.get('Set-Cookie',''))
            self.assertEqual(client.get('/studio.webmanifest').status_code,200)
            self.assertEqual(client.get('/studio-sw.js').status_code,200)
            self.assertEqual(client.get('/studio-icon.svg').status_code,200)
            # A secure studio session can access the API, but other visitors need the server token.
            accepted=client.post('/api/jobs',data={},base_url='https://studio.example',headers={'Origin':'https://studio.example'})
            self.assertEqual(accepted.status_code,400,accepted.get_data(as_text=True))
            anonymous=app.test_client()
            refused=anonymous.post('/api/jobs',data={},base_url='https://studio.example',headers={'Origin':'https://studio.example'})
            self.assertEqual(refused.status_code,401)

    def test_private_job_status_and_audio_require_server_key(self):
        from app import create_app
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({'JOB_DIR':folder,'API_TOKEN':'test-access-key'}).test_client()
            for path in ('/api/jobs/'+'a'*48,'/api/jobs/'+'a'*48+'/audio','/api/jobs/'+'a'*48+'/voice'):
                self.assertEqual(client.get(path).status_code,401)
                self.assertEqual(client.get(path,headers={'Authorization':'Bearer test-access-key'}).status_code,404)

    def test_oversized_file_is_rejected_before_scheduling(self):
        r=self.client.post('/api/jobs',data={'audio':(io.BytesIO(b'x'*(15*1024*1024+1)),'large.opus')})
        self.assertEqual(r.status_code,400)

    def test_whatsapp_video_above_voice_limit_is_accepted_and_larger_video_rejected(self):
        # A WhatsApp MP4 can exceed the 15MB speech-note cap. Avoid running
        # FFmpeg on dummy upload bytes; test admission and size logic exactly.
        from unittest import mock
        from app import create_app
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch('app.ThreadPoolExecutor') as executor:
                server=create_app({'TESTING':True,'JOB_DIR':folder,
                                   'MAX_CONTENT_LENGTH':64*1024*1024})
                client=server.test_client()
                too_big=io.BytesIO(b'0'*(45*1024*1024+1))
                response=client.post('/api/jobs',data={
                    'audio':(too_big,'oversized.mp4'),'make_video':'on'})
                self.assertEqual(response.status_code,400)
                self.assertIn('45MB',response.json['error'])
                video=io.BytesIO(b'0'*(15*1024*1024+1024))
                response=client.post('/api/jobs',data={
                    'audio':(video,'VID-WhatsApp.mp4'),'make_video':'on'})
                self.assertEqual(response.status_code,202,
                                 response.get_data(as_text=True))
                executor.return_value.submit.assert_called_once()


    def test_video_strategy_and_licensed_music_are_explicit_and_forwarded(self):
        from unittest import mock
        from app import create_app
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch('app.ThreadPoolExecutor') as executor:
                app=create_app({'TESTING':True,'JOB_DIR':folder})
                client=app.test_client()
                rejected=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'x'*5000),'voice.opus'),
                    'backing_music':(io.BytesIO(b'm'*10000),'song.mp3'),
                    'video_strategy':'new_story','make_video':'on'})
                self.assertEqual(rejected.status_code,400)
                self.assertIn('זכויות',rejected.json['error'])
                invalid=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'x'*5000),'voice.opus'),
                    'video_strategy':'some_unvalidated_command'})
                self.assertEqual(invalid.status_code,400)
                permitted=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'x'*5000),'voice.opus'),
                    'backing_music':(io.BytesIO(b'm'*10000),'song.mp3'),
                    'video_strategy':'new_story','make_video':'on',
                    'music_license_ack':'on'})
                self.assertEqual(permitted.status_code,202,
                                 permitted.get_data(as_text=True))
                call=executor.return_value.submit.call_args
                opts=call.args[3]
                self.assertEqual(opts['video_strategy'],'new_story')
                self.assertTrue(opts['music_license_ack'])
                self.assertTrue(pathlib.Path(opts['backing_music_path']).is_file())
                self.assertEqual(pathlib.Path(opts['backing_music_path']).stat().st_size,10000)

    def test_121_second_whatsapp_voice_no_longer_gets_rejected_or_truncated(self):
        import subprocess
        from unittest import mock
        from engine import load_audio
        content=subprocess.check_output(['ffmpeg','-v','error','-f','lavfi',
            '-i','sine=frequency=337:duration=121','-c:a','libopus',
            '-f','opus','pipe:1'])
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'voice.opus'
            path.write_bytes(content)
            audio=load_audio(path)
        self.assertGreater(len(audio),120*32000)
        self.assertLessEqual(len(audio),300*32000)
        # This test verifies that API intake preserves the complete audio.
        # A short mocked DSP result avoids spending several minutes in CI.
        proof=np.zeros((32000,2),dtype=np.float32)
        voice=np.zeros(32000,dtype=np.float32)
        with mock.patch('app.render_mix',return_value=(proof,voice)) as mix:
            r=self.client.post('/api/jobs',data={'humor':'off',
                'audio':(io.BytesIO(content),'voice.opus')})
            self.assertEqual(r.status_code,202)
            deadline=time.time()+45
            while time.time()<deadline:
                status=self.client.get(r.json['status_url']).json
                if status['state'] in ('done','error'):break
                time.sleep(.05)
            self.assertEqual(status['state'],'done',status)
            self.assertTrue(mix.called)
            original_clips=mix.call_args.args[0]
            self.assertEqual(len(original_clips),1)
            self.assertGreater(len(original_clips[0]),120*32000)

    def test_over_five_minutes_reports_actual_duration_violation(self):
        import subprocess
        content=subprocess.check_output(['ffmpeg','-v','error','-f','lavfi',
            '-i','sine=frequency=337:duration=301','-c:a','libopus',
            '-f','opus','pipe:1'])
        r=self.client.post('/api/jobs',data={'humor':'off',
            'audio':(io.BytesIO(content),'too-long.opus')})
        self.assertEqual(r.status_code,202)
        deadline=time.time()+45
        while time.time()<deadline:
            status=self.client.get(r.json['status_url']).json
            if status['state'] in ('done','error'):break
            time.sleep(.05)
        self.assertEqual(status['state'],'error',status)
        self.assertEqual(status['error_code'],'recording_too_long',status)
        self.assertIn('300',status['message'])


    def test_unreadable_audio_reports_codec_failure_not_false_duration(self):
        bad=io.BytesIO(b'not-an-opus-recording-'*100)
        response=self.client.post('/api/jobs',data={'humor':'off',
            'audio':(bad,'voice.opus')})
        self.assertEqual(response.status_code,202)
        deadline=time.time()+30
        while time.time()<deadline:
            status=self.client.get(response.json['status_url']).json
            if status['state'] in ('done','error'):break
            time.sleep(.05)
        self.assertEqual(status['state'],'error',status)
        self.assertEqual(status['error_code'],'decode_failed',status)
        self.assertEqual(status['error_stage'],'decode')
        self.assertIn('לפענח',status['message'])
        self.assertNotIn('120',status['message'])
        self.assertNotIn('not-an-opus',status['message'])

    def test_internal_dsp_failure_does_not_get_misreported_as_long_recording(self):
        from unittest import mock
        sample=np.sin(np.arange(16000)*2*np.pi*337/8000).astype(np.float32)
        with mock.patch('app.load_audio',return_value=sample), mock.patch('app.render_mix',side_effect=RuntimeError('private_dsp_detail')):
            response=self.client.post('/api/jobs',data={'humor':'off',
                'audio':(io.BytesIO(b'irrelevant'),'short.opus')})
            self.assertEqual(response.status_code,202)
            deadline=time.time()+20
            while time.time()<deadline:
                status=self.client.get(response.json['status_url']).json
                if status['state'] in ('done','error'):break
                time.sleep(.05)
        self.assertEqual(status['state'],'error',status)
        self.assertEqual(status['error_code'],'internal_processing_error',status)
        self.assertEqual(status['error_stage'],'mix')
        self.assertNotIn('120',status['message'])
        self.assertNotIn('private_dsp_detail',status['message'])
        self.assertTrue(status['error_ref'])

    def test_silent_audio_decoder_returns_actionable_error(self):
        from unittest import mock
        import subprocess
        from engine import load_audio,AudioDecodeError
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'silence.opus'
            path.write_bytes(b'placeholder')
            with mock.patch('engine.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')):
                with self.assertRaises(AudioDecodeError) as captured:
                    load_audio(path)
        self.assertEqual(captured.exception.code,'no_audio_stream')
        self.assertIn('ערוץ שמע',str(captured.exception))

if __name__=='__main__':unittest.main()
