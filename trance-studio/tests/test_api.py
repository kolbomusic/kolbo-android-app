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

    def test_private_job_status_and_audio_require_server_key(self):
        from app import create_app
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({'JOB_DIR':folder,'API_TOKEN':'test-access-key'}).test_client()
            for path in ('/api/jobs/'+'a'*48,'/api/jobs/'+'a'*48+'/audio'):
                self.assertEqual(client.get(path).status_code,401)
                self.assertEqual(client.get(path,headers={'Authorization':'Bearer test-access-key'}).status_code,404)

    def test_oversized_file_is_rejected_before_scheduling(self):
        r=self.client.post('/api/jobs',data={'audio':(io.BytesIO(b'x'*(15*1024*1024+1)),'large.opus')})
        self.assertEqual(r.status_code,400)

    def test_long_recording_is_rejected_before_render(self):
        import subprocess
        content=subprocess.check_output(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=337:duration=61','-c:a','libopus','-f','opus','pipe:1'])
        r=self.client.post('/api/jobs',data={'audio':(io.BytesIO(content),'long.opus')})
        self.assertEqual(r.status_code,202)
        deadline=time.time()+10
        while time.time()<deadline:
            status=self.client.get(r.json['status_url']).json
            if status['state'] in ('done','error'):break
            time.sleep(.02)
        self.assertEqual(status['state'],'error')

if __name__=='__main__':unittest.main()
