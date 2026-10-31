"""Distinguish actual WhatsApp vocal processing from background melody processing."""
import importlib.util
import pathlib
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('vocal_timeline',ROOT/'backend'/'engine.py')
eng=importlib.util.module_from_spec(spec);spec.loader.exec_module(eng)

class VoiceAndMelodyTests(unittest.TestCase):
    def voice(self,sr=8000,seconds=12):
        t=np.arange(sr*seconds,dtype=np.float32)/sr
        # Alternating active speech-like vowels and pauses across the timeline.
        env=np.where((t%1.35)<1.04,.42,.002)
        return (env*(np.sin(2*np.pi*231*t)+.33*np.sin(2*np.pi*492*t))).astype(np.float32)

    def test_fx_processed_at_source_time_not_only_after_recording(self):
        sr=8000;x=self.voice(sr,12)
        rng=np.random.default_rng(42)
        y=eng.vocal_fx_timeline(x,sr,145,'auto',3,rng)
        self.assertEqual(len(y),len(x))
        self.assertTrue(np.isfinite(y).all())
        # Must affect the beginning, middle, and later portions, all INSIDE
        # original speech, with pronounced effect not a nearly inaudible echo.
        for a,b in ((1,3),(5,8),(9,11)):
            difference=np.sqrt(np.mean((x[a*sr:b*sr]-y[a*sr:b*sr])**2))
            self.assertGreater(float(difference),.009,(a,b,difference))

    def test_off_returns_untouched_voice(self):
        x=self.voice()
        np.testing.assert_array_equal(eng.vocal_fx_timeline(x,8000,145,'off',3,np.random.default_rng(5)),x)

    def test_voice_is_forward_with_and_without_music(self):
        sr=8000;v=self.voice(sr,12)
        a=eng.render_mix([v],sample_rate=sr,seconds=30,humor='off',style='melodic',melody='1')
        b=eng.render_mix([v],sample_rate=sr,seconds=30,humor='auto',fx_intensity=3,style='melodic',melody='1')
        # Same deterministic source, genre, melody. Difference is vocal effects.
        start=int((4*60/145+1)*sr);end=int((4*60/145+11)*sr)
        self.assertGreater(float(np.sqrt(np.mean((a[start:end]-b[start:end])**2))),.01)
        # Music intro before speech remains the same (the original voice was
        # never fed to the synth or drums).
        self.assertLess(float(np.sqrt(np.mean((a[:int(sr*.6)]-b[:int(sr*.6)])**2))),.003)

    def test_auto_music_has_distinct_sections(self):
        sr=8000;clip=self.voice(sr,2)
        a=eng.render_mix([clip],sample_rate=sr,seconds=45,humor='off',melody='auto',style='mixed')
        b=eng.render_mix([clip],sample_rate=sr,seconds=45,humor='off',melody='1',style='mixed')
        self.assertEqual(a.shape,b.shape)
        # The distinctive four-bar sectional arrangement must not equal
        # keeping one motif fixed for the entire 45s piece.
        self.assertGreater(float(np.sqrt(np.mean((a[18*sr:32*sr]-b[18*sr:32*sr])**2))),.01)

if __name__=='__main__':unittest.main()
