import json
import http.client
import threading
import unittest
from http.server import ThreadingHTTPServer
from staging.app import Handler
class TestKolboSafePreview(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
 def call(self,method,path,body=None):
  connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
  connection.request(method,path,body=body)
  response=connection.getresponse();result=(response.status,response.read());connection.close();return result
 def test_android_contract(self):
  code,raw=self.call("GET","/v1/app-config");obj=json.loads(raw)
  self.assertEqual(code,200);self.assertEqual(obj["api_contract"],449)
  self.assertEqual(obj["service"],"kolbo-volunteer-mesh")
  self.assertTrue(obj["preview_only"]);self.assertTrue(obj["owner_auth_required"])
  self.assertFalse(obj["private_media_upload_enabled"])
 def test_safe_studio(self):
  code,raw=self.call("GET","/studio")
  self.assertEqual(code,200);self.assertIn("אין להעלות".encode(),raw)
 def test_health_never_claims_gpu(self):
  code,raw=self.call("GET","/healthz")
  self.assertEqual(code,200);self.assertFalse(json.loads(raw)["gpu_ready"])
 def test_deny_all_uploads(self):
  for method in ("POST","PUT","DELETE","PATCH"):
   code,raw=self.call(method,"/v1/jobs",b"private photo")
   self.assertEqual(code,503);self.assertFalse(json.loads(raw)["accepted"])
 def test_deny_worker_data_fetch(self):
  code,_=self.call("GET","/v1/worker/jobs/id/payload");self.assertEqual(code,404)
 def test_no_secrets(self):
  for route in ("/v1/app-config","/healthz","/studio"):
   _,data=self.call("GET",route);self.assertNotIn(b"KOLBO_MESH_OWNER_TOKEN",data)
if __name__=="__main__":unittest.main()
