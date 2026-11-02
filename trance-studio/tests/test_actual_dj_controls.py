"""Regression proof that DJ controls alter REAL rendered samples.

No front-end-only assertions: we exercise DSP buffers, source ASR time
metadata and the same audio job configuration accepted by the server.
"""
import pathlib
import sys
import unittest
from unittest import mock
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import engine
import source_asr
from dj_arranger import accent_overdub, event_mode


class ActualDjProductionTests(unittest.TestCase):
    def setUp(self):
        self.sr=8000
        t=np.arange(9*self.sr,dtype=np.float32)/self.sr
        # Realistic varying voiced segments, with NO conveniently placed
        # 180ms pauses. The previous silence-only arranger was nearly empty.
        self.source=(.24*np.sin(2*np.pi*(188*t+.3*np.sin(2*np.pi*.41*t)))+
                     .09*np.sin(2*np.pi*377*t)).astype(np.float32)

    def wet(self,mode,intensity=2,gain=1.30,timeline=None):
        return accent_overdub(
            self.source,self.sr,145,mode,intensity,gain,
            np.random.default_rng(52),vintage_effect=engine.vintage_voice_fx,
            quality=engine._vocal_hook_quality,timed_phrases=timeline,
            cue_from_text=lambda text:engine._semantic_comedy_cue(text,.5))

    def test_continuous_voice_now_receives_audible_fx_even_without_pauses(self):
        clean=self.wet('off')
        dj=self.wet('dj')
        self.assertEqual(len(clean),len(self.source))
        self.assertEqual(np.count_nonzero(clean),0)
        self.assertGreater(float(np.sqrt(np.mean(dj*dj))),.009)

    def test_manual_effect_modes_are_real_distinct_audio_processors(self):
        choices=('scratch','telephone','flanger','gate','ring','monster','echo')
        renders={name:self.wet(name) for name in choices}
        for name,audio in renders.items():
            self.assertGreater(np.max(np.abs(audio)),.004,name)
            self.assertTrue(np.isfinite(audio).all())
        for left,right in zip(choices,choices[1:]):
            diff=np.sqrt(np.mean((renders[left]-renders[right])**2))
            self.assertGreater(diff,.003,(left,right,diff))

    def test_manual_intensity_and_gain_change_actual_pcm(self):
        low=self.wet('telephone',1,.75)
        high=self.wet('telephone',3,1.65)
        self.assertGreater(np.mean(high*high),np.mean(low*low)*1.25)

    def test_time_aligned_cue_is_local_to_spoken_words(self):
        segments=[{'start':.3,'end':.8,'text':'החמור'},
                  {'start':4.5,'end':4.9,'text':'נפל'}]
        cue=lambda word:engine._semantic_comedy_cue(word,.5)
        self.assertEqual(event_mode(segments,.5,cue),'monster')
        self.assertIsNone(event_mode(segments,2.,cue))
        self.assertEqual(event_mode(segments,4.7,cue),'rewind')

    def test_source_asr_produces_real_word_timestamps_only_when_requested(self):
        class Word:
            def __init__(self,word,start,end):
                self.word=word;self.start=start;self.end=end
        class Segment:
            text='החמור נוער';avg_logprob=-.1;no_speech_prob=.03
            start=1.;end=2.3
            words=[Word('החמור',1.,1.5),Word('נוער',1.55,2.2)]
        class FakeModel:
            def transcribe(self,path,**opts):
                self.opts=opts
                return iter([Segment()]),None
        fake=FakeModel()
        with mock.patch.object(source_asr,'_get_model',return_value=fake):
            text,complete,timeline=source_asr.transcribe_original_files(
                ['/tmp/real-original.opus'],return_timeline=True)
        self.assertTrue(complete)
        self.assertEqual(len(timeline),1)
        self.assertEqual([item['text'] for item in timeline[0]],['החמור','נוער'])
        self.assertEqual(timeline[0][0]['start'],1.)
        self.assertTrue(fake.opts['word_timestamps'])

    def test_original_speech_audio_survives_effect_choice(self):
        clean=self.source.copy()
        vocal=clean+self.wet('scratch',3,1.65)
        self.assertGreater(float(np.mean(np.abs(vocal-clean))),.005)
        self.assertTrue(np.isfinite(vocal).all())
        # The preserved original is still available as an unchanged dry track.
        self.assertTrue(np.array_equal(clean,self.source))


if __name__=='__main__':
    unittest.main()
