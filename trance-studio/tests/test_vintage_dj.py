"""Regression tests for vintage DJ processing; short, deterministic offline samples."""
import importlib.util
import pathlib
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trance_dj_engine',ROOT/'backend'/'engine.py')
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class VintageDJTests(unittest.TestCase):
    SR=8000

    def sample(self,seconds=.74):
        t=np.arange(int(self.SR*seconds))/self.SR
        # A modulated voice-like signal with changing syllabic envelope.
        env=.45+.45*np.cos(2*np.pi*3*t)**2
        return (.23*env*(np.sin(2*np.pi*240*t)+.32*np.sin(2*np.pi*465*t))).astype(np.float32)

    def test_stretch_preserves_pitchish_tone_but_changes_length(self):
        clip=self.sample(.62)
        out=engine.stretch_voice(clip,2.0,self.SR)
        self.assertGreater(len(out),len(clip)*1.8)
        self.assertEqual(out.dtype,np.float32)
        self.assertTrue(np.isfinite(out).all())
        self.assertGreater(float(np.sqrt(np.mean(out*out))),.005)

    def test_zero_crossing_can_cut_inside_active_word(self):
        x=self.sample(1.0)
        cut=engine.zero_crossing_cut(x,len(x)//2,self.SR)
        self.assertGreater(cut,len(x)*.47)
        self.assertLess(cut,len(x)*.53)

    def test_tape_stop_and_pitch_shift_are_real(self):
        clip=self.sample()
        stop=engine.tape_stop(clip,self.SR)
        raised=engine.pitch_speed(clip,7,self.SR)
        self.assertLess(len(raised),len(clip))
        self.assertTrue(np.isfinite(stop).all())
        self.assertGreater(float(np.sqrt(np.mean((stop[:1000]-clip[:1000])**2))),.002)
        self.assertLess(float(np.mean(stop[-200:]**2)),float(np.mean(stop[100:300]**2)))

    def test_beat_roll_breaks_and_stutters(self):
        clip=self.sample(1.0)
        roll=engine.broken_roll(clip,self.SR,145,np.random.default_rng(3))
        self.assertGreater(len(roll),int(self.SR*.5))
        self.assertTrue(np.any(roll==0))
        self.assertTrue(np.isfinite(roll).all())

    def test_all_effect_modes_produce_real_nonempty_audio(self):
        clip=self.sample()
        rng=np.random.default_rng(42)
        for mode in engine.HUMOR:
            if mode=='off':continue
            with self.subTest(mode=mode):
                y=engine.vintage_voice_fx(clip,mode,self.SR,145,rng)
                self.assertGreater(len(y),int(.1*self.SR))
                self.assertTrue(np.isfinite(y).all())
                self.assertLessEqual(float(np.max(np.abs(y))),1.01)
                self.assertGreater(float(np.sqrt(np.mean(y*y))),.001)

    def test_intensity_levels_change_arrangement_and_keep_duration(self):
        clip=self.sample(2.1)
        a=engine.render_mix([clip],sample_rate=self.SR,seconds=30,
                            humor='auto',fx_intensity=1,style='mixed')
        b=engine.render_mix([clip],sample_rate=self.SR,seconds=30,
                            humor='auto',fx_intensity=3,style='mixed')
        self.assertEqual(a.shape,b.shape)
        self.assertGreater(float(np.sqrt(np.mean((a-b)**2))),.002)
        for out in (a,b):
            self.assertTrue(np.isfinite(out).all())
            self.assertLessEqual(float(np.max(np.abs(out))),.98)

    def test_invalid_density_is_rejected(self):
        with self.assertRaises(ValueError):
            engine.render_mix([self.sample()],sample_rate=self.SR,
                              seconds=30,fx_intensity=5)

    def test_long_recording_tail_changes_mix_even_with_dj_effects(self):
        sr=self.SR;t=np.arange(sr)/sr
        recording=np.zeros(sr*14,np.float32)
        recording[sr:2*sr]=.26*np.sin(2*np.pi*311*t)
        recording[12*sr:13*sr]=.24*np.sin(2*np.pi*519*t)
        silence_tail=recording.copy()
        silence_tail[12*sr:13*sr]=0
        a=engine.render_mix([recording],sample_rate=sr,seconds=30,humor='auto')
        b=engine.render_mix([silence_tail],sample_rate=sr,seconds=30,humor='auto')
        self.assertEqual(a.shape,b.shape)
        # 12 second phrase lands at ~13.6s after intro; compare this region,
        # excluding any FX turnaround later in the arrangement.
        begin=int((4*60/145+12)*sr)
        end=min(len(a),begin+sr)
        self.assertGreater(float(np.sqrt(np.mean((a[begin:end]-b[begin:end])**2))),.025)

if __name__=='__main__':
    unittest.main()
