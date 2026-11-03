"""Regression: a blocked free AI Space must not end the only video path.

This test checks automatic backend routing and a real decodable MP4 produced
from a deterministic licensed-footage stand-in. It does not claim that a
public provider or any real Wikimedia download is reliably available.
"""
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from unittest.mock import patch

import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app import create_app
from ai_video import AIVideoUnavailable


class SmartStoryFallbackTests(unittest.TestCase):
    def sample(self):
        memory=io.BytesIO()
        sr=8000
        pcm=(9000*np.sin(np.arange(sr*2)*2*np.pi*250/sr)).astype('<i2')
        with wave.open(memory,'wb') as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(sr)
            recording.writeframes(pcm.tobytes())
        memory.seek(0)
        return memory

    def test_smart_story_gets_real_mp4_when_ai_provider_fails_but_footage_exists(self):
        import engine
        made=[]
        def create_test_footage(audio,video,plan,work_dir,progress=None):
            # Real varying frames, 360x640 H264 + synthesized MP3 soundtrack,
            # never a waveform or a static image.
            subprocess.run([
                "ffmpeg","-nostdin","-v","error","-y",
                "-f","lavfi","-i","testsrc2=size=360x640:rate=12",
                "-i",str(audio),"-map","0:v:0","-map","1:a:0",
                "-t","2.0","-c:v","libx264","-threads","1",
                "-profile:v","baseline","-preset","ultrafast",
                "-crf","35","-c:a","aac",
                "-movflags","+faststart",str(video)
            ],check=True,timeout=30)
            made.append(str(video))
            return [{"action":"donkey_bray",
                     "page":"https://commons.wikimedia.org/wiki/File:Example.webm",
                     "license":"CC BY 4.0"}]

        plan={"source":"grounded_transcript","transcript":"החמור נוער בחוזקה",
              "scenes":[{"action":"donkey_bray","query":"donkey braying",
                         "start":0.,"end":2.,"spoken":"החמור נוער בחוזקה"}],
              "visual_coverage":"matched","unmatched_clauses":0}
        with tempfile.TemporaryDirectory() as folder:
            client=create_app({"TESTING":True,"JOB_DIR":folder}).test_client()
            def short_mix(clips,**options):
                sr=32000
                t=np.arange(sr*2,dtype=np.float32)/sr
                vocal=(.18*np.sin(2*np.pi*220*t)).astype(np.float32)
                mix=np.stack([vocal,vocal],axis=1)
                return mix,vocal,[]
            with patch("app.render_mix",side_effect=short_mix), \
                 patch("app.load_audio",return_value=np.ones(32000,np.float32)*.05), \
                 patch("app.visual_plan",return_value=plan), \
                 patch("app.align_storyboard_to_vocal",side_effect=lambda board,*args,**kw: board), \
                 patch("app.export_live_story",side_effect=create_test_footage), \
                 patch("ai_video.generate_ai_story",side_effect=AIVideoUnavailable("quota exhausted")), \
                 patch("isolated_asr.transcribe_in_child",side_effect=AssertionError("redundant ASR")):
                result=client.post("/api/jobs",data={
                    "audio":(self.sample(),"words.wav"),
                    "seconds":"30","make_video":"on","video_requested":"on",
                    "video_strategy":"smart_story","ai_video_consent":"on",
                    "transcript":"החמור נוער בחוזקה","transcript_origin":"auto"})
                self.assertEqual(result.status_code,202,result.get_json())
                job=result.get_json()
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    state=client.get(job["status_url"]).get_json()
                    if state.get("state") in ("done","error"):
                        break
                    time.sleep(.05)
                self.assertEqual(state.get("state"),"done",state)
                self.assertEqual(state.get("video_status"),"done",state)
                self.assertEqual(state.get("video_mode"),"matched_footage",state)
                self.assertEqual(len(made),1)
                file=pathlib.Path(made[0])
                self.assertGreater(file.stat().st_size,18000)
                probe=subprocess.run(["ffprobe","-v","error","-show_entries",
                    "stream=codec_type,codec_name","-of","json",str(file)],
                    capture_output=True,text=True,check=True,timeout=15)
                tracks=json.loads(probe.stdout)["streams"]
                self.assertTrue(any(x["codec_name"]=="h264" and x["codec_type"]=="video" for x in tracks))
                self.assertTrue(any(x["codec_type"]=="audio" for x in tracks))
                self.assertTrue(state.get("video_url"))
                self.assertEqual(client.get(state["video_url"]).status_code,200)


if __name__=="__main__":
    unittest.main()
