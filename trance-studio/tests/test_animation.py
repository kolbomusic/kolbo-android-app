"""Automated movie acceptance: real moving frames, synchronized audio, Hebrew semantic storyboard."""
import importlib.util, io, json, math, pathlib, subprocess, tempfile, time, unittest, wave, sys
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from storyboard import storyboard, align_storyboard_to_vocal, render_frame, export_animation
from app import create_app

class AnimatedStoryTests(unittest.TestCase):
    def test_storyboard_timing_tracks_speech_not_silent_music(self):
        sr=8000
        voice=np.zeros(sr*12,dtype=np.float32)
        t=np.arange(sr*4)/sr
        voice[2*sr:6*sr]=.25*np.sin(2*np.pi*233*t)
        board=align_storyboard_to_vocal(
            storyboard('נסעתי באוטו. הגעתי לים.',12),voice,sr)
        self.assertEqual(board['alignment'],'vocal_activity_estimated')
        self.assertEqual([x['kind'] for x in board['scenes']],['car','water'])
        # Uniform allocation would split at 6 seconds, close to silence.
        # Voice-aware boundary falls inside the 2-6 second speaking window.
        self.assertGreater(board['scenes'][0]['end'],2.2)
        self.assertLess(board['scenes'][0]['end'],5.7)
        self.assertAlmostEqual(board['scenes'][-1]['end'],12.,places=1)

    def test_unknown_words_never_imply_music_party(self):
        story=storyboard('אני חושב על משהו ולא יודע מה יקרה',18)
        self.assertEqual(story['scenes'][0]['kind'],'speech')
        self.assertEqual(story['scenes'][0]['caption'],'אני חושב על משהו ולא יודע מה יקרה')

    def test_semantic_video_requires_real_speech_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app({'TESTING':True,'JOB_DIR':tmp,'API_TOKEN':'unit-only'})
            c=app.test_client()
            r=c.post('/api/jobs',data={'audio':(io.BytesIO(b'not a wave'),'hebrew.wav'),
                'make_video':'on','transcript':'','seconds':'30'})
            self.assertEqual(r.status_code,422)
            self.assertEqual(r.get_json()['code'],'TRANSCRIPT_REQUIRED')
            self.assertEqual(list(pathlib.Path(tmp).iterdir()),[])

    def test_no_semantic_animation_from_only_one_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app({'TESTING':True,'JOB_DIR':tmp,'API_TOKEN':'unit-only'})
            c=app.test_client()
            r=c.post('/api/jobs',data={'audio':(io.BytesIO(b'bad'),'hebrew.wav'),
                'make_video':'on','transcript':'חמור'})
            self.assertEqual(r.status_code,422)

    def test_semantic_hebrew_scenes_only_with_transcription(self):
        story=storyboard('נסעתי באוטו. הגעתי לים. פגשתי חמור. אחר כך אכלתי פיצה!',30)
        self.assertEqual([x['kind'] for x in story['scenes']],['car','water','animal','food'])
        self.assertIn('provided_transcript',story['source'])
        self.assertEqual(story['scenes'][-1]['end'],30)

    def test_silent_fallback_does_not_fake_recognized_words(self):
        story=storyboard('',13)
        self.assertEqual(story['source'],'audio_reactive_no_transcript')
        self.assertTrue(all(s['kind']=='party' and not s['caption'] for s in story['scenes']))

    def test_real_character_motion_between_successive_frames(self):
        story=storyboard('נסעתי באוטו. ראיתי חמור.',3)
        a=np.asarray(render_frame(.1,story,.2,1))
        b=np.asarray(render_frame(.4,story,.7,4))
        self.assertEqual(a.shape,(640,360,3))
        self.assertGreater(float(np.mean(np.abs(a.astype(float)-b.astype(float)))),1.0)

    def test_direct_mp4_has_video_and_audio_tracks_and_changes_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=pathlib.Path(tmp)
            mp3=tmp/'voice.mp3';out=tmp/'movie.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi',
                            '-i','sine=frequency=300:duration=2.3','-codec:a',
                            'libmp3lame','-q:a','5',str(mp3)],check=True)
            sr=8000;t=np.arange(int(2.3*sr))/sr
            voice=(.22*np.sin(2*np.pi*230*t)).astype(np.float32)
            audio=np.column_stack((voice,voice)).astype(np.float32)
            export_animation(mp3,out,storyboard('רוקדים במסיבה',2.3),
                             audio,voice,sr=sr)
            self.assertGreater(out.stat().st_size,4000)
            probe=json.loads(subprocess.check_output(
                ['ffprobe','-v','quiet','-of','json','-show_streams',str(out)]))
            types=[v['codec_type'] for v in probe['streams']]
            self.assertIn('audio',types);self.assertIn('video',types)
            frames=subprocess.check_output(
                ['ffmpeg','-v','error','-i',str(out),'-vf','fps=2',
                 '-frames:v','3','-f','rawvideo','-pix_fmt','gray','pipe:1'])
            size=360*640
            self.assertGreaterEqual(len(frames),size*2)
            self.assertNotEqual(frames[:size],frames[size:2*size])

    def test_one_click_api_returns_actual_movie_and_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app({'TESTING':True,'JOB_DIR':tmp,'API_TOKEN':'unit-only'})
            c=app.test_client()
            sr=8000;seconds=2
            t=np.arange(sr*seconds)/sr
            x=(.25*np.sin(2*np.pi*230*t)).astype(np.float32)
            buf=io.BytesIO()
            with wave.open(buf,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
                w.writeframes((x*32000).astype('<i2').tobytes())
            buf.seek(0)
            r=c.post('/api/jobs',data={'audio':(buf,'hebrew.wav'),'make_video':'on',
                        'transcript':'אני נוסע באוטו. עכשיו אני בים',
                        'seconds':'30','humor':'auto','fx_intensity':'2'})
            self.assertEqual(r.status_code,202,r.get_json())
            info=r.get_json()
            status=None
            for attempt in range(150):
                status=c.get(info['status_url']).get_json()
                if status.get('state') in ('done','error'):break
                time.sleep(.3)
            self.assertEqual(status.get('state'),'done',status)
            self.assertEqual(status['video_status'],'done',status)
            self.assertIn('video_url',status)
            movie=c.get(status['video_url'])
            self.assertEqual(movie.status_code,200)
            self.assertIn('video/mp4',movie.content_type)
            self.assertGreater(len(movie.data),25000)
            stream=c.get(status['video_preview_url'])
            self.assertEqual(stream.status_code,200)
            self.assertEqual(stream.content_type,'video/mp4')
            self.assertNotIn('attachment',stream.headers.get('Content-Disposition',''))
            board=c.get(status['storyboard_url']).get_json()
            self.assertEqual([x['kind'] for x in board['scenes']],['car','water'])
            self.assertEqual(c.get(status['download_url']).status_code,200)
            self.assertEqual(c.get(status['voice_url']).status_code,200)

if __name__=='__main__':unittest.main()
