"""Regressions for local child-process ASR with bounded IPC."""
import json
import pathlib
import sys
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from isolated_asr import transcribe_in_child, IsolatedAsrUnavailable


class IsolatedAsrTests(unittest.TestCase):
    def test_transcript_and_word_timestamps_return_without_resident_model(self):
        payload={"text":"המשאית נוסעת עכשיו","complete":True,
                 "timeline":[[{"start":0.5,"end":1.3,"text":"המשאית"}]]}
        with mock.patch("isolated_asr.subprocess.run",
                        return_value=SimpleNamespace(stdout=json.dumps(payload))) as run:
            words,complete,timeline=transcribe_in_child(
                [ROOT/"tests"/"example.opus"])
        self.assertEqual(words,"המשאית נוסעת עכשיו")
        self.assertTrue(complete)
        self.assertEqual(timeline[0][0]["start"],0.5)
        args,kwargs=run.call_args
        self.assertEqual(args[0][0],sys.executable)
        self.assertTrue(args[0][1].endswith("isolated_asr.py"))
        self.assertNotIn("shell",kwargs)
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])

    def test_failed_model_worker_does_not_cancel_audio_mixing(self):
        with mock.patch("isolated_asr.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("asr",240)):
            with self.assertRaises(IsolatedAsrUnavailable):
                transcribe_in_child([ROOT/"tests"/"example.opus"])

    def test_rejects_oversized_or_mismatched_child_timing(self):
        invalid={"text":"דיבור אמיתי","complete":True,"timeline":[[],[]]}
        with mock.patch("isolated_asr.subprocess.run",
                        return_value=SimpleNamespace(stdout=json.dumps(invalid))):
            with self.assertRaises(IsolatedAsrUnavailable):
                transcribe_in_child([ROOT/"tests"/"example.opus"])

    def test_backend_frees_mixer_arrays_before_video(self):
        src=(ROOT/"backend"/"app.py").read_text(encoding="utf-8")
        self.assertIn("transcribe_in_child(paths)",src)
        self.assertIn("del audio, rendered, clips",src)
        self.assertLess(src.index("del audio, rendered, clips"),
                        src.index("if options.get('video_requested'):",src.index("del audio, rendered, clips")))
        self.assertIn("version='1.16.18'",src)

    def test_original_audio_is_unloaded_while_local_whisper_child_runs(self):
        src=(ROOT/"backend"/"app.py").read_text(encoding="utf-8")
        first=src.index("clips=[load_audio(p) for p in paths]")
        unload=src.index("del clips",first)
        asr=src.index("asr_result=transcribe_in_child(paths)",unload)
        reload=src.index("clips=[load_audio(p) for p in paths]",asr)
        mixer=src.index("rendered=render_mix(clips",reload)
        self.assertLess(first,unload)
        self.assertLess(unload,asr)
        self.assertLess(asr,reload)
        self.assertLess(reload,mixer)
        self.assertIn("isolated_original_asr",src)
        self.assertIn("app.config.get('TESTING')",src)

    def test_free_docker_preloads_small_multilingual_model_offline(self):
        docker=(ROOT/"Dockerfile").read_text(encoding="utf-8")
        self.assertIn("KOLBO_ASR_MODEL=tiny",docker)
        self.assertIn("KOLBO_ASR_DIR=/opt/kolbo-asr/tiny",docker)
        self.assertIn("download_model('tiny'",docker)
        self.assertNotIn("download_model('base'",docker)

    def test_memory_guard_avoids_oom_kill_before_asr_child(self):
        import isolated_asr
        with mock.patch.object(isolated_asr,"_safe_memory_for_asr",return_value=False):
            with mock.patch("isolated_asr.subprocess.run") as run:
                with self.assertRaises(IsolatedAsrUnavailable):
                    transcribe_in_child([ROOT/"tests"/"example.opus"])
                run.assert_not_called()

    def test_cgroup_memory_guard_uses_read_only_usage_and_limit(self):
        import isolated_asr
        def contents(self):
            if str(self).endswith("memory.max"):
                return str(512*1024*1024)
            if str(self).endswith("memory.current"):
                return str(330*1024*1024)
            raise OSError("unknown cgroup path")
        with mock.patch.object(pathlib.Path,"read_text",contents):
            self.assertFalse(isolated_asr._safe_memory_for_asr())
        def roomy(self):
            if str(self).endswith("memory.max"):
                return str(512*1024*1024)
            if str(self).endswith("memory.current"):
                return str(150*1024*1024)
            raise OSError("unknown cgroup path")
        with mock.patch.object(pathlib.Path,"read_text",roomy):
            self.assertTrue(isolated_asr._safe_memory_for_asr())


if __name__=="__main__":
    unittest.main()
