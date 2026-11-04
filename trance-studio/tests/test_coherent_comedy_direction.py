"""Quality-gated comic direction. Short harsh FX and irrelevant stock
footage are failures even if a valid MP3/MP4 was technically produced.
No third-party models, private recordings or paid services are needed.
"""
import pathlib
import sys
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import engine
from comedy_performance import perform_comic_voice
from live_video import (visual_plan,require_faithful_action_footage,
                        UnavailableVideo)


class CoherentComicDirectionTests(unittest.TestCase):
    SR=8000

    def voice(self,seconds,active=None):
        sr=self.SR
        x=np.zeros(int(seconds*sr),dtype=np.float32)
        for index,(a,b) in enumerate(active or [(0.,seconds)]):
            start=int(sr*a);stop=int(sr*b)
            t=np.arange(stop-start,dtype=np.float32)/sr
            # Realistic voiced harmonics at several moving pitches.
            x[start:stop]=.26*np.sin(2*np.pi*(191+index*62)*t)+.055*np.sin(2*np.pi*480*t)
        return x

    def perform(self,x,transcript="",humor="auto",quality=None):
        output=x.copy()
        cues=perform_comic_voice(output,0,[(0,len(x),0,len(x))],
            self.SR,145,humor,3,1.35,np.random.default_rng(32),
            engine.vintage_voice_fx,transcript_hint=transcript,
            semantic_cue=engine._semantic_comedy_cue,quality_fn=quality)
        return output,cues

    def test_five_second_whatsapp_gets_one_full_phrase_not_three_squeaks(self):
        original=self.voice(5.37,[(.3,1.4),(2.4,3.5)])
        result,cues=self.perform(original)
        self.assertEqual(len(cues),1,cues)
        cue=cues[0]
        self.assertEqual(cue["effect"],"stretch")
        self.assertGreater((cue["end_frame"]-cue["start_frame"])/self.SR,.90)
        self.assertEqual(len(result),len(original))
        self.assertTrue(np.isfinite(result).all())
        self.assertGreater(float(np.sqrt(np.mean((result-original)**2))),.008)

    def test_one_story_motif_not_random_cycling_character_palette(self):
        original=self.voice(27,[(0,8),(10,16),(19,26)])
        result,cues=self.perform(original,transcript="הוא סיפר לנו מה קרה בבית")
        self.assertGreaterEqual(len(cues),2,cues)
        self.assertEqual({cue["effect"] for cue in cues},{"stretch"})
        self.assertLessEqual(len(cues),5)
        self.assertLess(float(np.max(np.abs(result))),1.0)

    def test_real_keyword_can_ground_a_single_consistent_comic_character(self):
        x=self.voice(12)
        changed,cues=self.perform(x,transcript="החמור נוער בחוזקה")
        self.assertTrue(cues)
        self.assertEqual({x["effect"] for x in cues},{"monster"})

    def test_no_timed_semantic_word_no_fake_actor_or_sfx(self):
        x=self.voice(6,[(.1,5.7)])
        _,cues=self.perform(x,transcript="נדבר שוב מחר בבוקר")
        self.assertTrue(cues)
        self.assertEqual({x["effect"] for x in cues},{"stretch"})
        self.assertNotIn("robot",{x["effect"] for x in cues})
        self.assertNotIn("helium",{x["effect"] for x in cues})

    def test_auto_music_punchline_is_not_double_layered_stingers(self):
        x=self.voice(9,[(.1,3.),(5.,8.9)])
        mix,vocal,timeline=engine.render_mix(
            [x],sample_rate=self.SR,seconds=0,humor="auto",
            return_voice=True,return_video_timeline=True,fx_intensity=3)
        self.assertTrue(any(e["kind"]=="voice_mod" for e in timeline))
        self.assertFalse(any(e["kind"]=="voice_fx" for e in timeline),
            "Auto voice stingers once competed with in-word voice morphs")
        self.assertLess(len(mix)/self.SR,16)
        self.assertEqual(len(mix),len(vocal))

    def test_source_video_guard_does_not_label_generic_noun_as_action(self):
        board=visual_plan("החמור",8)
        self.assertTrue(board["scenes"])
        with self.assertRaisesRegex(UnavailableVideo,"זוהה נושא כללי"):
            require_faithful_action_footage(board)

    def test_unmatched_chapters_do_not_inherit_unrelated_stock_video(self):
        board=visual_plan("החמור נוער ואז דיברנו על משהו אחר לגמרי",14)
        self.assertGreater(board["unmatched_clauses"],0)
        with self.assertRaisesRegex(UnavailableVideo,"לא זוהו מספיק"):
            require_faithful_action_footage(board)

    def test_grounded_action_can_still_return_real_footage(self):
        board=visual_plan("החמור נוער בחוזקה",8)
        self.assertEqual(board["unmatched_clauses"],0)
        self.assertIs(require_faithful_action_footage(board),board)


if __name__=="__main__":
    unittest.main()
