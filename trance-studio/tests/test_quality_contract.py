"""Offline acoustic acceptance checks: all sound families and sensible timing.

These cannot certify that an edit is funny; they catch broken output,
overlong filler, unchanged controls, clipping and loss of the final voice.
No real user recordings are committed to this public repository.
"""
import pathlib
import sys
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import engine


class QualityContractTests(unittest.TestCase):
    sr=8000

    def voice(self,seconds,base=211):
        sr=self.sr
        t=np.arange(round(seconds*sr),dtype=np.float32)/sr
        voiced=(np.sin(2*np.pi*(base*t+.22*np.sin(t*2.1)))+
                .23*np.sin(2*np.pi*(base*2.06*t)))*.18
        # Meaningful consonant-like varying accents + real short silences.
        envelope=(.4+.6*np.sin(2*np.pi*3.3*t)**2)
        gaps=np.where((t%2.4)>.28,1.,.01).astype(np.float32)
        return (voiced*envelope*gaps).astype(np.float32)

    def test_two_short_whatsapp_notes_do_not_create_empty_60s_bed(self):
        clips=[self.voice(6.84,217),self.voice(5.38,257)]
        music,stem=engine.render_mix(
            clips,sample_rate=self.sr,seconds=0,humor="auto",
            fx_intensity=2,return_voice=True)
        duration=len(music)/self.sr
        self.assertGreater(duration,13,
            "All original spoken sentences plus punchlines need room")
        self.assertLess(duration,26,
            "Auto-duration must not make 12 seconds of speech into a minute")
        self.assertEqual(len(stem),len(music))
        self.assertTrue(np.isfinite(music).all())
        self.assertLess(float(np.max(np.abs(music))),.97)
        self.assertGreater(float(np.sqrt(np.mean(stem[-7*self.sr:]**2))),.018,
            "Last WhatsApp recording must remain audible in the final output")

    def test_explicit_minute_is_never_silently_changed(self):
        result=engine.render_mix([self.voice(6.8)],sample_rate=self.sr,
                 seconds=60,humor="auto")
        self.assertEqual(len(result),60*self.sr)

    def test_auto_long_note_keeps_final_speech_and_no_extra_30s_padding(self):
        audio=engine.render_mix([self.voice(27)],sample_rate=self.sr,
                 seconds=0,humor="auto")
        self.assertGreater(len(audio)/self.sr,27)
        self.assertLess(len(audio)/self.sr,36,
            "Auto-length should track the source, not add 30s of empty music")

    def test_each_named_voice_effect_changes_pcm_without_nonfinite_values(self):
        original=self.voice(.95)
        for name in engine.HUMOR:
            if name=="off":
                continue
            with self.subTest(name=name):
                effected=engine.vintage_voice_fx(original,name,self.sr,145,
                                                  np.random.default_rng(25))
                self.assertGreater(len(effected),int(.08*self.sr))
                self.assertTrue(np.isfinite(effected).all())
                self.assertLessEqual(np.max(np.abs(effected)),1.01)
                common=min(len(original),len(effected))
                self.assertGreater(float(np.sqrt(np.mean(
                    (effected[:common]-original[:common])**2))),.002,
                    "An advertised sound mode must affect real PCM samples")

    def test_all_named_music_styles_are_audible_and_not_identical(self):
        source=self.voice(2.5)
        sounds=[]
        for style in engine.STYLES:
            result=engine.render_mix([source],sample_rate=self.sr,
                  seconds=0,humor="auto",style=style,mix_variation=12)
            self.assertTrue(np.isfinite(result).all(),style)
            self.assertGreater(float(np.sqrt(np.mean(result**2))),.025,style)
            self.assertLess(float(np.max(np.abs(result))),.98,style)
            sounds.append(result)
        # Distinct style controls must not all return the exact same mix.
        distinct=set()
        for render in sounds:
            distinct.add((round(float(np.sum(render[::97])),2),
                          round(float(np.std(render)),4)))
        self.assertGreaterEqual(len(distinct),7,
            "Most of the style selector choices must produce unique output")

    def test_six_melody_choices_affect_actual_audio_not_just_ui(self):
        source=self.voice(2.5)
        variations=[]
        for melody in ("1","2","3","4","5","6"):
            output=engine.render_mix([source],sample_rate=self.sr,
                      seconds=0,humor="off",melody=melody)
            variations.append(output)
        signatures={(round(float(np.sum(x[::101])),3),
                     round(float(np.std(x)),4)) for x in variations}
        self.assertGreaterEqual(len(signatures),5)


if __name__=="__main__":
    unittest.main()
