"""Regression coverage: browser ASR failure must NOT preempt MP4 preparation."""
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

import app as server
import source_asr


class SourceAsrRecoveryTests(unittest.TestCase):
    def test_preloaded_model_is_used_without_online_download(self):
        with tempfile.TemporaryDirectory() as temp:
            pathlib.Path(temp, 'model.bin').write_bytes(b'preloaded model marker')
            with (mock.patch.dict('os.environ',{'KOLBO_ASR_DIR':temp}),
                  mock.patch('faster_whisper.WhisperModel') as ctor):
                old_model=source_asr._MODEL
                try:
                    source_asr._MODEL=None
                    source_asr._get_model()
                    self.assertEqual(ctor.call_args.args[0],temp)
                    ctor.assert_called_once()
                finally:
                    source_asr._MODEL=old_model

    def test_native_android_hands_off_to_server_before_heavy_browser_asr(self):
        page=(ROOT/'web'/'studio.html').read_text(encoding='utf-8')
        self.assertIn('if(window.KolboAndroid)',page)
        self.assertIn("form.set('make_video',wantsVideo?'on':'off')",page)
        self.assertIn("form.set('transcript',verifyTranscript(recognized)?recognized:'')",page)

    def test_original_utterances_are_used_not_music(self):
        class FakeSegment:
            def __init__(self, text): self.text=text
        class FakeModel:
            def transcribe(self, path, **kwargs):
                self.last=(path,kwargs)
                return iter([FakeSegment('החמור נוער בחוזקה')]), None
        fake=FakeModel()
        with mock.patch.object(source_asr,'_get_model',return_value=fake):
            transcript,completed=source_asr.transcribe_original_files(
                [pathlib.Path('/tmp/original.opus')])
        self.assertEqual(transcript,'החמור נוער בחוזקה')
        self.assertTrue(completed)
        self.assertEqual(fake.last[0],'/tmp/original.opus')
        self.assertEqual(fake.last[1]['language'],'he')

    def test_partial_recognition_never_invents_missing_speech(self):
        class FakeSegment:
            text='החקלאי מאכיל חיות'
        class FakeModel:
            def transcribe(self,path,**kwargs):
                if 'bad' in path: raise RuntimeError('decoder failed')
                return iter([FakeSegment()]), None
        with mock.patch.object(source_asr,'_get_model',return_value=FakeModel()):
            transcript,complete=source_asr.transcribe_original_files(
                ['/tmp/good.opus','/tmp/bad.opus'])
        self.assertEqual(transcript,'החקלאי מאכיל חיות')
        self.assertFalse(complete)

    def test_nonsense_is_never_visualized_as_real_words(self):
        self.assertFalse(source_asr._valid_utterance('blah blah'))
        self.assertFalse(source_asr._valid_utterance('חמור חמור'))
        self.assertTrue(source_asr._valid_utterance('החמור נוער'))

    def test_short_hebrew_speech_retried_without_vad(self):
        class FakeSegment:
            text = "הנה המשאית נוסעת"
        class FakeModel:
            def __init__(self): self.calls = []
            def transcribe(self, path, **kwargs):
                self.calls.append((str(path), kwargs['vad_filter']))
                return (iter([]) if kwargs['vad_filter']
                        else iter([FakeSegment()])), None
        fake = FakeModel()
        with (mock.patch.object(source_asr, '_get_model', return_value=fake),
              mock.patch.object(source_asr, '_clean_voice') as normalize):
            transcript, complete = source_asr.transcribe_original_files(['/tmp/whatsapp.opus'])
        self.assertTrue(complete)
        self.assertEqual(transcript, 'הנה המשאית נוסעת')
        self.assertEqual(fake.calls, [('/tmp/whatsapp.opus', True),
                                      ('/tmp/whatsapp.opus', False)])
        normalize.assert_not_called()

    def test_normalized_original_retry_when_vad_free_pass_fails(self):
        class FakeSegment:
            text = "הכלב נובח בבית"
        class FakeModel:
            def __init__(self): self.paths = []
            def transcribe(self, path, **kwargs):
                self.paths.append(str(path))
                return iter([FakeSegment()] if str(path).endswith('normalized.wav') else []), None
        fake = FakeModel()
        with tempfile.TemporaryDirectory() as directory:
            wav = pathlib.Path(directory, 'normalized.wav')
            wav.touch()
            with (mock.patch.object(source_asr, '_get_model', return_value=fake),
                  mock.patch.object(source_asr, '_clean_voice', return_value=wav)):
                transcript, complete = source_asr.transcribe_original_files(['/tmp/from-whatsapp.opus'])
            self.assertEqual(transcript, 'הכלב נובח בבית')
            self.assertTrue(complete)
            self.assertEqual(fake.paths, ['/tmp/from-whatsapp.opus'] * 2 + [str(wav)])
            self.assertFalse(wav.exists())

    def test_reject_explicit_low_confidence_even_when_text_is_hebrew(self):
        class FakeSegment:
            text = "המשאית נוסעת עכשיו"
            avg_logprob = -2.3
            no_speech_prob = 0.12
        class FakeModel:
            def transcribe(self, path, **kwargs): return iter([FakeSegment()]), None
        self.assertEqual(source_asr._recognize(FakeModel(), '/tmp/audio.opus', use_vad=False), '')

    def test_missing_browser_transcript_submits_video_request_without_422(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(server,'ThreadPoolExecutor') as factory:
                application=server.create_app({'TESTING':True,'JOB_DIR':temp})
                response=application.test_client().post('/api/jobs',data={
                    'audio':(io.BytesIO(b'example original media bytes'),'voice.opus'),
                    'transcript':'',
                    'transcript_origin':'auto',
                    'make_video':'on',
                    'video_requested':'on',
                })
                self.assertEqual(response.status_code,202,response.get_data(as_text=True))
                options=factory.return_value.submit.call_args.args[3]
                self.assertTrue(options['make_video'])
                self.assertTrue(options['video_requested'])
                self.assertFalse(options['transcript'])


if __name__=='__main__':
    unittest.main()
