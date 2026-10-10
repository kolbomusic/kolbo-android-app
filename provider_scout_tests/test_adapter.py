import unittest
from provider_scout.adapter import recognize, plan_from_public

EXAMPLE={'named_endpoints':{'/generate_video':{'parameters':[
 {'parameter_name':'prompt','component':'Textbox','type':{'type':'string'}},
 {'parameter_name':'input_image','component':'Image','type':{'type':'file'}},
 {'parameter_name':'width','component':'Number','parameter_default':512},
 {'parameter_name':'height','component':'Number','parameter_default':512},
 {'parameter_name':'duration','component':'Number','type':{'type':'integer'}},
 {'parameter_name':'seed','component':'Number','parameter_default':42},
 ],'returns':[{'component':'Video','type':{'type':'file'}}]}}}

class AdapterTests(unittest.TestCase):
 def test_recognize_and_compose_remote_call(self):
  p=recognize(EXAMPLE)
  self.assertEqual(len(p),1)
  self.assertEqual(p[0].api_name,'/generate_video')
  a=p[0].arguments('Orange ball bounces exactly twice.',8,{'path':'/some.png'})
  self.assertEqual(a,['Orange ball bounces exactly twice.',{'path':'/some.png'},512,512,8,42])
 def test_public_plan_roundtrip(self):
  p=recognize(EXAMPLE)[0]
  pp=plan_from_public(p.public())
  self.assertEqual(pp.arguments('Test prompt.',8,{'path':'/x'}),p.arguments('Test prompt.',8,{'path':'/x'}))
 def test_refuses_unknown_required_parameter(self):
  example=__import__('copy').deepcopy(EXAMPLE)
  example['named_endpoints']['/generate_video']['parameters'].append({'parameter_name':'arbitrary_secret_token','component':'Textbox'})
  self.assertEqual(recognize(example),[])
 def test_refuses_video_without_explicit_duration(self):
  example=__import__('copy').deepcopy(EXAMPLE)
  ps=example['named_endpoints']['/generate_video']['parameters']
  ps[:]=[p for p in ps if p['parameter_name']!='duration']
  self.assertEqual(recognize(example),[])
 def test_refuses_endpoint_without_video(self):
  example=__import__('copy').deepcopy(EXAMPLE)
  example['named_endpoints']['/generate_video']['returns']=[{'component':'Image','type':{'type':'image'}}]
  self.assertEqual(recognize(example),[])
 def test_refuses_private_and_multiple_image(self):
  ex=__import__('copy').deepcopy(EXAMPLE)
  ex['named_endpoints']['/generate_video']['api_visibility']='private'
  self.assertFalse(recognize(ex))
 def test_wrong_duration_raises(self):
  with self.assertRaises(ValueError):recognize(EXAMPLE)[0].arguments('Orange ball.',60,{'path':'/a'})