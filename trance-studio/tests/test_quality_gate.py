"""Audio acceptance tests; algorithmic checks do not replace human listening."""
import importlib.util
import pathlib
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("kolbo_quality_engine",ROOT/"backend"/"engine.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

class QualityGate(unittest.TestCase):
    sr=8000
    def speech_like(self,seconds):
        sr=self.sr
        t=np.arange(int(sr*seconds))/sr
        # Three speech-like harmonics, loud/quiet phonemes and brief pauses.
        envelope=.12+.18*(.5+.5*np.sin(2*np.pi*.9*t))**2
        envelope*=np.where((t%.95)<.83,1.,.13)
        return (envelope*(np.sin(2*np.pi*187*t)+.35*np.sin(2*np.pi*375*t)
                          +.12*np.sin(2*np.pi*810*t))).astype(np.float32)

    def test_source_speech_is_cleaned_not_crushed(self):
        source=self.speech_like(9)
        got=engine.prepare_voice(source,self.sr)
        self.assertEqual(len(source),len(got))
        self.assertTrue(np.isfinite(got).all())
        # The time alignment and recognizable pitch structure remain intact.
        corr=float(np.corrcoef(source[800:-800],got[800:-800])[0,1])
        self.assertGreater(corr,.77)
        self.assertLess(float(np.max(np.abs(got))),1.0)

    def test_no_deletion_of_ending_when_adding_voice_fx(self):
        original=self.speech_like(21)
        p=engine.vocal_fx_timeline(original,self.sr,145,'auto',3,np.random.default_rng(14))
        self.assertEqual(len(original),len(p))
        self.assertTrue(np.isfinite(p).all())
        for start,end in ((0,4),(9,13),(17,20)):
            a=original[start*self.sr:end*self.sr]
            b=p[start*self.sr:end*self.sr]
            self.assertGreater(float(np.sqrt(np.mean(b*b))),.015)
            self.assertGreater(float(np.corrcoef(a,b)[0,1]),.36)

    def test_music_variations_are_different_and_reproducible(self):
        voice=self.speech_like(2.0)
        a=engine.render_mix([voice],sample_rate=self.sr,seconds=30,
                            humor='off',mix_variation=1)
        b=engine.render_mix([voice],sample_rate=self.sr,seconds=30,
                            humor='off',mix_variation=2)
        c=engine.render_mix([voice],sample_rate=self.sr,seconds=30,
                            humor='off',mix_variation=1)
        self.assertEqual(a.shape,b.shape)
        np.testing.assert_array_equal(a,c)
        self.assertGreater(float(np.sqrt(np.mean((a-b)**2))),.004)

    def test_voice_stem_is_mono_and_distinct_from_music(self):
        voice=self.speech_like(3.)
        full,vocal=engine.render_mix([voice],sample_rate=self.sr,seconds=30,
                            humor='auto',return_voice=True,mix_variation=10)
        self.assertEqual(full.ndim,2)
        self.assertEqual(full.shape[1],2)
        self.assertEqual(vocal.ndim,1)
        self.assertEqual(len(vocal),len(full))
        self.assertGreater(float(np.sqrt(np.mean(vocal*vocal))),.01)

    def test_dynamic_mix_has_safe_peaks(self):
        source=self.speech_like(12)
        a=engine.render_mix([source],sample_rate=self.sr,seconds=60,
                            style='mixed',melody='auto',humor='auto',fx_intensity=3)
        self.assertTrue(np.isfinite(a).all())
        self.assertLessEqual(float(np.max(np.abs(a))),.95)
        self.assertGreater(float(np.sqrt(np.mean(a*a))),.008)

    def test_multiple_original_messages_preserve_order_and_tail(self):
        sr=self.sr
        messages=[self.speech_like(3), self.speech_like(7), self.speech_like(4)]
        a=engine.render_mix(messages,sample_rate=sr,seconds=30,humor='off')
        tail=messages[-1].copy()
        tail[-sr:]*=0
        b=engine.render_mix(messages[:-1]+[tail],sample_rate=sr,seconds=30,humor='off')
        # Differences in late source samples must affect the output; no skip
        # or eight-second clipping of subsequent messages.
        self.assertEqual(a.shape,b.shape)
        self.assertGreater(float(np.sqrt(np.mean((a-b)**2))),.001)

if __name__=='__main__':unittest.main()
