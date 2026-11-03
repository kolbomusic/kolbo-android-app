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

    def test_master_fade_avoids_full_length_float64_time_arrays(self):
        src=inspect.getsource(engine.render_mix)
        self.assertIn("fade=np.ones(n,dtype=np.float32)",src)
        self.assertIn("music*=fade[:,None]",src)
        self.assertNotIn("np.clip(np.arange(n)/(sr*.025)",src)


if __name__=="__main__":
    unittest.main()
