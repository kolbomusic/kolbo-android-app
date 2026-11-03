"""Exact private end-to-end tests for per-phone free ZeroGPU quota fallback."""
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from app import create_app
from ai_video import AIVideoUnavailable
from live_video import UnavailableVideo


class BrowserAIQuotaTests(unittest.TestCase):
    def sample(self):
        buffer=io.BytesIO()
        sr=8000
        t=np.arange(sr)/sr
        audio=(10000*np.sin(2*np.pi*220*t)).astype('<i2')
        with wave.open(buffer,'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sr)
            wav.writeframes(audio.tobytes())
        buffer.seek(0)
        return buffer

    def wait(self,client,url):
        for i in range(160):
            status=client.get(url).get_json()
            if status.get('state') in ('done','error'):
                return status
            time.sleep(.25)
        self.fail('mix did not finish')

    def test_local_hebrew_prompt_is_private_and_export_requires_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({'TESTING':True,'JOB_DIR':folder,'API_TOKEN':'test'}).test_client()
            with patch('app.visual_plan',side_effect=UnavailableVideo('no action')):
                response=client.post('/api/jobs',data={
                    'audio':(self.sample(),'spoken.wav'),
                    'make_video':'on','video_requested':'on',
                    'ai_video_consent':'off',
                    'transcript':'האיש זורק כוס זכוכית על הרצפה',
                    'transcript_origin':'auto','seconds':'30'
                })
                self.assertEqual(response.status_code,202)
                data=response.get_json()
                state=self.wait(client,data['status_url'])
            self.assertEqual(state['state'],'done',state)
            self.assertNotIn('client_ai_prompt',state)
            self.assertEqual(client.get('/api/jobs/'+data['id']+'/ai-plan').status_code,403)
            result=client.post('/api/jobs/'+data['id']+'/generated-video',
                json={'video_url':'https://lightricks-ltx-2-5.hf.space/gradio_api/file=/tmp/gradio/x.mp4'})
            self.assertEqual(result.status_code,403)
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_ai_plan_recovery_uses_consented_original_shots_not_prompt_rewrite(self):
        spoken='האיש זורק כוס זכוכית על הרצפה. הכוס נשברת לרסיסים.'
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({'TESTING':True,'JOB_DIR':folder,
                               'API_TOKEN':'test'}).test_client()
            with patch('source_asr.transcribe_original_files',
                       return_value=(spoken,True,[])), patch(
                'ai_video.generate_ai_story',
                side_effect=AIVideoUnavailable('quota unavailable')):
                response=client.post('/api/jobs',data={
                    'audio':(self.sample(),'speech.wav'),
                    'make_video':'on','video_requested':'on',
                    'ai_video_consent':'on','video_strategy':'new_story',
                    'transcript_origin':'auto','seconds':'30'})
                self.assertEqual(response.status_code,202,response.get_json())
                data=response.get_json()
                state=self.wait(client,data['status_url'])
            self.assertEqual(state['state'],'done')
            self.assertEqual(state['video_status'],'unavailable')
            endpoint='/api/jobs/'+data['id']+'/ai-plan'
            plan=client.get(endpoint)
            self.assertEqual(plan.status_code,200,plan.get_json())
            result=plan.get_json()
            self.assertEqual(result['prompts'],state['client_ai_scene_prompts'])
            self.assertEqual(result['weights'],state['client_ai_scene_weights'])
            self.assertEqual(result['scene_count'],len(result['prompts']))
            self.assertGreater(result['scene_count'],1)
            self.assertIn('הכוס',result['prompts'][-1])
            self.assertFalse(any('video_url' in p for p in result))
            self.assertEqual(client.get('/api/jobs/'+'a'*48+'/ai-plan').status_code,404)

    def test_phone_clip_can_complete_failed_automatic_hebrew_video(self):
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({'TESTING':True,'JOB_DIR':folder,'API_TOKEN':'test'}).test_client()
            with patch('ai_video.generate_ai_story',
                       side_effect=AIVideoUnavailable('quota unavailable')), \
                 patch('app.visual_plan',
                       side_effect=UnavailableVideo('no archive action')):
                response=client.post('/api/jobs',data={
                    'audio':(self.sample(),'spoken.wav'),
                    'make_video':'on','video_requested':'on',
                    'ai_video_consent':'on',
                    'transcript':'האיש זורק כוס זכוכית על הרצפה',
                    'transcript_origin':'auto','seconds':'30'
                })
                self.assertEqual(response.status_code,202,response.get_json())
                data=response.get_json()
                state=self.wait(client,data['status_url'])
            self.assertEqual(state['state'],'done',state)
            self.assertEqual(state['video_status'],'unavailable')
            self.assertIn('client_ai_prompt',state)
            self.assertIn('זכוכית',state['client_ai_prompt'])
            def fake_download(url,destination):
                self.assertIn('ltx-2-5.hf.space',url)
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                    '-f','lavfi','-i','testsrc=size=512x704:rate=12:duration=2',
                    '-c:v','libx264','-preset','ultrafast','-crf','32',
                    str(destination)],check=True,timeout=30)
                return 2.0
            url='https://lightricks-ltx-2-5.hf.space/gradio_api/file=/tmp/gradio/clip.mp4'
            with patch('ai_video._download_public_video',side_effect=fake_download) as dl:
                ready=client.post('/api/jobs/'+data['id']+'/generated-video',
                                  json={'video_url':url})
            self.assertEqual(ready.status_code,422,ready.get_json())
            self.assertIn('קליפ AI יחיד קצר',ready.get_json()['error'])
            dl.assert_called_once()
            after=self.wait(client,data['status_url'])
            self.assertEqual(after['video_status'],'unavailable')
            self.assertNotIn('video_url',after)
            self.assertEqual(client.get(after['download_url']).status_code,200)


if __name__=='__main__':
    unittest.main()
