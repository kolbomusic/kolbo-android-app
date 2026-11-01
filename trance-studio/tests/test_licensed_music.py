"""Real licensed backing-track ingest and voice-led music mix tests."""
import pathlib,subprocess,sys,tempfile,unittest
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from licensed_music import mix_licensed_backing,BackingTrackError

class LicensedBackingTests(unittest.TestCase):
    sr=8000
    def make_song(self,path,duration=1.4):
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                        '-f','lavfi','-i',f'sine=frequency=440:duration={duration}',
                        '-c:a','libmp3lame',str(path)],check=True,timeout=25)

    def test_a_real_music_file_replaces_synth_without_erasing_original_voice(self):
        with tempfile.TemporaryDirectory() as d:
            source=pathlib.Path(d)/'authorized.mp3'
            self.make_song(source)
            sr=self.sr;t=np.arange(sr*4)/sr
            voice=np.zeros(len(t),np.float32)
            voice[sr:sr*3]=.2*np.sin(2*np.pi*230*t[sr:sr*3])
            mixed=mix_licensed_backing(source,voice,sr)
            self.assertEqual(mixed.shape,(len(voice),2))
            self.assertTrue(np.isfinite(mixed).all())
            self.assertLessEqual(np.max(np.abs(mixed)),.94)
            # The song loops during silent intro/outro.
            self.assertGreater(float(np.sqrt(np.mean(mixed[sr//2:sr]**2))),.01)
            # Spoken voice must be perceptible above the dynamically ducked bed.
            self.assertGreater(float(np.sqrt(np.mean(mixed[sr:sr*3]**2))),.12)

    def test_rejects_empty_and_unsupported_music(self):
        with tempfile.TemporaryDirectory() as d:
            wrong=pathlib.Path(d)/'unlicensed.mp4';wrong.write_bytes(b'x')
            with self.assertRaises(BackingTrackError):
                mix_licensed_backing(wrong,np.ones(8000,np.float32),8000)
            with self.assertRaises(BackingTrackError):
                mix_licensed_backing(pathlib.Path(d)/'none.mp3',
                                     np.ones(8000,np.float32),8000)

if __name__=='__main__':unittest.main()
