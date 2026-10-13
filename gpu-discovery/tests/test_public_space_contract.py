"""No-network tests: contracts alone never authorize a generation request."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from public_space_contract import inspect_provider,PROVIDERS,inspect_all

class ContractAuditTests(unittest.TestCase):
    def test_known_hosts_not_user_supplied(self):
        self.assertEqual(len(PROVIDERS),4)
        self.assertTrue(all(url.startswith("https://") and url.endswith(".hf.space")
                            for _,url in PROVIDERS))
    def test_endpoint_names_only_no_credentials_media(self):
        def fake(base,path,**kw):
            self.assertEqual(path,"/gradio_api/info")
            return {"named_endpoints":{
                "/generate_video":{"parameters":[{"parameter_name":"prompt","example_input":"SECRET"},
                                                  {"parameter_name":"image","example_input":"photo.png"}],
                                   "returns":[{"label":"video"}]},
                "/health":{"parameters":[]}}}
        data=inspect_provider("sample","https://example.hf.space",getter=fake)
        self.assertTrue(data["api_contract_detected"])
        self.assertEqual(data["generation_endpoints"][0]["parameter_names"],["prompt","image"])
        self.assertNotIn("SECRET",str(data))
        self.assertFalse(data["gpu_job_submitted"])
        self.assertFalse(data["video_generated"])
        self.assertFalse(data["media_uploaded"])
        self.assertFalse(data["zero_cost_inference_verified"])
    def test_non_json_metadata_failure_is_not_gpu_proof(self):
        def broken(base,path,**kw):raise ValueError("broken")
        r=inspect_provider("sample","https://example.hf.space",getter=broken)
        self.assertFalse(r["metadata_available"])
        self.assertFalse(r["video_generated"])
        self.assertEqual(r["metadata_error_type"],"ValueError")
    def test_metadata_without_generation_is_not_provider(self):
        def fake(base,path,**kw):
            return {"named_endpoints":{"/status":{"parameters":[]}}}
        r=inspect_provider("sample","https://example.hf.space",getter=fake)
        self.assertTrue(r["metadata_available"])
        self.assertFalse(r["api_contract_detected"])
if __name__=="__main__":unittest.main()
