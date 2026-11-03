"""Render 512 MiB: failed heavy DSP child must not erase a voice recording."""
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest import mock
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import isolated_mix

def create_source(folder, duration=2):
    path=pathlib.Path(folder)/"recording.wav"
    sr=8000
    t=np.arange(int(sr*duration),dtype=np.float32)/sr
    with wave.open(str(path),"wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sr)
        out.writeframes((np.sin(2*np.pi*360*t)*9500).astype("<i2").tobytes())
    return path

def opts():
    return {"seconds":30,"bpm":145,"style":"mixed","melody":"auto",
            "humor":"off","fx_intensity":1,"fx_gain":1.15,
            "mix_variation":0,"voice_level":1}

class IsolatedMixTests(unittest.TestCase):
    def test_memory_budget_does_not_start_child_and_still_delivers_full_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            original=create_source(temp,2.5)
            folder=pathlib.Path(temp)/"job"
            folder.mkdir()
            with mock.patch.object(isolated_mix,"_memory_allows_heavy_mix",return_value=False):
                with mock.patch.object(isolated_mix.sys,"executable","/invalid/should-not-run"):
                    result=isolated_mix.process_in_child([original],opts(),folder)
            self.assertEqual(result["mix_quality"],"voice_rescue")
            self.assertAlmostEqual(result["audio_seconds"],2.5,delta=.14)
            self.assertTrue((folder/"mix.mp3").is_file())
            self.assertTrue((folder/"voice.mp3").is_file())
            self.assertFalse((folder/".private-mix-options.json").exists())

    def test_child_kill_is_caught_and_voice_only_rescue_survives(self):
        with tempfile.TemporaryDirectory() as temp:
            original=create_source(temp,2)
            folder=pathlib.Path(temp)/"job"
            folder.mkdir()
            subprocess_real=subprocess.run
            attempts=[]
            def process(args,*a,**k):
                if args[0]==sys.executable and str(args[1]).endswith("isolated_mix.py"):
                    attempts.append("heavy")
                    raise subprocess.CalledProcessError(137,args)
                return subprocess_real(args,*a,**k)
            with mock.patch.object(isolated_mix,"_memory_allows_heavy_mix",return_value=True):
                with mock.patch.object(isolated_mix.subprocess,"run",side_effect=process):
                    result=isolated_mix.process_in_child([original],opts(),folder)
            self.assertEqual(attempts,["heavy"])
            self.assertEqual(result["mix_quality"],"voice_rescue")
            self.assertAlmostEqual(result["audio_seconds"],2,delta=.14)
            self.assertFalse((folder/".private-mix-options.json").exists())

    def test_full_isolated_dj_workflow_produces_real_mp3_and_terminates_child(self):
        with tempfile.TemporaryDirectory() as temp:
            original=create_source(temp,1.5)
            folder=pathlib.Path(temp)/"job"
            folder.mkdir()
            with mock.patch.object(isolated_mix,"_memory_allows_heavy_mix",return_value=True):
                result=isolated_mix.process_in_child(
                    [original],opts(),folder,timeout=150)
            self.assertEqual(result["mix_quality"],"full_dj")
            self.assertGreater(result["audio_seconds"],30)
            self.assertGreater((folder/"mix.mp3").stat().st_size,40_000)
            self.assertGreater((folder/"voice.mp3").stat().st_size,10_000)
            self.assertFalse((folder/".private-mix-options.json").exists())

    def test_cgroup_low_headroom_returns_false(self):
        def low(self):
            if str(self).endswith("memory.max"):return str(512*1024*1024)
            if str(self).endswith("memory.current"):return str(380*1024*1024)
            raise OSError("not here")
        with mock.patch.object(pathlib.Path,"read_text",low):
            self.assertFalse(isolated_mix._memory_allows_heavy_mix())

    def test_product_app_uses_child_only_outside_test_mode(self):
        app=(ROOT/"backend"/"app.py").read_text(encoding="utf-8")
        self.assertIn("app.config.get('TESTING') or os.environ.get('KOLBO_MIX_ISOLATED')=='0'",app)
        self.assertIn("result=process_in_child(",app)
        self.assertIn("mix_quality=result['mix_quality']",app)
        self.assertIn("version='1.16.20'",app)


if __name__=="__main__":unittest.main()
