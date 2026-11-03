"""Prove long audio export no longer copies full PCM bytes into RAM."""
import inspect
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import engine


class StreamingMp3ExportTests(unittest.TestCase):
    def test_ffmpeg_preserves_stereo_mp3_without_a_whole_track_input_copy(self):
        src=inspect.getsource(engine.export_mp3)
        self.assertIn("memoryview(data).cast('B')",src)
        self.assertIn("256*1024",src)
        self.assertIn("subprocess.Popen",src)
        self.assertNotIn(".tobytes()",src)
        sr=32000
        t=np.arange(sr*3,dtype=np.float32)/sr
        music=np.stack([
            .18*np.sin(2*np.pi*330*t),
            .12*np.sin(2*np.pi*550*t)],axis=1).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            mp3=pathlib.Path(tmp)/"mix.mp3"
            engine.export_mp3(music,mp3,sr=sr)
            self.assertGreater(mp3.stat().st_size,25000)
            p=subprocess.run([
                "ffprobe","-v","error","-show_entries",
                "stream=codec_name,channels,sample_rate",
                "-show_entries","format=duration",
                "-of","json",str(mp3)
            ],check=True,capture_output=True,text=True,timeout=15)
            info=json.loads(p.stdout)
            self.assertAlmostEqual(float(info["format"]["duration"]),3,delta=.12)
            audio=next(s for s in info["streams"] if s["codec_name"]=="mp3")
            self.assertEqual(audio["channels"],2)
            self.assertEqual(int(audio["sample_rate"]),sr)
            # Decode real produced MP3 instead of checking filename only.
            out=engine.load_audio(mp3,sample_rate=sr)
            self.assertGreater(float(np.max(np.abs(out))),.05)

    def test_mastering_does_not_allocate_full_length_sidechain_or_fade(self):
        src=inspect.getsource(engine.render_mix)
        self.assertIn("_duck_music_in_chunks(music,vocal,fx_highlight,sr)",src)
        self.assertIn("_peak_abs_in_chunks(music)",src)
        self.assertNotIn("fade=np.ones(n,dtype=np.float32)",src)
        self.assertNotIn("np.max(np.abs(music))",src)
        self.assertNotIn("np.clip(np.arange(n)/(sr*.025)",src)
        self.assertNotIn("np.flatnonzero(np.abs(vocal)>.009)",src)

    def test_chunked_vocal_sidechain_matches_original_across_boundaries(self):
        from scipy.ndimage import maximum_filter1d
        from scipy.signal import lfilter
        sr=32000
        n=sr*3+123
        t=np.arange(n,dtype=np.float32)/sr
        voice=(.23*np.sin(2*np.pi*197*t)*((np.arange(n)//3300)%3!=0)).astype(np.float32)
        fx=np.where((np.arange(n)//4999)%3==0,.75,0).astype(np.float32)
        expected=np.ones((n,2),dtype=np.float32)
        env=maximum_filter1d(np.abs(voice),size=max(1,int(sr*.025)))
        env=lfilter([.003],[1,-.997],env).astype(np.float32)
        expected*=((1-.67*np.clip(env/.18,0,1))*(1-.68*fx))[:,None]
        actual=np.ones_like(expected)
        engine._duck_music_in_chunks(actual,voice,fx,sr,chunk_frames=4096)
        np.testing.assert_allclose(actual,expected,rtol=2e-5,atol=2e-5)

    def test_limiter_peak_scans_chunks_without_full_stereo_copy(self):
        signal=np.zeros((200_001,2),dtype=np.float32)
        signal[173456,1]=-1.23
        self.assertAlmostEqual(engine._peak_abs_in_chunks(signal,7777),1.23,places=5)


if __name__=="__main__":
    unittest.main()
