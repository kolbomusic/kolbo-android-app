"""Scene changes use real word boundaries mapped through DJ source spans."""
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from word_scene_alignment import align_storyboard_to_source_words


class GroundedSceneTimingTests(unittest.TestCase):
    def test_scene_cuts_follow_actual_hebrew_word_times_in_export(self):
        # The initial 1.6s musical intro is NOT part of the source timeline.
        segments=[{"kind":"voice","source_file":0,
                   "start":1.6,"end":7.6,"source_seek":0.}]
        transcript=[[{"start":.2,"end":.65,"text":"החמור"},
                     {"start":.8,"end":1.2,"text":"נוער"},
                     {"start":1.45,"end":1.9,"text":"בדיוק"},
                     {"start":2.9,"end":3.3,"text":"החקלאי"},
                     {"start":3.9,"end":4.3,"text":"מגיש"},
                     {"start":5.1,"end":5.5,"text":"קש"}]]
        board={"scenes":[
            {"spoken":"החמור נוער בדיוק","start":0.,"end":4.},
            {"spoken":"החקלאי מגיש קש","start":4.,"end":10.}
        ]}
        self.assertTrue(align_storyboard_to_source_words(
            board,transcript,segments,10.))
        self.assertAlmostEqual(board["scenes"][0]["end"],1.6+2.9,places=2)
        self.assertEqual(board["scenes"][1]["start"],
                         board["scenes"][0]["end"])
        self.assertEqual(board["scenes"][-1]["end"],10.)
        self.assertEqual(board["alignment"],"original_source_word_timestamps")

    def test_incomplete_or_missing_timing_never_mutates_storyboard(self):
        empty={"scenes":[{"spoken":"החמור נוער","start":0.,"end":3.},
                         {"spoken":"החקלאי מגיש","start":3.,"end":7.}]}
        original=[dict(s) for s in empty["scenes"]]
        self.assertFalse(align_storyboard_to_source_words(empty,[],[],7.))
        self.assertEqual(empty["scenes"],original)
        words=[[{"start":1.,"end":1.5,"text":"נוער"}]]
        self.assertFalse(align_storyboard_to_source_words(empty,words,
            [{"kind":"voice","source_file":0,
              "start":0.,"end":1.,"source_seek":0.}],7.))
        self.assertEqual(empty["scenes"],original)

    def test_second_whatsapp_file_gets_its_own_output_position(self):
        segments=[{"kind":"voice","source_file":0,
                   "start":1.,"end":3.,"source_seek":0.},
                  {"kind":"voice","source_file":1,
                   "start":5.,"end":7.,"source_seek":0.}]
        spoken=[[{"start":.3,"end":.6,"text":"החמור"},
                 {"start":.7,"end":1.,"text":"נוער"}],
                [{"start":.1,"end":.4,"text":"הכלב"},
                 {"start":.6,"end":1.,"text":"נובח"}]]
        board={"scenes":[{"spoken":"החמור נוער","start":0,"end":5},
                         {"spoken":"הכלב נובח","start":5,"end":8}]}
        self.assertTrue(align_storyboard_to_source_words(board,spoken,segments,8.))
        self.assertAlmostEqual(board["scenes"][0]["end"],5.1,places=2)
