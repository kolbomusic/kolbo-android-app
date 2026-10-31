"""Production story tests: video must not be unrelated cartoons or captions."""
import io
import hashlib
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
            self.assertEqual(state['video_status'],'unavailable',state)
            self.assertEqual(state['storyboard_source'],'original_asr_failed')
            self.assertEqual(state['visual_coverage'],'none')
            self.assertNotIn('video_url',state)
            self.assertIn('לא ניתן לתמלל',state['video_error'])
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_original_source_fingerprint_detects_mismatched_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            response=client.post('/api/jobs',data={
                'audio':(self.wave(),'source.wav'),'make_video':'off',
                'source_hashes':'0'*64})
            self.assertEqual(response.status_code,409,response.get_json())
            self.assertIn('המקור',response.get_json()['error'])
            self.assertFalse(any(pathlib.Path(directory).iterdir()))

    def test_original_source_fingerprint_accepted_for_identical_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            source=self.wave(); data=source.read()
            response=client.post('/api/jobs',data={
                'audio':(io.BytesIO(data),'source.wav'),
                'source_hashes':hashlib.sha256(data).hexdigest(),
                'make_video':'off','seconds':'30'})
            self.assertEqual(response.status_code,202,response.get_json())

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
            self.assertEqual(state['video_status'],'unavailable',state)
            self.assertEqual(state['storyboard_source'],'no_grounded_story')
            self.assertEqual(state['visual_coverage'],'none')
            self.assertNotIn('video_url',state)
            self.assertIn('אין צילומים',state['video_error'])
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_partial_script_is_not_passed_off_as_full_semantic_movie(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            response=client.post('/api/jobs',data={
                'audio':(self.wave(),'source.wav'),'make_video':'on',
                'transcript':'אני נוסע באוטו. אחר כך קרה משהו שלא זוהה.',
                'transcript_origin':'auto','seconds':'30'})
            self.assertEqual(response.status_code,202,response.get_json())
            state={}
            for _ in range(140):
                state=client.get(response.get_json()['status_url']).get_json()
                if state.get('state') in ('done','error'):break
                time.sleep(.25)
            self.assertEqual(state['state'],'done',state)
            self.assertEqual(state['video_status'],'unavailable',state)
            self.assertNotIn('video_url',state)
            self.assertIn('חלק מהמשפטים',state['video_error'])
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_dense_speech_alignment_never_overflows_video_length(self):
        sr=8000
        duration=2.4
        from live_video import visual_plan
        phrases=['החמור נוער','אני נוסע באוטו']*9
        board=visual_plan('. '.join(phrases),duration)
        t=np.arange(int(sr*duration))/sr
        v=(.25*np.sin(2*np.pi*230*t)).astype(np.float32)
        result=align_storyboard_to_vocal(board,v,sr)
        cuts=result['scenes']
        self.assertEqual(len(cuts),18)
        self.assertTrue(all(sc['end']>sc['start'] for sc in cuts))
        self.assertAlmostEqual(cuts[-1]['end'],duration,places=2)
        self.assertTrue(all(0<=sc['start']<duration for sc in cuts))

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
