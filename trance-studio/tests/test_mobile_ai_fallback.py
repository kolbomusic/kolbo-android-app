"""Phone-generated free AI video: keep voice on Kolbo, private prompts, MP4 mux.

All tests use invented spoken Hebrew and locally synthesized moving frames.
No private WhatsApp media is checked into a public repository.
"""
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
from client_ai_fallback import MobileClipError,combine_mobile_ai_clips,validate_mp4_clip


def sample_audio():
    sr=8000
    t=np.arange(sr*2)/sr
    samples=(np.sin(2*np.pi*343*t)*8500).astype('<i2')
    raw=io.BytesIO()
    with wave.open(raw,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
        w.writeframes(samples.tobytes())
    raw.seek(0)
    return raw


def synthetic_clip(path,kind='testsrc2',seconds=2):
    subprocess.run([
        'ffmpeg','-nostdin','-loglevel','error','-y',
        '-f','lavfi','-i',f'{kind}=size=512x512:rate=16:duration={seconds}',
        '-c:v','libx264','-pix_fmt','yuv420p','-preset','veryfast',
        '-crf','23','-movflags','+faststart',str(path)
    ],check=True,timeout=35)


def completed_job(client,opts, timeout=75):
    r=client.post('/api/jobs',data={'audio':(sample_audio(),'speech.wav'),
                                    'make_video':'on','video_requested':'on',
                                    'transcript':'','transcript_origin':'auto',
                                    'seconds':'30',**opts})
    assert r.status_code==202,r.get_json()
    job=r.get_json()
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        status=client.get(job['status_url']).get_json()
        if status['state'] in ('done','error'):
            return job,status
        time.sleep(.08)
    raise AssertionError('job timed out')


class PhoneAIRecoveryTests(unittest.TestCase):
    def test_no_outside_prompt_or_video_upload_without_original_user_consent(self):
        with tempfile.TemporaryDirectory() as folder,patch(
            'source_asr.transcribe_original_files',
            return_value=('איש זורק כוס זכוכית על הרצפה. הכוס נשברת.',True)):
            app=create_app({'TESTING':True,'JOB_DIR':folder,'API_TOKEN':'test'})
            client=app.test_client()
            job,status=completed_job(client,{'ai_video_consent':'off'})
            self.assertEqual(status['state'],'done',status)
            self.assertNotIn('client_ai_fallback',status)
            self.assertNotIn('prompts',status)
            self.assertNotIn('client_ai_prompt',status)
            self.assertEqual(client.post('/api/jobs/'+job['id']+'/ai-clips',
                                         data={'clip':(io.BytesIO(b'bad'),'clip.mp4')}).status_code,403)

    def test_original_hebrew_audio_to_private_prompt_to_two_video_shots(self):
        spoken='איש זורק כוס זכוכית על הרצפה. הכוס נשברת לרסיסים.'
        with tempfile.TemporaryDirectory() as folder:
            app=create_app({'TESTING':True,'JOB_DIR':folder,'API_TOKEN':'test'})
            client=app.test_client()
            with patch('source_asr.transcribe_original_files',
                       return_value=(spoken,True)),patch(
                'ai_video.generate_ai_story',
                side_effect=AIVideoUnavailable('public GPU quota unavailable')):
                job,status=completed_job(client,{'ai_video_consent':'on'})
            self.assertEqual(status['state'],'done',status)
            self.assertEqual(status['video_status'],'unavailable',status)
            self.assertTrue(status['client_ai_fallback'],status)
            self.assertIn('client_ai_prompt',status)
            self.assertIn('כוס',status['client_ai_prompt'])

            files=[]
            for i,kind in enumerate(('testsrc','testsrc2')):
                p=pathlib.Path(folder)/f'clip-{i}.mp4'
                synthetic_clip(p,kind)
                self.assertGreater(validate_mp4_clip(p),.67)
                files.append(p.read_bytes())
            result=client.post('/api/jobs/'+job['id']+'/ai-clips',data={
                'clip':[(io.BytesIO(data),f'clip-{i}.mp4') for i,data in enumerate(files)]})
            self.assertEqual(result.status_code,200,result.get_json())
            answer=result.get_json()
            self.assertEqual(answer['video_mode'],'ai_generated_client_fallback')
            self.assertEqual(answer['visual_coverage'],'approximate')
            completed=client.get(job['status_url']).get_json()
            self.assertEqual(completed['video_status'],'done',completed)
            self.assertNotIn('video_error',completed)
            self.assertEqual(completed['ai_clips_generated'],2)
            mp4=client.get(completed['video_url'])
            self.assertEqual(mp4.status_code,200)
            media=pathlib.Path(folder)/'output.mp4'
            media.write_bytes(mp4.data)
            probe=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format','-of','json',str(media)]))
            video=next(s for s in probe['streams'] if s['codec_type']=='video')
            self.assertEqual((video['codec_name'],video['width'],video['height']),
                             ('h264',360,640))
            self.assertEqual({s['codec_type'] for s in probe['streams']},
                             {'video','audio'})
            self.assertGreater(float(probe['format']['duration']),29)
            subprocess.run(['ffmpeg','-v','error','-ss','20','-i',str(media),
                            '-frames:v','1','-f','null','-'],check=True)
            self.assertNotIn('client_ai_prompt',completed)
            self.assertEqual(client.get(completed['download_url']).status_code,200)

    def test_compact_but_real_moving_mp4_is_not_mistaken_for_missing_clip(self):
        # Public model clips may compress extremely well. Security comes from
        # ftyp, ffprobe and decoded frame-motion validation, not an arbitrary
        # 12-KB minimum. This intentionally stays below that old threshold.
        with tempfile.TemporaryDirectory() as folder:
            clip=pathlib.Path(folder)/'tiny-moving.mp4'
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','testsrc=size=192x192:rate=8:duration=1.1',
                '-c:v','libx264','-crf','39','-pix_fmt','yuv420p',
                str(clip)
            ],check=True,timeout=30)
            self.assertLess(clip.stat().st_size,12000)
            self.assertGreater(clip.stat().st_size,2048)
            self.assertGreater(validate_mp4_clip(clip),.67)

    def test_three_ordered_real_motion_scenes_follow_original_speech_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            audio=root/'voice-and-trance.mp3'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                            '-f','lavfi','-i','sine=frequency=400:duration=9',
                            '-c:a','libmp3lame',str(audio)],check=True)
            frames=[]
            for i,kind in enumerate(('testsrc','testsrc2','testsrc')):
                p=root/f'original-ai-clip-{i}.mp4'
                synthetic_clip(p,kind,seconds=2)
                frames.append(p)
            video=root/'story.mp4'
            plan=combine_mobile_ai_clips(
                frames,audio,video,root/'encode',weights=[1,2,3])
            self.assertEqual(plan['ai_clips_generated'],3)
            self.assertEqual(plan['pacing_basis'],'original_transcript_spoken_word_counts')
            scenes=plan['scenes']
            self.assertAlmostEqual(scenes[0]['end'],1.5,delta=.3)
            self.assertAlmostEqual(scenes[1]['end'],4.5,delta=.3)
            self.assertAlmostEqual(scenes[2]['end'],9.0,delta=.3)
            self.assertEqual(scenes[-1]['start'],scenes[1]['end'])
            probe=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(video)]))
            stream=next(x for x in probe['streams'] if x['codec_type']=='video')
            self.assertEqual((stream['codec_name'],stream['width'],stream['height']),
                             ('h264',360,640))
            self.assertGreater(float(probe['format']['duration']),8.4)
            subprocess.run(['ffmpeg','-v','error','-ss','6.5','-i',str(video),
                            '-frames:v','1','-f','null','-'],check=True)
            with self.assertRaises(MobileClipError):
                combine_mobile_ai_clips(frames,audio,root/'bad.mp4',
                    root/'invalid-weights',weights=[1,2,float('nan')])

    def test_rejects_fake_mp4_and_never_discards_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app({'TESTING':True,'JOB_DIR':folder,'API_TOKEN':'test'})
            client=app.test_client()
            with patch('source_asr.transcribe_original_files',
                       return_value=('האדם מספר סיפור עם דמויות.',True)),patch(
                'ai_video.generate_ai_story',
                side_effect=AIVideoUnavailable('quota')):
                job,status=completed_job(client,{'ai_video_consent':'on'})
            res=client.post('/api/jobs/'+job['id']+'/ai-clips',data={
                'clip':(io.BytesIO(b'#EXTM3U\\nhttp://127.0.0.1/private'), 'bad.mp4')})
            self.assertEqual(res.status_code,400,res.get_json())
            self.assertEqual(client.get('/api/jobs/'+job['id']+'/audio').status_code,200)
            self.assertTrue(client.get(job['status_url']).get_json()['client_ai_fallback'])
            self.assertNotIn('video_url',client.get(job['status_url']).get_json())

if __name__=='__main__':
    unittest.main()
