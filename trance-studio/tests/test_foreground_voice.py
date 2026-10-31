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
        self.assertGreater(float(abs(np.sqrt(np.mean(a*a))-np.sqrt(np.mean(b*b)))),.0003)

    def test_stereo_mix_speech_still_covers_last_words(self):
        x=self.voice(10)
        full,stem=e.render_mix([x],sample_rate=self.sr,seconds=30,humor='auto',
                               fx_intensity=3,fx_gain=1.3,return_voice=True)
        self.assertEqual(full.shape[0],len(stem))
        self.assertLessEqual(float(np.max(np.abs(full))),.95)
        self.assertTrue(np.isfinite(full).all())
        self.assertGreater(float(np.sqrt(np.mean(stem[8*self.sr:15*self.sr]**2))),.01)

if __name__=='__main__':unittest.main()
