"""Acceptance tests: WhatsApp voice effects must be foreground and never overlap spoken words."""
import importlib.util, pathlib, unittest
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('foreground_voice',ROOT/'backend'/'engine.py')
e=importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

class ForegroundVoiceTests(unittest.TestCase):
    sr=8000
    def voice(self, secs=12):
        t=np.arange(self.sr*secs)/self.sr
        envelope=np.where((t%1.3)<1.05,.31,.004)
        return (envelope*(np.sin(2*np.pi*230*t)+.22*np.sin(2*np.pi*520*t))).astype(np.float32)

    def test_auto_hook_scoring_prefers_clear_voiced_syllables_to_hiss(self):
        sr=self.sr
        t=np.arange(int(.40*sr))/sr
        voiced=(.18*np.sin(2*np.pi*225*t)+
                .035*np.sin(2*np.pi*450*t)).astype(np.float32)
        rng=np.random.default_rng(30)
        hiss=(rng.standard_normal(len(t))*.19).astype(np.float32)
        score_voice=e._vocal_hook_quality(voiced,sr)
        score_hiss=e._vocal_hook_quality(hiss,sr)
        self.assertGreater(score_voice,score_hiss*1.6)
        self.assertEqual(e._vocal_hook_quality(np.zeros(len(t)),sr),0.)
        self.assertGreater(score_voice,0.015)

    def test_original_hebrew_content_guides_comedy_fx_in_auto_mode(self):
        self.assertEqual(e._semantic_comedy_cue('החמור נוער בחוזקה.',.5),
                         'monster')
        self.assertEqual(e._semantic_comedy_cue('כולם צוחקים בקול.',.5),
                         'comic_roll')
        self.assertEqual(e._semantic_comedy_cue('ואז האיש נפל.',.5),
                         'rewind')
        self.assertEqual(e._semantic_comedy_cue('התינוק בוכה.',.5),
                         'helium')
        self.assertEqual(e._semantic_comedy_cue('כולם רוקדים.',.5),
                         'yo_yo')
        self.assertIsNone(e._semantic_comedy_cue('הוא לא צוחק.',.5))
        self.assertIsNone(e._semantic_comedy_cue('אנחנו נדבר מחר.',.5))
        # Different clauses select different punchlines in chronological
        # order, but the FX is still placed only at physical pauses.
        script='החמור נוער בחוזקה. כולם צוחקים. ואז האיש נפל.'
        self.assertEqual(e._semantic_comedy_cue(script,.12),'monster')
        self.assertEqual(e._semantic_comedy_cue(script,.48),'comic_roll')
        self.assertEqual(e._semantic_comedy_cue(script,.95),'rewind')

    def test_auto_comedy_remains_non_destructive_with_hebrew_story_hint(self):
        x=self.voice(16)
        y,mask,spans=e.arranged_vocal_track(
            x,self.sr,145,'auto',3,1.2,np.random.default_rng(12),
            transcript_hint='החמור נוער. כולם צוחקים. ואז האיש נפל.')
        reconstructed=np.concatenate([y[a:b] for _,_,a,b in spans])
        np.testing.assert_array_equal(reconstructed,x)
        self.assertTrue(np.any(mask>.5))
        for _,_,start,end in spans:
            self.assertTrue(np.all(mask[start:end]==0))

    def test_dramatic_voice_effect_lasts_musical_beats_not_truncated_600ms(self):
        x=self.voice(16)
        y,mask,spans=e.arranged_vocal_track(
            x,self.sr,145,'monster',3,1.15,np.random.default_rng(18))
        # The previous implementation cut ALL effects to 1.55 beats
        # (~641ms at BPM 145), even when a 2-beat stretch was needed.
        durations=[]
        inside=False
        for i,val in enumerate(mask):
            if val>.5 and not inside:
                start=i;inside=True
            if inside and (val<=.5 or i==len(mask)-1):
                durations.append((i-start)/self.sr)
                inside=False
        self.assertTrue(durations)
        self.assertGreater(max(durations),.70)
        self.assertLess(max(durations),1.15)
        np.testing.assert_array_equal(
            np.concatenate([y[a:b] for _,_,a,b in spans]),x)
        self.assertTrue(np.isfinite(y).all())

    def test_source_entirely_preserved_and_fx_never_overlaid(self):
        x=self.voice(16)
        y,fx,spans=e.arranged_vocal_track(x,self.sr,145,'auto',3,1.2,np.random.default_rng(12))
        self.assertGreater(len(y),len(x))
        self.assertGreater(float(np.sum(fx)),1000)
        reconstructed=np.concatenate([y[out_start:out_end] for a,b,out_start,out_end in spans])
        np.testing.assert_array_equal(reconstructed,x)
        # Absolutely no FX mask during original words, regardless of volume.
        for a,b,os,oe in spans:
            self.assertTrue(np.all(fx[os:oe]==0))
        # Effects are audible, have actual samples, and occur between chunks.
        self.assertGreater(float(np.sqrt(np.mean(y[fx>.5]**2))),.02)
        self.assertTrue(np.isfinite(y).all())

    def test_all_edits_are_at_measured_pauses_and_source_is_bit_exact(self):
        sr=self.sr
        t=np.arange(sr*18)/sr
        speech=np.zeros(len(t),dtype=np.float32)
        # Each syllabic phrase is separated by 340 ms of actual silence.
        for start in np.arange(0,17,1.7):
            a=int(start*sr);b=min(len(speech),a+int(sr*1.36))
            wave=np.arange(b-a)/sr
            speech[a:b]=.29*np.sin(2*np.pi*227*wave)
        y,mask,spans=e.arranged_vocal_track(
            speech,sr,145,'stretch',3,1.2,np.random.default_rng(21))
        reconstructed=np.concatenate([y[a:b] for _,_,a,b in spans])
        np.testing.assert_array_equal(reconstructed,speech)
        self.assertTrue(all(np.all(mask[os:oe]==0) for _,_,os,oe in spans))
        # No arbitrarily placed edits inside voiced portions of the source:
        # every non-final chunk must end in a genuinely quiet source gap.
        for source_start,source_end,_,_ in spans[:-1]:
            cut=source_end
            neighbourhood=speech[max(0,cut-int(.025*sr)):min(len(speech),cut+int(.025*sr))]
            self.assertLess(float(np.sqrt(np.mean(neighbourhood**2))),.01)
        # A 18-second speech recording cannot be inflated to twice its length.
        self.assertLess(len(y)-len(speech),sr*4)

    def test_continuous_speech_is_never_chopped_at_fixed_intervals(self):
        sr=self.sr;t=np.arange(sr*15)/sr
        # No low-energy gaps: only a tail-end, optional voice flourish.
        source=(.22*np.sin(2*np.pi*223*t)).astype(np.float32)
        y,mask,spans=e.arranged_vocal_track(
            source,sr,145,'auto',3,1.0,np.random.default_rng(5))
        self.assertEqual(len(spans),1)
        self.assertEqual(spans[0][0:2],(0,len(source)))
        np.testing.assert_array_equal(y[:len(source)],source)
        self.assertLess(len(y)-len(source),sr*.9)

    def test_new_distinct_comedy_voice_modes_change_original_sound(self):
        voice=self.voice(3)
        names=('helium','monster','yo_yo','comic_roll','rewind')
        results=[]
        for mode in names:
            processed=e.vintage_voice_fx(voice,mode,self.sr,145,np.random.default_rng(4))
            self.assertGreater(len(processed),self.sr//4)
            self.assertTrue(np.isfinite(processed).all())
            self.assertGreater(np.sqrt(np.mean(processed**2)),.01)
            # Each full effect must be materially different from the input.
            length=min(len(voice),len(processed))
            self.assertGreater(float(np.mean((processed[:length]-voice[:length])**2)),.0005)
            results.append(processed)
        # FX output can share the same 3.15s safety cap. Compare audio
        # textures, not lengths, because distinct pitch FX can be equal length.
        for i in range(len(results)):
            for j in range(i+1,len(results)):
                n=min(len(results[i]),len(results[j]))
                self.assertGreater(
                    float(np.sqrt(np.mean((results[i][:n]-results[j][:n])**2))),
                    .025)

    def test_dense_humor_more_fx_and_original_words_preserved(self):
        voice=self.voice(16)
        quiet,mask1,spans1=e.arranged_vocal_track(
            voice,self.sr,145,'chaos',1,1.2,np.random.default_rng(17))
        loud,mask3,spans3=e.arranged_vocal_track(
            voice,self.sr,145,'chaos',3,1.2,np.random.default_rng(17))
        self.assertGreater(int(mask3.sum()),int(mask1.sum()))
        np.testing.assert_array_equal(
            np.concatenate([loud[a:b] for _,_,a,b in spans3]),voice)
        np.testing.assert_array_equal(
            np.concatenate([quiet[a:b] for _,_,a,b in spans1]),voice)
        for _,_,start,end in spans3:
            self.assertTrue(np.all(mask3[start:end]==0))

    def test_short_message_also_gets_a_solo(self):
        x=self.voice(2)
        y,mask,spans=e.arranged_vocal_track(x,self.sr,145,'pitch',3,1.2,np.random.default_rng(5))
        self.assertGreater(len(y),len(x))
        self.assertGreater(int(np.count_nonzero(mask)),100)
        self.assertEqual(sum(b-a for a,b,_,_ in spans),len(x))

    def test_fx_loudness_setting_really_changes_wet_audio(self):
        x=self.voice(8)
        low,ml,_=e.arranged_vocal_track(x,self.sr,145,'stretch',3,.60,np.random.default_rng(5))
        high,mh,_=e.arranged_vocal_track(x,self.sr,145,'stretch',3,1.6,np.random.default_rng(5))
        self.assertEqual(low.shape,high.shape)
        np.testing.assert_array_equal(ml,mh)
        self.assertGreater(float(np.sqrt(np.mean(high[mh>.5]**2))),
                           float(np.sqrt(np.mean(low[ml>.5]**2)))*1.17)

    def test_specific_preset_is_used_and_autoselection_varies(self):
        x=self.voice(13)
        a,ma,_=e.arranged_vocal_track(x,self.sr,145,'pitch',3,1.1,np.random.default_rng(17))
        b,mb,_=e.arranged_vocal_track(x,self.sr,145,'stretch',3,1.1,np.random.default_rng(17))
        self.assertEqual(a.shape[0]>len(x),True)
        self.assertTrue(np.any(ma))
        self.assertTrue(np.any(mb))
        # Presets should sound different, not merely differ in loudness.
        # Normalized professional inserts can share the same overall RMS.
        n=min(len(a),len(b))
        self.assertGreater(float(np.sqrt(np.mean((a[:n]-b[:n])**2))),.002)

    def test_stereo_mix_speech_still_covers_last_words(self):
        x=self.voice(10)
        full,stem=e.render_mix([x],sample_rate=self.sr,seconds=30,humor='auto',
                               fx_intensity=3,fx_gain=1.3,return_voice=True)
        self.assertEqual(full.shape[0],len(stem))
        self.assertLessEqual(float(np.max(np.abs(full))),.95)
        self.assertTrue(np.isfinite(full).all())
        self.assertGreater(float(np.sqrt(np.mean(stem[8*self.sr:15*self.sr]**2))),.01)

if __name__=='__main__':unittest.main()
