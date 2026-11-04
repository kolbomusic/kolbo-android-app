"""Regression of real original-source Hebrew ASR word timing handoff.

The actual recorded voice stays on the user's device or private mixer.
No invented timing when browser recognition fails; JSON is bounded.
"""
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import app as api


class OriginalWordAlignmentTests(unittest.TestCase):
    def test_valid_groups_keep_exact_original_word_times(self):
        expected=[[{"start":0.31,"end":0.82,"text":"החמור"},
                   {"start":0.90,"end":1.47,"text":"נוער"}],[]]
        accepted=api._safe_browser_word_timeline(
            json.dumps(expected,ensure_ascii=False),2)
        self.assertEqual(accepted,expected)

    def test_untrusted_timestamps_are_never_guessed_or_applied(self):
        examples=([
            [{"start":2.0,"end":1.0,"text":"מילה"}],
            [{"start":0.3,"end":301.0,"text":"מילה"}],
            [{"start":0.3,"end":.8,"text":"מילה"},
             {"start":.1,"end":.9,"text":"מילה"}],
            [{"start":0.3,"end":.9,"text":" " * 81}],
            [{"start":float('nan'),"end":2.0,"text":"מילה"}],
        ])
        for group in examples:
            with self.subTest(group=group):
                self.assertIsNone(api._safe_browser_word_timeline(
                    json.dumps([group],ensure_ascii=False),1))
        self.assertIsNone(api._safe_browser_word_timeline('not json',1))
        self.assertIsNone(api._safe_browser_word_timeline('[]',1))
        self.assertIsNone(api._safe_browser_word_timeline('x'*64001,1))

    def test_job_uses_device_word_times_without_second_whisper_pass(self):
        words=[[{"start":0.31,"end":0.82,"text":"החמור"},
                {"start":0.90,"end":1.47,"text":"נוער"}]]
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(api,"ThreadPoolExecutor") as pool:
                application=api.create_app({"TESTING":True,"JOB_DIR":folder})
                client=application.test_client()
                accepted=client.post("/api/jobs",data={
                    "audio":(io.BytesIO(b"voice-bytes"),"test.opus"),
                    "seconds":"0","humor":"auto",
                    "transcript":"החמור נוער כאן","transcript_origin":"auto",
                    "transcript_timeline":json.dumps(words,ensure_ascii=False)})
                self.assertEqual(accepted.status_code,202,accepted.get_json())
                call=pool.return_value.submit.call_args.args
                options=call[3]
                self.assertEqual(options["browser_timeline"],words)
                observed={}
                def render(clips,**kwargs):
                    observed["timeline"]=kwargs["transcript_timeline"]
                    length=32000*4
                    return np.zeros((length,2),np.float32),np.zeros(length,np.float32)
                with mock.patch.object(api,"load_audio",
                        return_value=np.ones(64000,np.float32)*.15), \
                     mock.patch.object(api,"render_mix",side_effect=render), \
                     mock.patch.object(api,"export_mp3",
                        side_effect=lambda x,path,sr=32000:
                            pathlib.Path(path).write_bytes(b"safe-test")), \
                     mock.patch("source_asr.transcribe_original_files",
                        side_effect=AssertionError("unneeded local ASR")):
                    call[0](*call[1:])
                self.assertEqual(observed["timeline"],words)
                status=client.get(accepted.get_json()["status_url"]).get_json()
                self.assertEqual(status["state"],"done",status)


if __name__=="__main__":
    unittest.main()
