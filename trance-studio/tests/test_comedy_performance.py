"""Genuine in-word comedy acceptance: no more dry WhatsApp plus music.

Offline, deterministic, no GPU/API fees, and no source voices committed.
Tests assert audible phoneme modification, bounded length, preserved tail,
source alignment, and visible-video edit decisions for the SAME FX times.
"""
import pathlib
import sys
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import engine
from comedy_performance import perform_comic_voice
from beat_video_editor import sync_edit_decisions


class VocalComedyPerformanceTests(unittest.TestCase):
    sr=8000

    def speech(self,seconds=9):
        t=np.arange(int(seconds*self.sr),dtype=np.float32)/self.sr
        signal=(.21*np.sin(2*np.pi*(216*t+.14*np.sin(t*2.2)))+
                .045*np.sin(2*np.pi*426*t)).astype(np.float32)
        signal*=np.where((t%2.2)<1.84,1.,.004).astype(np.float32)
        return signal

    def treatment(self,length=9,humor="auto",intensity=3,word_times=None):
        original=self.speech(length)
        out=np.zeros(len(original)+self.sr*3,dtype=np.float32)
        start=int(.8*self.sr)
        out[start:start+len(original)]=original
        events=perform_comic_voice(
            out,start,[(0,len(original),0,len(original))],
            self.sr,145,humor,intensity,1.5,np.random.default_rng(18),
            engine.vintage_voice_fx,word_times=word_times,
            semantic_cue=engine._semantic_comedy_cue)
        return original,out,start,events

    def test_auto_modifies_real_speech_not_only_inserted_fx(self):
        original,out,start,events=self.treatment()
        self.assertGreaterEqual(len(events),2,events)
        wet=out[start:start+len(original)]
        diff=float(np.sqrt(np.mean((wet-original)**2)))
        self.assertGreater(diff,.035,
            "A user must hear a new character performance DURING words")
        self.assertLess(float(np.max(np.abs(wet))),.99)
        self.assertTrue(np.isfinite(wet).all())
        self.assertTrue(any(e["start_frame"]>start for e in events))
        self.assertGreater(events[-1]["start_frame"],start+3*self.sr)
        # The source duration and original speech tail are never deleted.
        self.assertEqual(len(wet),len(original))
        self.assertGreater(float(np.sqrt(np.mean(wet[-self.sr:]**2))),.04)
        self.assertEqual(len(out),len(original)+3*self.sr)

    def test_no_humor_keeps_original_speech_bit_identical(self):
        original,out,start,events=self.treatment(humor="off")
        self.assertEqual(events,[])
        np.testing.assert_array_equal(out[start:start+len(original)],original)

    def test_the_actual_word_humor_chooses_grounded_monster_voice(self):
        words=[{"start":.4,"end":.9,"text":"החמור"},
               {"start":1.0,"end":1.4,"text":"נוער"},
               {"start":4.3,"end":4.8,"text":"החמור"},
               {"start":5.0,"end":5.4,"text":"נוער"},
               {"start":7.5,"end":8.2,"text":"החמור"}]
        original,out,start,events=self.treatment(word_times=words)
        self.assertTrue(any(e["effect"]=="monster" for e in events),events)

    def test_selected_dj_modes_change_in_word_samples(self):
        original=self.speech(9)
        outputs={}
        for humor in ("helium","monster","pitch","robot","yo_yo","stretch"):
            source=self.speech(9)
            out=np.zeros(len(source)+8000,dtype=np.float32)
            out[:len(source)]=source
            cues=perform_comic_voice(out,0,[(0,len(source),0,len(source))],
                self.sr,145,humor,3,1.4,np.random.default_rng(18),
                engine.vintage_voice_fx)
            self.assertTrue(cues,humor)
            self.assertGreater(
                float(np.sqrt(np.mean((out[:len(source)]-source)**2))),
                .015,humor)
            outputs[humor]=out
        self.assertFalse(np.array_equal(outputs["helium"],outputs["monster"]))
        self.assertFalse(np.array_equal(outputs["pitch"],outputs["robot"]))

    def test_final_mixed_voice_stem_contains_true_in_word_fx(self):
        original=self.speech(8)
        music,stem,timeline=engine.render_mix(
            [original],sample_rate=self.sr,seconds=0,humor="auto",
            fx_intensity=3,fx_gain=1.5,
            return_voice=True,return_video_timeline=True,
            transcript_hint="החמור נוער וכולם צוחקים")
        self.assertEqual(len(music),len(stem))
        self.assertTrue(np.isfinite(music).all())
        modifiers=[e for e in timeline if e["kind"]=="voice_mod"]
        self.assertGreaterEqual(len(modifiers),2,timeline)
        self.assertTrue(all(e["start"]<e["end"] for e in modifiers))
        self.assertTrue(all(0<=e["source_seek"]<8 for e in modifiers))
        # Check explicitly the already-adjusted voice sample against the
        # dry *prepared* source using the 1:1 recorded timestamp mapping.
        prepared=engine.prepare_voice(original,self.sr)
        deviations=[]
        for e in modifiers:
            a=int(round(e["start"]*self.sr))
            b=int(round(e["end"]*self.sr))
            src=int(round(e["source_seek"]*self.sr))
            count=min(b-a,len(prepared)-src)
            if count>int(.16*self.sr):
                deviations.append(float(np.sqrt(np.mean(
                    (stem[a:a+count]-prepared[src:src+count])**2))))
        self.assertGreater(max(deviations),.025)
        self.assertLess(len(music)/self.sr,24)

    def test_video_must_react_to_in_word_audio_without_resetting_source(self):
        cues=[
          {"kind":"voice","source_file":0,"start":1.66,"end":7.66,
           "source_seek":0.,"effect":"auto","intensity":3},
          {"kind":"voice_mod","source_file":0,"start":3.16,"end":3.82,
           "source_seek":1.50,"effect":"helium","intensity":3},
          {"kind":"voice_mod","source_file":0,"start":5.15,"end":5.85,
           "source_seek":3.49,"effect":"monster","intensity":3},
        ]
        cuts=sync_edit_decisions(9,145,7,cues,fx_intensity=3)
        mods=[cut for cut in cuts if cut["kind"]=="voice_mod"]
        self.assertEqual(len(mods),2,cuts)
        self.assertTrue(all(cut["speed"]==1 for cut in mods))
        self.assertGreater(mods[0]["zoom"],1.15)
        self.assertEqual([e["look"] for e in mods],["pitch","stretch"])
        self.assertAlmostEqual(mods[0]["source_seek"],1.5,delta=.04)
        self.assertAlmostEqual(mods[1]["source_seek"],3.49,delta=.04)
        self.assertAlmostEqual(sum(e["duration"] for e in cuts),9.,delta=.08)
        self.assertTrue(all(cuts[i]["start"]<=cuts[i+1]["start"]
                            for i in range(len(cuts)-1)))


if __name__=="__main__":
    unittest.main()
