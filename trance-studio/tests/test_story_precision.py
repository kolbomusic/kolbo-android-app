"""Editorial acceptance: faithful original Hebrew events and timing, not merely an MP4.

Only invented fictional story examples. No private speech recordings,
external model calls, or invented recognition results.
"""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from story_precision import plan_narration,scene_durations
from ai_video import cinematic_prompt,build_ai_scene_plan,_narrative_shots


class PreciseNarrationTests(unittest.TestCase):
    def test_two_real_physical_events_are_ordered_and_never_replaced(self):
        s='החמור נוער בקול חזק. אחר כך החקלאי מגיש לו קש לאכול.'
        scenes=plan_narration(s)
        self.assertEqual(len(scenes),2,scenes)
        self.assertIn('החמור נוער בקול חזק',scenes[0]['spoken'])
        self.assertNotIn('מגיש',scenes[0]['spoken'])
        self.assertIn('החקלאי מגיש לו קש',scenes[1]['spoken'])
        self.assertEqual(scenes[1]['continuity'],['חמור'])
        prompts=build_ai_scene_plan(s)
        self.assertEqual(len(prompts),2)
        self.assertIn('החמור נוער',prompts[0]['prompt'])
        self.assertIn('חקלאי',prompts[1]['prompt'])
        self.assertIn('חמור',prompts[1]['prompt']) # grounded continuity from prior sentence
        self.assertTrue(prompts[1]['continuity_from_original'])

    def test_speech_negation_remains_negation_not_generated_bray(self):
        s='החמור לא נוער היום. החקלאי כן מגיש לו קש.'
        scenes=build_ai_scene_plan(s)
        self.assertIn('לא נוער',scenes[0]['prompt'])
        self.assertNotIn('donkey braying',scenes[0]['prompt'])
        self.assertIn('מגיש',scenes[1]['prompt'])

    def test_no_arbitrary_word_count_cut_in_one_coherent_sentence(self):
        s=('האישה הגדולה שהגיעה מהעיר הרחוקה בשעות הבוקר '
           'נכנסה בשקט אל הבניין הישן ששכן ליד התחנה '
           'והביאה איתה שתי מזוודות אדומות ויפות מאוד')
        self.assertGreater(len(s.split()),16)
        scenes=plan_narration(s)
        self.assertEqual(len(scenes),1,scenes)
        self.assertIn('שתי מזוודות אדומות',scenes[0]['spoken'])

    def test_temporal_connectors_create_order_without_inventing_verbs(self):
        s='החמור נוער ואז החקלאי בא לידו ואז החמור מתחיל לאכול'
        shots=plan_narration(s)
        self.assertEqual(len(shots),2,shots)
        self.assertIn('החמור נוער',shots[0]['spoken'])
        self.assertIn('החמור מתחיל לאכול',shots[-1]['spoken'])
        joined=' '.join(sh['spoken'] for sh in shots)
        for phrase in ('החמור נוער','החקלאי בא לידו','החמור מתחיל לאכול'):
            self.assertIn(phrase,joined)

    def test_ambiguous_pronoun_never_guess_which_actor(self):
        s='האיש והילד נכנסו לבית. ואז הוא יצא.'
        scenes=plan_narration(s)
        self.assertEqual(len(scenes),2)
        self.assertEqual(scenes[1]['continuity'],[])
        self.assertNotIn('The boy',build_ai_scene_plan(s)[1]['prompt'])

    def test_original_text_not_replaced_with_generic_humor_meme(self):
        s='האישה לקחה כלי נגינה ישן אל מחסן והתיישבה לכתוב שיר.'
        plan=build_ai_scene_plan(s)
        self.assertEqual(len(plan),1)
        self.assertIn('כלי נגינה',plan[0]['prompt'])
        self.assertNotIn('donkey braying',plan[0]['prompt'])
        self.assertNotIn('truck driving',plan[0]['prompt'])

    def test_asr_misspelling_is_kept_unmodified_no_fake_correction(self):
        s='איש זורק קוס זחוכית על הרצפה. הקוס נשברת לרסיסים.'
        plan=build_ai_scene_plan(s)
        all_text=' '.join(sc['spoken'] for sc in plan)
        self.assertIn('קוס זחוכית',all_text)
        self.assertNotIn('כוס זכוכית',all_text)

    def test_imbalanced_clause_lengths_affect_video_scene_lengths(self):
        s=('החמור נוער. החקלאי קם מהמיטה ולקח קלשון גדול '
           'ואחר כך התקרב באיטיות לחמור והושיט לו קש')
        scenes=plan_narration(s)
        self.assertEqual(len(scenes),2,scenes)
        durations=scene_durations(36,scenes)
        self.assertEqual(round(sum(durations),2),36)
        self.assertLess(durations[0],durations[1])
        self.assertGreater(durations[1],20)

    def test_very_long_transcript_remains_bounded_and_no_empty_shots(self):
        sample='החמור נוער והחקלאי מגיש לו אוכל. '
        scenes=plan_narration(sample*1000)
        self.assertLessEqual(len(scenes),2)
        self.assertTrue(all(s['spoken'].strip() for s in scenes))
        self.assertLessEqual(sum(len(s['spoken']) for s in scenes),4200)

    def test_scene_order_matches_source_before_english_prompt(self):
        s='המשאית נוסעת בכביש. ואז הכלב נובח בחצר.'
        plan=build_ai_scene_plan(s)
        self.assertEqual([('המשאית' in p['spoken']) for p in plan],[True,False])
        self.assertEqual([('הכלב' in p['spoken']) for p in plan],[False,True])
        self.assertEqual([p['spoken'] for p in plan],_narrative_shots(s))


if __name__=='__main__':unittest.main()
