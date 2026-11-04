"""Acceptance tests for the paid-service-free local FFmpeg sound palette.

Real stereo MP3 files are rendered and decoded; tests never call a network
provider, use GPU credits, download models or use a billing token.
"""
import io
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import audio_tools
import app

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg required")
class FreeSoundPaletteTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=pathlib.Path(tmp.name)
        self.voice=self.root/"speech.wav"
        # Nonstationary speech-like signal with frequency and amplitude
        # changes; pure sine is insufficient to catch several bad FX modes.
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                        "-f","lavfi","-i",
                        "aevalsrc=0.19*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*3*t))+"
                        "0.09*sin(2*PI*440*t):s=22050:d=2.3",
                        "-c:a","pcm_s16le",str(self.voice)],
                       check=True,timeout=20)

    def test_all_sixteen_local_effects_produce_decodable_audio(self):
        self.assertEqual(len(audio_tools.FREE_VOICE_MODES),16)
        rendered={}
        for mode in audio_tools.FREE_VOICE_MODES:
            with self.subTest(mode=mode):
                file=self.root/(mode+".mp3")
                processed=audio_tools.render_audio_tool(self.voice,file,mode=mode)
                self.assertGreater(processed.stat().st_size,3000)
                duration=audio_tools.probe_audio(processed)
                self.assertGreater(duration,1.45)
                self.assertLess(duration,4.)
                # Successful decoding alone is not evidence of good humor,
                # but corrupted or silent MP3 is always an unacceptable result.
                raw=subprocess.check_output([
                    "ffmpeg","-nostdin","-v","error","-i",str(file),
                    "-ac","1","-ar","8000","-f","f32le","-"],
                    timeout=15)
                samples=np.frombuffer(raw,dtype="<f4")
                self.assertGreater(len(samples),8000)
                self.assertGreater(float(np.std(samples)),.003,
                    "Sound processor returned silent/near-constant PCM")
                self.assertLess(float(np.max(np.abs(samples))),.99,
                    "Inter-sample MP3 peaks clipped beyond safe digital headroom")
                rendered[mode]=raw
        self.assertNotEqual(rendered["pitch_up"],rendered["pitch_down"])
        self.assertNotEqual(rendered["telephone"],rendered["chorus"])
        self.assertNotEqual(rendered["robot"],rendered["reverse"])
        self.assertNotEqual(rendered["slow"],rendered["fast"])

    def test_refuse_long_reverse_to_protect_free_server_ram(self):
        long_file=self.root/"long.wav"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                        "-f","lavfi","-i","sine=frequency=235:duration=33",
                        str(long_file)],check=True,timeout=20)
        with self.assertRaisesRegex(audio_tools.AudioToolError,"30"):
            audio_tools.render_audio_tool(long_file,self.root/"reverse.mp3",
                                          mode="reverse")

    def test_api_local_effect_has_no_secret_or_payment_parameter(self):
        application=app.create_app({"TESTING":True,"JOB_DIR":str(self.root)})
        client=application.test_client()
        response=client.post("/api/audio-tools/render",data={
            "rights":"yes","mode":"robot",
            "source":(io.BytesIO(self.voice.read_bytes()),"speech.wav")})
        self.assertEqual(response.status_code,200,response.get_json(silent=True))
        self.assertEqual(response.mimetype,"audio/mpeg")
        self.assertGreater(len(response.data),3000)
        response.close()

    def test_unknown_or_billable_effects_are_never_accepted(self):
        for mode in ("subscription","gpu_paid","ai_cover","stripe","credits"):
            with self.subTest(mode=mode):
                with self.assertRaises(audio_tools.AudioToolError):
                    audio_tools.render_audio_tool(
                        self.voice,self.root/"refused.mp3",mode=mode)
        for filter_chain in audio_tools.FREE_VOICE_MODES.values():
            self.assertNotIn("https:",filter_chain)
            self.assertNotIn("http:",filter_chain)
            self.assertNotIn("$",filter_chain)


if __name__=="__main__":
    unittest.main()
