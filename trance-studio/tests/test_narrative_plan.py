"""Precision regressions: preserve spoken chronology, subjects and negations.

No customer audio/text is used; all fictional Hebrew samples are synthetic.
"""
import sys
import pathlib
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from narrative_plan import (
    narrative_beats,scene_prompts,scene_weights,scene_prompt,MAX_STORY_SCENES,
)
from ai_video import _narrative_shots


class NarrativePlanTests(unittest.TestCase):
    def test_farmer_donkey_pitchfork_hay_happens_in_spoken_order(self):
        words=('החמור נוער בקול חזק. אחר כך החקלאי עם קלשון '
               'מגיש לחמור קש. לבסוף החמור אוכל את הקש.')
        scenes=narrative_beats(words)
        self.assertEqual(len(scenes),3)
        self.assertIn('חמור',scenes[0].spoken_text)
        self.assertIn('חקלאי',scenes[1].spoken_text)
        self.assertIn('אוכל',scenes[2].spoken_text)
        self.assertIn('a donkey',scenes[0].english_hints)
        self.assertIn('a farmer',scenes[1].english_hints)
        self.assertIn('a pitchfork',scenes[1].english_hints)
        self.assertIn('hay',scenes[1].english_hints)
        self.assertIn('eats and chews',scenes[2].english_hints)
        texts=scene_prompts(words)
        self.assertEqual(len(texts),3)
        self.assertTrue(all('Photorealistic moving' in t for t in texts))
        self.assertTrue(all('No unrelated events' in t for t in texts))
        self.assertEqual(_narrative_shots(words),
                         [b.spoken_text for b in scenes])

    def test_glass_throw_and_shatter_are_two_different_events(self):
        words='האיש זורק כוס זכוכית על הרצפה. הכוס נשברת לרסיסים.'
        scenes=narrative_beats(words)
        self.assertEqual(len(scenes),2)
        self.assertTrue(any('throws an object' in h for h in scenes[0].english_hints))
        self.assertIn('an object shatters into fragments',scenes[1].english_hints)
        self.assertNotIn('a donkey',scenes[0].english_hints)
        self.assertGreater(scenes[0].word_count,0)

    def test_phonetic_whisper_misspelling_preserves_real_words(self):
        asr='יש זורק קוס זחוכית על הרצפה, הקוס נשברת לרסיסים'
        scenes=narrative_beats(asr)
        self.assertEqual(len(scenes),2)
        self.assertIn('קוס',scenes[0].spoken_text)
        self.assertIn('a glass cup',scenes[0].english_hints)
        self.assertIn('glass',scenes[0].english_hints)
        self.assertIn('an object shatters into fragments',scenes[1].english_hints)

    def test_do_not_turn_negated_event_into_positive_scene(self):
        words='החמור לא נוער. הכלב לא נובח. האיש לא נופל.'
        beats=narrative_beats(words)
        self.assertEqual(len(beats),3)
        for beat in beats:
            self.assertFalse(beat.explicit_action,beat)
            self.assertIn('respect negations',scene_prompt(beat))
        self.assertNotIn('brays',scene_prompt(beats[0]))

    def test_limit_to_three_contiguous_beats_without_losing_final_event(self):
        words=('הכלב נובח. החמור נוער. האיש רץ. '
               'המשאית נוסעת בכביש. האיש צוחק. הכוס נשברת.')
        beats=narrative_beats(words)
        self.assertEqual(len(beats),MAX_STORY_SCENES)
        self.assertIn('הכלב',beats[0].spoken_text)
        self.assertIn('הכוס נשברת',beats[-1].spoken_text)
        merged=' '.join(x.spoken_text for x in beats)
        for word in ('הכלב','החמור','האיש','המשאית','הכוס'):
            self.assertIn(word,merged)
        self.assertEqual(len(scene_weights(words)),len(beats))

    def test_unknown_audio_narration_never_invents_actors_or_events(self):
        text='החיים מוזרים מאוד כאן ולא תמיד ברור מה זה אומר'
        beats=narrative_beats(text)
        self.assertEqual(len(beats),1)
        self.assertFalse(beats[0].explicit_action)
        self.assertNotIn('donkey',scene_prompt(beats[0]))
        self.assertNotIn('truck',scene_prompt(beats[0]))
        self.assertIn(text,scene_prompt(beats[0]))

    def test_partial_punctuation_and_connectors_preserve_spoken_order(self):
        words='הילד הולך ואז החמור נוער אחר כך המשאית נוסעת'
        beats=narrative_beats(words)
        self.assertEqual(len(beats),3)
        self.assertIn('הילד הולך',beats[0].spoken_text)
        self.assertIn('החמור נוער',beats[1].spoken_text)
        self.assertIn('המשאית נוסעת',beats[2].spoken_text)

    def test_no_infinite_or_unbounded_segments(self):
        self.assertEqual(narrative_beats(''),[])
        with self.assertRaises(ValueError):
            narrative_beats('הכלב נובח',max_scenes=0)
        verylong=('הכלב נובח ואז האיש רץ. '*500)
        plan=narrative_beats(verylong)
        self.assertLessEqual(len(plan),3)
        self.assertTrue(all(len(x.spoken_text)<4000 for x in plan))


if __name__=='__main__':
    unittest.main()
