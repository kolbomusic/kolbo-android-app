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
            result=client.post('/api/jobs/'+data['id']+'/generated-video',
                json={'video_url':'https://lightricks-ltx-2-5.hf.space/gradio_api/file=/tmp/gradio/x.mp4'})
            self.assertEqual(result.status_code,403)
            self.assertEqual(client.get(state['download_url']).status_code,200)

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
            self.assertEqual(ready.status_code,200,ready.get_json())
            dl.assert_called_once()
            details=ready.get_json()
            self.assertEqual(details['video_status'],'done')
            self.assertEqual(details['video_mode'],'ai_generated_on_device')
            after=self.wait(client,data['status_url'])
            self.assertIn('video_url',after)
            self.assertNotIn('client_ai_prompt',after)
            video=client.get(details['video_preview_url'])
            self.assertEqual(video.status_code,200)
            self.assertGreater(len(video.data),25000)
            movie=pathlib.Path(folder)/'output.mp4'
            movie.write_bytes(video.data)
            check=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format','-of',
                'json',str(movie)]))
            v=next(s for s in check['streams'] if s['codec_type']=='video')
            self.assertEqual((v['codec_name'],v['width'],v['height']),
                             ('h264',360,640))
            self.assertEqual({s['codec_type'] for s in check['streams']},
                             {'video','audio'})
            self.assertGreater(float(check['format']['duration']),29.3)
            self.assertEqual(client.get(after['download_url']).status_code,200)


if __name__=='__main__':
    unittest.main()
