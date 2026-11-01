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

    def test_authorized_backing_keeps_comic_accents_after_speech_pauses(self):
        with tempfile.TemporaryDirectory() as d:
            source=pathlib.Path(d)/'authorized.mp3'
            self.make_song(source)
            sr=self.sr
            t=np.arange(sr*5,dtype=np.float32)/sr
            voice=np.zeros(len(t),np.float32)
            # Two distinct spoken phrases, with enough real silence to place
            # an accent. The original sample voice must not be overwritten.
            voice[sr:2*sr]=.20*np.sin(2*np.pi*225*t[sr:2*sr])
            voice[3*sr:4*sr]=.18*np.sin(2*np.pi*245*t[3*sr:4*sr])
            song=mix_licensed_backing(source,voice,sr,transcript_hint='החמור נוער. כולם צוחקים.',
                                      bpm=145,humor='auto')
            no_fx=mix_licensed_backing(source,voice,sr,transcript_hint='',
                                      bpm=145,humor='auto')
            off=mix_licensed_backing(source,voice,sr,transcript_hint='החמור נוער.',
                                    bpm=145,humor='off')
            self.assertEqual(song.shape,no_fx.shape)
            self.assertTrue(np.isfinite(song).all())
            self.assertGreater(float(np.max(np.abs(song-no_fx))),.025)
            clean=mix_licensed_backing(source,voice,sr,transcript_hint='',
                                       bpm=145,humor='off')
            np.testing.assert_array_equal(off,clean)
            # Untranscribed audio still gets a few rhythmically safe
            # punchline accents rather than returning completely dry.
            self.assertGreater(float(np.max(np.abs(no_fx-clean))),.02)

    def test_rejects_empty_and_unsupported_music(self):
        with tempfile.TemporaryDirectory() as d:
            wrong=pathlib.Path(d)/'unlicensed.mp4';wrong.write_bytes(b'x')
            with self.assertRaises(BackingTrackError):
                mix_licensed_backing(wrong,np.ones(8000,np.float32),8000)
            with self.assertRaises(BackingTrackError):
                mix_licensed_backing(pathlib.Path(d)/'none.mp3',
                                     np.ones(8000,np.float32),8000)

if __name__=='__main__':unittest.main()
