import importlib.util
import pathlib
import unittest
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT/'backend'/'engine.py').exists(), 'Python remix engine is missing'
        spec = importlib.util.spec_from_file_location('engine', ROOT/'backend'/'engine.py')
        if spec is None:
            raise AssertionError('Python remix engine is missing')
        cls.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.engine)

    def test_render_is_finite_stereo_and_exact_length(self):
        sr = 8000
        t = np.arange(sr*2)/sr
        voice = (0.35*np.sin(2*np.pi*337*t)).astype(np.float32)
        x = self.engine.render_mix([voice], sample_rate=sr, seconds=30, bpm=145)
        self.assertEqual(x.shape, (sr*30, 2))
        self.assertTrue(np.isfinite(x).all())
        self.assertLessEqual(float(np.abs(x).max()), 0.981)
        self.assertGreater(float(np.sqrt(np.mean(x*x))), 0.03)

    def test_original_voice_changes_render(self):
        sr=8000
        t=np.arange(sr)/sr
        a=self.engine.render_mix([np.sin(2*np.pi*337*t).astype(np.float32)*.2],sample_rate=sr,seconds=30)
        b=self.engine.render_mix([np.sin(2*np.pi*619*t).astype(np.float32)*.2],sample_rate=sr,seconds=30)
        self.assertGreater(float(np.sqrt(np.mean((a-b)**2))),.02)

    def test_silence_and_bad_settings_are_rejected(self):
        for opts in ({'bpm':0},{'seconds':900},{'style':'other'}):
            with self.assertRaises(ValueError):
                self.engine.render_mix([np.ones(8000,dtype=np.float32)*.1],sample_rate=8000,**opts)
        with self.assertRaises(ValueError):
            self.engine.render_mix([np.zeros(8000,dtype=np.float32)],sample_rate=8000)

if __name__=='__main__':unittest.main()
