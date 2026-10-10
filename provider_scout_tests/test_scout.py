import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from provider_scout.scout import safe_space_host,safe_space_id,scan
from test_adapter import EXAMPLE

class Response:
 status_code=200
 def __init__(self,content):self.body=__import__('json').dumps(content).encode()
 def iter_content(self,chunk_size=16_384):yield self.body
 def close(self):pass

class ScoutTests(unittest.TestCase):
 def test_host_only_hf_spaces(self):
  self.assertEqual(safe_space_host('chopperblu-ltx-2-5-demo'),'https://chopperblu-ltx-2-5-demo.hf.space')
  for host in ['chopperblu.hf.space','evil.com','good--evil','127.0.0.1','localhost','bad/path']:
   with self.subTest(host=host):
    with self.assertRaises(ValueError):safe_space_host(host)
 def test_space_id_validation(self):
  self.assertTrue(safe_space_id('author/LTX-demo'))
  for s in ['http://evil','a/../c','../../etc','owner//space','owner/space/path','']:
   self.assertFalse(safe_space_id(s))
 def test_discovery_schema_matched_but_not_production_eligible(self):
  hub=MagicMock()
  hub.search_spaces.return_value=[SimpleNamespace(id='author/demo')]
  hub.space_info.return_value=SimpleNamespace(private=False,disabled=False,subdomain='author-demo',card_data={'license':'apache-2.0'})
  session=MagicMock();session.get.return_value=Response(EXAMPLE)
  result=scan(max_candidates=1,terms=['image to video'],client=hub,session=session)
  c=result['candidates'][0]
  self.assertEqual(c['status'],'schema_matched')
  self.assertEqual(c['capabilities'][0]['api_name'],'/generate_video')
  self.assertFalse(c['production_eligible'])
  self.assertEqual(c['probe'],'not_run')
  self.assertFalse(c['pricing_verified'])
  session.get.assert_called_once()
 def test_metadata_too_big_refused(self):
  from provider_scout.scout import _get_limited_json
  s=MagicMock();r=MagicMock(status_code=200)
  r.iter_content.return_value=[b'x'*270_000];s.get.return_value=r
  with self.assertRaisesRegex(ValueError,'REMOTE_METADATA_TOO_BIG'):_get_limited_json(s,'https://safe.hf.space/gradio_api/info')
  self.assertTrue(r.close.called)