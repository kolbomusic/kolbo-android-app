"""Production story tests: video must not be unrelated cartoons or captions."""
import io
import pathlib
import sys
import tempfile
import time
import unittest
import wave
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from app import create_app
from live_video import UnavailableVideo
from storyboard import align_storyboard_to_vocal


class ProductionStoryTests(unittest.TestCase):
    def wave(self):
        buf=io.BytesIO()
        sr=8000;t=np.arange(sr*2)/sr
        x=(.24*np.sin(2*np.pi*230*t)).astype('<f4')
        with wave.open(buf,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
            w.writeframes((x*32000).astype('<i2').tobytes())
        buf.seek(0)
        return buf

    def test_failed_auto_transcription_reports_no_mp4_truthfully(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            response=client.post('/api/jobs',data={
                'audio':(self.wave(),'source.wav'),
                'make_video':'off','video_requested':'on',
                'transcription_failed':'on','transcript':'','seconds':'30'})
            self.assertEqual(response.status_code,202,response.get_json())
            state=None
            for _ in range(140):
                state=client.get(response.get_json()['status_url']).get_json()
                if state.get('state') in ('done','error'):break
                time.sleep(.25)
            self.assertEqual(state['state'],'done',state)
            self.assertEqual(state['video_status'],'unavailable')
            self.assertEqual(state['storyboard_source'],'automatic_transcription_failed')
            self.assertNotIn('video_url',state)
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_no_video_without_original_speech_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            response=client.post('/api/jobs',data={'audio':(self.wave(),'source.wav'),
                'make_video':'on','transcript':''})
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.get_json()['code'],'TRANSCRIPT_REQUIRED')

    def test_no_unrelated_video_when_footage_unavailable_but_audio_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            with patch('app.export_live_story',side_effect=UnavailableVideo(
                'אין צילומים מתאימים לסיפור הזה')):
                response=client.post('/api/jobs',data={'audio':(self.wave(),'voice.wav'),
                   'make_video':'on','transcript':'החמור נוער.','seconds':'30',
                   'transcript_origin':'auto'})
                self.assertEqual(response.status_code,202,response.get_json())
                path=response.get_json()['status_url']
                state=None
                for _ in range(140):
                    state=client.get(path).get_json()
                    if state.get('state') in ('done','error'):break
                    time.sleep(.25)
            self.assertEqual(state['state'],'done',state)
            self.assertEqual(state['video_status'],'unavailable')
            self.assertEqual(state['storyboard_source'],'no_unrelated_video')
            self.assertNotIn('video_url',state)
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_aligned_segments_work_without_visible_subtitles(self):
        story={'transcript':'החמור נוער. החקלאי נותן לחמור אוכל.',
               'scenes':[{'start':0,'end':5,'spoken':'החמור נוער','caption':''},
                         {'start':5,'end':10,'spoken':'החקלאי נותן לחמור אוכל','caption':''}]}
        sr=8000
        t=np.arange(5*sr)/sr
        voice=np.zeros(10*sr,np.float32)
        voice[2*sr:7*sr]=.2*np.sin(2*np.pi*218*t)
        adjusted=align_storyboard_to_vocal(story,voice,sr)
        self.assertEqual(adjusted['alignment'],'vocal_activity_estimated')
        self.assertGreater(adjusted['scenes'][0]['end'],2)
        self.assertEqual(adjusted['scenes'][0]['caption'],'')

if __name__=='__main__':unittest.main()
