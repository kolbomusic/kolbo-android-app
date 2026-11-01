"""Validate original, audible, timed cartoon punctuation on actual FX inserts."""
import sys,pathlib,unittest
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from comic_stingers import create_sting,add_comic_stings

class ComicStingsTests(unittest.TestCase):
    def test_distinct_punchlines_are_audible_and_limited(self):
        sr=8000
        n=sr*8
        bed=np.zeros((n,2),dtype=np.float32)
        fx_mask=np.zeros(n,dtype=np.float32)
        fx_mask[2*sr:2*sr+int(sr*.56)]=1.
        fx_mask[5*sr:5*sr+int(sr*.56)]=1.
        out=add_comic_stings(
            bed,fx_mask,sr,145,
            lambda f: 'monster' if f<.4 else 'comic_roll')
        self.assertEqual(out.shape,bed.shape)
        self.assertTrue(np.isfinite(out).all())
        self.assertGreater(float(np.max(np.abs(out))),.08)
        self.assertLess(float(np.max(np.abs(out))),.6)
        self.assertGreater(float(np.max(np.abs(out[2*sr:3*sr]))),.07)
        self.assertGreater(float(np.max(np.abs(out[5*sr:6*sr]))),.07)
        np.testing.assert_array_equal(out[:sr],bed[:sr])
        np.testing.assert_array_equal(out[7*sr:],bed[7*sr:])

    def test_no_cue_or_no_focused_voice_fx_adds_nothing(self):
        sr=8000
        rng=np.random.default_rng(9)
        bed=rng.standard_normal((sr*3,2)).astype(np.float32)*.01
        active=np.zeros(len(bed),dtype=np.float32)
        active[sr:sr+int(.35*sr)]=1.
        fallback=add_comic_stings(bed,active,sr,145,lambda p:None)
        # Keywords can be absent in real WhatsApp speech. Still give an
        # acoustic comic accent at a selected existing voice-FX pause.
        self.assertGreater(float(np.max(np.abs(fallback-bed))),.07)
        np.testing.assert_array_equal(fallback[:sr],bed[:sr])
        np.testing.assert_array_equal(fallback[sr+int(.35*sr):],bed[sr+int(.35*sr):])
        np.testing.assert_array_equal(
            add_comic_stings(bed,np.zeros(len(bed)),sr,145,
                             lambda p:'monster'),bed)

    def test_comic_sound_cannot_overlap_next_spoken_word(self):
        sr=8000
        n=sr*5
        rng=np.random.default_rng(22)
        # Simulated dry voice at 3s starts after the 2s FX insert.
        source=rng.standard_normal((n,2)).astype(np.float32)*.035
        mask=np.zeros(n,dtype=np.float32)
        mask[2*sr:2*sr+int(.30*sr)]=1.
        out=add_comic_stings(source,mask,sr,145,lambda f:'monster')
        self.assertGreater(float(np.max(np.abs(out-source))),.05)
        np.testing.assert_array_equal(out[2*sr+int(.30*sr):],source[2*sr+int(.30*sr):])
        np.testing.assert_array_equal(out[:2*sr],source[:2*sr])
        self.assertTrue(np.isfinite(out).all())

    def test_comic_families_distinct_and_bounded(self):
        sounds=[create_sting(x,8000,145) for x in
                ('monster','comic_roll','rewind','helium','yo_yo','tape')]
        self.assertEqual(len(sounds),6)
        self.assertTrue(all(np.max(np.abs(s))<=.471 for s in sounds))
        self.assertTrue(all(float(np.sqrt(np.mean(s*s)))>.01 for s in sounds))
        self.assertNotAlmostEqual(float(np.mean(sounds[0][:100]**2)),
                                  float(np.mean(sounds[1][:100]**2)),places=4)

if __name__=='__main__':unittest.main()
