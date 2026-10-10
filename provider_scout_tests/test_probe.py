import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from provider_scout.probe import ProbeError,probe_one,_video_url,_output_pointer,generate_synthetic,_ffprobe
from provider_scout.adapter import recognize
from test_adapter import EXAMPLE

class Resp:
 is_redirect=False
 def __init__(self,body=None,jsonobj=None):self.body=body;self.obj=jsonobj
 def raise_for_status(self):pass
 def json(self):return self.obj
 def iter_lines(self,decode_unicode=True):return iter(self.body)
 def iter_content(self,chunk_size=65_536):return iter([self.body])
 def close(self):pass
 def __enter__(self):return self
 def __exit__(self,*a):pass

class Session:
 def __init__(self,vid):self.vid=vid;self.calls=[]
 def request(self,method,url,**kwargs):
  self.calls.append((method,url))
  if url.endswith('/gradio_api/upload'):return Resp(jsonobj=['/tmp/remote-input.png'])
  if url.endswith('/gradio_api/call/generate_video') and method=='POST':
   args=kwargs['json']['data']
   assert args[4]==8
   assert args[1]['meta']=={'_type':'gradio.FileData'}
   return Resp(jsonobj={'event_id':'abc123456789'})
  if url.endswith('/abc123456789'):
   import json
   return Resp(body=['event: complete','data: '+json.dumps([{'video':{'path':'/tmp/generated.mp4'}}]),''])
  if '/gradio_api/file=' in url:return Resp(body=self.vid)
  raise AssertionError('Unexpected remote endpoint '+url)

class ProbeTests(unittest.TestCase):
 def setUp(self):
  self.c={'id':'author/demo','status':'schema_matched','license_declared':'apache-2.0',
  'automated_public_demo_probe_candidate':True,'api_host':'https://author-demo.hf.space',
  'capabilities':[p.public() for p in recognize(EXAMPLE)]}
 def test_declines_new_provider_without_allowlist_and_no_network(self):
  fake=MagicMock()
  with self.assertRaisesRegex(ProbeError,'NOT_APPROVED_FOR_AUTOMATED_PROBE'):
   with patch.dict(os.environ,{'KOLBO_SYNTHETIC_PROBE_ALLOWLIST':''}):probe_one(self.c,Path('/tmp/never-provider-probe'),session=fake)
  fake.request.assert_not_called()
 def test_refuses_unknown_license(self):
  c={**self.c,'license_declared':'unknown'}
  with self.assertRaisesRegex(ProbeError,'UNVERIFIED_LICENSE'):probe_one(c,Path('/tmp/no-probe'))
 def test_refuses_external_download_url(self):
  with self.assertRaisesRegex(ProbeError,'UNTRUSTED_MEDIA_URL'):
   _video_url('http://169.254.169.254/private','https://author-demo.hf.space')
 def test_extract_nested_video_path(self):
  self.assertEqual(_output_pointer([{'video':{'path':'/tmp/generated.mp4'}}]),'/tmp/generated.mp4')
 def test_one_synthetic_generation_and_real_ffprobe_validation(self):
  if not __import__('shutil').which('ffmpeg'):self.skipTest('FFmpeg unavailable')
  with tempfile.TemporaryDirectory() as tmp:
   video=Path(tmp)/'fixture.mp4'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=green:s=128x128:r=12:d=8',
    '-f','lavfi','-i','sine=frequency=420:sample_rate=24000:duration=8','-c:v','libx264','-pix_fmt','yuv420p',
    '-c:a','aac','-shortest',str(video)],check=True,timeout=50)
   client=Session(video.read_bytes())
   with patch.dict(os.environ,{'KOLBO_SYNTHETIC_PROBE_ALLOWLIST':'author/demo'}):
    result=probe_one(self.c,Path(tmp)/'out',session=client)
   self.assertEqual(result['status'],'verified_synthetic_video_only')
   self.assertTrue(result['has_audio_stream'])
   self.assertEqual(result['semantic_prompt_adherence'],'not_verified')
   self.assertEqual(len(client.calls),4)
   self.assertEqual(result['result_sha256'],__import__('hashlib').sha256(video.read_bytes()).hexdigest())
 def test_no_auto_activation_after_single_technical_proof(self):
  self.assertTrue(self.c.get('production_eligible') is None)