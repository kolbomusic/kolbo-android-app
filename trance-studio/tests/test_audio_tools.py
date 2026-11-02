"""Real FFmpeg audio studio tests. Both outputs must decode as valid audio."""
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import audio_tools
import app

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg needed')
class AudioStudioAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        self.infile=self.root/'original.wav'
        self.second=self.root/'singer.wav'
        for output,freq in [(self.infile,220),(self.second,450)]:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
                '-f','lavfi','-i','sine=frequency='+str(freq)+':duration=1',
                '-ac','1',str(output)],check=True,timeout=10)

    def test_mastering_is_a_real_mp3_not_unmodified_upload(self):
        out=self.root/'mastered.mp3'
        result=audio_tools.render_audio_tool(self.infile,out,mode='master',
                                             sound='warm')
        self.assertGreater(result.stat().st_size,2000)
        self.assertGreater(audio_tools.probe_audio(out),.8)
        self.assertNotEqual(out.read_bytes()[:4],self.infile.read_bytes()[:4])

    def test_mixer_uses_both_files_and_changes_pcm(self):
        one=self.root/'mix.mp3'
        two=self.root/'different.mp3'
        audio_tools.render_audio_tool(self.infile,one,mode='mix',voice=self.second,
                                      backing_gain=25,voice_gain=150)
        audio_tools.render_audio_tool(self.infile,two,mode='mix',voice=self.second,
                                      backing_gain=125,voice_gain=30)
        self.assertNotEqual(one.read_bytes(),two.read_bytes())
        self.assertGreater(audio_tools.probe_audio(one),.8)

    def test_http_audio_tools_requires_rights_and_uploaded_media(self):
        service=app.create_app({'TESTING':True,'JOB_DIR':str(self.root)})
        client=service.test_client()
        response=client.post('/api/audio-tools/render',data={
            'source':(io.BytesIO(self.infile.read_bytes()),'original.wav'),
            'mode':'master'
        })
        self.assertEqual(response.status_code,400)
        response=client.post('/api/audio-tools/render',data={
            'source':(io.BytesIO(self.infile.read_bytes()),'original.wav'),
            'mode':'master','rights':'yes'
        })
        self.assertEqual(response.status_code,200,str(response.json))
        self.assertEqual(response.mimetype,'audio/mpeg')
        self.assertGreater(len(response.data),2048)
        response.close()
        self.assertFalse(list(self.root.glob('kolbo-audio-tools-*')),
                         'Must delete per-request audio files after streaming')

    def test_fake_ai_cover_is_not_advertised(self):
        from engine_registry import catalog
        current=catalog()
        self.assertFalse(any(item['id']=='voice-clone' and item['ready']
                             for items in current.values() if isinstance(items,list)
                             for item in items))

if __name__=='__main__':
    unittest.main()
