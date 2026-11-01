"""End-to-end API job recovery with mocked CPU-heavy rendering and no network."""
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import app as server
import source_asr


class VideoJobRecoveryTests(unittest.TestCase):
    def test_pyvav_decoder_error_does_not_destroy_the_music_job(self):
        # PyAV 19 changed av.open() and previously crashed the WHOLE worker.
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(server, 'ThreadPoolExecutor') as executor_factory:
                app=server.create_app({'TESTING':True,'JOB_DIR':temporary})
                client=app.test_client()
                response=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'voice bytes'),'original.opus'),
                    'make_video':'on', 'video_requested':'on',
                    'transcript':'', 'transcript_origin':'auto',
                })
                self.assertEqual(response.status_code,202)
                args=executor_factory.return_value.submit.call_args.args
                voice=np.zeros(32000*5,dtype=np.float32)
                def write_mp3(audio,path,sr=32000):
                    pathlib.Path(path).write_bytes(b'audio-output')
                with (mock.patch.object(source_asr,'transcribe_original_files',
                        side_effect=TypeError("open() got an unexpected keyword argument 'metadata_errors'")),
                      mock.patch.object(server,'load_audio',return_value=voice),
                      mock.patch.object(server,'render_mix',return_value=(voice,voice)),
                      mock.patch.object(server,'export_mp3',side_effect=write_mp3)):
                    args[0](*args[1:])
                result=client.get('/api/jobs/'+response.json['id']).json
                self.assertEqual(result['state'],'done',result)
                self.assertEqual(result['video_status'],'unavailable',result)
                self.assertTrue((pathlib.Path(temporary)/response.json['id']/'mix.mp3').exists())

    def test_server_asr_failure_recovery_keeps_mp4_requested_and_finishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(server, 'ThreadPoolExecutor') as executor_factory:
                app=server.create_app({'TESTING':True,'JOB_DIR':temporary})
                client=app.test_client()
                response=client.post('/api/jobs',data={
                    'audio':(io.BytesIO(b'original phone recording'),'voice.opus'),
                    'make_video':'on','video_requested':'on',
                    'transcript':'','transcript_origin':'auto'
                })
                self.assertEqual(response.status_code,202)
                job_id=response.json['id']
                args=executor_factory.return_value.submit.call_args.args
                work=args[0]
                voice=np.zeros(32000*5,dtype=np.float32)
                sources=[{
                    'action':'donkey_bray',
                    'page':'https://commons.wikimedia.org/wiki/File:Braying_donkey.webm',
                    'license':'CC0'
                }]
                def create_mp3(audio,path,sr=32000):
                    pathlib.Path(path).write_bytes(b'test-encoded-audio')
                def create_video(audio,output,board,work_dir,progress=None):
                    pathlib.Path(output).write_bytes(b'test-mp4')
                    return sources
                with (mock.patch.object(source_asr,'transcribe_original_files',
                                        return_value=('החמור נוער בחוזקה',True)),
                      mock.patch.object(server,'load_audio',return_value=voice),
                      mock.patch.object(server,'render_mix',return_value=(voice,voice)),
                      mock.patch.object(server,'export_mp3',side_effect=create_mp3),
                      mock.patch.object(server,'export_live_story',side_effect=create_video)):
                    work(*args[1:])
                final=client.get('/api/jobs/'+job_id)
                self.assertEqual(final.status_code,200)
                job=final.json
                self.assertEqual(job['state'],'done',job)
                self.assertEqual(job['video_status'],'done',job)
                self.assertEqual(job['transcript_origin'],'server_original_asr')
                self.assertIn('/video',job['video_url'])
                self.assertTrue((pathlib.Path(temporary)/job_id/'story.mp4').exists())


if __name__=='__main__':
    unittest.main()
