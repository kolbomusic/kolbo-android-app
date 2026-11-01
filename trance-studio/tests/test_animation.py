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

    def test_waveform_generator_has_been_removed_from_product(self):
        backend=pathlib.Path(__file__).resolve().parents[1]/'backend'
        self.assertFalse((backend/'voice_visual.py').exists())
        app_source=(backend/'app.py').read_text(encoding='utf-8')
        self.assertNotIn('export_voice_visualizer',app_source)
        self.assertNotIn('showwaves=',app_source)

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
            self.assertIn('תמלול',state['video_error'])
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
        # The request must be accepted first, and a second original-file
        # transcription attempt must run before concluding no grounded MP4.
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            with patch('source_asr.transcribe_original_files',
                       side_effect=RuntimeError('both ASR attempts unavailable')) as asr:
                response=client.post('/api/jobs',data={'audio':(self.wave(),'source.wav'),
                    'make_video':'on','transcript':''})
                self.assertEqual(response.status_code,202,response.get_json())
                state=None
                for _ in range(140):
                    state=client.get(response.get_json()['status_url']).get_json()
                    if state.get('state') in ('done','error'):break
                    time.sleep(.25)
                self.assertTrue(asr.called)
            self.assertEqual(state['state'],'done',state)
            self.assertEqual(state['video_status'],'unavailable',state)
            self.assertNotIn('video_url',state)
            self.assertIn('תמלול',state['video_error'])

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

    def test_partial_story_is_prepared_not_rejected_upfront(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test-only'})
            client=app.test_client()
            def export_checked(music,movie,plan,work,progress):
                self.assertEqual(plan['visual_coverage'],'partial')
                self.assertEqual(plan['unmatched_clauses'],1)
                self.assertEqual(plan['scenes'][0]['action'],'car_drive')
                # A real FFmpeg acceptance is tested in test_live_video.py.
                pathlib.Path(movie).write_bytes(b'0000ftypisom'+b'0'*400)
                return [{'action':'car_drive',
                    'page':'https://commons.wikimedia.org/wiki/File:Car_driving.webm',
                    'license':'CC BY 4.0'}]
            with patch('app.export_live_story',side_effect=export_checked):
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
            self.assertEqual(state['video_status'],'done',state)
            self.assertEqual(state['visual_coverage'],'partial',state)
            self.assertIn('video_url',state)
            self.assertIn('חלק מהמשפטים',state['video_note'])
            self.assertEqual(client.get(state['download_url']).status_code,200)

    def test_personal_transcript_never_leaves_own_server_without_ai_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test'})
            client=app.test_client()
            with patch('ai_video.generate_ai_story') as ai:
                response=client.post('/api/jobs',data={
                    'audio':(self.wave(),'source.wav'),'make_video':'on',
                    'video_requested':'on','ai_video_consent':'off',
                    'transcript':'הלילה סיפרתי סיפור ארוך לאחותי.',
                    'transcript_origin':'auto','seconds':'30'})
                self.assertEqual(response.status_code,202,response.get_json())
                state={}
                for _ in range(140):
                    state=client.get(response.get_json()['status_url']).get_json()
                    if state.get('state') in ('done','error'):
                        break
                    time.sleep(.25)
                self.assertEqual(state['state'],'done',state)
                ai.assert_not_called()
                self.assertEqual(state['video_status'],'unavailable',state)
                self.assertIn('download_url',state)

    def test_opted_in_narration_generates_ai_video_without_any_user_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app({'TESTING':True,'JOB_DIR':directory,'API_TOKEN':'test'})
            client=app.test_client()
            def fake_ai(words,audio,movie,folder,progress):
                self.assertIn('הכוס נשברה',words)
                pathlib.Path(movie).write_bytes(b'0000ftypisom'+b'0'*2000)
                return {'source':'generated_from_original_hebrew_transcript',
                        'video_mode':'ai_generated_experimental',
                        'ai_clips_generated':2,'ai_clip_seconds':3.9,
                        'visual_coverage':'approximate','sources':[],
                        'scenes':[{'action':'ai_generated_narrative'}]}
            with patch('ai_video.generate_ai_story',side_effect=fake_ai) as gen:
                response=client.post('/api/jobs',data={
                    'audio':(self.wave(),'source.wav'),'make_video':'on',
                    'video_requested':'on','ai_video_consent':'on',
                    'transcript':'האיש אמר שהכוס נשברה מול החלון.',
                    'transcript_origin':'auto','seconds':'30'})
                self.assertEqual(response.status_code,202,response.get_json())
                state={}
                for _ in range(140):
                    state=client.get(response.get_json()['status_url']).get_json()
                    if state.get('state') in ('done','error'):
                        break
                    time.sleep(.25)
                self.assertEqual(state['state'],'done',state)
                self.assertTrue(gen.called)
                self.assertEqual(state['video_status'],'done',state)
                self.assertEqual(state['video_mode'],'ai_generated_experimental',state)
                self.assertEqual(state['visual_coverage'],'approximate',state)
                self.assertEqual(state['visual_beats'],2,state)
                self.assertIn('video_url',state)
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
