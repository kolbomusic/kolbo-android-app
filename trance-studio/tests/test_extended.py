import importlib.util
import pathlib
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("kolbo_engine_extended",ROOT/"backend"/"engine.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

class SpeechCoverageTests(unittest.TestCase):
    def test_late_phrase_is_not_truncated(self):
        sr=8000
        x=np.zeros(sr*14,dtype=np.float32)
        t=np.arange(sr)/sr
        x[:sr]=.3*np.sin(2*np.pi*309*t)
        x[12*sr:13*sr]=.3*np.sin(2*np.pi*531*t)
        clean=engine.prepare_voice(x,sr)
        self.assertGreater(len(clean),sr*12)
        self.assertGreater(float(np.sqrt(np.mean(clean[-sr:]**2))),.015)

    def test_whispered_tail_never_disappears(self):
        sr=8000
        x=np.zeros(sr*11,dtype=np.float32)
        t=np.arange(sr)/sr
        x[:sr]=.48*np.sin(2*np.pi*305*t)
        x[9*sr:10*sr]=.006*np.sin(2*np.pi*643*t)
        prepared=engine.prepare_voice(x,sr)
        self.assertEqual(len(prepared),len(x))
        self.assertGreater(float(np.sqrt(np.mean(prepared[9*sr:10*sr]**2))),0.0001)

    def test_duration_extends_to_include_all_speech(self):
        sr=8000
        t=np.arange(sr*37)/sr
        clip=(.28*np.sin(2*np.pi*317*t)).astype(np.float32)
        out=engine.render_mix([clip],sample_rate=sr,seconds=30,humor="off",style="mixed")
        self.assertGreater(out.shape[0],sr*37)
        self.assertTrue(np.isfinite(out).all())

    def test_speech_cut_points_follow_real_silence(self):
        sr=8000
        x=np.zeros(sr*5,dtype=np.float32)
        x[sr:2*sr]=.25
        x[3*sr:4*sr]=.25
        intervals=engine.speech_boundaries(x,sr)
        self.assertEqual(len(intervals),2)
        self.assertLess(intervals[0][1],intervals[1][0])

    def test_styles_humor_and_melodies_change_mix(self):
        sr=8000
        t=np.arange(sr*3)/sr
        clip=(.26*np.sin(2*np.pi*337*t)).astype(np.float32)
        a=engine.render_mix([clip],sample_rate=sr,seconds=30,style="melodic",melody="1",humor="off")
        b=engine.render_mix([clip],sample_rate=sr,seconds=30,style="goa",melody="4",humor="cartoon")
        self.assertEqual(a.shape,b.shape)
        self.assertGreater(float(np.sqrt(np.mean((a-b)**2))),.005)

    def test_all_genres_and_modes_are_known(self):
        self.assertGreaterEqual(len(engine.STYLES),10)
        self.assertGreaterEqual(len(engine.HUMOR),7)

if __name__=="__main__": unittest.main()
